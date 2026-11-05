# Engineering Handbook

Cross-cutting rules for everyone (and every Claude) working in this repo. Stack-specific rules are in `BACKEND_GUIDE.md` and `FRONTEND_GUIDE.md`. Labels: `CLAUDE.md` §6.

## 1. Repository layout

```text
procurement-agent/
├── CLAUDE.md                  # entry point for every assistant
├── docker-compose.yml         # PostgreSQL 16 only (IN REPO)
├── .env.example               # placeholders only (IN REPO); real .env is untracked
├── .gitattributes             # LF line endings (IN REPO)
├── docs/                      # these documents
├── backend/                   # FastAPI app (IN REPO: app/main.py, app/config.py, tests/)
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── pytest.ini
└── frontend/                  # React + TypeScript + Vite (IN REPO)
    └── src/
```

Planned backend and frontend internals are in the two guides. Do not create folders "just in case"; create them when the first real file needs them.

## 2. Git workflow

**DECIDED:** the team commits directly to `main` (no long-lived branches). PR #1 (frontend scaffold) was an exception. Because nobody reviews before merge, the checks below are your only safety net. Run them locally.

Before every push:
1. `git status` — only intended files are staged; no `.env`, no `.venv`, no `node_modules`, no real data.
2. Run the checks for the side you touched (`CLAUDE.md` §4).
3. `git pull --rebase origin main`. If there are conflicts, resolve them, re-run the checks, then push. Never force-push `main`.
4. `git push origin main`.

**Commit messages:** Conventional Commits, as already used in history: `feat(frontend): ...`, `chore: ...`. Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`. Scope is `backend`, `frontend`, `db`, `policy`, `extraction`, `docs`, etc. One logical change per commit. Imperative mood, under ~72 characters.

**Avoiding collisions:** announce (in the team chat) which feature folder or files you are working on. Do not edit another person's in-progress files. Shared files are listed in `CLAUDE.md` §3.

**PROPOSED:** add a minimal CI workflow (backend `pytest`; frontend typecheck/lint/test/build) so `main` is checked automatically.

## 3. API contract (PROPOSED unless marked IN REPO)

The backend is the source of truth. Pydantic schemas → FastAPI OpenAPI → `npm run gen:api` (IN REPO) → generated TypeScript types. The frontend never hand-writes types that duplicate API schemas.

| Topic | Rule |
|---|---|
| Base URL | `http://127.0.0.1:8000` in development; frontend reads `VITE_API_BASE_URL` (IN REPO) |
| Health | `GET /health` → `{"status": "ok"}`, unversioned (IN REPO) |
| Feature routes | Prefixed `/api/v1/...`, plural nouns: `/api/v1/requests`, `/api/v1/requests/{request_id}` |
| JSON field names | `snake_case` on the wire. No automatic case conversion in the client |
| Enums | Uppercase strings, identical on both sides: `CONTINUE`, `BLOCK`, `HUMAN_REVIEW` |
| IDs | UUIDs as strings |
| Timestamps | ISO-8601, UTC, with `Z` |
| Money | Amount as a decimal **string** (never a float) plus ISO-4217 `currency` |
| Lists | `?limit=&offset=`; response `{"items": [...], "total": n}` |
| Methods/status | `POST` create → `201`; validation error → `422`; unauthenticated → `401`; forbidden → `403`; not found (including other tenants' rows) → `404`; policy/state conflict → `409` |
| Error body | One envelope for every error: `{"code": "SOME_CODE", "message": "Human readable", "field_errors": {"field": "message"} \| null}` |
| Internals | Never expose stack traces, SQL, secrets, or other tenants' existence in errors |

> **Known mismatch to resolve first (Q-002):** `frontend/src/lib/api-client.ts` (IN REPO) reads a top-level `message` and builds the code as `HTTP_<status>`, while FastAPI's default error body is `{"detail": ...}`. The backend must install exception handlers that produce the envelope above, and `api-client.ts` must be updated to read `code`, `message`, `field_errors`. Do this once, in one change, before adding feature endpoints.

## 4. Definition of Done (every task)

A task is not done because the code is written. It is done when:

- [ ] It follows the existing patterns in the relevant guide, or a deviation is recorded in `DECISIONS.md` and approved.
- [ ] Inputs are validated at the boundary; authorization is enforced server-side; tenant scoping is applied where relevant.
- [ ] Tests exist for normal, invalid-input, boundary, failure, and security cases that apply, and they pass.
- [ ] All checks pass (`CLAUDE.md` §4), with real output observed.
- [ ] No secrets, real data, or debugging leftovers committed. `.env.example` updated if a variable was added.
- [ ] Database changes have an Alembic migration that upgrades from the current head.
- [ ] `docs/PROJECT_STATUS.md` updated; `docs/DECISIONS.md` updated if a decision was made.
- [ ] Final report states what was run, what was not run, and what remains.

## 5. Security rules (apply to every feature)

- Secrets only via environment variables. `Settings` uses `SecretStr` so values do not appear in `repr`/logs (IN REPO, tested). Never log secrets, tokens, passwords, or full request texts unnecessarily.
- Passwords: hash with a standard password-hashing library; never store plaintext. Exact auth design is OPEN (Q-004); decide before coding auth.
- Server-side RBAC on every sensitive operation (approve/reject, policy edits, user admin). The frontend hides buttons for UX only.
- Tenant isolation: `organization_id` comes from the authenticated principal, never from request body/query. Every tenant-owned query is scoped; tests attempt cross-tenant reads and writes.
- LLM safety: user text is delimited and treated as data, never as instructions; LLM output is parsed into a strict Pydantic schema and rejected/escalated if invalid; the LLM cannot write policy tables, approve anything, or call state-changing tools.
- Fail closed on any technical failure in a policy-sensitive path.
- Audit events are append-only: no update/delete paths in application code.
- Parameterized queries only (SQLAlchemy); no string-built SQL.
- Frontend never renders untrusted text as HTML (ESLint bans `dangerouslySetInnerHTML`, IN REPO).
- CORS restricted to explicit origins (Q-003 — not configured yet). HTTPS in any deployed environment.
- Docs/OpenAPI pages only in `development` (IN REPO).
- Use synthetic data only in tests and demos.

## 6. Testing rules

- Backend: `pytest`, tests under `backend/tests/`, named `test_<topic>.py`. Policy rules need exhaustive table-style unit tests (each rule: triggers, does not trigger, boundary values).
- Frontend: Vitest + React Testing Library, co-located `*.test.tsx`; API calls mocked with MSW (installed, no handlers yet).
- Every bug fix starts with a failing test.
- LLM calls are never made in unit tests. Use a fake adapter that returns fixed outputs.
- Evaluation (System A vs B) runs separately from unit tests and uses the labelled case files; never tune on the held-out set.
- Report test results truthfully: passed / failed / not run.

## 7. Code and writing style (both stacks)

- Small, single-purpose functions and modules. Names say what, comments say why.
- Type everything (Python type hints; TypeScript `strict`, no `any`).
- No dead code, no commented-out blocks, no `print`/`console.log` left behind.
- Reuse existing utilities before adding new ones. Add a dependency only with a stated reason; mention it in your summary, and note it in `DECISIONS.md` if it is architectural.
- Comments and docs in simple, direct English.

## 8. Keeping documentation true

- `docs/PROJECT_STATUS.md`: update on every merged task.
- `docs/DECISIONS.md`: update when a decision is made or changed (date, reason, alternatives, impact). Never silently turn PROPOSED into DECIDED.
- If you find the docs disagree with the code, fix the doc in the same change, or log it in `PROJECT_STATUS.md` under Known issues.
