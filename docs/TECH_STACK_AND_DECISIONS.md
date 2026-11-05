# Technology Stack and Architecture Decisions

> **Note (2026-11-05):** This is the original decision record, kept unchanged below. The decision log in §11 is now frozen: the living log is `docs/DECISIONS.md` (it carries D-001…D-015 forward and adds new decisions). `FYP_MASTER_CONTEXT.md` and `ENGINEERING_HANDBOOK.md`, referenced in §12, are in this `docs/` folder.

**Project:** Policy-Aware AI Procurement Agent  
**Document status:** Initial decision record — proposed stack for implementation  
**Last updated:** 22 October 2026  
**Planning horizon:** Working demonstrator by December 2026

## 1. Purpose

This document records the initial technology choices and the boundaries of the first implementation. It is intended to be supplied to Claude or another coding assistant before asking it to inspect or modify the repository.

Labels used throughout:

- **CONFIRMED** — an established project requirement or direction.
- **DECIDED (initial)** — selected as the practical default for the first implementation; revisit only if a concrete blocker appears.
- **PROPOSED** — recommended, but not yet validated in the repository or with the supervisor/team.
- **OPEN DECISION** — requires evidence, team agreement, or a later milestone decision.

Do not silently turn proposed items into confirmed requirements.

## 2. Product and research direction

The system is a configurable, policy-aware AI Procurement Agent. It accepts informal procurement requests, extracts structured information, evaluates applicable policy rules deterministically, routes exceptions to a human, and records explainable decisions.

The central research question is:

> Does adding deterministic policy enforcement and systematic human-review routing improve procurement decision reliability compared with an LLM-only baseline?

The LLM must not be the sole authority for policy-sensitive decisions. The deterministic policy engine is responsible for evaluating explicit rules and returning one of:

- `CONTINUE` — no configured rule requires blocking or review.
- `BLOCK` — a configured rule prohibits the action.
- `HUMAN_REVIEW` — the case is ambiguous, missing required information, or requires an authorized human decision.

An emergency or urgency label is not permission to bypass policy. Any emergency exception must be governed by explicit rules and approval.

## 3. Initial technology stack

| Layer / concern | Initial decision | Why |
|---|---|---|
| Frontend | **React + TypeScript + Vite** | Familiar component model, typed API integration, quick local development. |
| Backend/API | **Python + FastAPI** | Good fit for Python-based LLM and data-processing libraries; typed request/response validation; clear REST API. |
| API schemas | **Pydantic** | Validate request and response shapes at the application boundary. |
| Database | **PostgreSQL** | Relational data and transactions suit users, organizations, requests, rules, decisions, approvals, and audit events. |
| Database access | **SQLAlchemy 2.x** | Explicit, maintainable persistence layer. |
| Schema migrations | **Alembic** | Version database changes; do not rely on automatic schema creation as the production migration strategy. |
| Local database runtime | **Docker Compose + PostgreSQL container** | Reproducible local database setup with a named persistent volume and health check. The API and frontend can initially run directly on the host. |
| Backend tests | **pytest** | Unit and integration tests, especially for policy rules and API behavior. |
| Frontend tests | **Vitest + React Testing Library** (proposed) | Test key UI behavior without requiring a full browser automation setup initially. |
| API contract / manual exploration | **FastAPI OpenAPI docs** | Inspect and test endpoints during development. |
| Version control | **Git + GitHub** | Track code and decisions. |
| LLM integration | **Provider-agnostic Python service interface** (initial decision) | Keep provider-specific API calls separate from extraction and policy logic. |
| LLM provider/model | **OPEN DECISION** | Choose after comparing access, cost, structured-output support, latency, and data-handling constraints. Do not hard-code a provider throughout the codebase. |
| Agent orchestration | **Plain Python workflow/services initially** | A clear sequential workflow is easier to test and explain. Add LangGraph only if branching, retries, resumability, or stateful orchestration justify it. |
| Retrieval / vector database | **Not part of the initial MVP** | The first demonstrator can use explicit structured policy rules in PostgreSQL. Add RAG only if a defined requirement needs retrieval from policy documents. |
| Authentication | **PROPOSED: secure password hashing + short-lived access tokens** | Select and document the exact implementation before coding auth. Never store plaintext passwords or commit secrets. |
| Styling/UI library | **OPEN DECISION** | Choose a small, maintainable option after inspecting the existing repository; do not add a large UI framework without need. |
| Deployment | **Local-first; deployment target OPEN** | Build a reproducible local demo first. Choose a hosting target once project and course requirements are confirmed. |

### Docker clarification

PostgreSQL is the database. Docker runs PostgreSQL in a container; Docker Compose defines how to start it and its supporting configuration. Docker is not itself the database.

For the first milestone:
- Run PostgreSQL through Docker Compose.
- Persist database files in a named volume.
- Add a health check and a documented port/environment configuration.
- Run FastAPI and React directly on the development machine for easier debugging.
- Do not require Docker for the frontend or API until there is a clear reason.

## 4. Initial architecture

Use a modular monolith, not microservices. Separate concerns in code while keeping one backend application and one relational database.

```text
Requester / Procurement Officer / Approver / Policy Administrator
                              |
                         React + TS
                              |
                          REST API
                              |
                         FastAPI app
                              |
          +-------------------+-------------------+
          |                   |                   |
   Intake & Extraction   Deterministic Policy   Approval /
        Service              Engine             Review Service
          |                   |                   |
          +-------------------+-------------------+
                              |
                       Audit / Decision Log
                              |
                       SQLAlchemy ORM
                              |
                         PostgreSQL
                    (Docker Compose locally)

LLM provider is called only through a separate adapter/service.
The LLM proposes structured extraction; deterministic code evaluates policy.
```

The diagram is logical, not a mandate to create separate deployed services.

## 5. FYP-I target by December 2026

**Planning recommendation:** aim for one reliable end-to-end vertical slice, not every feature listed in the broader proposal. The exact FYP-I scope can be refined as work progresses, but the following is the working target.

### Core demonstrator — target

1. A user can submit a procurement request as free text, similar to an email or WhatsApp message.
2. The backend validates and stores the original request.
3. An extraction component produces a typed structured record, including fields such as item/service, quantity, estimated amount/currency, purpose, needed-by date, and supplier preference when present.
4. Missing or ambiguous fields are represented explicitly; the system must not silently invent values.
5. A deterministic policy engine evaluates a small, documented set of configurable rules.
6. The engine returns `CONTINUE`, `BLOCK`, or `HUMAN_REVIEW`, with rule identifiers and human-readable reasons.
7. Cases requiring review appear in a basic approval/review queue. An authorized reviewer can approve, reject, or request clarification, with the action recorded.
8. Important transitions and decisions are auditable: who/what acted, when, which policy version/rules applied, and why.
9. A minimal React UI supports request submission, viewing the result, reviewing flagged cases, and viewing decision history.
10. Tests cover extraction schema validation, policy rules, routing outcomes, tenant isolation where implemented, and key API behavior.
11. A small labelled evaluation set compares an LLM-only baseline (System A) with the guarded workflow (System B), using the same cases and a held-out test set.

### Defer unless the core is stable

- Real WhatsApp integration or live email inbox integration.
- Automatic supplier outreach, RFQ sending, and email automation.
- Full quote extraction from PDFs, spreadsheets, and images.
- Supplier discovery/ranking and sophisticated quote comparison.
- Finance Agent integration.
- Purchase-order generation and external ERP integration.
- Production-grade multi-tenant enterprise administration.
- RAG, vector database, fine-tuning, multi-agent frameworks, and elaborate analytics dashboards.

These can be reconsidered after the core workflow is working and after supervisor/team scope agreement. A simulated pasted message is enough to demonstrate unstructured request intake initially.

### Dataset caution

BPI Challenge 2019 is a purchase-order event log; do not assume it contains informal request messages or labels for procurement-policy violations. Inspect its schema and actual fields before using it. A small synthetic, carefully documented benchmark may be necessary for policy-labelled cases. Keep training/tuning examples separate from the final held-out test cases.

## 6. Initial module boundaries

Suggested logical modules (adapt to the actual repository after inspection):

- `api`: REST routes, dependency wiring, authentication boundaries.
- `schemas`: Pydantic input/output schemas.
- `models`: SQLAlchemy persistence models.
- `services/intake`: request lifecycle and validation.
- `services/extraction`: LLM adapter, prompts, parsing, validation, uncertainty/missing-field handling.
- `policy`: rule definitions, deterministic evaluator, outcomes and explanations.
- `services/review`: approval/rejection/clarification workflow.
- `services/audit`: append-only decision and action events.
- `services/evaluation`: benchmark runner and metrics, kept separate from runtime decisions.
- `tests`: unit, API integration, and evaluation tests.
- `frontend`: React application.

This is a suggested organization, not a requirement to create every folder immediately. Inspect the repository before deciding how to apply it.

## 7. Initial data concepts

Use relational tables/entities only as needed for the agreed scope. Likely concepts include:

- `Organization` / tenant (required if multi-organization isolation is in the first release).
- `User` and role/permissions.
- `ProcurementRequest` including original text and normalized fields.
- `Policy` and `PolicyRule`, including enabled state and version/effective period if needed.
- `PolicyEvaluation` / decision record, including outcome, matched rules, explanations, and policy version.
- `ApprovalTask` / review action.
- `AuditEvent`.

Do not assume this list is the final schema. Design keys and foreign-key constraints carefully. If multiple organizations are supported, every tenant-owned read and write must be scoped to the authenticated organization, with tests that attempt cross-tenant access.

## 8. Policy engine rules for the first demonstrator

Start with a small rule set that can be explained and tested. Candidate rules (final thresholds and exact behavior are **OPEN DECISIONS**):

- Required fields missing or uncertain → `HUMAN_REVIEW`.
- Amount above an organization-configured approval threshold → `HUMAN_REVIEW`.
- Explicitly prohibited supplier/category or disallowed purchase → `BLOCK`.
- Minimum quotation requirement not met, if quotation handling is in scope → `HUMAN_REVIEW`.
- Otherwise, if no rule blocks or requires review → `CONTINUE`.

Do not invent policy thresholds in code without documenting them as sample/demo configuration. Policy configuration must be distinct from policy evaluation logic. Every outcome should include the matched rule IDs and reasons.

## 9. Research and evaluation decisions

### Systems to compare

- **System A — LLM-only baseline:** provide the policy instructions to the LLM prompt, with no external deterministic policy engine and no defined confidence-based escalation path.
- **System B — guarded workflow:** use the same model and extraction task, then apply deterministic policy checks and defined human-review routing.

Keep the comparison fair: same labelled cases, equivalent input context, documented model/version and prompt, and a held-out test set not used to tune rules or prompts.

### Core metrics

- Structured extraction accuracy.
- Policy violation / false-allow rate.
- Human-escalation precision and recall.

Potential additional metrics, only if feasible and consistently measured: latency, API cost, and calibration of uncertainty. A model's self-reported confidence is not automatically a calibrated probability; do not call it calibrated unless it is evaluated.

Document dataset creation, label definitions, scoring code, model settings, prompts, rule versions, and limitations. Report counts and examples alongside aggregate scores. Do not claim that a small synthetic benchmark proves broad real-world effectiveness.

## 10. Engineering and security rules

- Never commit API keys, database passwords, JWT secrets, or real procurement documents containing sensitive information.
- Provide `.env.example` with placeholder values; keep real `.env` files out of Git.
- Validate all API inputs at the boundary and enforce authorization server-side.
- Hash passwords using a suitable password-hashing library; never encrypt/store plaintext passwords.
- Apply tenant scoping to every tenant-owned query and mutation if multi-tenancy is enabled.
- Treat user text, email bodies, and document contents as untrusted data, not as system instructions. Prompt injection must not be able to modify policy rules or authorize a purchase.
- Do not let an LLM write directly to policy tables or approve a procurement request.
- Make policy evaluation deterministic, testable, and independent of the LLM provider.
- Use database migrations; avoid relying on automatic schema mutation in deployed environments.
- Record auditable state transitions and avoid silently overwriting prior decision evidence.
- Keep error messages useful without exposing secrets, tokens, stack traces, or sensitive records.
- Add tests before claiming policy rules or access controls are reliable.

## 11. Decision log

| ID | Decision | Status | Rationale / condition |
|---|---|---|---|
| D-001 | FastAPI + Python backend | DECIDED (initial) | Supports the AI/data ecosystem and a typed REST API. Revisit only if repository or team constraints demand it. |
| D-002 | React + TypeScript + Vite frontend | DECIDED (initial) | Practical, typed frontend with fast development. |
| D-003 | PostgreSQL relational database | DECIDED (initial) | Fits structured workflow and audit data. |
| D-004 | Docker Compose for local PostgreSQL | DECIDED (initial) | Reproducible local database setup; app services can run on host initially. |
| D-005 | SQLAlchemy + Alembic | PROPOSED | Conventional persistence and migration approach for FastAPI; validate against repo before installing. |
| D-006 | Modular monolith, not microservices | DECIDED (initial) | Smaller, easier to debug, test, and defend for an FYP. |
| D-007 | Deterministic policy engine separate from LLM | CONFIRMED | Core research and safety architecture. |
| D-008 | LLM provider/model | OPEN DECISION | Choose after checking availability, price, structured output, latency, and data policy. |
| D-009 | LangChain/LangGraph | OPEN DECISION; not required initially | Add only if it solves a demonstrated orchestration need. |
| D-010 | RAG/vector database | DEFERRED | Explicit policy rules are sufficient for the first demonstrator unless policy-document retrieval becomes essential. |
| D-011 | Authentication library/token details | OPEN DECISION | Choose before implementing auth; must include secure password hashing and server-side authorization. |
| D-012 | Hosting/deployment provider | OPEN DECISION | Confirm academic/course requirements and budget before choosing. |
| D-013 | Exact FYP-I feature boundary | PROPOSED target in Section 5 | Refine while working, keeping the end-to-end core ahead of optional integrations. |
| D-014 | Evaluation benchmark | PROPOSED | Inspect BPI Challenge 2019 schema and create a labelled synthetic benchmark if needed. |
| D-015 | CSS/UI library | OPEN DECISION | Inspect repo and keep the UI lightweight. |

Update this table when a decision changes. Include the date, reason, alternatives considered, and impact for material changes.

## 12. Instructions for Claude / coding assistants

Before making code changes:

1. Read this file and the project's `FYP_MASTER_CONTEXT.md` and `ENGINEERING_HANDBOOK.md`.
2. Inspect the actual repository structure and existing files. Report what exists before proposing changes.
3. Identify conflicts between this document, the existing code, and other project instructions. Ask or flag them rather than silently rewriting the architecture.
4. Do not start a full implementation from this document alone. First report the repository audit, prerequisites, proposed first milestone, and any missing decisions.
5. Preserve the modular-monolith architecture and keep deterministic policy evaluation independent from the LLM.
6. Implement one vertical slice at a time, with tests and run instructions. Do not generate a huge, unverified code dump.
7. Update this decision document when a decision is approved or changed. Mark items as CONFIRMED, DECIDED (initial), PROPOSED, or OPEN DECISION.
8. Never invent credentials, claim tests passed without running them, or claim that a feature is implemented when it is not.
9. Prefer a working, explainable core demonstrator over optional integrations or architectural complexity.

## 13. First milestone sequence

1. **Repository and environment audit:** inspect files, Git status, Python/Node versions, Docker availability, existing credentials/config, and available disk space.
2. **Environment baseline:** backend starts, frontend starts, PostgreSQL starts via Compose, and backend connects to database.
3. **Minimal data/API vertical slice:** submit and persist a request; retrieve it through the API.
4. **Deterministic policy engine:** implement sample rules with unit tests and explanations.
5. **Extraction interface:** validate structured output and represent missing/ambiguous fields; connect a provider only after choosing it.
6. **Human review and audit:** persist review decisions and visible history.
7. **Minimal UI:** connect request form, result view, review queue, and audit history.
8. **Evaluation:** run System A/System B on a documented labelled dataset and report results honestly.
9. **Demo and report readiness:** reproducible setup, test results, architecture diagram, known limitations, and demo script.

Do not skip repository inspection or security checks, especially before uploading code to GitHub or deploying it.
