# Project Status

Living progress record. Every Claude updates this when a task changes state. Do not mark a task Done unless its acceptance criteria and tests are satisfied and the checks were actually run.

**Last audit:** 2026-11-10 · `main` at `a72fa12` plus the merge of `feat/frontend-shadcn-base`. Checks were run in a cloud sandbox, not on teammates' machines. The database test was run against a temporary local PostgreSQL 16, **not** the Docker Compose container.

## 1. Milestone sequence (from `TECH_STACK_AND_DECISIONS.md` §13)

| # | Milestone | State | Evidence / notes |
|---|---|---|---|
| 1 | Repository and environment audit | Done | This document |
| 2 | Environment baseline | Done | Backend starts, frontend checks pass, and the backend connects to PostgreSQL (`check_connection()` test passes when a database is running). The Docker Compose container itself was not run in the audit sandbox |
| 3 | Minimal data/API vertical slice (submit + persist + retrieve a request) | Not started | Database connection exists, but no models, migrations, or routes yet |
| 4 | Deterministic policy engine with tests | Done | Engine and 100 tests in `backend/app/policy/` and `backend/tests/policy/`; rules approved (D-032 to D-036, D-039, D-040). Calling it from the workflow comes with the service layer |
| 5 | Extraction interface (schema, missing/ambiguous fields; provider later) | Not started | LLM provider OPEN (D-008) |
| 6 | Human review + audit | Not started | |
| 7 | Minimal UI (form, result, review queue, history) | Not started | shadcn/ui base components exist; no screens yet |
| 8 | Evaluation: System A vs System B | Not started | No dataset yet |
| 9 | Demo/report readiness | Not started | |

## 2. What is built (IN REPO)

**Backend:** FastAPI app factory; `/health`; docs hidden outside development; typed settings with secret masking; database connection layer (`app/db/session.py`: engine, session, `check_connection()`; SQLAlchemy 2 + psycopg 3); deterministic policy engine (`app/policy/`, rules POL-001 to POL-009 and POL-900).
**Frontend:** Vite + React 19 + TS strict + Tailwind 4; design tokens for the three policy outcomes; shadcn/ui base components in `src/components/ui/` (button, card, dialog, input, label, select, skeleton, sonner, table, textarea, badge); `PolicyOutcomeBadge`; `apiRequest` client; ESLint/Prettier/Husky guardrails; many libraries installed but unused.
**Infra:** Compose file for PostgreSQL 16 (port 5433, localhost-only, volume, healthcheck); `.env.example`; `.gitignore`; LF line endings.
**Docs:** `CLAUDE.md` and the `docs/` set, including `POLICY_RULES.md`.

## 3. Verified check results (2026-11-10, sandbox)

| Check | Result |
|---|---|
| `pytest` (backend/), database running | 81 passed, 1 deprecation warning (Starlette `TestClient` suggests `httpx2`) |
| `pytest -m "not integration"` (no database) | 80 passed, 1 deselected. Plain `pytest` without a database running fails only `test_database_connection_works` |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run format:check` | clean |
| `npm test` | 1 file, 3 tests passed |
| `npm run build` | succeeded (JS 250 kB, 81 kB gzip) |
| `npm audit` | not re-run after the merge; 7 moderate findings were reported on 2026-11-05 and are not triaged (Q-009) |
| `docker compose up` | **not run** |

## 4. Task board

| Task | Owner | State | Notes |
|---|---|---|---|
| 2.1 Database connection (SQLAlchemy, driver, session, connection test) | Haya | Done | Merged 2026-11-10 from `feat/frontend-shadcn-base`. Alembic is not installed yet |
| shadcn/ui base components | Haya | Done | Merged 2026-11-10 (D-015) |
| Standard error envelope + CORS (Q-002, Q-003) | _assign_ | Not started | Do before the first feature endpoint |
| Fix `requirements.txt` (D-025) | _assign_ | Partly done | Now UTF-8. Still a full `pip freeze`; the runtime/dev split is not done |
| Schema design (Q-006) | Ghina | In progress | 19 tables in 6 migrations with 126 database tests (207 passed with the existing 81), run in a cloud sandbox only. Not yet run on Ghina's machine and not merged, so not Done. Needs approval of D-037 and D-038 |
| Policy rules design (Q-007) | Maira | Done | Approved 2026-11-08; `docs/POLICY_RULES.md`, D-032 to D-036 |
| Policy engine code (Part B) | Maira | Done | If a rule changes, update its function in `rules.py`, the document and the example test together |
| Extraction agent (Q-008, then implementation) | _assign_ | Not started | First slice: schema, LLM adapter with a fake for tests, validation, conversion to the policy engine's `PolicyInput` |

Owners are not recorded in the repo; fill them in.

## 5. Known issues

1. `backend/requirements.txt` is a full `pip freeze` with no runtime/dev split and includes transitive packages.
2. Frontend error parsing (`message`) does not match FastAPI's default error body (`detail`).
3. No CORS configuration, so the browser cannot call the API yet.
4. No README; setup knowledge lives only in `CLAUDE.md` and chat.
5. No CI; `main` is unprotected and unchecked on push.
6. Python/Node versions not pinned.
7. Plain `pytest` fails one test (`test_database_connection_works`) when the PostgreSQL container is not running. Start it with `docker compose up -d`, or run `pytest -m "not integration"`.
8. Alembic is not installed, so there are no migrations yet.

## 6. Change log (newest first; one line per merged task)

| Date | Who | Change |
|---|---|---|
| 2026-11-19 | Maira Qazi | Policy engine review: approval limits and budget re-checked before the purchase order (D-039, D-040), new example cases C21 to C23, 25 new tests; workflow order fixed in `FYP_MASTER_CONTEXT.md` (validate before clarify); D-041 and D-042 proposed; one PRE_PO contract test in `tests/db` now reads the selected quotation and approved amount from the database (232 tests pass with the schema) |
| 2026-11-10 | Haya | Merged `feat/frontend-shadcn-base`: database connection layer (Task 2.1, with config tests and one integration test), shadcn/ui base components, UTF-8 `requirements.txt`, `.env` path no longer depends on the working folder |
| 2026-11-08 | Maira Qazi | Added policy engine (`backend/app/policy/`) with tests covering the 20 example cases, edge cases and fail-closed behaviour; recorded the approved rules (D-032 to D-036) and closed Q-007 |
| 2026-11-05 | Ghina-Durrani | Aligned Module 1 docs: urgency detection, clarification loop, English only (D-028 to D-031) |
| 2026-11-05 | Maira Qazi | Added and simplified `docs/POLICY_RULES.md` (Q-007 draft) |
| 2026-11-05 | Claude (via Haya) | Audit; added `CLAUDE.md` and `docs/` set |
| 2026-10-22 | HayaAmir05 | Merged PR #1: frontend scaffold (Vite, React, TS, Tailwind, tooling, `PolicyOutcomeBadge`) |
| 2026-10-22 | Ghina-Durrani | Backend foundation (FastAPI, settings, health tests, Compose, `.env.example`) |
| 2026-10-22 | Ghina-Durrani | Added `.gitignore` |
