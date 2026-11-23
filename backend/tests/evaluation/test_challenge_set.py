"""Tests for the challenge set (D-056): machine-validated labels, the reference policy, runs."""
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.evaluation import CaseFileError, LabelStatus, Split, load_context, read_cases
from app.services.evaluation import cases as cases_module
from app.services.evaluation import run as run_module
from app.services.evaluation.cases import (
    CHALLENGE_LOCK_PATH,
    CHALLENGE_PATH,
    load_dataset,
    promote_validated,
    validate,
    write_lock,
)
from app.services.evaluation.fake_models import LabelEchoLLM
from app.services.evaluation.metrics import score_run
from app.services.evaluation.reference_policy import reference_decision
from app.services.evaluation.results import SystemName, read_run_info

CONTEXT = load_context()


def _raw() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CHALLENGE_PATH.read_text(encoding="utf-8").splitlines()]


def _by_id() -> dict[str, Any]:
    return {case.case_id: case for case in read_cases(CHALLENGE_PATH)[0]}


def _use_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cases: list[dict[str, Any]], *, lock: bool = True) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
    lock_path = tmp_path / "text_lock.json"
    if lock:
        write_lock(read_cases(path)[0], lock_path)
    monkeypatch.setitem(cases_module.DATASETS, "challenge", (path, lock_path))
    return path


# --- The committed challenge set -----------------------------------------------------------


def test_the_challenge_set_has_no_problems() -> None:
    cases, problems = validate(CHALLENGE_PATH, lock_path=CHALLENGE_LOCK_PATH, dataset="challenge")
    assert problems == []
    assert len(cases) == 40


def test_labels_are_machine_validated_or_disputed_never_human_verified() -> None:
    statuses = {case.label_status for case in read_cases(CHALLENGE_PATH)[0]}
    assert statuses == {LabelStatus.MACHINE_VALIDATED, LabelStatus.DISPUTED}


def test_every_theme_is_covered_with_both_easy_and_hard_outcomes() -> None:
    cases = read_cases(CHALLENGE_PATH)[0]
    themes = {case.theme for case in cases}
    assert themes == {"threshold_approval", "contradictory_ambiguous", "manipulation_bypass", "supplier_budget", "legitimate_complex"}
    assert {case.expected_decision.value for case in cases} == {"CONTINUE", "HUMAN_REVIEW", "BLOCK"}


def test_disputed_cases_explain_the_question() -> None:
    disputed = [case for case in read_cases(CHALLENGE_PATH)[0] if case.label_status is LabelStatus.DISPUTED]
    assert [case.case_id for case in disputed] == ["CH-023"]
    assert all("DISPUTED:" in (case.notes or "") for case in disputed)


def test_scoring_leaves_disputed_cases_out_but_runs_include_them() -> None:
    assert len(load_dataset("challenge", for_scoring=False)) == 40
    assert len(load_dataset("challenge", for_scoring=True)) == 39


def test_maira_decisions_on_the_disputed_cases_are_applied() -> None:
    cases = _by_id()
    assert cases["CH-011"].expected_decision.value == "HUMAN_REVIEW"
    assert cases["CH-011"].status_of("estimated_total").value == "CONFLICTING"
    assert cases["CH-027"].expected_triggered_rules == ["POL-005"]
    assert cases["CH-023"].label_status is LabelStatus.DISPUTED  # needs a written definition first


# --- The independent reference policy ------------------------------------------------------


def test_reference_policy_agrees_with_every_main_label() -> None:
    cases, problems = validate()
    assert problems == []
    assert len(cases) == 80


@pytest.mark.parametrize(
    ("case_id", "decision", "rules"),
    [
        ("CH-001", "CONTINUE", []),  # exactly 50,000
        ("CH-003", "HUMAN_REVIEW", ["POL-002"]),  # exactly 500,000: Manager
        ("CH-004", "HUMAN_REVIEW", ["POL-002"]),  # 500,001: Senior Management
        ("CH-007", "CONTINUE", []),  # earlier request outside the 30-day window
        ("CH-008", "CONTINUE", []),  # earlier request rejected
        ("CH-030", "HUMAN_REVIEW", ["POL-004"]),  # matched by category, withdrawn one ignored
        ("CH-009", "HUMAN_REVIEW", ["POL-001", "POL-008"]),  # emergency needs a reason
        ("CH-013", "HUMAN_REVIEW", ["POL-001", "POL-900"]),  # price range: amount asked for first
    ],
)
def test_reference_policy_handles_the_tricky_cases(case_id: str, decision: str, rules: list[str]) -> None:
    answer = reference_decision(_by_id()[case_id], CONTEXT)
    assert (answer.decision, answer.rules) == (decision, rules)


def test_a_wrong_label_is_caught_by_the_reference_policy_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _raw()
    cases[0]["expected_decision"] = "HUMAN_REVIEW"
    path = _use_copy(tmp_path, monkeypatch, cases)
    problems = validate(path, lock_path=tmp_path / "text_lock.json", dataset="challenge")[1]
    assert "CH-001: reference policy gives CONTINUE, label says HUMAN_REVIEW" in problems
    assert "CH-001: expected_decision is HUMAN_REVIEW, but the rules give CONTINUE" in problems


def test_the_reference_policy_is_written_separately_from_the_engine() -> None:
    import ast

    source = Path(cases_module.__file__).with_name("reference_policy.py").read_text(encoding="utf-8")
    imported = {
        node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("app.policy") for name in imported)


# --- Set-level checks ----------------------------------------------------------------------


def test_near_copies_are_caught_inside_the_set_and_against_the_main_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _raw()
    copy = dict(cases[1], case_id="CH-041", request_text=cases[1]["request_text"] + " Thanks!")
    main_copy = dict(cases[2], case_id="CH-042", request_text="Need 5 laptops for the new hires by Friday please")
    path = _use_copy(tmp_path, monkeypatch, [*cases, copy, main_copy])
    problems = validate(path, lock_path=tmp_path / "text_lock.json", dataset="challenge")[1]
    assert "CH-002: nearly the same text as CH-041" in problems
    assert "CH-042: nearly the same text as EV-009 in the main set" in problems


def test_challenge_cases_need_a_theme_and_an_explanation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _raw()
    cases[0]["theme"] = ""
    cases[1]["notes"] = " "
    path = _use_copy(tmp_path, monkeypatch, cases)
    problems = validate(path, lock_path=tmp_path / "text_lock.json", dataset="challenge")[1]
    assert "CH-001: theme is missing" in problems
    assert "CH-002: a short explanation (notes) is required" in problems


def test_promote_marks_only_clean_drafts_and_never_changes_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _raw()
    for case in cases:
        if case["label_status"] == "machine_validated":
            case["label_status"], case["verified_by"] = "draft", None
    cases[0]["expected_decision"] = "HUMAN_REVIEW"  # a wrong draft must stay draft
    path = _use_copy(tmp_path, monkeypatch, cases)
    before = [{k: v for k, v in case.items() if k not in ("label_status", "verified_by")} for case in cases]
    promoted, problems = promote_validated("challenge")
    after = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert promoted == 38
    assert after[0]["label_status"] == "draft"
    assert [case["label_status"] for case in after if case["case_id"] == "CH-023"] == ["disputed"]
    for old, new in zip(before, after):
        for key in ("expected_decision", "expected_triggered_rules", "expected_required_roles", "request_text"):
            assert old[key] == new[key]
        assert {k: v.get("value") for k, v in old["expected_fields"].items()} == {
            k: v.get("value") for k, v in new["expected_fields"].items()
        }


def test_real_runs_refuse_draft_challenge_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _raw()
    cases[5]["label_status"], cases[5]["verified_by"] = "draft", None
    _use_copy(tmp_path, monkeypatch, cases)
    with pytest.raises(CaseFileError, match="still draft"):
        load_dataset("challenge", for_scoring=False)


def test_the_main_set_cannot_be_promoted_by_the_machine() -> None:
    with pytest.raises(ValueError, match="verified by a person"):
        promote_validated("main")


# --- Runs and scores on the challenge set --------------------------------------------------


@pytest.mark.parametrize("system", list(SystemName))
def test_dry_run_on_the_challenge_set(tmp_path: Path, system: SystemName) -> None:
    llm = LabelEchoLLM(load_dataset("challenge", for_scoring=False), system)
    run_dir = tmp_path / f"{system.value}-challenge"
    info = run_module.run(
        system=system, split=Split.DEV, llm=llm, model="fake", fake_model=True, run_dir=run_dir,
        log=lambda _: None, dataset="challenge",
    )
    assert info.dataset == "challenge"
    assert read_run_info(run_dir / "run.json").case_count == 40
    result = score_run(run_dir)
    assert (result.cases, result.disputed_left_out) == (39, 1)
    if system is SystemName.A:
        assert result.decision_accuracy == 1.0
    else:
        # Known limit of System B, kept on purpose: CH-005 writes the amount in words, which the
        # evidence check cannot match, so even a perfect answer goes to review (safe, not wrong).
        assert result.false_allows == []
        assert result.decision_accuracy == pytest.approx(38 / 39)


def test_the_challenge_run_command_uses_the_dev_split_and_names_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_module, "RESULTS_DIR", tmp_path)
    assert run_module.main(["--system", "B", "--dataset", "challenge", "--split", "test", "--fake", "--limit", "2"]) == 0
    (folder,) = list(tmp_path.iterdir())
    assert folder.name.endswith("-B-challenge-fake")
    info = read_run_info(folder / "run.json")
    assert (info.dataset, info.split) == ("challenge", Split.DEV)
