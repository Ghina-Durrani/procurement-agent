# Decision Log

The single living record of technical and scope decisions. It continues the log in `TECH_STACK_AND_DECISIONS.md` (§11 of that file is now frozen; update this file instead). Rationale and background for the original choices remain in `TECH_STACK_AND_DECISIONS.md`.

Rules: never silently promote PROPOSED → DECIDED. To change a decision, add a dated note with reason, alternatives considered, and impact. Labels: `CLAUDE.md` §6.

## Decisions

| ID | Decision | Status | Notes |
|---|---|---|---|
| D-001 | Python + FastAPI backend | DECIDED · IN REPO | FastAPI 0.159, Pydantic 2 |
| D-002 | React + TypeScript + Vite frontend | DECIDED · IN REPO | React 19, Vite 8, TS strict |
| D-003 | PostgreSQL relational database | DECIDED | Container is IN REPO (Postgres 16) |
| D-004 | Docker Compose for local PostgreSQL only | DECIDED · IN REPO | API and frontend run on the host. Named volume `pgdata`, healthcheck, host port `127.0.0.1:5433` |
| D-005 | SQLAlchemy 2.x + psycopg 3 driver | DECIDED · IN REPO | SQLAlchemy 2.1, psycopg 3.3. Connection layer is `backend/app/db/session.py` |
| D-005b | Alembic for migrations | PROPOSED | Added with the schema (D-037), not merged yet. `backend/alembic/env.py` connects through `app.db.session`, so the app and the migrations use the same settings. Becomes DECIDED · IN REPO once merged and tested. Alembic does not detect new CHECK constraints on existing tables, so read every migration by hand |
| D-006 | Modular monolith, no microservices | DECIDED | |
| D-007 | Deterministic policy engine separate from the LLM | CONFIRMED | Core of the research design |
| D-008 | LLM provider / model | OPEN | Behind a provider-agnostic adapter; compare cost, structured output, latency, data policy |
| D-009 | LangChain / LangGraph | OPEN, not needed initially | Plain Python workflow first |
| D-010 | RAG / vector database | DEFERRED | Explicit rules in PostgreSQL suffice for the first slice |
| D-011 | Authentication library and token design | OPEN | Must include secure password hashing and server-side RBAC |
| D-012 | Hosting / deployment | OPEN | Local-first demo |
| D-013 | Exact FYP-I feature boundary | PROPOSED | Core slice in `FYP_MASTER_CONTEXT.md` §6; needs supervisor confirmation (Q-001) |
| D-014 | Evaluation benchmark: synthetic, labelled | PROPOSED | Inspect BPI 2019 schema first; keep held-out test set separate |
| D-015 | UI library: shadcn/ui (style `radix-nova`, neutral base, Radix primitives, sonner toasts, lucide icons), with components copied into `src/components/ui/` | DECIDED · IN REPO | Merged 2026-11-10. `components/ui` is excluded from lint and format (generated code). The outcome colours stay in `styles/tokens.css` (D-016) |
| D-016 | Tailwind CSS 4 with design tokens in `styles/tokens.css` | DECIDED · IN REPO | No raw hex in components |
| D-017 | Frontend libraries: TanStack Query, React Hook Form + zod, react-router, lucide-react, class-variance-authority | DECIDED · installed; usage patterns PROPOSED | Not yet used by any feature |
| D-018 | Frontend tests: Vitest + React Testing Library + jest-dom + MSW | DECIDED · IN REPO | MSW handlers not written yet |
| D-019 | Frontend quality gates: ESLint (strict custom rules), Prettier, Husky + lint-staged | DECIDED · IN REPO | Bans `any`, `dangerouslySetInnerHTML`, direct `fetch`, deep feature imports |
| D-020 | API types generated from backend OpenAPI (`openapi-typescript`, `npm run gen:api`) | DECIDED · IN REPO | Backend is the contract source |
| D-021 | Settings via pydantic-settings; secrets as `SecretStr`; docs/OpenAPI only in development | DECIDED · IN REPO | Covered by tests |
| D-022 | Team commits directly to `main`; no feature branches | DECIDED | PR #1 was an exception. Compensate with local checks; see D-027 |
| D-023 | API conventions (Handbook §3): `/api/v1`, snake_case, uppercase enums, decimal-string money, UTC ISO timestamps, one error envelope | PROPOSED | Approve before the first feature endpoint |
| D-024 | Backend layout and dependency direction (Backend Guide §3) | PROPOSED | `policy/` has no I/O and no LLM imports |
| D-025 | Split `requirements.txt` (runtime) / `requirements-dev.txt`, saved as UTF-8, direct deps only | PROPOSED, partly done | The file is now UTF-8. It is still one full `pip freeze`; the split is not done |
| D-026 | Add `ruff` (+ `mypy`) for the backend | PROPOSED | |
| D-027 | Add minimal CI (backend pytest; frontend typecheck/lint/test/build) | PROPOSED | Useful because of D-022 |
| D-028 | Urgency detection: the LLM finds urgency evidence (quoted text); deterministic code computes the proposed priority (normal / high priority / emergency). Priority is a proposal only and never approves or bypasses policy | DECIDED | Agreed by the project owner in chat. Consistent with D-007. Exact enum strings to be fixed with the schema (Q-006) |
| D-029 | Clarification loop: the system asks the requester about missing or unclear details, maximum 2 rounds; after that, or on low-confidence/failed extraction, route to a human (fail closed) | DECIDED | Agreed by the project owner in chat. The round limit of 2 is to be confirmed in development (D-031) |
| D-030 | Input language for Module 1 is English only (no Roman Urdu); synthetic data only | DECIDED | Agreed by the project owner in chat. Replaces the earlier Roman Urdu idea |
| D-031 | Urgency thresholds (working values: 7 days and 3 days to deadline) and the clarification round limit (working value: 2) | OPEN | To be confirmed during development, not with the supervisor now. Do not treat the working values as final |
| D-032 | Policy rules POL-001 to POL-009 plus POL-900 (fail closed), the three checkpoints (`INTAKE`, `PRE_PO`, `APPROVAL`) and precedence (`BLOCK` > `HUMAN_REVIEW` > `CONTINUE`), as defined in `docs/POLICY_RULES.md` | DECIDED | Approved by the team on 2026-11-08. Answers Q-007. Implemented in `backend/app/policy/`. All amounts and lists remain demo values (OPEN) |
| D-033 | Insufficient budget (POL-007) returns `BLOCK` | DECIDED | Decided by Maira (policy engine owner), 2026-11-08 |
| D-034 | Emergencies do not waive the quotation rule (POL-003): too few quotes gives `HUMAN_REVIEW` by a Procurement Officer | DECIDED | Decided by Maira (policy engine owner), 2026-11-08. Consistent with D-007 and D-028 |
| D-035 | Extraction reliability is judged by `extraction_status` (schema validation result), not by a model-reported confidence score | DECIDED | Decided by Maira (policy engine owner), 2026-11-08. This is how "low-confidence" in D-029 is measured by the policy engine |
| D-036 | Quantity is a required detail for every request, including services | DECIDED | Decided by Maira (policy engine owner), 2026-11-08 |
| D-037 | Database schema, 19 tables in 6 migrations. Core (0001-0002): `organizations`, `users`, `procurement_requests`, `extractions`, `clarifications`, `policy_configs`, `policy_evaluations`, `audit_events`. Reference data (0003): `suppliers`, `supplier_categories`, `budgets`. Approvals (0004): `approvals`. Sourcing (0005): `rfqs`, `rfq_suppliers`, `documents`, `quotations`, `quotation_items`, `supplier_evaluations`. Ordering (0006): `purchase_orders`. Rules: every company-owned row has `organization_id` and foreign keys force both rows into the same organization; money is `NUMERIC(14,2)`; enums are text plus a CHECK and the engine's own enums are imported from `app.policy.types`; role names are plain text; `currency` has no default so a missing currency still reaches POL-900; `policy_evaluations` and `audit_events` are append-only (trigger); policy settings are versioned rows; a purchase order must match its quotation exactly and cannot exceed the request's approved amount (foreign keys and a CHECK); a quotation waiting for verification or badly extracted cannot be selected; a budget cannot be over-committed | PROPOSED | Drafted by Ghina with Claude, 2026-11-14, as the answer to Q-006. Tables for stages after 0002 follow D-038 |
| D-038 | The schema models supplier sourcing, RFQs, quotations, supplier evaluation, budgets (finance check) and purchase orders, although CLAUDE.md lists them as deferred or optional | PROPOSED | Ghina asked for the full-project schema on 2026-11-14. This covers the schema only. Building those features still depends on Q-001 (scope and ownership), and the team should confirm it |

## Open questions (need a person to decide)

| ID | Question | Blocks |
|---|---|---|
| Q-001 | Which of the broader seven-agent vision is in FYP-I scope, and which teammate owns which module? (`app/main.py` already says "Module 1 — Requirement Extraction".) Confirm with the supervisor | Planning, schema scope |
| Q-002 | Approve the error envelope (D-023) and update `api-client.ts` + backend handlers together. Today the client expects `message`; FastAPI sends `detail` | First endpoint |
| Q-003 | CORS allow-list for the dev frontend origin (`localhost:5173`, `127.0.0.1:5173`), configured via `Settings` | First browser→API call |
| Q-004 | Authentication design (D-011) and role model | Any protected endpoint |
| Q-005 | Pin the Python version (and Node version) the team uses; add to the Handbook | Reproducible setup |
| Q-006 | Database schema: entities, columns, relationships, tenancy | Database tasks |
| Q-008 | LLM provider and model (D-008) | Extraction agent |
| Q-009 | Triage 7 moderate `npm audit` findings | Security hygiene |

## Change log

| Date | Change | By |
|---|---|---|
| 2026-11-05 | Created from repo audit at commit `8f5b114`; added D-016…D-027, Q-001…Q-009 | Claude (via Haya) |
| 2026-11-05 | Added D-028…D-031 (urgency detection, clarification loop, English only, thresholds OPEN) to align with Module 1 requirements agreed by the project owner | Claude (via Ghina) |
| 2026-11-05 | Q-007 draft added in `docs/POLICY_RULES.md` (rules POL-001…POL-009, POL-900; all PROPOSED, demo values OPEN) | Maira Qazi |
| 2026-11-08 | Policy rules approved: added D-032…D-036, closed Q-007 | Maira Qazi |
| 2026-11-10 | Merged shadcn/ui and the database layer: D-005 split into D-005 (DECIDED · IN REPO) and D-005b (Alembic, PROPOSED); D-015 resolved (shadcn/ui); D-025 partly done | Claude (via Haya) |
| 2026-11-14 | Drafted the full schema (D-037, D-038); updated D-005b (Alembic); Q-006 answered in a first version, to be approved | Claude (via Ghina) |
