"""Test data builders for the policy engine: the demo settings and the "starting request".

Values match docs/POLICY_RULES.md sections 6 and 7. They are demo values only.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.policy import Checkpoint, PolicyConfig, PolicyInput, RecentRequest

ORG_ID = UUID("00000000-0000-0000-0000-0000000000a1")
REQUESTER_ID = UUID("00000000-0000-0000-0000-0000000000b1")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-0000000000b2")
REQUEST_ID = UUID("00000000-0000-0000-0000-0000000000c1")
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
SUPPLIER = "Alpha Traders"


def demo_config(**changes: Any) -> PolicyConfig:
    values: dict[str, Any] = {
        "organization_id": ORG_ID,
        "policy_version": "demo-2026-11-05.1",
        "accepted_currencies": ["PKR"],
        "required_fields": ["item_description", "quantity", "estimated_total", "currency"],
        # A business reason is optional for ordinary purchases up to the no-approval limit (D-053).
        "conditionally_required_fields": [
            {
                "field": "business_justification",
                "required_above": "50000.00",
                "required_for_emergency": True,
                "required_for_categories": ["SOFTWARE", "HAZARDOUS_CHEMICALS", "VEHICLES"],
            }
        ],
        "approval_tiers": [
            {"up_to": "50000.00", "approver_role": None},
            {"up_to": "500000.00", "approver_role": "MANAGER"},
            {"up_to": None, "approver_role": "SENIOR_MANAGER"},
        ],
        "quotation_bands": [
            {"up_to": "100000.00", "min_quotations": 1},
            {"up_to": None, "min_quotations": 3},
        ],
        "split_window_days": 30,
        "split_watched_thresholds": ["50000.00", "100000.00", "500000.00"],
        "split_ignored_statuses": ["REJECTED", "WITHDRAWN"],
        "allowed_categories": [
            "OFFICE_SUPPLIES",
            "IT_HARDWARE",
            "FURNITURE",
            "MAINTENANCE_SERVICES",
            "CLEANING_SUPPLIES",
            "PRINTING",
            "TRAVEL",
        ],
        "controlled_categories": {
            "SOFTWARE": "IT_APPROVER",
            "HAZARDOUS_CHEMICALS": "HSE_APPROVER",
            "VEHICLES": "SENIOR_MANAGER",
        },
        "prohibited_categories": ["WEAPONS", "ALCOHOL", "PERSONAL_USE", "GIFT_CARDS"],
        "procurement_officer_role": "PROCUREMENT_OFFICER",
        "finance_approver_role": "FINANCE_APPROVER",
        "emergency_approver_role": "SENIOR_MANAGER",
    }
    values.update(changes)
    return PolicyConfig.model_validate(values)


def recent(days_ago: int, total: str, **changes: Any) -> RecentRequest:
    """An earlier request by the same requester, by default from the same supplier."""
    values: dict[str, Any] = {
        "request_id": UUID(int=1000 + days_ago),
        "submitted_at": NOW - timedelta(days=days_ago),
        "estimated_total": Decimal(total),
        "currency": "PKR",
        "status": "APPROVED",
        "supplier_name": SUPPLIER,
        "item_category": "OFFICE_SUPPLIES",
    }
    values.update(changes)
    return RecentRequest.model_validate(values)


def starting_request(**changes: Any) -> PolicyInput:
    """The 'starting request' from POLICY_RULES.md section 7; each test changes a few fields."""
    values: dict[str, Any] = {
        "request_id": REQUEST_ID,
        "organization_id": ORG_ID,
        "checkpoint": Checkpoint.INTAKE,
        "requester_user_id": REQUESTER_ID,
        "submitted_at": NOW,
        "extraction_status": "VALID",
        "missing_fields": [],
        "estimated_total": Decimal("30000.00"),
        "currency": "PKR",
        "item_category": "OFFICE_SUPPLIES",
        "supplier_name": SUPPLIER,
        "supplier_status": "APPROVED",
        "budget_status": "AVAILABLE",
        "proposed_priority": "NORMAL",
        "recent_requests": [],
    }
    values.update(changes)
    return PolicyInput.model_validate(values)


def pre_po_request(**changes: Any) -> PolicyInput:
    """A request at the 'before purchase order' moment: estimated and cleared at 30,000 PKR,
    one approved supplier's quotation of 30,000 PKR selected, budget available."""
    values: dict[str, Any] = {
        "checkpoint": Checkpoint.PRE_PO,
        "selected_quotation_total": Decimal("30000.00"),
        "approved_total": Decimal("30000.00"),
        "quotation_count": 1,
    }
    values.update(changes)
    return starting_request(**values)
