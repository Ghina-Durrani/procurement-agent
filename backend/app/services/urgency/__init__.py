"""Urgency step: the proposed priority, computed by code from what the extraction reported.

Typical use, after extraction (and after any clarification, so a deadline given in a reply
counts):

    proposal = propose_priority(result.urgency.level, result.delivery_deadline, sent_on)
    policy_input = to_policy_input(result, ..., proposed_priority=proposal.priority)
"""
from .deadline import resolve_deadline
from .priority import (
    DUE_SOON_WITHIN_DAYS,
    HIGH_PRIORITY_WITHIN_DAYS,
    PriorityProposal,
    propose_priority,
)

__all__ = [
    "DUE_SOON_WITHIN_DAYS",
    "HIGH_PRIORITY_WITHIN_DAYS",
    "PriorityProposal",
    "propose_priority",
    "resolve_deadline",
]
