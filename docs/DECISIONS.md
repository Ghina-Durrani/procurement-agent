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
| D-005 | SQLAlchemy 2.x + Alembic; psycopg 3 driver | PROPOSED | Not installed yet. Needed for the database-connection task |
| D-006 | Modular monolith, no microservices | DECIDED | |
| D-007 | Deterministic policy engine separate from the LLM | CONFIRMED | Core of the research design |
| D-008 | LLM provider / model | OPEN | Behind a provider-agnostic adapter; compare cost, structured output, latency, data policy |
| D-009 | LangChain / LangGraph | OPEN, not needed initially | Plain Python workflow first |
| D-010 | RAG / vector database | DEFERRED | Explicit rules in PostgreSQL suffice for the first slice |
| D-011 | Authentication library and token design | OPEN | Must include secure password hashing and server-side RBAC |
| D-012 | Hosting / deployment | OPEN | Local-first demo |
| D-013 | Exact FYP-I feature boundary | PROPOSED | Core slice in `FYP_MASTER_CONTEXT.md` §6; needs supervisor confirmation (Q-001) |
| D-014 | Evaluation benchmark: synthetic, labelled | PROPOSED | Inspect BPI 2019 schema first; keep held-out test set separate |
| D-015 | UI library | PARTLY RESOLVED | Tailwind 4 chosen (D-016). Primitive library for `components/ui` still OPEN |
| D-016 | Tailwind CSS 4 with design tokens in `styles/tokens.css` | DECIDED · IN REPO | No raw hex in components |
| D-017 | Frontend libraries: TanStack Query, React Hook Form + zod, react-router, lucide-react, class-variance-authority | DECIDED · installed; usage patterns PROPOSED | Not yet used by any feature |
| D-018 | Frontend tests: Vitest + React Testing Library + jest-dom + MSW | DECIDED · IN REPO | MSW handlers not written yet |
| D-019 | Frontend quality gates: ESLint (strict custom rules), Prettier, Husky + lint-staged | DECIDED · IN REPO | Bans `any`, `dangerouslySetInnerHTML`, direct `fetch`, deep feature imports |
| D-020 | API types generated from backend OpenAPI (`openapi-typescript`, `npm run gen:api`) | DECIDED · IN REPO | Backend is the contract source |
| D-021 | Settings via pydantic-settings; secrets as `SecretStr`; docs/OpenAPI only in development | DECIDED · IN REPO | Covered by tests |
| D-022 | Team commits directly to `main`; no feature branches | DECIDED | PR #1 was an exception. Compensate with local checks; see D-027 |
| D-023 | API conventions (Handbook §3): `/api/v1`, snake_case, uppercase enums, decimal-string money, UTC ISO timestamps, one error envelope | PROPOSED | Approve before the first feature endpoint |
| D-024 | Backend layout and dependency direction (Backend Guide §3) | PROPOSED | `policy/` has no I/O and no LLM imports |
| D-025 | Split `requirements.txt` (runtime) / `requirements-dev.txt`, saved as UTF-8, direct deps only | PROPOSED | Current file is a UTF-16 `pip freeze` |
| D-026 | Add `ruff` (+ `mypy`) for the backend | PROPOSED | |
| D-027 | Add minimal CI (backend pytest; frontend typecheck/lint/test/build) | PROPOSED | Useful because of D-022 |

## Open questions (need a person to decide)

| ID | Question | Blocks |
|---|---|---|
| Q-001 | Which of the broader seven-agent vision is in FYP-I scope, and which teammate owns which module? (`app/main.py` already says "Module 1 — Requirement Extraction".) Confirm with the supervisor | Planning, schema scope |
| Q-002 | Approve the error envelope (D-023) and update `api-client.ts` + backend handlers together. Today the client expects `message`; FastAPI sends `detail` | First endpoint |
| Q-003 | CORS allow-list for the dev frontend origin (`localhost:5173`, `127.0.0.1:5173`), configured via `Settings` | First browser→API call |
| Q-004 | Authentication design (D-011) and role model | Any protected endpoint |
| Q-005 | Pin the Python version (and Node version) the team uses; add to the Handbook | Reproducible setup |
| Q-006 | Database schema: entities, columns, relationships, tenancy | Database tasks |
| Q-007 | Initial policy rules: rule types, thresholds (sample/demo values), precedence | Policy engine |
| Q-008 | LLM provider and model (D-008) | Extraction agent |
| Q-009 | Triage 7 moderate `npm audit` findings | Security hygiene |

## Change log

| Date | Change | By |
|---|---|---|
| 2026-11-05 | Created from repo audit at commit `8f5b114`; added D-016…D-027, Q-001…Q-009 | Claude (via Haya) |
