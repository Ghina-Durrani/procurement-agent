"""Fixed-choice values stored in the database.

Values the policy engine already defines are imported from app.policy.types, so the
database and the engine can never disagree. All enums are uppercase text (BACKEND_GUIDE).
Role names are NOT an enum: the policy engine returns role names as plain text that each
organization sets in its PolicyConfig, and the role model is still open (Q-004).
"""
from enum import Enum

from app.policy.types import (
    Checkpoint,
    ExtractionStatus,
    PolicyOutcome,
    Priority,
    SupplierStatus,
)

__all__ = [
    "ActorType",
    "Checkpoint",
    "ExtractionStatus",
    "PolicyOutcome",
    "Priority",
    "RequestStatus",
    "SupplierStatus",
]


class RequestStatus(str, Enum):
    """Where a request is in the workflow. Must match the service layer when it exists."""

    RECEIVED = "RECEIVED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    QUOTING = "QUOTING"  # approved; collecting and comparing quotations
    ORDERED = "ORDERED"  # a purchase order has been issued


class ActorType(str, Enum):
    USER = "USER"  # a logged-in person
    SYSTEM = "SYSTEM"  # deterministic code (service layer, policy engine)
    AGENT = "AGENT"  # an LLM-based component


class ApprovalDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RfqStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class RfqRecipientStatus(str, Enum):
    INVITED = "INVITED"
    RESPONDED = "RESPONDED"
    DECLINED = "DECLINED"


class QuotationSource(str, Enum):
    MANUAL_ENTRY = "MANUAL_ENTRY"
    EXTRACTED = "EXTRACTED"  # read from an uploaded document


class PurchaseOrderStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"
