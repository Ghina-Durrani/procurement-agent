"""Tests for the priority step: deadline phrases and the priority rules (D-028, D-049)."""
from datetime import date

import pytest

from app.policy import Priority
from app.services.extraction import UrgencyLevel
from app.services.urgency import PriorityProposal, propose_priority, resolve_deadline

THURSDAY = date(2026, 11, 19)  # a Thursday
NORMAL, URGENT, EMERGENCY = UrgencyLevel.NORMAL, UrgencyLevel.URGENT, UrgencyLevel.EMERGENCY_CLAIMED


# --- Deadline phrases -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("today", date(2026, 11, 19)),
        ("ASAP", date(2026, 11, 19)),
        ("immediately", date(2026, 11, 19)),
        ("right now", date(2026, 11, 19)),
        ("in an hour", date(2026, 11, 19)),
        ("within 24 hours", date(2026, 11, 20)),
        ("tomorrow", date(2026, 11, 20)),
        ("by tomorrow morning", date(2026, 11, 20)),
        ("by Friday", date(2026, 11, 20)),
        ("before Monday", date(2026, 11, 23)),
        ("by Thursday", date(2026, 11, 19)),  # nearest Thursday on or after today
        ("next Thursday", date(2026, 11, 26)),  # "next" is strictly after today
        ("Needed by next Monday", date(2026, 11, 23)),
        ("within 3 days", date(2026, 11, 22)),
        ("within two weeks", date(2026, 12, 3)),
        ("in 10 days", date(2026, 11, 29)),
        ("by end of week", date(2026, 11, 20)),
        ("by end of month", date(2026, 11, 30)),
        ("by the 25th", date(2026, 11, 25)),
        ("by the 15th", date(2026, 12, 15)),  # the 15th of this month has passed
        ("20 Nov", date(2026, 11, 20)),
        ("by 3rd December", date(2026, 12, 3)),
        ("December 1", date(2026, 12, 1)),
        ("by 10 Nov", date(2026, 11, 10)),  # stays in the past: overdue, not next year
    ],
)
def test_clear_deadline_phrases(phrase: str, expected: date) -> None:
    assert resolve_deadline(phrase, THURSDAY) == expected


@pytest.mark.parametrize(
    "phrase",
    [None, "", "   ", "before summer", "soon", "when possible", "by 31 Feb", "by the 31st", "by the 0th"],
)
def test_unclear_deadlines_are_not_guessed(phrase: str | None) -> None:
    assert resolve_deadline(phrase, THURSDAY) is None


def test_the_15th_in_december_rolls_into_january() -> None:
    assert resolve_deadline("by the 15th", date(2026, 12, 20)) == date(2027, 1, 15)


# --- Priority rules -------------------------------------------------------------------------


def propose(urgency: UrgencyLevel, phrase: str | None) -> PriorityProposal:
    return propose_priority(urgency, phrase, THURSDAY)


def test_no_urgency_and_no_deadline_is_normal() -> None:
    proposal = propose(NORMAL, None)
    assert proposal.priority is Priority.NORMAL
    assert proposal.due_soon is False
    assert proposal.reasons == []


def test_a_claimed_emergency_is_an_emergency_whatever_the_deadline() -> None:
    assert propose(EMERGENCY, None).priority is Priority.EMERGENCY
    assert propose(EMERGENCY, "within two weeks").priority is Priority.EMERGENCY


def test_urgent_words_give_high_priority_even_with_a_far_deadline() -> None:
    assert propose(URGENT, None).priority is Priority.HIGH_PRIORITY
    assert propose(URGENT, "by end of month").priority is Priority.HIGH_PRIORITY


@pytest.mark.parametrize(
    ("phrase", "priority", "due_soon", "days_left"),
    [
        ("today", Priority.HIGH_PRIORITY, False, 0),
        ("by Friday", Priority.HIGH_PRIORITY, False, 1),
        ("within 3 days", Priority.HIGH_PRIORITY, False, 3),  # 3 days is still high priority
        ("within 4 days", Priority.NORMAL, True, 4),  # 4 to 7 days: normal, due soon
        ("within 7 days", Priority.NORMAL, True, 7),
        ("within 8 days", Priority.NORMAL, False, 8),
        ("within two weeks", Priority.NORMAL, False, 14),
        ("by 10 Nov", Priority.HIGH_PRIORITY, False, -9),  # overdue
    ],
)
def test_deadline_thresholds(phrase: str, priority: Priority, due_soon: bool, days_left: int) -> None:
    proposal = propose(NORMAL, phrase)
    assert (proposal.priority, proposal.due_soon, proposal.days_left) == (priority, due_soon, days_left)


def test_due_soon_is_only_a_tag_on_normal_requests() -> None:
    assert propose(EMERGENCY, "within 5 days").due_soon is False
    assert propose(URGENT, "within 5 days").due_soon is False


def test_an_unreadable_deadline_is_ignored_and_explained() -> None:
    proposal = propose(NORMAL, "before summer")
    assert proposal.priority is Priority.NORMAL
    assert proposal.deadline is None
    assert proposal.reasons == ["The deadline could not be read as a date, so it was not used."]


def test_reasons_explain_the_priority() -> None:
    assert propose(NORMAL, "by Friday").reasons == ["The deadline is in 1 day(s)."]
    assert propose(NORMAL, "within 5 days").reasons == ["Due soon: the deadline is in 5 days."]
    assert propose(NORMAL, "by 10 Nov").reasons == ["The deadline passed 9 day(s) ago."]
    assert propose(EMERGENCY, None).reasons == [
        "The requester claims an emergency (Senior Management must confirm)."
    ]


def test_thresholds_can_be_changed_by_the_caller() -> None:
    proposal = propose_priority(NORMAL, "within 5 days", THURSDAY, high_within_days=5)
    assert proposal.priority is Priority.HIGH_PRIORITY


def test_priority_step_has_no_clock_database_or_llm_imports() -> None:
    import ast
    import pathlib

    import app.services.urgency as package

    banned = {"time", "sqlalchemy", "httpx", "app.db", "app.services.extraction.openai_compatible"}
    for path in pathlib.Path(package.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not any(name == b or name.startswith(b + ".") for b in banned), (path.name, name)
        # date.today() / datetime.now() would make results depend on when they run.
        source = path.read_text(encoding="utf-8")
        assert "today()" not in source and ".now(" not in source, path.name
