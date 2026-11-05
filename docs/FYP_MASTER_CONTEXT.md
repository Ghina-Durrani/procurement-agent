# FYP Master Context

Single reference for *what we are building and why*. Terminology here is the team's vocabulary: use these exact terms in code, tests, UI text, and the report.

Labels: see `CLAUDE.md` §6.

## 1. Identity

**Working title:** Policy-Aware AI Procurement Agent — Intelligent Sourcing, Compliance, and Human-in-the-Loop Decision Making.

The system takes procurement requests written informally (free text, email/WhatsApp-style messages), extracts structured requirements, validates them, applies **configurable company policies with a deterministic engine**, routes uncertain or approval-required cases to authorized humans, and records every decision in an audit trail. In FYP-I it recommends or prepares the next step only; it does not place orders or pay anything.

Different organizations configure different rules. Each organization has isolated users, requests, policies, and data.

## 2. Research question and evaluation (CONFIRMED)

> Can deterministic policy enforcement and systematic human-review routing improve the reliability of an LLM-based procurement workflow compared with an LLM-only baseline?

- **System A:** LLM-only baseline. The policy text is in the prompt; no external policy engine; no defined escalation path.
- **System B:** same (or comparable) LLM + deterministic validation + policy engine + human-review routing.
- Both run on the **same labelled cases**, with a **held-out test set** never used to tune prompts or rules.

**Primary metrics:** (1) extraction accuracy, (2) policy violation / false-allow rate, (3) human-escalation precision and recall. Optional: latency, API cost.

**Contribution claim:** we measure the effect of policy-as-code guardrails + review routing on reliability. We do **not** claim that procurement agents or LLM extraction are novel. Every research-gap claim must cite a real, verified paper. Never invent papers, results, datasets, or citations. A small synthetic benchmark does not prove real-world effectiveness; state limitations honestly. A model's self-reported confidence is not calibrated unless we evaluate it.

## 3. Core workflow (CONFIRMED)

1. Accept a request, assign a unique ID, preserve the original text unchanged.
2. **Extraction (LLM)** → structured fields, with source evidence where feasible.
3. **Validation** (code) → missing, invalid, ambiguous, or conflicting information.
4. **Policy engine** (code) → apply configurable rules.
5. Outcome is exactly one of: `CONTINUE`, `BLOCK`, `HUMAN_REVIEW`.
6. Ask for clarification or route to an authorized reviewer when needed.
7. Record request, extraction, policy version, triggered rules, outcome, reviewer actions, timestamps.
8. Present a recommendation / next step. No real purchases or payments.

## 4. Design principles (CONFIRMED)

- The LLM is never the sole authority for policy-sensitive decisions.
- Missing or unknown information is never invented. Preserve evidence from the original text.
- **Urgency, priority, and authorization are different concepts.** Urgency alone neither requires approval nor bypasses policy. An emergency exception must be an explicit rule with explicit approval.
- Budget approval does not satisfy every procurement rule. A request within budget can still violate supplier, quotation, or approval rules.
- Policy checks and calculations are deterministic code. RAG, if ever used, only retrieves text; retrieval is not authorization.
- Pretrained LLM + structured prompting first. Fine-tuning only if evidence demands it.
- Do not assume `total ÷ quantity` equals a stated unit price (taxes, delivery may be included).
- Small, credible end-to-end vertical slice. No separate AI agent for every small task.
- Do not assume public-sector procurement rules (e.g. PPRA) apply to private companies.

## 5. Actors and terms (use these exact names)

| Term | Meaning |
|---|---|
| Requester | Submits requests |
| Procurement Officer | Handles procurement work and clarifications |
| Approver / Manager | Makes authorized approval decisions |
| Policy Administrator | Configures policy rules |
| System Administrator | Manages the system |
| Organization | The tenant. Owns users, requests, policies |
| Policy engine | Deterministic software component (not an AI agent, not a human actor) |
| Extraction agent | LLM-based component that proposes structured fields |
| Policy outcome | `CONTINUE` \| `BLOCK` \| `HUMAN_REVIEW` (exact uppercase strings everywhere) |
| Rule ID | Stable identifier of a policy rule, returned with every outcome |
| Policy version | Snapshot of rules used for an evaluation, stored so decisions are reproducible |
| Audit event | Append-only record of who/what did what, when, and why |

## 6. Scope

**Core (FYP-I target, December 2026) — one reliable vertical slice:**
submit free-text request → store original → extract → validate → policy outcome with rule IDs and reasons → review queue (approve / reject / request clarification) → audit history → minimal React UI → small labelled evaluation set comparing System A vs System B.

**Deferred unless the core is stable and scope is re-confirmed:** real WhatsApp/email integration; automatic supplier outreach/RFQ sending; PDF/spreadsheet/image quote extraction; supplier discovery/ranking and quote comparison; Finance Agent integration; purchase-order generation / ERP; production-grade multi-tenant administration; RAG/vector DB; fine-tuning; multi-agent frameworks; analytics dashboards.

**Potential extensions (NOT confirmed requirements):** supplier sourcing and RFQ management, quotation analysis, finance/budget checks, PO preparation.

> **OPEN (see `DECISIONS.md` Q-001):** the project description also lists a broader seven-agent vision (requirement extraction, supplier sourcing, RFQ, quotation processing, supplier evaluation, finance, PO). The team must confirm with the supervisor which of these are in FYP-I scope, and which teammate owns which module. Until confirmed, build only the core above.

## 7. Data separation (CONFIRMED)

Keep these three things distinct, in code and in the database:

- **A. Application records**: organizations, users, requests, extractions, evaluations, approvals, audit events.
- **B. Labelled evaluation cases**: `case_id`, `request_text`, `expected_fields_json`, `expected_missing_fields`, `expected_ambiguities`, `expected_conflicts`, `expected_policy_decision`, `expected_triggered_rules`, `case_category`. Never mixed into application tables.
- **C. Configurable policy rules**: versioned. Configuration is separate from evaluation logic.

Synthetic data is acceptable; document its limitations. BPI Challenge 2019 is a purchase-order event log: inspect its real schema before using it, and do not assume it has informal text or policy labels. Other background sources: Open Contracting Data Registry, Global Public Procurement Database, PPRA rules (context only).

Likely extraction fields: item description, quantity, unit, specifications, estimated unit price and total, currency, delivery deadline/location, optional urgency, business justification, preferred supplier, mentioned supplier restrictions, missing fields, ambiguities, conflicts, source evidence.

## 8. Requirements summary

**Functional:** accept and preserve requests; extract structured fields; detect missing/invalid/ambiguous/conflicting info; authorized policy configuration with versioning; evaluate policies with rule IDs and reasons; route incomplete cases for clarification; route approval-required cases to authorized reviewers; record approval/rejection with reviewer identity, timestamp, rationale; keep audit trail and policy-version snapshot; evaluate System B against System A.

**Non-functional:** reproducible deterministic decisions; explainability and traceability; security, role-based access, privacy, organization-level isolation; maintainability and configurable policies; usability, testability, measurable performance.

## 9. Core entities (design target, not yet implemented)

Organization, User, ProcurementRequest, ExtractedRequestDetails, PolicyRule, PolicyEvaluation, Approval, AuditEvent. Optional only if in scope: Supplier, Quotation, QuotationLineItem, RequestLineItem.

Typed columns for important fields (quantity, currency, deadlines, statuses, relationships); JSON only for flexible supplemental fields. The exact schema is a pending decision (see `PROJECT_STATUS.md`).
