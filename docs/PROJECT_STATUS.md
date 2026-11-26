# Project Status

Living progress record. Update it when a task changes state. Do not mark a task Done unless its acceptance criteria and tests are satisfied and the checks were actually run. **The application does not work end to end yet:** its main parts work and are tested on their own, but no application workflow joins them (section 3).

**Last audit:** 2026-11-24 (D-057), updated the same day when the first vertical slice was finished (tasks 1 to 4). Branch `feat/extraction-slice`, ahead of `main` (`14f9bd5`) and **not merged**. Checks in section 5 were run in a cloud sandbox on that date; the real-model runs in section 4 were run on Maira's laptop.

## 1. Agreed roadmap from here (D-057)

The team built the uncertain parts first on purpose: the policy engine, the AI extraction and the System A vs System B experiment. That work is kept. From now on the order is:

1. Finish the 40-case challenge experiment for both systems (development data).
2. Analyse the results; find real safety or correctness failures.
3. Fix critical failures only. Record minor limitations instead of tuning prompts again and again.
4. Build the **first vertical slice** (below).
5. Grow it into the full procurement workflow, one slice at a time.
6. Run the 50 held-out test cases **once, near the end**, after the research pipeline is integrated into the app and frozen.

No new development datasets, weaker-model experiments or major redesigns without discussing the need first.

**Where we are (2026-11-24):** step 1 waits for Groq's daily allowance (section 4), so step 4 started in parallel, as agreed by Maira. **The first vertical slice is built and tested** (tasks 1 to 4, section 3.1). It was tried in a real browser on Maira's laptop on 2026-11-26. Next: step 5 extensions, starting with clarification.

**First vertical slice (target of step 4).** Reuses the existing parts:
employee submits a request in a minimal React form → API receives it → database stores the original → Groq extraction → evidence checks → policy engine → decision, rule IDs and reasons saved → the employee opens the request and sees its status.

**Then, in later slices:** at most two clarification rounds with the requester; human review and approval as a separate workflow; audit history; proper request states and transitions. The wider FYP scope stays (`FYP_MASTER_CONTEXT.md` §6): supplier matching, RFQs, quotation extraction and comparison, Finance Agent, purchase orders and reporting, subject to Q-001.

## 2. Milestones (`TECH_STACK_AND_DECISIONS.md` §13)

| # | Milestone | State | Evidence / notes |
|---|---|---|---|
| 1 | Repository and environment audit | Done | 2026-11-05; re-audited 2026-11-24 |
| 2 | Environment baseline | Done | Backend and frontend checks pass; backend reaches PostgreSQL in tests. `docker compose up` was not run in the sandbox |
| 3 | Minimal data/API vertical slice | **Done (first slice)** | Tasks 1 to 4: React form → API → database → extraction (fake or live AI) → evidence checks → policy engine → decision and reasons saved → status page. Tried in a real browser on 2026-11-26 |
| 4 | Deterministic policy engine | Done | `backend/app/policy/`, 125 tests; not yet called by any app workflow |
| 5 | Extraction interface and provider | Done, integrated | Used by the app since slice task 3 (D-059). Clarification loop not built |
| 6 | Human review and audit | Not started | Tables exist (`approvals`, `audit_events`); no logic |
| 7 | Minimal UI | In progress | Employee screens: my requests, new request, request details (slice tasks 2 and 4). No reviewer screens |
| 8 | Evaluation: System A vs System B | In progress | Dev run 1 done; challenge run in progress; final 50-case run waits until near the end (D-057) |
| 9 | Demo and report readiness | Not started | |

## 3. Component status

### 3.1 Implemented and tested

| Component | Where | Tests | Notes |
|---|---|---|---|
| Backend foundation: `create_app()`, `/health`, typed settings with `SecretStr`, database connection layer | `main` | 6 | Docs hidden outside development (D-021) |
| Database schema: 19 tables, 6 Alembic migrations, SQLAlchemy models, append-only triggers on `policy_evaluations` and `audit_events` | `main` (`83f32bc`, Ghina) | 126 (`tests/db`, need PostgreSQL) | Run on PostgreSQL 16 in the sandbox; not confirmed on teammates' machines. D-037 and D-038 still need team approval |
| Policy engine: POL-001 to POL-010 and POL-900; checkpoints `INTAKE`, `PRE_PO`, `APPROVAL`; precedence BLOCK > HUMAN_REVIEW > CONTINUE; examples C01 to C25 | up to D-040 on `main`, the rest on the branch | 125 (`tests/policy`) | Pure code: no database, AI or clock |
| Configurable reason for buying: required above 50,000 PKR or for a claimed emergency; otherwise optional (`conditionally_required_fields`) | branch | in `tests/policy` | D-053, D-054 |
| Extraction agent `extraction-v1`: status, value and exact evidence per field; one call to Groq `openai/gpt-oss-120b` through an OpenAI-style client; one retry on broken JSON; rate-limit retry wrapper | branch | 185 (`tests/extraction`) | D-043, D-044, D-008 |
| Safeguards: evidence checks; category classified by the AI from the item and kept only if backed by the item words; AI-reported instructions (quote checked by code) and a fixed word list, both feeding POL-010 | branch | in `tests/extraction` | D-051, D-052, D-053. Word lists frozen at `a863a76` |
| Priority step: urgency signal plus deadline → proposed priority and a "due soon" tag | branch | 50 (`tests/urgency`) | D-049 |
| Evaluation framework: System A (AI decides from rules in its prompt), System B runner (the product pipeline), `run`, `check_cases` and `metrics` commands, resumable runs, prompt fingerprints, one final run per system | branch | 122 (`tests/evaluation`) | D-045, D-047, D-050 |
| Evaluation data: 80 main cases (30 dev verified by Maira, 50 test draft, split locked); 40 challenge cases (39 machine-validated, 1 disputed); independent reference version of the rules used to check labels | branch | in `tests/evaluation` | D-047, D-056 |
| Request intake API (slice task 1): `POST /api/v1/requests` (201, original text saved unchanged, status `RECEIVED`, one `REQUEST_RECEIVED` audit event in the same transaction), `GET /api/v1/requests/{id}` and `GET /api/v1/requests` (own requests only, `{items, total}`); standard error envelope for every error; development-only current user (D-058) and demo seed command | branch (`app/api/`, `app/core/errors.py`, `app/schemas/`, `app/services/intake/`) | 19 (`tests/api`, need PostgreSQL) + 4 (`tests/test_errors.py`) | Cross-company and colleague reads give 404; client cannot set organization, requester or status. Also run against a live server on 2026-11-24. No AI call yet |
| Processing in the app (slice task 3): after saving, the System B pipeline runs (one extraction call, evidence checks, priority, company facts from the database, policy engine) and saves the extraction, the policy evaluation with its exact input, the request columns, the status and two audit events; failures save a fail-closed decision. `EXTRACTION_MODE` fake (default, no tokens) or live (D-059) | branch (`app/services/intake/processing.py`, `company_facts.py`, `llm.py`) | 11 (`tests/api/test_request_processing.py`) + 6 (`tests/test_intake_llm.py`) | Tested outcomes: CONTINUE, missing amount, blocked supplier, manager approval, AI failure, no settings (no AI call), no budget, instructions in text, other company's supplier list. The AI is always a scripted fake in tests |
| Employee screens (slice tasks 2 and 4): `features/requests` with my requests, new request (React Hook Form + zod) and request details (decision with `PolicyOutcomeBadge`, reasons, missing details, what was read, which AI read it); React Query and react-router set up in `App.tsx`; API types generated from the real OpenAPI schema; `api-client.ts` reads the error envelope (Q-002); CORS (D-060) | branch (`frontend/src/features/requests/`, `src/types/api.generated.ts`) | 17 frontend tests (MSW; an unmocked request fails the test) | All untrusted text is rendered as plain text (tested). Checked against a live backend from the dev origin, and tried in a real browser on Maira's laptop (2026-11-26) |
| Frontend scaffold: React 19, Vite 8, TS strict, Tailwind 4, shadcn/ui base components, `PolicyOutcomeBadge`, `apiRequest` client, lint and format rules | `main` | 3 | Checks re-run 2026-11-24 |

### 3.2 Implemented but not integrated

Each part below works and is tested **on its own**. No application workflow connects them yet.

- **Live AI in the app:** built and tested only through its fail-closed path (no key). Not yet run against real Groq from the app; do that only when the token allowance is free.
- **Schema tables for later steps:** clarifications, approvals, quotations, purchase orders and the rest exist but no app code uses them yet.

### 3.3 In progress

- **40-case challenge experiment:** System B run 1 finished on Maira's laptop on 2026-11-24, but from CH-032 Groq's free daily token limit (200,000 tokens) was reached: CH-032, 034, 036, 038 and 040 never got a model answer and ended in fail-closed `HUMAN_REVIEW` (confirmed: `LLMRateLimited` errors, 34 rate-limit waits). Its scores (84.6% decision accuracy) are therefore **not a clean estimate** and are not reported as results. Plan: run System A alone on a day with fresh allowance, then a fresh full System B run; the run folder stays on Maira's laptop as a record.
- **50 held-out test labels:** still draft. They must be verified before the final run near the end.
- **Merging `feat/extraction-slice` into `main`:** not done (15 commits). D-046 says finished tasks are merged; the merge needs the team's agreement.
- **D-037 / D-038 (schema) approval:** schema is on `main`, approval still PROPOSED.

### 3.4 Not started

- Real login (D-011); today only the development stand-in exists (D-058).
- Clarification workflow, at most two rounds (D-029).
- Human review queue and approvals (separate from clarification), with role checks.
- Authentication and role-based access (D-011, Q-004).
- Audit event recording by the application.
- Request states and transitions.
- Frontend screens: request form, request status, review queue, history.
- README, CI.
- Later modules: supplier matching, RFQs, quotation extraction and comparison, Finance Agent, purchase orders, reporting. Some have tables (D-038) but no logic.

## 4. Experiments and results

| Run | Data | Model | State | Result |
|---|---|---|---|---|
| Live check T1 to T6 | 6 synthetic requests | Groq `openai/gpt-oss-120b` | Done (2026-11-22/23, Maira's laptop) | Found two prompt problems (category left empty; "categorise as..." obeyed), fixed by D-052. After the fixes all 6 matched the expected answers |
| **Dev run 1** | 30 verified dev cases | same, for both systems | **Done and recorded** (2026-11-23, code `dc9be8c`) | Both systems 30/30 correct decisions, 0 false allows. System B better on rule lists (93.3% vs 90.0%), field status (97.0% vs 94.7%) and field values (95.6% vs 92.1%); System A better on urgency (100% vs 96.7%). Files in `evaluation/results/` |
| Challenge run | 40 challenge cases (39 scored) | same | **In progress.** System B run 1 hit the daily token limit (5 cases without a model answer), so it is not counted; a fresh System B run is planned. System A run (2026-11-26): 36 cases answered; CH-026 to CH-029 failed on a network outage and will be retried with `--retry-failed` (D-061) | Valid answers in that run already show two false allows, CH-011 and CH-027 (section 7, issues 13 and 14). Clean runs for both systems still needed |
| Final run | 50 held-out test cases | same | Not started; near the end (D-057) | Labels still draft |

The dev cases did not separate the two systems on decisions. That is a finding, not a failure. Limits: synthetic English requests, one model, development data only. Details: `docs/EVALUATION_CASES.md` §8 and §9, `evaluation/results/README.md`.

## 5. Verified check results (2026-11-24, cloud sandbox)

| Check | Result |
|---|---|
| `pytest` (backend/), PostgreSQL 16 running | **661 passed**: policy 125, database 126, extraction 185, urgency 50, evaluation 127, API 32, basic and app settings 16 (2026-11-26) |
| `pytest -m "not integration"` (no database) | 502 passed, 159 deselected |
| `mypy app` | no issues in 59 files (mypy is used in the sandbox; not in `requirements.txt`, D-026) |
| `check_cases` (80 main cases) | no problems; 30 verified, 50 draft |
| `check_cases --dataset challenge` | no problems; 39 machine-validated, 1 disputed |
| Frontend `npm run typecheck`, `lint`, `format:check` | clean |
| Frontend `npm test` | 3 files, 19 tests passed |
| Frontend `npm run build` | succeeded (456 kB, 145 kB gzip; router, React Query and forms added) |
| Live check | backend + Vite dev server: CORS preflight and a submission from the dev origin worked (dev case EV-005 → CONTINUE, APPROVED); EV-009 → HUMAN_REVIEW, NEEDS_CLARIFICATION |
| `npm audit` | not re-run; 7 moderate findings from 2026-11-05 not triaged (Q-009) |
| `docker compose up`, migrations on teammates' machines | not run |

## 6. Who did what

| Area | Owner |
|---|---|
| Backend foundation, Compose, `.gitignore` | Ghina |
| Frontend scaffold, shadcn/ui base, database connection layer | Haya |
| Database schema and migrations (D-037, D-038) | Ghina |
| Extraction agent first slice (D-043) | Haya |
| Policy rules and engine; extraction-v1 and later extraction changes; priority step; evaluation cases, experiment, challenge set | Maira |

## 7. Known issues

1. `backend/requirements.txt` is a full `pip freeze` with no runtime/dev split (D-025); `mypy` is not listed.
2. Frontend error parsing (`message`) does not match FastAPI's default error body (`detail`) (Q-002).
3. No CORS configuration, so the browser cannot call the API yet (Q-003).
4. No README; setup knowledge lives in `CLAUDE.md` and chat.
5. No CI; `main` is unprotected.
6. Python and Node versions not pinned (Q-005).
7. Plain `pytest` needs PostgreSQL for the 126 database tests and one connection test; without it, run `pytest -m "not integration"`.
8. Migrations have not been run on teammates' machines.
9. The evidence check proves a value's words appear in the request; it cannot prove the requester told the truth. Amounts written only in words are discarded, so those requests go to review (challenge case CH-005).
10. Both prompts say "never calculate", so a total that disagrees with item prices is not detected (challenge case CH-011).
11. The Groq free tier is limited (check the Groq console). Runs use `--pause` and can be resumed.
12. `PROJECT_STATUS.md` fell behind the code between 2026-11-12 and 2026-11-24; fixed by this audit. Keep it updated at each milestone (D-057).
13. **Unresolved safety finding, CH-011 (false allow, both systems expected):** "10 webcams at Rs 4,000 each ... total Rs 35,000". The model took the stated total; the quote exists, so the evidence check passed, and no code compares quantity × unit price with the total. Someone could understate a total to stay under approval limits. Smallest safe fix (not built): the model quotes a unit price with evidence, and code does the multiplication; a mismatch makes the total `CONFLICTING` (POL-001). Needs one field added to the shared field rules, so System A gets the same text.
14. **Unresolved safety finding, CH-027 (false allow, System B):** "from Metro Furniture or QuickDeal Imports" (QuickDeal is blocked). The model correctly said supplier `AMBIGUOUS`, but `to_policy_input` sets `supplier_conflict` only for `CONFLICTING`, so the engine saw "no supplier" and POL-005 did not fire. Smallest safe fix (not built): treat an `AMBIGUOUS` supplier like `CONFLICTING` in that one function, so POL-005 gives `HUMAN_REVIEW`. The blocked supplier would still be stopped at `PRE_PO`. Both fixes wait for D-057 step 3, after clean runs.
15. The development current user (D-058) is not authentication. Anyone who can reach the dev API acts as the demo user. It refuses every call outside development.
16. The app's fake AI (default) only knows the 30 dev case texts; any other text fails closed to `HUMAN_REVIEW` (POL-900). Use `EXTRACTION_MODE=live` to try your own text, which spends Groq tokens.
17. When the amount is missing, the app also shows POL-007 (budget cannot be checked), unlike the experiment, where `context.json` assumes the budget is available (D-059).
18. Processing runs inside the submit call, so a live AI call adds a few seconds to the response. A background job can come later if needed.
19. Tried in a real browser on 2026-11-26 (Maira's laptop): submit, approval and the review screens worked. Found and fixed: unreadable requests were shown as "needs more details"; repeated rule IDs.

## 8. Next milestone

**Step 5, first extension: clarification** (at most 2 rounds, D-029): a request in `NEEDS_CLARIFICATION` asks the employee for the missing details, re-runs extraction and the policy engine, and after 2 rounds goes to human review. Then the review queue (`AWAITING_APPROVAL`), audit history and request states. First, try the slice in a real browser on Maira's laptop. The challenge runs continue separately when Groq allows.

## 9. Change log (newest first; one line per merged task)

| Date | Who | Change |
|---|---|---|
| 2026-11-26 | Maira Qazi | `run --retry-failed` (D-061): re-runs only cases that never reached the model, keeps every saved line, and metrics score the latest result and name the retried cases; 5 tests added and the full command rehearsed with a fake run |
| 2026-11-26 | Maira Qazi | First slice tried in a real browser on Maira's laptop (dev case → Approved). Two fixes from that test: an unreadable request now shows "Being verified" with a plain explanation instead of a misleading list of missing details (D-059), and each rule is shown once with its reasons grouped. 3 backend and 2 frontend tests added |
| 2026-11-24 | Maira Qazi | First vertical slice finished: tasks 2 to 4 (employee screens, processing with extraction and the policy engine, decision and reasons on the status page), fake/live AI setting and CORS (D-059, D-060), Q-002 and Q-003 closed; 17 backend and 14 frontend tests added |
| 2026-11-24 | Maira Qazi | Vertical slice task 1: request intake API (submit, save, retrieve), error envelope, development current user (D-058), demo seed; 23 new tests. Challenge run status corrected (rate-limited, not counted); CH-011 and CH-027 recorded as unresolved safety findings |
| 2026-11-24 | Maira Qazi | Documentation audit (D-057): `PROJECT_STATUS.md` rewritten from the real repository state (four status groups, verified checks, experiments, agreed roadmap); stale claims corrected in `TECH_STACK_AND_DECISIONS.md`, `DECISIONS.md`, `BACKEND_GUIDE.md`, `FYP_MASTER_CONTEXT.md` (facts only, scope unchanged), `EXTRACTION_MODULE_DESIGN.md`, `EVALUATION_CASES.md` and `CLAUDE.md`. Documentation only |
| 2026-11-24 | Maira Qazi | Challenge set: CH-011 and CH-027 decided (`HUMAN_REVIEW`), CH-023 stays disputed (no written rule for mixed personal use); 39 machine-validated, 1 disputed; no engine, prompt or main-case changes |
| 2026-11-24 | Maira Qazi | D-056: 40-case development challenge set with machine-validated labels (draft = independent reference policy = engine), 3 disputed cases flagged, near-copy checks, `--dataset challenge` for run/check/metrics; reference check added for the 80 main cases (all agree); 24 new tests (613 pass with the database). Not run yet |
| 2026-11-24 | Maira Qazi | Dev run 1 with Groq recorded (both systems 30/30 decisions, 0 false allows; B more accurate on fields and rules). D-055: three shared prompt refinements (corrections, purpose as reason, deadline is not urgency); EV-040 wording; 589 tests pass with the database |
| 2026-11-23 | Maira Qazi | D-054: reason for buying required only above 50,000 PKR or for an emergency (not by category); a missing amount is clarified first; no label changes; 586 tests pass with the database |
| 2026-11-23 | Maira Qazi | D-053: configurable reason requirement (`conditionally_required_fields`; optional up to 50,000 PKR for ordinary purchases); POL-010 covers skipping checks and misclassification instructions; POL-010 is a person's label in the answer key; labels EV-011, EV-041, EV-046 updated by the rule change; 23 new tests (583 pass with the database) |
| 2026-11-22 | Maira Qazi | First real Groq test (6 synthetic requests, on Maira's laptop). D-052: category is classified from the item with code descriptions and must rest on the item words; the model reports instructions aimed at the system (quote checked by code, feeds POL-010); 11 new tests (562 pass with the database) |
| 2026-11-22 | Maira Qazi | D-051: category word check in extraction (`guards.py`), new rule POL-010 (instructions aimed at the system) in the policy engine and in System A's rules, example C25; labels of the 8 prompt-injection cases updated (EV-072 now `HUMAN_REVIEW`); 50 new tests (551 pass with the database) |
| 2026-11-22 | Maira Qazi | Experiment built (D-050): System A prompt and runner, System B runner, `run` and `metrics` commands, `RetryingLLMClient` for rate limits, shared `FIELD_RULES` (System B's prompt unchanged byte for byte), split-aware `load_cases`; dry runs reproduce every expected answer; 41 new tests (501 pass with the database); two weak spots of System B found (fixed by D-051) |
| 2026-11-22 | Maira Qazi | Verified the labels of the 30 dev evaluation cases; the 50 test cases stay draft until before the final run |
| 2026-11-19 | Maira Qazi | Priority step in `app/services/urgency/` (D-049): deadline phrases to dates, high priority within 3 days, "due soon" tag within 7 days; the evaluation uses it; D-031 thresholds settled |
| 2026-11-19 | Maira Qazi | Evaluation cases: 80 draft cases in `evaluation/cases/` (10 categories, 30 dev / 50 test, split locked), shared company facts in `context.json`, checker `python -m app.services.evaluation.check_cases`, `docs/EVALUATION_CASES.md`, D-047 proposed. Policy: POL-005 sends conflicting suppliers to review (D-048, example C24). 53 new tests (410 pass with the database) |
| 2026-11-19 | Maira Qazi | Extraction schema `extraction-v1`: status, value and evidence per field, urgency signal, whole-number quantity, `delivery_location`, field-to-column mapping (D-044); added `docs/EXTRACTION_MODULE_DESIGN.md`; 30 new tests; required-field names in the database contract test now use the extraction names |
| 2026-11-19 | Maira Qazi | Merged `main` into `feat/extraction-slice` (schema + policy update); Haya's extraction decision renumbered D-037 → D-043 |
| 2026-11-19 | Maira Qazi | Policy engine review: approval limits and budget re-checked before the purchase order (D-039, D-040), new example cases C21 to C23, 25 new tests; workflow order fixed in `FYP_MASTER_CONTEXT.md` (validate before clarify); D-041 and D-042 proposed; one PRE_PO contract test in `tests/db` now reads the selected quotation and approved amount from the database (232 tests pass with the schema) |
| 2026-11-12 | Haya (with Claude) | Extraction agent first slice in `backend/app/services/extraction/` with 95 tests and an offline demo; added `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS` settings (D-008, D-043) |
| 2026-11-10 | Haya | Merged `feat/frontend-shadcn-base`: database connection layer (Task 2.1, with config tests and one integration test), shadcn/ui base components, UTF-8 `requirements.txt`, `.env` path no longer depends on the working folder |
| 2026-11-08 | Maira Qazi | Added policy engine (`backend/app/policy/`) with tests covering the 20 example cases, edge cases and fail-closed behaviour; recorded the approved rules (D-032 to D-036) and closed Q-007 |
| 2026-11-05 | Ghina-Durrani | Aligned Module 1 docs: urgency detection, clarification loop, English only (D-028 to D-031) |
| 2026-11-05 | Maira Qazi | Added and simplified `docs/POLICY_RULES.md` (Q-007 draft) |
| 2026-11-05 | Claude (via Haya) | Audit; added `CLAUDE.md` and `docs/` set |
| 2026-10-22 | HayaAmir05 | Merged PR #1: frontend scaffold (Vite, React, TS, Tailwind, tooling, `PolicyOutcomeBadge`) |
| 2026-10-22 | Ghina-Durrani | Backend foundation (FastAPI, settings, health tests, Compose, `.env.example`) |
| 2026-10-22 | Ghina-Durrani | Added `.gitignore` |
