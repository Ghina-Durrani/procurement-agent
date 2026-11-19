"""Propose a priority from the urgency signal and the deadline (D-028, D-049).

The LLM only reports what the request says (the urgency signal and the deadline words). This
code turns that into a proposed priority with fixed rules:

    EMERGENCY      the requester claims an emergency
    HIGH_PRIORITY  urgent words, or the deadline is within 3 days (or already passed)
    NORMAL         everything else; tagged "due soon" when the deadline is within 7 days

Priority only orders the review queue. It never approves anything and never skips a rule;
EMERGENCY adds a Senior Management check (POL-008).
"""
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.policy import Priority
from app.services.extraction.schemas import UrgencyLevel

from .deadline import resolve_deadline

# D-049 (decided 2026-11-19). Kept here, not in the policy settings: priority is not a policy
# outcome. Move to per-organization settings if organizations need different values.
HIGH_PRIORITY_WITHIN_DAYS = 3
DUE_SOON_WITHIN_DAYS = 7


class PriorityProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    priority: Priority
    due_soon: bool  # NORMAL request whose deadline is close; a display tag only
    deadline: date | None  # None when the deadline is missing or unclear
    days_left: int | None  # negative when the deadline has passed
    reasons: list[str]


def propose_priority(
    urgency: UrgencyLevel,
    deadline_phrase: str | None,
    sent_on: date,
    *,
    high_within_days: int = HIGH_PRIORITY_WITHIN_DAYS,
    due_soon_within_days: int = DUE_SOON_WITHIN_DAYS,
) -> PriorityProposal:
    """sent_on is the day the request was sent, in the organization's local time."""
    deadline = resolve_deadline(deadline_phrase, sent_on)
    days_left = (deadline - sent_on).days if deadline is not None else None
    reasons: list[str] = []

    if urgency is UrgencyLevel.EMERGENCY_CLAIMED:
        priority = Priority.EMERGENCY
        reasons.append("The requester claims an emergency (Senior Management must confirm).")
    elif urgency is UrgencyLevel.URGENT:
        priority = Priority.HIGH_PRIORITY
        reasons.append("The request states time pressure.")
    elif days_left is not None and days_left <= high_within_days:
        priority = Priority.HIGH_PRIORITY
    else:
        priority = Priority.NORMAL

    if days_left is not None:
        if days_left < 0:
            reasons.append(f"The deadline passed {-days_left} day(s) ago.")
        elif days_left <= high_within_days:
            reasons.append(f"The deadline is in {days_left} day(s).")
        elif days_left <= due_soon_within_days:
            reasons.append(f"Due soon: the deadline is in {days_left} days.")
    elif deadline_phrase and deadline_phrase.strip():
        reasons.append("The deadline could not be read as a date, so it was not used.")

    due_soon = (
        priority is Priority.NORMAL
        and days_left is not None
        and high_within_days < days_left <= due_soon_within_days
    )
    return PriorityProposal(
        priority=priority,
        due_soon=due_soon,
        deadline=deadline,
        days_left=days_left,
        reasons=reasons,
    )
