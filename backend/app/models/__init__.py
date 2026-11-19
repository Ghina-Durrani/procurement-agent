"""Import every model so Base.metadata knows all tables (Alembic needs this)."""
from app.models.governance import Approval, AuditEvent, PolicyConfig, PolicyEvaluation
from app.models.ordering import PurchaseOrder
from app.models.procurement import Clarification, Extraction, ProcurementRequest
from app.models.reference import Budget, Supplier, SupplierCategory
from app.models.sourcing import (
    Document,
    Quotation,
    QuotationItem,
    Rfq,
    RfqSupplier,
    SupplierEvaluation,
)
from app.models.tenancy import Organization, User

__all__ = [
    "PurchaseOrder",
    "Document",
    "Quotation",
    "QuotationItem",
    "Rfq",
    "RfqSupplier",
    "SupplierEvaluation",
    "Approval",
    "AuditEvent",
    "Budget",
    "Clarification",
    "Extraction",
    "Organization",
    "PolicyConfig",
    "PolicyEvaluation",
    "ProcurementRequest",
    "Supplier",
    "SupplierCategory",
    "User",
]
