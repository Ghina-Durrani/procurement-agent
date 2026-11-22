"""System B: the LLM extracts, our code checks the evidence, the policy engine decides.

This is the same pipeline the product uses: extract_request, then propose_priority, then
to_policy_input with company facts looked up by code, then evaluate. Nothing here asks the
model for a decision.
"""
import time

from app.policy import evaluate
from app.services.extraction import LLMClient, extract_request, known_categories, to_policy_input
from app.services.extraction.prompt import build_system_prompt
from app.services.extraction.schemas import EXTRACTED_FIELDS
from app.services.urgency import propose_priority

from .cases import EvaluationCase
from .context import EvaluationContext, company_facts
from .results import CaseResult, PredictedField, SystemName, field_value


def system_b_prompt(context: EvaluationContext) -> str:
    return build_system_prompt(known_categories(context.policy_config))


def run_system_b(case: EvaluationCase, llm: LLMClient, context: EvaluationContext) -> CaseResult:
    started = time.perf_counter()
    config = context.policy_config
    extraction = extract_request(
        case.request_text,
        llm,
        categories=known_categories(config),
        required_fields=config.required_fields,
    )
    proposal = propose_priority(
        extraction.urgency.level, extraction.delivery_deadline, context.submitted_at.date()
    )
    facts = company_facts(case.case_id, extraction.supplier_name, case.context, context)
    policy_input = to_policy_input(
        extraction,
        request_id=facts["request_id"],
        organization_id=facts["organization_id"],
        submitted_at=facts["submitted_at"],
        supplier_status=facts["supplier_status"],
        budget_status=facts["budget_status"],
        proposed_priority=proposal.priority,
        recent_requests=facts["recent_requests"],
    )
    decision = evaluate(policy_input, config)
    fields = {
        name: PredictedField(
            status=extraction.field_status(name), value=field_value(extraction.value(name))
        )
        for name in EXTRACTED_FIELDS
    }
    return CaseResult(
        case_id=case.case_id,
        system=SystemName.B,
        split=case.split,
        decision=decision.outcome,
        triggered_rules=sorted(set(decision.triggered_rule_ids)),
        required_roles=sorted(set(decision.required_approver_roles)),
        fields=fields,
        urgency=extraction.urgency.level,
        missing_fields=list(extraction.missing_fields),
        # The engine still decides when extraction failed (it fails closed); keep the reason.
        error="; ".join(extraction.problems) or None,
        notes=list(extraction.ambiguities),
        seconds=round(time.perf_counter() - started, 3),
    )
