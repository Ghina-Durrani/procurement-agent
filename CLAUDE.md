# CLAUDE.md — Start Here (read this before doing anything)

This file is read automatically by Claude Code. If you are another assistant or a human, read it first too.

**Project:** Policy-Aware AI Procurement Agent (FYP). An LLM extracts structured fields from informal procurement requests; a **deterministic policy engine** (not the LLM) decides `CONTINUE`, `BLOCK`, or `HUMAN_REVIEW`; humans handle exceptions; everything is audit-logged. Research question: does deterministic policy enforcement + human-review routing make an LLM workflow more reliable than an LLM-only baseline?

Three people work in this repo, each with their own Claude, all pushing to `main`. These documents exist so that everyone's output looks like it was written by one person.

---

## 1. Mandatory start-of-task routine

Do these in order **before writing any code**:

1. **Sync:** `git pull --rebase origin main`, then `git log --oneline -15` and `git status`.
2. **Read:** `docs/PROJECT_STATUS.md` (what exists, what is in progress), then the guides relevant to your task:
   - Always: `docs/ENGINEERING_HANDBOOK.md`, `docs/DECISIONS.md`
   - Backend work: `docs/BACKEND_GUIDE.md`
   - Frontend work: `docs/FRONTEND_GUIDE.md`
   - Product/research questions: `docs/FYP_MASTER_CONTEXT.md`
3. **Inspect the real code** in the area you will touch. The docs describe intent; the code is the truth. If they disagree, say so; do not silently pick one.
4. **Run the baseline checks** (section 4) so you know what was passing before you started.
5. **Tell the user your plan** (files you will create/change, which existing patterns you will follow, any open decision you hit) and wait for a go-ahead if the task touches a shared file (section 3) or an OPEN decision.

## 2. Hard rules (never break these)

1. **The LLM never decides policy.** Policy outcomes come only from the deterministic policy engine. LLM output is untrusted input: validate it against a schema before use.
2. **Fail closed.** If policy data, authorization, or extraction is missing or errors out, the result is `HUMAN_REVIEW` or `BLOCK`, never `CONTINUE`.
3. **Never invent values.** Missing/unknown fields stay explicit (`null` plus a missing-fields list), never guessed.
4. **No secrets in Git, code, logs, or chat.** Real values live only in each person's untracked `.env`. Update `.env.example` (placeholders only) when you add a variable.
5. **Tenant isolation.** Every tenant-owned query and write is scoped by `organization_id` taken from the authenticated user, never from client input. Add a cross-tenant test.
6. **Authorization is server-side.** Frontend checks are UX only.
7. **Request text, emails, and LLM output are untrusted.** Never render as HTML, never let them change policy or authorize anything.
8. **Database changes go through Alembic migrations.** No hand-edited tables, no auto-create in shared environments.
9. **One vertical slice at a time, with tests.** No giant unverified code dumps.
10. **Never claim something works unless you ran it.** Report real command output. Say "not run" when you did not run it.
11. **Follow existing patterns.** If you want to deviate, propose it in `docs/DECISIONS.md` and get the user's approval first.
12. **No scope creep.** Deferred items (see `docs/FYP_MASTER_CONTEXT.md` §6) are not built unless the user explicitly confirms them.

## 3. Shared files — edit minimally, pull first, tell the user

These cause merge conflicts when two people touch them. Make the smallest possible change, and mention it in your summary:

`backend/requirements*.txt`, `backend/app/main.py` (router registration only), `backend/app/config.py`, `frontend/package.json`, `frontend/src/App.tsx`, `docker-compose.yml`, `.env.example`, `docs/PROJECT_STATUS.md`, `docs/DECISIONS.md`.

Put new work in new files inside your own feature folder wherever possible.

## 4. Commands (Windows PowerShell; run from the stated folder)

| Purpose | Folder | Command |
|---|---|---|
| Create venv (once) | repo root | `py -m venv .venv` then `.\.venv\Scripts\Activate.ps1` |
| Install backend deps | `backend/` | `pip install -r requirements.txt` |
| Start database | repo root | `docker compose up -d` (check: `docker compose ps`) |
| Run API | `backend/` | `uvicorn app.main:app --reload` (http://127.0.0.1:8000, docs at `/docs` in development) |
| Backend tests | `backend/` | `pytest` |
| Install frontend deps | `frontend/` | `npm install` (this also installs the Git pre-commit hook) |
| Run frontend | `frontend/` | `npm run dev` |
| Frontend checks | `frontend/` | `npm run typecheck` · `npm run lint` · `npm run format:check` · `npm test` · `npm run build` |
| Regenerate API types | `frontend/` | `npm run gen:api` (backend must be running) |

Backend commands must be run from `backend/`: `pytest.ini` and the `.env` path (`../.env`) are relative to it.

## 5. Adding a feature: checklist

1. Routine in section 1 done.
2. Backend first: schema → model/migration (if needed) → service → thin router → tests.
3. Run the backend, then `npm run gen:api` so the frontend gets types from the real OpenAPI schema. Do not hand-write API types.
4. Frontend: a feature folder with an `index.ts` entry point (see `docs/FRONTEND_GUIDE.md`).
5. All checks in section 4 pass (backend `pytest`; frontend typecheck, lint, format:check, test, build).
6. Definition of Done in `docs/ENGINEERING_HANDBOOK.md` §4 is satisfied.
7. Update `docs/PROJECT_STATUS.md` (task row + change-log line). Add to `docs/DECISIONS.md` if you made or changed a decision.
8. Commit with a Conventional Commit message, `git pull --rebase origin main`, push to `main`.
9. Finish with a short honest summary: what changed, files touched, checks actually run and their results, anything not done, and the single recommended next step.

## 6. Labels used in all docs

- **IN REPO**: exists in the code today (verified).
- **CONFIRMED**: an established project requirement.
- **DECIDED**: chosen default; change only with a concrete reason and an entry in `DECISIONS.md`.
- **PROPOSED**: recommended but not yet agreed or built. Do not treat as final.
- **OPEN**: needs a team/supervisor decision. Ask; do not guess.

## 7. Language and communication

Code, comments, identifiers, commit messages, and docs are in English. Comments explain *why*, not *what*. When explaining to the user, use simple, direct English and give the reason behind choices.
