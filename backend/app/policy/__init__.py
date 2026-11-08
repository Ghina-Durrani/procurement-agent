"""Deterministic policy engine (no database, no API, no LLM). See docs/POLICY_RULES.md.

Other modules call evaluate() with a PolicyInput and the organization's PolicyConfig.
"""
from . import rules
from .engine import evaluate
from .types import (
    ApprovalTier,
    BudgetStatus,
    Checkpoint,
    ExtractionStatus,
    PolicyConfig,
    PolicyInput,
    PolicyOutcome,
    PolicyResult,
    Priority,
    QuotationBand,
    RecentRequest,
    SupplierStatus,
    TriggeredRule,
)

__all__ = [
    "ApprovalTier",
    "BudgetStatus",
    "Checkpoint",
    "ExtractionStatus",
    "PolicyConfig",
    "PolicyInput",
    "PolicyOutcome",
    "PolicyResult",
    "Priority",
    "QuotationBand",
    "RecentRequest",
    "SupplierStatus",
    "TriggeredRule",
    "evaluate",
    "rules",
]
