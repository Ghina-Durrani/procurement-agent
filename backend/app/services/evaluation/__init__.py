"""Evaluation of System A against System B on labelled cases. Never used at runtime.

Cases and their checks: cases.py. Trusted company facts for the runs: context.py.
Labelling rules: docs/EVALUATION_CASES.md.
"""
from .cases import (
    CaseCategory,
    CaseFileError,
    EvaluationCase,
    ExpectedField,
    LabelStatus,
    Split,
    check_case,
    check_case_set,
    check_lock,
    expected_policy_input,
    load_cases,
    read_cases,
    validate,
    write_lock,
)
from .context import (
    PRIORITY_FOR_URGENCY,
    CaseContext,
    EvaluationContext,
    company_facts,
    load_context,
    supplier_status_for,
)

__all__ = [
    "PRIORITY_FOR_URGENCY",
    "CaseCategory",
    "CaseContext",
    "CaseFileError",
    "EvaluationCase",
    "EvaluationContext",
    "ExpectedField",
    "LabelStatus",
    "Split",
    "check_case",
    "check_case_set",
    "check_lock",
    "company_facts",
    "expected_policy_input",
    "load_cases",
    "load_context",
    "read_cases",
    "supplier_status_for",
    "validate",
    "write_lock",
]
