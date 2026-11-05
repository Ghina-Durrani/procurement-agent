# Backend Guide

Python + FastAPI modular monolith. Read `ENGINEERING_HANDBOOK.md` first. Labels: `CLAUDE.md` §6.

## 1. What exists today (IN REPO, verified 2026-11-05 at commit `8f5b114`)

- `backend/app/main.py`: `create_app()` factory; `/health`; `/docs` and `/openapi.json` only when `APP_ENV=development`.
- `backend/app/config.py`: `Settings` (pydantic-settings), `get_settings()` cached with `lru_cache`. Secrets typed as `SecretStr`. Reads `../.env` (so run from `backend/`).
- `backend/tests/test_health.py`: 3 tests (health, docs hidden in production, secrets not printed). All pass.
- Installed libraries: FastAPI 0.159, Pydantic 2.14, pydantic-settings, Uvicorn, pytest, httpx, python-dotenv.
- **Not present yet:** database layer (no SQLAlchemy, no driver, no Alembic), routers, models, services, auth, CORS, LLM adapter, policy engine, logging setup.

## 2. Established patterns — follow these exactly

**App factory.** Build the app in `create_app()`. Do not create module-level global state besides `app = create_app()`.

**Configuration.** Every setting is a typed field on `Settings` with a safe default or `None`. Secrets use `SecretStr`. Read settings via `get_settings()` only (never `os.environ` directly, never a second `Settings()`). Add each new variable to `.env.example` with a placeholder and a comment. Never put a real value in code.

**Tests.** Use `TestClient(create_app())`. When a test changes environment variables: `monkeypatch.setenv(...)`, call `get_settings.cache_clear()` before building the app, and call it again at the end of the test so other tests start clean. Test files: `backend/tests/test_<topic>.py`. Comments in tests explain the purpose.

**Docstrings/comments.** A module docstring says what the module is for. Comments explain why a choice was made (see `config.py`).

## 3. Planned structure (PROPOSED — create folders only when the first real file needs them)

```text
backend/app/
├── main.py              # create_app(), middleware, exception handlers, router registration only
├── config.py
├── api/
│   ├── deps.py          # FastAPI dependencies: db session, current user, current organization
│   └── v1/
│       └── <feature>.py # thin routers: parse → call service → return schema
├── schemas/             # Pydantic request/response models (API boundary)
├── models/              # SQLAlchemy ORM models
├── db/
│   ├── base.py          # DeclarativeBase, naming convention
│   └── session.py       # engine, sessionmaker, get_db dependency
├── services/
│   ├── intake/          # request lifecycle
│   ├── extraction/      # LLM adapter, prompts, parsing, validation
│   ├── review/          # approve / reject / clarify workflow
│   ├── audit/           # append-only audit events
│   └── evaluation/      # System A vs B runner and metrics (never used at runtime)
├── policy/              # rule definitions, deterministic evaluator, outcomes
└── core/
    └── errors.py        # domain exceptions + the standard error envelope handlers
backend/alembic/         # migrations (created by `alembic init`)
backend/tests/
```

**Dependency direction (strict):** `api` → `services` → (`policy`, `models`/`db`, `extraction adapter`). `policy` imports **nothing** from `api`, `db`, `services`, or any LLM library: it is pure functions over plain inputs, which is what makes it deterministic and testable. Routers contain no business logic. Services never import from `api`.

## 4. Layer rules

**Routers (`api/v1`)**
- One router module per feature; register in `main.py` with the `/api/v1` prefix.
- Declare `response_model` and status codes explicitly. Use dependencies for DB session and current user/organization.
- Raise domain exceptions; the registered handlers turn them into the standard error envelope (Handbook §3). Never return raw exceptions.

**Schemas**
- Separate `XxxCreate`, `XxxRead`, `XxxUpdate` models. `model_config = ConfigDict(extra="forbid")` on inputs.
- Enforce limits (e.g. `max_message_chars` from settings, IN REPO) at the boundary.
- Money as `Decimal`, serialized as string. Enums are `str, Enum` with uppercase values.

**Models and database**
- SQLAlchemy 2.x style (`Mapped[...]`, `mapped_column`), PostgreSQL. UUID primary keys, `created_at` / `updated_at` as timezone-aware UTC.
- Every tenant-owned table has `organization_id` (non-null FK, indexed).
- Typed columns for important fields; JSON/JSONB only for flexible extras.
- Table names plural `snake_case`; constraint/index names via a shared naming convention in `db/base.py`.
- Schema changes only via Alembic: `alembic revision --autogenerate -m "..."`, then **review the generated file by hand**, then `alembic upgrade head`. One migration per logical change; never edit a migration already on `main`.
- `DATABASE_URL` points at the Compose database. Host port is **5433** (IN REPO, bound to `127.0.0.1`). PROPOSED driver: psycopg 3, URL form `postgresql+psycopg://USER:PASSWORD@127.0.0.1:5433/DBNAME`. Confirm before installing (D-005).
- Tenant scoping: data-access functions take `organization_id` as a required argument and filter by it. No unscoped "get by id" for tenant-owned data.

**Services**
- Own the business logic and transactions. Plain functions or small classes with explicit dependencies; easy to unit test with a fake DB session or test database.
- Audit events are written in the same transaction as the state change they describe.

**Extraction (LLM)**
- Provider-agnostic interface, e.g. a `Protocol` with one method taking the request text and returning a validated `ExtractionResult` schema. A fake implementation is used in all tests. Provider choice is OPEN (D-008); do not hard-code a provider.
- Prompt places the request text inside clear delimiters and states that its content is data. Parse output with Pydantic; on parse/validation failure return a result flagged for review, never a guess.
- Extraction output records missing fields, ambiguities, conflicts, and source evidence; unknown values are `None`, not invented.
- `llm_api_key` comes from `Settings`; never log prompts containing sensitive text beyond what the audit design allows.

**Policy engine**
- Input: a typed, validated extraction plus the organization's rule set (and version). Output: a `PolicyDecision` with `outcome` (`CONTINUE` | `BLOCK` | `HUMAN_REVIEW`), `matched_rule_ids`, human-readable `reasons`, and `policy_version`.
- Precedence is explicit and documented: `BLOCK` > `HUMAN_REVIEW` > `CONTINUE`. No rule matched means `CONTINUE` only when required fields are present and valid.
- Unknown rule type, missing data, or an internal error ⇒ `HUMAN_REVIEW` (fail closed), never `CONTINUE`.
- Rule thresholds are configuration (data), not constants in code. Sample/demo values must be labelled as such.
- Rules are pure and individually testable. Each rule has a stable ID.

**Audit**
- Append-only table; no update/delete code paths. Record actor (user or system component), action, target, timestamp, policy version, rule IDs, reason.

## 5. Style

- Type hints on all functions; `from __future__` imports not needed. Python version for the team is not pinned yet (Q-005): use features available in the version everyone runs.
- 4-space indentation, `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants. Line length ≤ 100.
- PROPOSED: add `ruff` (lint + format) and `mypy` as dev tools, then enforce in the Definition of Done. Until then, match the style of existing files.
- No `print`; use the `logging` module (logging setup is not yet defined — PROPOSED: standard library logging with structured, secret-free messages).

## 6. Dependencies

- `backend/requirements.txt` is currently a full `pip freeze` saved as **UTF-16** (generated by PowerShell redirection), which is why Git shows it as binary-looking and diffs badly. pip can still read it, but fix it: convert to UTF-8 and keep only direct dependencies (PROPOSED: `requirements.txt` for runtime, `requirements-dev.txt` for `pytest`/`httpx`).
- Never create or update requirements with `pip freeze > requirements.txt` in Windows PowerShell. Edit the file in an editor saved as UTF-8, or add lines by hand.
- Add a dependency only with a stated reason; pin the version; mention it in your summary.

## 7. Known gaps to handle when first needed

- CORS is not configured. The frontend dev server (`http://localhost:5173` / `http://127.0.0.1:5173`) will be blocked until an allow-list of origins is added, driven by a `Settings` field (Q-003).
- Standard error-envelope handlers do not exist yet (Q-002).
- `Settings.env_file="../.env"` works only when started from `backend/`. Acceptable for now; if it causes trouble, resolve the path from `__file__` and record the change.
