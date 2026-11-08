"""The policy engine: runs the rules for a checkpoint and picks the final answer.

Pure and deterministic: no database, no clock, no LLM. The same input and settings
always give the same result. Anything unexpected fails closed (POL-900), so the
engine never answers CONTINUE when it is unsure. See docs/POLICY_RULES.md.
"""
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from . import rules
from .types import Checkpoint, PolicyConfig, PolicyInput, PolicyOutcome, PolicyResult, TriggeredRule

# Stricter outcomes win: BLOCK > HUMAN_REVIEW > CONTINUE.
_STRICTNESS = {PolicyOutcome.CONTINUE: 0, PolicyOutcome.HUMAN_REVIEW: 1, PolicyOutcome.BLOCK: 2}


def evaluate(
    policy_input: PolicyInput | Mapping[str, Any],
    config: PolicyConfig | Mapping[str, Any] | None,
) -> PolicyResult:
    """Evaluate one request at one checkpoint against one organization's settings.

    Accepts already-validated objects or raw dictionaries. Invalid raw data does not
    raise: it produces a HUMAN_REVIEW result with POL-900.
    """
    settings = _read(config, PolicyConfig)
    data = _read(policy_input, PolicyInput)
    checkpoint = data.checkpoint if data else None

    if settings is None:
        return _fail_closed_result(
            checkpoint, None, None, "Policy settings are missing or invalid."
        )
    role = settings.procurement_officer_role
    version = settings.policy_version
    if data is None:
        return _fail_closed_result(None, version, role, "Request data is invalid or incomplete.")
    if data.organization_id != settings.organization_id:
        return _fail_closed_result(
            checkpoint, version, role, "Policy settings belong to a different organization."
        )

    triggered: list[TriggeredRule] = []
    try:
        triggered.extend(rules.input_checks(data, settings))
    except Exception:  # noqa: BLE001 - any failure must fail closed, never CONTINUE
        triggered.append(rules.fail_closed(role, "Request data could not be checked."))

    for rule_id in rules.RULES_BY_CHECKPOINT[data.checkpoint]:
        try:
            triggered.extend(rules.RULE_FUNCTIONS[rule_id](data, settings))
        except rules.MissingInput as missing:
            reason = f"Information needed by the rules is missing: {missing.field}."
            triggered.append(rules.fail_closed(role, reason))
        except Exception:  # noqa: BLE001 - internal details are not shown to users
            triggered.append(rules.fail_closed(role, f"Rule {rule_id} could not be evaluated."))

    return _build_result(data.checkpoint, version, triggered)


def _read(value: Any, model: type[PolicyInput] | type[PolicyConfig]) -> Any:
    if value is None or isinstance(value, model):
        return value
    try:
        return model.model_validate(value)
    except (ValidationError, TypeError, ValueError):
        return None


def _fail_closed_result(
    checkpoint: Checkpoint | None, version: str | None, role: str | None, reason: str
) -> PolicyResult:
    return _build_result(checkpoint, version, [rules.fail_closed(role, reason)])


def _build_result(
    checkpoint: Checkpoint | None, version: str | None, triggered: list[TriggeredRule]
) -> PolicyResult:
    unique: list[TriggeredRule] = []
    for rule in triggered:
        if rule not in unique:
            unique.append(rule)
    # Rule-ID order; POL-900 sorts last. sorted() is stable, so equal IDs keep their order.
    ordered = sorted(unique, key=lambda rule: rule.rule_id)

    outcome = max(
        (rule.outcome for rule in ordered),
        key=_STRICTNESS.__getitem__,
        default=PolicyOutcome.CONTINUE,
    )
    roles: list[str] = []
    for rule in ordered:
        if rule.required_approver_role and rule.required_approver_role not in roles:
            roles.append(rule.required_approver_role)

    return PolicyResult(
        outcome=outcome,
        checkpoint=checkpoint,
        triggered_rules=ordered,
        required_approver_roles=roles,
        policy_version=version,
    )
