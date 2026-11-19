"""Tests for the labelled evaluation cases and the checks that guard them.

Two groups: the real case file must pass every check, and each check must catch the mistake it
exists for (tested on edited copies in a temporary folder).
"""
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.policy import PolicyConfig, Priority, SupplierStatus
from app.services.evaluation import (
    PRIORITY_FOR_URGENCY,
    CaseContext,
    CaseFileError,
    LabelStatus,
    Split,
    load_cases,
    load_context,
    read_cases,
    supplier_status_for,
    validate,
    write_lock,
)
from app.services.evaluation.cases import CASES_PATH
from app.services.evaluation.check_cases import main as check_cases_main
from app.services.extraction import FieldStatus, UrgencyLevel
from tests.policy.policy_factories import demo_config

CONTEXT = load_context()


def _raw_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines()]


def _case(case_id: str) -> dict[str, Any]:
    return next(case for case in _raw_cases() if case["case_id"] == case_id)


def _write(folder: Path, cases: list[dict[str, Any]], *, lock: bool = True) -> Path:
    path = folder / "cases.jsonl"
    path.write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
    if lock:
        parsed, problems = read_cases(path)
        assert not problems
        write_lock(parsed, folder / "split_lock.json")
    return path


def _problems(folder: Path, cases: list[dict[str, Any]], *, lock: bool = True) -> list[str]:
    path = _write(folder, cases, lock=lock)
    return validate(path, lock_path=folder / "split_lock.json")[1]


def _with(case_id: str, **changes: Any) -> list[dict[str, Any]]:
    """All cases, with one case changed."""
    cases = _raw_cases()
    for case in cases:
        if case["case_id"] == case_id:
            case.update(changes)
    return cases


def _with_field(case_id: str, name: str, **changes: Any) -> list[dict[str, Any]]:
    cases = _raw_cases()
    for case in cases:
        if case["case_id"] == case_id:
            case["expected_fields"][name].update(changes)
    return cases


# --- The real file -------------------------------------------------------------------------


def test_real_case_file_has_no_problems() -> None:
    cases, problems = validate()
    assert problems == []
    assert len(cases) >= 60


def test_real_case_file_covers_every_outcome_status_and_urgency() -> None:
    cases, _ = validate()
    assert {case.expected_decision.value for case in cases} == {"CONTINUE", "HUMAN_REVIEW", "BLOCK"}
    statuses = {field.status for case in cases for field in case.expected_fields.values()}
    assert statuses == set(FieldStatus)
    assert {case.expected_urgency for case in cases} == set(UrgencyLevel)


def test_real_split_is_about_forty_sixty_within_every_category() -> None:
    cases, _ = validate()
    per_category = Counter((case.category, case.split) for case in cases)
    for category in {case.category for case in cases}:
        assert per_category[(category, Split.DEV)] >= 1
        assert per_category[(category, Split.TEST)] > per_category[(category, Split.DEV)]


def test_evaluation_policy_settings_match_the_documented_demo_settings() -> None:
    # One set of demo numbers: POLICY_RULES.md section 6, as used by the policy tests.
    assert CONTEXT.policy_config == demo_config()


def test_check_cases_command_passes_on_the_real_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_cases_main([]) == 0
    assert "No problems found." in capsys.readouterr().out


# --- Metrics must refuse draft labels ------------------------------------------------------


def test_draft_labels_are_refused_when_verified_labels_are_required(tmp_path: Path) -> None:
    path = _write(tmp_path, _raw_cases())
    with pytest.raises(CaseFileError, match="not verified yet"):
        load_cases(path, lock_path=tmp_path / "split_lock.json", require_verified=True)


def test_fully_verified_cases_load(tmp_path: Path) -> None:
    cases = _raw_cases()
    for case in cases:
        case.update(label_status="verified", verified_by="Maira Qazi")
    path = _write(tmp_path, cases)
    loaded = load_cases(path, lock_path=tmp_path / "split_lock.json", require_verified=True)
    assert all(case.label_status is LabelStatus.VERIFIED for case in loaded)


def test_verified_case_must_name_the_person(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-001", label_status="verified", verified_by=" "))
    assert problems == ["EV-001: a verified case must name who verified it (verified_by)"]


# --- Labels are checked against the policy engine ------------------------------------------


def test_wrong_expected_decision_is_caught(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-001", expected_decision="HUMAN_REVIEW"))
    assert problems == [
        "EV-001: expected_decision is HUMAN_REVIEW, but the rules give CONTINUE"
    ]


def test_wrong_rule_list_is_caught(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-009", expected_triggered_rules=["POL-001"]))
    assert problems == [
        "EV-009: expected_triggered_rules is ['POL-001'], rules give ['POL-001', 'POL-900']"
    ]


def test_wrong_roles_are_caught(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-009", expected_required_roles=["MANAGER"]))
    assert problems == [
        "EV-009: expected_required_roles is ['MANAGER'], rules give ['PROCUREMENT_OFFICER']"
    ]


def test_wrong_urgency_label_changes_the_engine_answer(tmp_path: Path) -> None:
    # Labelling a normal request as an emergency must not slip through: POL-008 would fire.
    problems = _problems(tmp_path, _with("EV-001", expected_urgency="EMERGENCY_CLAIMED"))
    assert "EV-001: expected_decision is CONTINUE, but the rules give HUMAN_REVIEW" in problems


def test_case_context_reaches_the_engine(tmp_path: Path) -> None:
    # EV-055 is a split purchase only because of its recent request.
    case = _case("EV-055")
    assert case["context"]["recent_requests"]
    problems = _problems(tmp_path, _with("EV-055", context={}))
    assert "EV-055: expected_decision is HUMAN_REVIEW, but the rules give CONTINUE" in problems


def test_budget_override_reaches_the_engine(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-001", context={"budget_status": "INSUFFICIENT"}))
    assert "EV-001: expected_decision is CONTINUE, but the rules give BLOCK" in problems


# --- Label shape ---------------------------------------------------------------------------


def test_value_on_a_missing_field_is_caught(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with_field("EV-001", "unit", value="pcs"))
    assert problems == ["EV-001: unit: value must be null when MISSING"]


def test_present_field_without_value_is_caught(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with_field("EV-001", "delivery_location", value=None))
    assert problems == ["EV-001: delivery_location: PRESENT needs a value"]


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("quantity", 0, "quantity: must be a whole number above zero"),
        ("quantity", "5", "quantity: must be a whole number above zero"),
        ("estimated_total", "-10", "estimated_total: must be a positive amount written as a string"),
        ("estimated_total", "lots", "estimated_total: must be a positive amount written as a string"),
        ("estimated_total", 7500, "estimated_total: must be a positive amount written as a string"),
        ("currency", "Rs", "currency: must be a 3-letter code such as PKR"),
        ("item_description", "  ", "item_description: must be non-empty text"),
    ],
)
def test_bad_values_are_caught(tmp_path: Path, name: str, value: Any, message: str) -> None:
    problems = _problems(tmp_path, _with_field("EV-001", name, value=value))
    assert f"EV-001: {message}" in problems


def test_float_values_are_rejected_when_reading(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with_field("EV-001", "estimated_total", value=7500.0), lock=False)
    assert any(problem.startswith("line 1: expected_fields.estimated_total.value") for problem in problems)


def test_missing_list_must_match_the_statuses(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-009", expected_missing_fields=["currency"]))
    assert problems[0].startswith("EV-009: expected_missing_fields is ['currency']")


def test_unknown_category_is_caught(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with_field("EV-001", "item_category", value="GADGETS"))
    assert problems == ["EV-001: item_category: 'GADGETS' is not a known category code"]


def test_supplier_must_appear_in_the_text(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with_field("EV-002", "supplier_name", value="TechZone"))
    assert problems == ["EV-002: supplier_name: 'TechZone' does not appear in the request text"]


def test_every_field_must_be_labelled(tmp_path: Path) -> None:
    cases = _raw_cases()
    del cases[0]["expected_fields"]["unit"]
    problems = _problems(tmp_path, cases)
    assert problems == [
        "EV-001: expected_fields must list every field (missing ['unit'], unknown [])"
    ]


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _with("EV-001", expected_decison="CONTINUE"), lock=False)
    assert any("expected_decison" in problem for problem in problems)


# --- The whole set and the split lock ------------------------------------------------------


def test_duplicate_ids_and_texts_are_caught(tmp_path: Path) -> None:
    cases = _raw_cases()
    cases.append(dict(cases[0]))
    problems = _problems(tmp_path, cases)
    assert "EV-001: duplicate case_id" in problems
    assert "EV-001: same request text as an earlier case" in problems


def test_category_without_dev_cases_is_caught(tmp_path: Path) -> None:
    cases = _raw_cases()
    for case in cases:
        if case["category"] == "prohibited":
            case["split"] = "test"
    problems = _problems(tmp_path, cases)
    assert "category prohibited: needs cases in both dev and test" in problems


def test_dev_share_outside_the_range_is_caught(tmp_path: Path) -> None:
    cases = _raw_cases()
    for case in cases:
        case["split"] = "dev"
    problems = _problems(tmp_path, cases)
    assert "dev share is 100%, expected between 30% and 50%" in problems


def test_missing_lock_is_reported(tmp_path: Path) -> None:
    problems = _problems(tmp_path, _raw_cases(), lock=False)
    assert problems == [
        "the split is not locked yet (run check_cases --lock once, before any tuning)"
    ]


def test_lock_catches_changed_text_split_added_and_removed_cases(tmp_path: Path) -> None:
    cases = _raw_cases()
    _write(tmp_path, cases)  # lock the original
    cases[0]["request_text"] += " Thanks."
    cases[1]["split"] = "dev" if cases[1]["split"] == "test" else "test"
    removed = cases.pop(2)
    cases.append({**removed, "case_id": "EV-999", "request_text": "Need 2 pens for the desk, Rs 100, ran out."})
    _write(tmp_path, cases, lock=False)  # keep the original lock
    problems = validate(tmp_path / "cases.jsonl", lock_path=tmp_path / "split_lock.json")[1]
    assert "EV-001: split or request text changed after the split was locked" in problems
    assert "EV-002: split or request text changed after the split was locked" in problems
    assert "EV-003: removed after the split was locked" in problems
    assert "EV-999: added after the split was locked" in problems


def test_label_corrections_do_not_break_the_lock(tmp_path: Path) -> None:
    cases = _raw_cases()
    _write(tmp_path, cases)
    cases[0]["notes"] = "checked"
    cases[0]["label_status"] = "verified"
    cases[0]["verified_by"] = "Maira Qazi"
    _write(tmp_path, cases, lock=False)
    assert validate(tmp_path / "cases.jsonl", lock_path=tmp_path / "split_lock.json")[1] == []


# --- Company facts -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "status"),
    [
        (None, None),
        ("   ", None),
        ("TechZone", SupplierStatus.APPROVED),
        ("  techzone ", SupplierStatus.APPROVED),
        ("Office   Mart", SupplierStatus.APPROVED),
        ("QUICKDEAL IMPORTS", SupplierStatus.BLOCKED),
        ("TechZone Karachi", SupplierStatus.NOT_APPROVED),
        ("Star Electronics", SupplierStatus.NOT_APPROVED),
    ],
)
def test_supplier_lookup(name: str | None, status: SupplierStatus | None) -> None:
    assert supplier_status_for(name, CONTEXT.suppliers) is status


def test_only_a_claimed_emergency_becomes_an_emergency_priority() -> None:
    emergencies = [level for level, priority in PRIORITY_FOR_URGENCY.items() if priority is Priority.EMERGENCY]
    assert emergencies == [UrgencyLevel.EMERGENCY_CLAIMED]
    assert set(PRIORITY_FOR_URGENCY) == set(UrgencyLevel)


def test_recent_request_money_cannot_be_a_float() -> None:
    with pytest.raises(ValueError, match="not a float"):
        CaseContext.model_validate({"recent_requests": [{"days_ago": 1, "estimated_total": 10.5}]})


def test_settings_file_is_a_valid_policy_config() -> None:
    assert isinstance(CONTEXT.policy_config, PolicyConfig)
