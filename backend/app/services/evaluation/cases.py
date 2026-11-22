"""Labelled evaluation cases: their format, loading, and the checks that catch label mistakes.

The cases live in evaluation/cases/cases.jsonl (one JSON object per line) and are kept apart
from application data (FYP_MASTER_CONTEXT.md section 7). Labelling rules are in
docs/EVALUATION_CASES.md.

Three kinds of checks:
1. Each case on its own: shape, types, value only when PRESENT, missing list matches statuses.
2. Each case against the policy engine: the expected decision, rules and roles must be what the
   approved rules give for the expected facts. A mismatch means a label mistake (or an engine
   bug), so a person must look at it.
3. The whole set: unique IDs, every category in both splits, and a locked split, so the
   held-out test texts cannot change quietly after tuning starts.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from app.policy import Checkpoint, ExtractionStatus, PolicyInput, PolicyOutcome, evaluate
from app.services.extraction import FieldStatus, UrgencyLevel
from app.services.extraction.guards import instruction_phrases
from app.services.extraction.schemas import EXTRACTED_FIELDS

from .context import (
    CASES_DIR,
    CONTEXT_PATH,
    CaseContext,
    EvaluationContext,
    company_facts,
    load_context,
    priority_for,
)

CASES_PATH = CASES_DIR / "cases.jsonl"
LOCK_PATH = CASES_DIR / "split_lock.json"

# Design: about 40% development, 60% held-out test (EXTRACTION_MODULE_DESIGN.md section 6).
DEV_SHARE_RANGE = (0.30, 0.50)
MIN_CASES_PER_CATEGORY = 3


class CaseFileError(Exception):
    """The case file cannot be used. Carries every problem found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


class CaseCategory(str, Enum):
    COMPLETE_VALID = "complete_valid"
    MISSING_REQUIRED = "missing_required"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    URGENT_STATED = "urgent_stated"
    EMERGENCY_CLAIMED = "emergency_claimed"
    ABOVE_THRESHOLD = "above_threshold"
    PROHIBITED = "prohibited"
    PROMPT_INJECTION = "prompt_injection"
    INFORMAL_NOISY = "informal_noisy"


class Split(str, Enum):
    DEV = "dev"  # may be used to tune prompts
    TEST = "test"  # held out: run once, after prompts are frozen


class LabelStatus(str, Enum):
    DRAFT = "draft"  # written, not yet checked by a team member
    VERIFIED = "verified"  # a team member checked every label


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExpectedField(_Strict):
    status: FieldStatus
    # Quantity is a JSON number; money is a string so no precision is lost; the rest is text.
    value: StrictInt | StrictStr | None = None


class EvaluationCase(_Strict):
    case_id: str = Field(pattern=r"^EV-\d{3}$")
    split: Split
    category: CaseCategory
    request_text: str = Field(min_length=1, max_length=2000)
    context: CaseContext = Field(default_factory=CaseContext)
    expected_fields: dict[str, ExpectedField]
    expected_urgency: UrgencyLevel
    expected_missing_fields: list[str]
    expected_checkpoint: Checkpoint
    expected_decision: PolicyOutcome
    expected_triggered_rules: list[str]
    expected_required_roles: list[str]
    label_status: LabelStatus
    verified_by: str | None = None
    notes: str | None = None

    def status_of(self, name: str) -> FieldStatus:
        return self.expected_fields[name].status

    def value_of(self, name: str) -> Any:
        """The expected value in the type the extraction uses (Decimal for money)."""
        field = self.expected_fields[name]
        if field.status is not FieldStatus.PRESENT or field.value is None:
            return None
        if name == "estimated_total":
            return Decimal(str(field.value))
        return field.value


def _value_problems(name: str, field: ExpectedField) -> list[str]:
    if field.status is not FieldStatus.PRESENT:
        return [] if field.value is None else [f"{name}: value must be null when {field.status.value}"]
    value = field.value
    if value is None:
        return [f"{name}: PRESENT needs a value"]
    if name == "quantity":
        ok = isinstance(value, int) and value > 0
        return [] if ok else [f"{name}: must be a whole number above zero"]
    if name == "estimated_total":
        try:
            amount = Decimal(value) if isinstance(value, str) else None
        except InvalidOperation:
            amount = None
        ok = amount is not None and amount.is_finite() and amount > 0
        return [] if ok else [f"{name}: must be a positive amount written as a string"]
    if not isinstance(value, str) or not value.strip():
        return [f"{name}: must be non-empty text"]
    if name == "currency" and not (len(value) == 3 and value.isalpha() and value.isupper()):
        return [f"{name}: must be a 3-letter code such as PKR"]
    return []


def check_case(case: EvaluationCase, context: EvaluationContext) -> list[str]:
    """Every problem with one case, each prefixed with its ID. Empty means it looks right."""
    problems: list[str] = []
    config = context.policy_config

    names = set(case.expected_fields)
    if names != set(EXTRACTED_FIELDS):
        missing = sorted(set(EXTRACTED_FIELDS) - names)
        extra = sorted(names - set(EXTRACTED_FIELDS))
        problems.append(f"expected_fields must list every field (missing {missing}, unknown {extra})")
        return [f"{case.case_id}: {problem}" for problem in problems]

    for name in EXTRACTED_FIELDS:
        problems.extend(_value_problems(name, case.expected_fields[name]))

    category = case.value_of("item_category")
    known = {*config.allowed_categories, *config.controlled_categories, *config.prohibited_categories}
    if category is not None and category not in known:
        problems.append(f"item_category: '{category}' is not a known category code")

    supplier = case.value_of("supplier_name")
    if supplier is not None and supplier.casefold() not in case.request_text.casefold():
        problems.append(f"supplier_name: '{supplier}' does not appear in the request text")

    should_be_missing = [
        name for name in config.required_fields if case.status_of(name) is not FieldStatus.PRESENT
    ]
    if case.expected_missing_fields != should_be_missing:
        problems.append(
            f"expected_missing_fields is {case.expected_missing_fields}, but the field statuses "
            f"give {should_be_missing}"
        )

    if case.expected_checkpoint is not Checkpoint.INTAKE:
        problems.append("expected_checkpoint: extraction cases are evaluated at INTAKE")
    for label, items in (
        ("expected_triggered_rules", case.expected_triggered_rules),
        ("expected_required_roles", case.expected_required_roles),
    ):
        if items != sorted(set(items)):
            problems.append(f"{label} must be sorted with no repeats")
    if case.label_status is LabelStatus.VERIFIED and not (case.verified_by or "").strip():
        problems.append("a verified case must name who verified it (verified_by)")

    # Only compare with the engine when the labels themselves are well formed.
    if not problems:
        problems.extend(_engine_problems(case, context))
    return [f"{case.case_id}: {problem}" for problem in problems]


def expected_policy_input(case: EvaluationCase, context: EvaluationContext) -> PolicyInput:
    """The policy input a perfect extraction of this case would produce."""
    supplier = case.value_of("supplier_name")
    return PolicyInput(
        checkpoint=Checkpoint.INTAKE,
        extraction_status=ExtractionStatus.VALID,
        missing_fields=case.expected_missing_fields,
        estimated_total=case.value_of("estimated_total"),
        currency=case.value_of("currency"),
        item_category=case.value_of("item_category"),
        supplier_name=supplier,
        supplier_conflict=case.status_of("supplier_name") is FieldStatus.CONFLICTING,
        # A fact about the text itself, found by the same code System B uses (D-051).
        instructions_in_request=bool(instruction_phrases(case.request_text)),
        proposed_priority=priority_for(
            case.expected_urgency, case.value_of("delivery_deadline"), context
        ),
        **company_facts(case.case_id, supplier, case.context, context),
    )


def _engine_problems(case: EvaluationCase, context: EvaluationContext) -> list[str]:
    result = evaluate(expected_policy_input(case, context), context.policy_config)
    problems = []
    if result.outcome is not case.expected_decision:
        problems.append(
            f"expected_decision is {case.expected_decision.value}, but the rules give "
            f"{result.outcome.value}"
        )
    rules = sorted(set(result.triggered_rule_ids))
    if rules != case.expected_triggered_rules:
        problems.append(f"expected_triggered_rules is {case.expected_triggered_rules}, rules give {rules}")
    roles = sorted(set(result.required_approver_roles))
    if roles != case.expected_required_roles:
        problems.append(f"expected_required_roles is {case.expected_required_roles}, rules give {roles}")
    return problems


def check_case_set(cases: list[EvaluationCase]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    texts: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            problems.append(f"{case.case_id}: duplicate case_id")
        seen.add(case.case_id)
        text = " ".join(case.request_text.split()).casefold()
        if text in texts:
            problems.append(f"{case.case_id}: same request text as an earlier case")
        texts.add(text)
    if not cases:
        return ["the case file is empty"]
    for category in CaseCategory:
        in_category = [case for case in cases if case.category is category]
        splits = {case.split for case in in_category}
        if len(in_category) < MIN_CASES_PER_CATEGORY:
            problems.append(
                f"category {category.value}: {len(in_category)} cases, needs at least "
                f"{MIN_CASES_PER_CATEGORY}"
            )
        elif splits != {Split.DEV, Split.TEST}:
            problems.append(f"category {category.value}: needs cases in both dev and test")
    dev_share = sum(case.split is Split.DEV for case in cases) / len(cases)
    low, high = DEV_SHARE_RANGE
    if not low <= dev_share <= high:
        problems.append(f"dev share is {dev_share:.0%}, expected between {low:.0%} and {high:.0%}")
    return problems


def read_cases(path: Path = CASES_PATH) -> tuple[list[EvaluationCase], list[str]]:
    """Parse the file. Returns the cases that parsed and a problem for each line that did not."""
    cases: list[EvaluationCase] = []
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(EvaluationCase.model_validate(json.loads(line)))
        except json.JSONDecodeError as error:
            problems.append(f"line {number}: not valid JSON ({error.msg})")
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
                for issue in error.errors()
            )
            problems.append(f"line {number}: {details}")
    return cases, problems


def _fingerprint(case: EvaluationCase) -> str:
    return hashlib.sha256(f"{case.split.value}\n{case.request_text}".encode()).hexdigest()


def write_lock(cases: list[EvaluationCase], path: Path = LOCK_PATH) -> None:
    """Record each case's split and text. Labels may still be corrected after this."""
    lock = {
        "about": "Split recorded before any tuning. Do not edit by hand; see docs/EVALUATION_CASES.md.",
        "cases": {case.case_id: _fingerprint(case) for case in sorted(cases, key=lambda c: c.case_id)},
    }
    path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def check_lock(cases: list[EvaluationCase], path: Path = LOCK_PATH) -> list[str]:
    if not path.exists():
        return ["the split is not locked yet (run check_cases --lock once, before any tuning)"]
    locked: dict[str, str] = json.loads(path.read_text(encoding="utf-8")).get("cases", {})
    current = {case.case_id: _fingerprint(case) for case in cases}
    problems = [f"{case_id}: removed after the split was locked" for case_id in sorted(set(locked) - set(current))]
    problems += [f"{case_id}: added after the split was locked" for case_id in sorted(set(current) - set(locked))]
    problems += [
        f"{case_id}: split or request text changed after the split was locked"
        for case_id in sorted(set(locked) & set(current))
        if locked[case_id] != current[case_id]
    ]
    return problems


def validate(
    cases_path: Path = CASES_PATH,
    context_path: Path = CONTEXT_PATH,
    lock_path: Path = LOCK_PATH,
) -> tuple[list[EvaluationCase], list[str]]:
    """Run every check. Returns the parsed cases and all problems found."""
    context = load_context(context_path)
    cases, problems = read_cases(cases_path)
    for case in cases:
        problems.extend(check_case(case, context))
    problems.extend(check_case_set(cases))
    problems.extend(check_lock(cases, lock_path))
    return cases, problems


def load_cases(
    cases_path: Path = CASES_PATH,
    context_path: Path = CONTEXT_PATH,
    lock_path: Path = LOCK_PATH,
    *,
    require_verified: bool,
    split: Split | None = None,
) -> list[EvaluationCase]:
    """Cases ready to use, or CaseFileError. Metrics must pass require_verified=True.

    A draft label has not been checked by a person, and the design does not allow results to
    be reported on unchecked labels (EXTRACTION_MODULE_DESIGN.md section 6). With split, only
    that split is returned and only its labels must be verified, so the dev cases can be used
    while the test labels wait for their check. The whole file is still validated.
    """
    cases, problems = validate(cases_path, context_path, lock_path)
    if split is not None:
        cases = [case for case in cases if case.split is split]
    if require_verified:
        drafts = [case.case_id for case in cases if case.label_status is not LabelStatus.VERIFIED]
        if drafts:
            problems.append(
                f"{len(drafts)} case(s) are not verified yet (first: {drafts[0]}); a team member "
                "must check every label before results count"
            )
    if problems:
        raise CaseFileError(problems)
    return cases
