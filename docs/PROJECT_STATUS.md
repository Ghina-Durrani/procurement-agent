# Project Status

Living progress record. Every Claude updates this when a task changes state. Do not mark a task Done unless its acceptance criteria and tests are satisfied and the checks were actually run.

**Last audit:** 2026-11-05 · `main` at `8f5b114` (last commit 2026-10-22). Checks below were run in a cloud sandbox, not on teammates' machines, and Docker/PostgreSQL was **not** run.

## 1. Milestone sequence (from `TECH_STACK_AND_DECISIONS.md` §13)

| # | Milestone | State | Evidence / notes |
|---|---|---|---|
| 1 | Repository and environment audit | Done | This document |
| 2 | Environment baseline | Partly done | Backend app starts and `/health` test passes. Frontend typecheck/lint/test/build pass. `docker-compose.yml` for PostgreSQL exists but was not verified here. **Backend ↔ database connection not done** |
| 3 | Minimal data/API vertical slice (submit + persist + retrieve a request) | Not started | No DB layer, models, or routes yet |
| 4 | Deterministic policy engine with tests | Not started | |
| 5 | Extraction interface (schema, missing/ambiguous fields; provider later) | Not started | LLM provider OPEN (D-008) |
| 6 | Human review + audit | Not started | |
| 7 | Minimal UI (form, result, review queue, history) | Not started | Only a placeholder page and `PolicyOutcomeBadge` exist |
| 8 | Evaluation: System A vs System B | Not started | No dataset yet |
| 9 | Demo/report readiness | Not started | |

## 2. What is built (IN REPO)

**Backend:** FastAPI app factory; `/health`; docs hidden outside development; typed settings with secret masking; 3 passing tests.
**Frontend:** Vite + React 19 + TS strict + Tailwind 4; design tokens for the three policy outcomes; `PolicyOutcomeBadge` with 3 passing tests; `apiRequest` client; ESLint/Prettier/Husky guardrails; many libraries installed but unused.
**Infra:** Compose file for PostgreSQL 16 (port 5433, localhost-only, volume, healthcheck); `.env.example`; `.gitignore`; LF line endings.
**Docs:** this documentation set (added 2026-11-05).

## 3. Verified check results (2026-11-05, sandbox)

| Check | Result |
|---|---|
| `pytest` (backend/) | 3 passed, 1 deprecation warning (Starlette `TestClient` suggests `httpx2`) |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run format:check` | clean |
| `npm test` | 1 file, 3 tests passed |
| `npm run build` | succeeded (JS 252 kB, 79 kB gzip) |
| `npm audit` | 7 moderate findings, not triaged (Q-009) |
| `docker compose up` | **not run** |

## 4. Task board

| Task | Owner | State | Notes |
|---|---|---|---|
| 2.1 Database connection (SQLAlchemy, driver, session, connection test) | _assign_ | Not in `main` as of `8f5b114` | Depends on D-005 approval |
| Standard error envelope + CORS (Q-002, Q-003) | _assign_ | Not started | Do before the first feature endpoint |
| Fix `requirements.txt` (D-025) | _assign_ | Not started | |
| Schema design (Q-006) | _assign_ | Not started | Next planning step |
| Policy rules design (Q-007) | Maira (PROPOSED) | Draft ready for team review | `docs/POLICY_RULES.md`; Part B (engine code) waits for approval |
| Extraction agent (Q-008, then implementation) | _assign_ | Not started | After schema and policy rules |

Owners are not recorded in the repo; fill them in.

## 5. Known issues

1. `backend/requirements.txt` is a UTF-16 full `pip freeze`, no runtime/dev split, includes transitive packages.
2. Frontend error parsing (`message`) does not match FastAPI's default error body (`detail`).
3. No CORS configuration, so the browser cannot call the API yet.
4. No README; setup knowledge lives only in `CLAUDE.md` and chat.
5. No CI; `main` is unprotected and unchecked on push.
6. Python/Node versions not pinned.
7. `Settings.env_file="../.env"` requires running from `backend/`.
8. `FYP_MASTER_CONTEXT.md`, `ENGINEERING_HANDBOOK.md`, and `TECH_STACK_AND_DECISIONS.md` were referenced but missing from the repo before this documentation set.

## 6. Change log (newest first; one line per merged task)

| Date | Who | Change |
|---|---|---|
| 2026-11-05 | Maira Qazi | Simplified `docs/POLICY_RULES.md` (same rules and cases, plainer wording, fewer open questions) |
| 2026-11-05 | Maira Qazi | Added `docs/POLICY_RULES.md`: Q-007 policy rules draft (PROPOSED, for review) |
| 2026-11-05 | Claude (via Haya) | Audit; added `CLAUDE.md` and `docs/` set |
| 2026-10-22 | HayaAmir05 | Merged PR #1: frontend scaffold (Vite, React, TS, Tailwind, tooling, `PolicyOutcomeBadge`) |
| 2026-10-22 | Ghina-Durrani | Backend foundation (FastAPI, settings, health tests, Compose, `.env.example`) |
| 2026-10-22 | Ghina-Durrani | Added `.gitignore` |
