"""The extraction agent: request text in, checked ExtractionResult out.

Flow: ask the model -> parse its JSON -> validate the shape -> verify every field against
the original request -> work out the missing required details -> return a status.

Every field ends with a status (PRESENT, MISSING, AMBIGUOUS, CONFLICTING). The model proposes
it; our code only keeps PRESENT when the value is backed by words that really appear in the
request. A value without such words becomes MISSING; a quote that exists but does not match
the value becomes AMBIGUOUS, so a person or the clarification loop looks at it.

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
from typing import Any

from pydantic import ValidationError

from app.policy import ExtractionStatus

from .guards import instruction_phrases, restricted_categories_mentioned
from .llm import LLMClient, LLMError
from .prompt import build_system_prompt, build_user_message
from .schemas import (
    EXTRACTED_FIELDS,
    FIELDS_WITH_EVIDENCE,
    ExtractedField,
    ExtractionResult,
    FieldStatus,
    LLMReply,
    UrgencyLevel,
    UrgencySignal,
)

PRESENT = FieldStatus.PRESENT
MISSING = FieldStatus.MISSING
AMBIGUOUS = FieldStatus.AMBIGUOUS

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
    result = _extract(text, llm, categories, required_fields, max_chars, max_attempts)
    # Checked on the text itself, so it holds even when the model failed or was fooled.
    found = instruction_phrases(text) if text else []
    return result.model_copy(update={"instructions_found": found}) if found else result


def _extract(
    text: str,
    llm: LLMClient,
    categories: Sequence[str],
    required_fields: Sequence[str],
    max_chars: int,
    max_attempts: int,
) -> ExtractionResult:
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


def _parse(raw: str) -> tuple[LLMReply | None, str]:
    """Turn the model's text into LLMReply. Returns (None, why) when it cannot."""
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
        return LLMReply.model_validate(data), ""
    except ValidationError as error:
        # Only field names are reported, never the values.
        names = sorted({str(e["loc"][0]) for e in error.errors() if e["loc"]})
        return None, f"The model answer had invalid fields: {', '.join(names) or 'unknown'}."


def _check(
    parsed: LLMReply,
    text: str,
    categories: Sequence[str],
    required_fields: Sequence[str],
) -> ExtractionResult:
    notes = [_short(note) for note in parsed.notes[:_MAX_NOTES] if note.strip()]
    fields: dict[str, ExtractedField] = {}
    for name in EXTRACTED_FIELDS:
        field, note = _check_field(name, getattr(parsed, name), text, categories)
        fields[name] = field
        if note:
            notes.append(note)

    category_note = _guard_category(fields, text)
    if category_note:
        notes.append(category_note)

    urgency, urgency_note = _check_urgency(parsed, text)
    if urgency_note:
        notes.append(urgency_note)

    # Anything not PRESENT is still missing for the policy engine (POL-001). A required name we
    # do not know how to fill also counts as missing: fail closed.
    missing = [
        name
        for name in required_fields
        if name not in fields or fields[name].status is not PRESENT
    ]
    return ExtractionResult(
        status=ExtractionStatus.VALID,
        fields=fields,
        urgency=urgency,
        missing_fields=missing,
        ambiguities=notes[: _MAX_NOTES * 2],
    )


def _guard_category(fields: dict[str, ExtractedField], text: str) -> str | None:
    """Keep the model's category only if it agrees with restricted-item words in the request.

    "24 bottles of beer" can only be ALCOHOL. If the model chose anything else (or was told to),
    the category becomes CONFLICTING, so a person checks it (POL-006). Never the other way:
    the words never set a category by themselves.
    """
    mentioned = restricted_categories_mentioned(text)
    field = fields["item_category"]
    if not mentioned or field.status is not PRESENT or field.value in mentioned:
        return None
    fields["item_category"] = ExtractedField(status=FieldStatus.CONFLICTING, evidence=field.evidence)
    return (
        f"item_category: the request uses words of {', '.join(sorted(mentioned))}, but the model "
        f"chose {field.value}; sent for checking."
    )


def _check_field(
    name: str, reported: Any, text: str, categories: Sequence[str]
) -> tuple[ExtractedField, str | None]:
    status: FieldStatus = reported.status
    value = reported.value
    quote = reported.evidence
    # The quote is only kept if it really appears in the request.
    found = quote if quote and _contains(text, quote) else None

    if status is not PRESENT:
        # value stays None unless PRESENT (design rule). A quote for an unclear or conflicting
        # detail is useful for the clarification question, so it is kept when it is real.
        note = None
        if quote and not found:
            note = f"{name}: the quoted words do not appear in the request; discarded."
        return ExtractedField(status=status, evidence=found), note

    if value is None:
        return ExtractedField(status=MISSING), None

    if name == "item_category":
        code, note = _normalise_category(value, categories)
        if code is None:
            return ExtractedField(status=MISSING), note
        return ExtractedField(status=PRESENT, value=code, evidence=found), None

    if name == "currency" and isinstance(value, str):
        value = value.strip().upper()

    if name in FIELDS_WITH_EVIDENCE:
        problem = _verify(name, value, quote, text)
        if problem is not None:
            note, quote_was_real = problem
            # A real quote that does not match the value: the request says something, but not
            # clearly this. Otherwise there is no proof at all, so the detail counts as missing.
            status = AMBIGUOUS if quote_was_real else MISSING
            return ExtractedField(status=status, evidence=found), note
        # _verify passed, so the quote is real and non-empty.
        evidence = " ".join((found or "").split())
        return ExtractedField(status=PRESENT, value=value, evidence=evidence), None

    return ExtractedField(status=PRESENT, value=value, evidence=found), None


def _check_urgency(parsed: LLMReply, text: str) -> tuple[UrgencySignal, str | None]:
    level, quote = parsed.urgency.level, parsed.urgency.evidence
    if quote and _contains(text, quote):
        return UrgencySignal(level=level, evidence=" ".join(quote.split())), None
    note = None
    if quote:
        note = "urgency_evidence: the quoted words do not appear in the request; discarded."
    elif level is not UrgencyLevel.NORMAL:
        note = "urgency: no supporting words from the request were given; reported as NORMAL."
    # Urgency without real words from the request is not reported (it is only a signal).
    return UrgencySignal(), note


def _verify(field: str, value: object, quote: str | None, text: str) -> tuple[str, bool] | None:
    """Return (note, quote_was_real) if the value cannot be backed by the request, else None."""
    if not quote or not quote.strip():
        return f"{field}: no supporting words from the request were given; value discarded.", False
    if not _contains(text, quote):
        return f"{field}: the quoted words do not appear in the request; value discarded.", False
    if field == "estimated_total" and not _number_matches(value, quote, required=True):
        return f"{field}: the amount does not match the quoted words; value discarded.", True
    if field == "quantity" and not _number_matches(value, quote, required=False):
        return f"{field}: the number does not match the quoted words; value discarded.", True
    return None


def _contains(text: str, quote: str) -> bool:
    # Ignore case and extra spaces/line breaks only. Nothing else is forgiven.
    return " ".join(quote.split()).casefold() in " ".join(text.split()).casefold()


def _number_matches(value: object, quote: str, *, required: bool) -> bool:
    """Does the number appear in the quote (allowing 1,500 / 45k / 1.5 lakh)?

    required=True (money): a quote with no digits at all fails, because we cannot check it.
    required=False (quantity): words such as "two" are accepted on the quote alone.
    """
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
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
