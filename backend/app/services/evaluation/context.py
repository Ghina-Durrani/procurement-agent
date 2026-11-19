"""Trusted company facts for the evaluation, and how they reach the policy engine.

In the real system, facts such as "is this supplier approved?" or "is there budget?" come from
the database, never from the LLM. The evaluation has no database, so the same facts come from
evaluation/cases/context.json. System B and the label check both use this module, so they see
the request through exactly the same company data.
"""
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.policy import BudgetStatus, PolicyConfig, Priority, RecentRequest, SupplierStatus
from app.services.extraction import UrgencyLevel

REPO_ROOT = Path(__file__).resolve().parents[4]
CASES_DIR = REPO_ROOT / "evaluation" / "cases"
CONTEXT_PATH = CASES_DIR / "context.json"

# Fixed IDs so the same case always builds the same policy input (reproducible runs).
_ID_NAMESPACE = UUID("6f2c7d1e-5b0a-4c8e-9a51-0e7a2b3c4d5f")

# PROPOSED (D-047): until the priority step is built (D-028, D-031), the evaluation maps the
# urgency signal straight to a priority. Deadline-based thresholds are left out on purpose:
# their values are still OPEN. Only EMERGENCY changes a policy outcome (POL-008).
PRIORITY_FOR_URGENCY = {
    UrgencyLevel.NORMAL: Priority.NORMAL,
    UrgencyLevel.URGENT: Priority.HIGH_PRIORITY,
    UrgencyLevel.EMERGENCY_CLAIMED: Priority.EMERGENCY,
}


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SupplierDirectory(_Strict):
    approved: list[str]
    blocked: list[str]


class EvaluationContext(_Strict):
    about: str = ""
    submitted_at: AwareDatetime
    default_budget_status: BudgetStatus
    suppliers: SupplierDirectory
    policy_config: PolicyConfig


class RecentRequestSpec(_Strict):
    """An earlier request by the same requester, written relative to submitted_at."""

    days_ago: int = Field(ge=0)
    estimated_total: Decimal = Field(gt=0)
    supplier_name: str | None = None
    item_category: str | None = None
    status: str = "APPROVED"

    @field_validator("estimated_total", mode="before")
    @classmethod
    def _no_float(cls, value: Any) -> Any:
        if isinstance(value, float):
            raise ValueError("money must be written as a string, not a float")
        return value


class CaseContext(_Strict):
    """Per-case changes to the shared context."""

    budget_status: BudgetStatus | None = None
    recent_requests: list[RecentRequestSpec] = Field(default_factory=list)


def load_context(path: Path = CONTEXT_PATH) -> EvaluationContext:
    return EvaluationContext.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()


def supplier_status_for(name: str | None, directory: SupplierDirectory) -> SupplierStatus | None:
    """Look a supplier up the way the database lookup will: ignore case and extra spaces.

    No name gives None (no supplier yet). A name that is not on either list is NOT_APPROVED.
    """
    if name is None or not name.strip():
        return None
    key = _normalise(name)
    if key in {_normalise(blocked) for blocked in directory.blocked}:
        return SupplierStatus.BLOCKED
    if key in {_normalise(approved) for approved in directory.approved}:
        return SupplierStatus.APPROVED
    return SupplierStatus.NOT_APPROVED


def recent_requests_for(
    case_id: str, specs: list[RecentRequestSpec], submitted_at: datetime
) -> list[RecentRequest]:
    return [
        RecentRequest(
            request_id=uuid5(_ID_NAMESPACE, f"{case_id}/recent/{index}"),
            submitted_at=submitted_at - timedelta(days=spec.days_ago),
            estimated_total=spec.estimated_total,
            currency="PKR",
            status=spec.status,
            supplier_name=spec.supplier_name,
            item_category=spec.item_category,
        )
        for index, spec in enumerate(specs)
    ]


def request_id_for(case_id: str) -> UUID:
    return uuid5(_ID_NAMESPACE, case_id)


def company_facts(
    case_id: str,
    supplier_name: str | None,
    case_context: CaseContext,
    context: EvaluationContext,
) -> dict[str, Any]:
    """The PolicyInput values that come from company data, for one case.

    supplier_name is whatever the system under test read from the request; its status is
    looked up here, exactly as the real workflow will look it up in the database.
    """
    return {
        "request_id": request_id_for(case_id),
        "organization_id": context.policy_config.organization_id,
        "submitted_at": context.submitted_at,
        "supplier_status": supplier_status_for(supplier_name, context.suppliers),
        "budget_status": case_context.budget_status or context.default_budget_status,
        "recent_requests": recent_requests_for(
            case_id, case_context.recent_requests, context.submitted_at
        ),
    }
