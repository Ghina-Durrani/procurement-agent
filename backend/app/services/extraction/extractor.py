"""The extraction agent: request text in, checked ExtractionResult out.

Flow: ask the model -> parse its JSON -> validate the shape -> verify every value against
the original request -> work out the missing required details -> return a status.

Rules this file keeps (CLAUDE.md hard rules 1-3 and 7):
- It never raises to the caller. Any failure becomes status FAILED or INVALID, which the
  policy engine turns into HUMAN_REVIEW.
- It never keeps a value it cannot back with words that really appear in the request.
- It never decides policy. It only reports what the request says.
"""
import json
import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from app.policy import ExtractionStatus

from .llm import LLMClient, LLMError
from .prompt import build_system_prompt, build_user_message
from .schemas import (
    EXTRACTED_FIELDS,
    FIELDS_WITH_EVIDENCE,
    ExtractionResult,
    LLMExtraction,
)

# The first answer may be malformed; one more try is allowed, then we stop (free tiers are small).
DEFAULT_MAX_ATTEMPTS = 2
_MAX_NOTES = 10
_MAX_NOTE_CHARS = 300

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|lakhs?|lacs?|crores?)?\b", re.IGNORECASE)
_MULTIPLIER = {
    "k": Decimal(1_000),
    "m": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "lakh": Decimal(100_000),
    "lakhs": Decimal(100_000),
    "lac": Decimal(100_000),
    "lacs": Decimal(100_000),
    "crore": Decimal(10_000_000),
    "crores": Decimal(10_000_000),
}


def extract_request(
    request_text: str,
    llm: LLMClient,
    *,
    categories: Sequence[str],
    required_fields: Sequence[str],
    max_chars: int = 5000,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> ExtractionResult:
    """Extract the details of one request. See the module docstring for the guarantees."""
    text = request_text.strip() if isinstance(request_text, str) else ""
    if not text:
        return _stop(ExtractionStatus.INVALID, required_fields, "The request text is empty.")
    if len(text) > max_chars:
        return _stop(
            ExtractionStatus.INVALID,
            required_fields,
            f"The request is longer than {max_chars} characters.",
        )

    system_prompt = build_system_prompt(categories)
    user_message = build_user_message(text)
    problems: list[str] = []
    for _ in range(max(1, max_attempts)):
        try:
            raw = llm.complete(system_prompt, user_message)
        except LLMError as error:
            return _stop(ExtractionStatus.FAILED, required_fields, f"{type(error).__name__}: {error}")
        except Exception:  # noqa: BLE001 - any failure must end in review, never a crash
            return _stop(
                ExtractionStatus.FAILED, required_fields, "The language model call failed unexpectedly."
            )
        parsed, problem = _parse(raw)
        if parsed is not None:
            try:
                return _check(parsed, text, categories, required_fields)
            except Exception:  # noqa: BLE001 - a bug here must still end in review
                return _stop(
                    ExtractionStatus.FAILED, required_fields, "The model answer could not be processed."
                )
        problems.append(problem)
    return _stop(ExtractionStatus.INVALID, required_fields, *problems)


def _stop(
    status: ExtractionStatus, required_fields: Sequence[str], *problems: str
) -> ExtractionResult:
    # Nothing could be read, so every required detail is still missing.
    return ExtractionResult(
        status=status, missing_fields=list(required_fields), problems=list(problems)
    )


def _parse(raw: str) -> tuple[LLMExtraction | None, str]:
    """Turn the model's text into LLMExtraction. Returns (None, why) when it cannot."""
    text = raw.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        # parse_float=Decimal keeps 1500.50 exact. A float would already have lost precision.
        data = json.loads(text, parse_float=Decimal)
    except (ValueError, InvalidOperation, RecursionError):
        return None, "The model answer was not valid JSON."
    if not isinstance(data, dict):
        return None, "The model answer was not a JSON object."
    try:
        return LLMExtraction.model_validate(data), ""
    except ValidationError as error:
        # Only field names are reported, never the values.
        names = sorted({str(e["loc"][0]) for e in error.errors() if e["loc"]})
        return None, f"The model answer had invalid fields: {', '.join(names) or 'unknown'}."


def _check(
    parsed: LLMExtraction,
    text: str,
    categories: Sequence[str],
    required_fields: Sequence[str],
) -> ExtractionResult:
    values: dict[str, object] = {name: getattr(parsed, name) for name in EXTRACTED_FIELDS}
    notes = [_short(note) for note in parsed.ambiguities[:_MAX_NOTES] if note.strip()]
    kept_evidence: dict[str, str] = {}

    for field in FIELDS_WITH_EVIDENCE:
        if values[field] is None:
            continue
        quote = parsed.evidence.get(field)
        problem = _verify(field, values[field], quote, text)
        if problem:
            values[field] = None
            notes.append(problem)
        else:
            kept_evidence[field] = " ".join((quote or "").split())

    if values["urgency_evidence"] is not None and not _contains(text, str(values["urgency_evidence"])):
        values["urgency_evidence"] = None
        notes.append("urgency_evidence: the quoted words do not appear in the request; discarded.")

    values["item_category"], category_note = _normalise_category(values["item_category"], categories)
    if category_note:
        notes.append(category_note)
    if isinstance(values["currency"], str):
        values["currency"] = values["currency"].strip().upper()

    # A required name we do not know how to fill counts as missing: fail closed.
    missing = [name for name in required_fields if values.get(name) is None]
    return ExtractionResult(
        status=ExtractionStatus.VALID,
        missing_fields=missing,
        ambiguities=notes[: _MAX_NOTES * 2],
        evidence=kept_evidence,
        **values,  # type: ignore[arg-type]
    )


def _verify(field: str, value: object, quote: str | None, text: str) -> str | None:
    """Return a note if the value cannot be backed by the request, else None."""
    if not quote or not quote.strip():
        return f"{field}: no supporting words from the request were given; value discarded."
    if not _contains(text, quote):
        return f"{field}: the quoted words do not appear in the request; value discarded."
    if field == "estimated_total" and not _number_matches(value, quote, required=True):
        return f"{field}: the amount does not match the quoted words; value discarded."
    if field == "quantity" and not _number_matches(value, quote, required=False):
        return f"{field}: the number does not match the quoted words; value discarded."
    return None


def _contains(text: str, quote: str) -> bool:
    # Ignore case and extra spaces/line breaks only. Nothing else is forgiven.
    return " ".join(quote.split()).casefold() in " ".join(text.split()).casefold()


def _number_matches(value: object, quote: str, *, required: bool) -> bool:
    """Does the number appear in the quote (allowing 1,500 / 45k / 1.5 lakh)?

    required=True (money): a quote with no digits at all fails, because we cannot check it.
    required=False (quantity): words such as "two" are accepted on the quote alone.
    """
    if not isinstance(value, Decimal):
        return False
    candidates: list[Decimal] = []
    for number, suffix in _NUMBER.findall(quote):
        try:
            base = Decimal(number.replace(",", ""))
        except InvalidOperation:
            continue
        candidates.append(base)
        if suffix:
            candidates.append(base * _MULTIPLIER[suffix.casefold()])
    if not candidates:
        return not required
    return any(value == candidate for candidate in candidates)


def _normalise_category(value: object, categories: Sequence[str]) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    code = str(value).strip().upper().replace(" ", "_").replace("-", "_")
    if code in {c.upper() for c in categories}:
        return code, None
    return None, f"item_category: '{_short(str(value), 60)}' is not on the approved list; discarded."


def _short(note: str, limit: int = _MAX_NOTE_CHARS) -> str:
    return " ".join(note.split())[:limit]
