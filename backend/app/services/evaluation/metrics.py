"""Score runs against the verified answer key and compare System A with System B.

Run from backend/:
    python -m app.services.evaluation.metrics evaluation/results/<run A> evaluation/results/<run B>

Definitions (docs/EVALUATION_CASES.md section 8):
- "escalated" means any decision other than CONTINUE. A case with no decision (the system gave
  no usable answer) is not allowed through, so it counts as escalated, and is also reported.
- false-allow rate: of the cases that should be reviewed or blocked, how many got CONTINUE.
  This is the main safety number.
- missed-block rate: of the cases that should be blocked, how many were not blocked.
- over-escalation rate: of the cases that should continue, how many did not.
- field status accuracy: every field of every case; a field a system did not report is MISSING.
- field value accuracy: fields that should be PRESENT, reported PRESENT with the right value.
  Numbers and codes must match exactly; free text matches when one side's words contain the
  other's (ignoring case and punctuation).
- missing-field precision and recall: required fields that need follow-up (not PRESENT).
Only verified labels are used; draft labels are refused.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.policy import PolicyOutcome
from app.services.extraction import FieldStatus
from app.services.extraction.schemas import EXTRACTED_FIELDS

from .cases import CaseFileError, EvaluationCase, LabelStatus, load_dataset
from .context import load_context
from .results import CaseResult, PredictedField, RunInfo, read_results, read_run_info

CONTINUE = PolicyOutcome.CONTINUE
BLOCK = PolicyOutcome.BLOCK
_EXACT_FIELDS = {"quantity", "estimated_total", "currency", "item_category"}
_WORD = re.compile(r"[a-z0-9]+")


def _ratio(part: int, whole: int) -> float | None:
    return None if whole == 0 else part / whole


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


def values_match(name: str, expected: Any, predicted: Any) -> bool:
    if expected is None or predicted is None:
        return False
    if name in {"quantity", "estimated_total"}:
        try:
            return Decimal(str(expected)) == Decimal(str(predicted))
        except InvalidOperation:
            return False
    if name in _EXACT_FIELDS:
        return str(expected).strip().casefold() == str(predicted).strip().casefold()
    want, got = _words(str(expected)), _words(str(predicted))
    return bool(want and got) and (want <= got or got <= want)


@dataclass
class Score:
    system: str
    run_id: str
    fake_model: bool
    cases: int
    no_decision: int
    decision_accuracy: float | None
    false_allow_rate: float | None
    false_allows: list[str]
    missed_block_rate: float | None
    over_escalation_rate: float | None
    escalation_precision: float | None
    escalation_recall: float | None
    rules_exact_match: float | None
    roles_exact_match: float | None
    field_status_accuracy: float | None
    field_value_accuracy: float | None
    missing_precision: float | None
    missing_recall: float | None
    urgency_accuracy: float | None
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    disputed_left_out: int = 0
    dataset: str = "main"


def score(cases: list[EvaluationCase], results: list[CaseResult], info: RunInfo) -> Score:
    by_id = {result.case_id: result for result in results}
    absent = [case.case_id for case in cases if case.case_id not in by_id]
    if absent:
        raise ValueError(f"{len(absent)} case(s) have no result in run {info.run_id} (first: {absent[0]}).")
    required = load_context().policy_config.fields_to_collect()

    correct = rules_ok = roles_ok = urgency_ok = no_decision = 0
    should_escalate = escalated_ok = should_block = blocked = should_continue = over = predicted_escalate = 0
    false_allows: list[str] = []
    status_ok = status_total = value_ok = value_total = 0
    miss_tp = miss_fp = miss_fn = 0
    per_category: dict[str, dict[str, int]] = defaultdict(lambda: {"cases": 0, "correct": 0, "false_allows": 0})

    for case in cases:
        result = by_id[case.case_id]
        decision = result.decision
        expected = case.expected_decision
        bucket = per_category[case.category.value]
        bucket["cases"] += 1
        if decision is None:
            no_decision += 1
        if decision is expected:
            correct += 1
            bucket["correct"] += 1
        did_escalate = decision is not CONTINUE  # no decision is not an allow
        predicted_escalate += did_escalate
        if expected is not CONTINUE:
            should_escalate += 1
            escalated_ok += did_escalate
            if not did_escalate:
                false_allows.append(case.case_id)
                bucket["false_allows"] += 1
        else:
            should_continue += 1
            over += did_escalate
        if expected is BLOCK:
            should_block += 1
            blocked += decision is BLOCK
        rules_ok += result.triggered_rules == case.expected_triggered_rules
        roles_ok += result.required_roles == case.expected_required_roles
        urgency_ok += result.urgency is case.expected_urgency

        for name in EXTRACTED_FIELDS:
            want = case.expected_fields[name]
            got = result.fields.get(name, PredictedField(status=FieldStatus.MISSING))
            status_total += 1
            status_ok += got.status is want.status
            if want.status is FieldStatus.PRESENT:
                value_total += 1
                value_ok += got.status is FieldStatus.PRESENT and values_match(name, want.value, got.value)
        for name in required:
            want_missing = name in case.expected_missing_fields
            got_missing = result.fields.get(name, PredictedField(status=FieldStatus.MISSING)).status is not FieldStatus.PRESENT
            miss_tp += want_missing and got_missing
            miss_fp += got_missing and not want_missing
            miss_fn += want_missing and not got_missing

    n = len(cases)
    return Score(
        system=info.system.value,
        run_id=info.run_id,
        fake_model=info.fake_model,
        cases=n,
        no_decision=no_decision,
        decision_accuracy=_ratio(correct, n),
        false_allow_rate=_ratio(len(false_allows), should_escalate),
        false_allows=false_allows,
        missed_block_rate=_ratio(should_block - blocked, should_block),
        over_escalation_rate=_ratio(over, should_continue),
        escalation_precision=_ratio(escalated_ok, predicted_escalate),
        escalation_recall=_ratio(escalated_ok, should_escalate),
        rules_exact_match=_ratio(rules_ok, n),
        roles_exact_match=_ratio(roles_ok, n),
        field_status_accuracy=_ratio(status_ok, status_total),
        field_value_accuracy=_ratio(value_ok, value_total),
        missing_precision=_ratio(miss_tp, miss_tp + miss_fp),
        missing_recall=_ratio(miss_tp, miss_tp + miss_fn),
        urgency_accuracy=_ratio(urgency_ok, n),
        by_category={
            category: {
                **counts,
                "decision_accuracy": _ratio(counts["correct"], counts["cases"]),
            }
            for category, counts in sorted(per_category.items())
        },
    )


_ROWS = [
    ("False-allow rate (lower is safer)", "false_allow_rate"),
    ("Missed-block rate", "missed_block_rate"),
    ("Over-escalation rate", "over_escalation_rate"),
    ("Decision accuracy", "decision_accuracy"),
    ("Escalation precision", "escalation_precision"),
    ("Escalation recall", "escalation_recall"),
    ("Triggered rules exact match", "rules_exact_match"),
    ("Approver roles exact match", "roles_exact_match"),
    ("Field status accuracy", "field_status_accuracy"),
    ("Field value accuracy", "field_value_accuracy"),
    ("Missing-field precision", "missing_precision"),
    ("Missing-field recall", "missing_recall"),
    ("Urgency accuracy", "urgency_accuracy"),
]


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def render(scores: list[Score]) -> str:
    lines = []
    if any(item.fake_model for item in scores):
        lines += ["**DRY RUN with the fake model: these numbers test the plumbing and are not a result.**", ""]
    header = "| Metric | " + " | ".join(f"System {item.system} ({item.run_id})" for item in scores) + " |"
    lines += [header, "|---" * (len(scores) + 1) + "|"]
    lines.append("| Cases | " + " | ".join(str(item.cases) for item in scores) + " |")
    lines.append("| No usable decision | " + " | ".join(str(item.no_decision) for item in scores) + " |")
    if any(item.disputed_left_out for item in scores):
        lines.append("| Disputed cases left out | " + " | ".join(str(item.disputed_left_out) for item in scores) + " |")
    for label, key in _ROWS:
        lines.append(f"| {label} | " + " | ".join(_pct(getattr(item, key)) for item in scores) + " |")
    for item in scores:
        if item.false_allows:
            lines.append(f"\nSystem {item.system} let through: {', '.join(item.false_allows)}")
    return "\n".join(lines)


def score_run(run_dir: Path) -> Score:
    info = read_run_info(run_dir / "run.json")
    everything = load_dataset(info.dataset, split=info.split, for_scoring=False)
    cases = load_dataset(info.dataset, split=info.split, for_scoring=True)
    result = score(cases, read_results(run_dir / "results.jsonl"), info)
    result.disputed_left_out = sum(case.label_status is LabelStatus.DISPUTED for case in everything)
    result.dataset = info.dataset
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score evaluation runs against the answer key.")
    parser.add_argument("runs", nargs="+", type=Path, help="run folders under evaluation/results/")
    parser.add_argument("--json", type=Path, help="also write the scores to this JSON file")
    args = parser.parse_args(argv)
    try:
        scores = [score_run(run) for run in args.runs]
    except (CaseFileError, ValueError, FileNotFoundError) as error:
        print(f"Refused: {error}")
        return 1
    print(render(scores))
    if args.json:
        args.json.write_text(json.dumps([asdict(item) for item in scores], indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
