"""Who may decide which review item (D-065).

Two kinds of role:
- Management ladder: the roles in the company's approval tiers, from the lowest amount band
  to the highest (demo: MANAGER, then SENIOR_MANAGER). A higher role may also decide items
  for a lower one, as in a real delegation-of-authority table: a senior manager can approve
  what a manager can.
- Specialist roles (demo: PROCUREMENT_OFFICER, FINANCE_APPROVER): exact match only. Their
  review is a different check (supplier, prompt injection, budget), not a smaller amount, so
  seniority does not replace it.
The ladder comes from the company's own settings, so no role names are written in code.
"""
from app.policy import PolicyConfig


def _norm(role: str) -> str:
    return role.strip().upper()


def management_ladder(config: PolicyConfig) -> list[str]:
    """Approver roles of the amount tiers, lowest band first, without repeats."""
    ladder: list[str] = []
    for tier in config.approval_tiers:
        if tier.approver_role and _norm(tier.approver_role) not in ladder:
            ladder.append(_norm(tier.approver_role))
    return ladder


def roles_user_can_decide(user_role: str, config: PolicyConfig | None) -> set[str]:
    """The required roles whose items this user may decide.

    Without valid company settings only the exact role counts (fail closed: no ladder).
    """
    role = _norm(user_role)
    allowed = {role}
    if config is None:
        return allowed
    ladder = management_ladder(config)
    if role in ladder:
        allowed.update(ladder[: ladder.index(role)])
    return allowed
