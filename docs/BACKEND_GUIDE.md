# Backend Guide

Python + FastAPI modular monolith. Read `ENGINEERING_HANDBOOK.md` first. Labels: `CLAUDE.md` §6.

## 1. What exists today (IN REPO, verified 2026-11-10 after merging `feat/frontend-shadcn-base`)

- `backend/app/main.py`: `create_app()` factory; `/health`; `/docs` and `/openapi.json` only when `APP_ENV=development`.
- `backend/app/config.py`: `Settings` (pydantic-settings), `get_settings()` cached with `lru_cache`. Secrets typed as `SecretStr`. Reads the root `.env` by absolute path, so it no longer matters which folder you start from. Database settings are `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` (there is no `DATABASE_URL`); `Settings.build_database_url()` builds the URL safely (special characters in the password are escaped).
- `backend/app/db/session.py`: `get_engine()`, `get_session_factory()`, `get_db()` (FastAPI dependency that closes the session), `check_connection()`. SQLAlchemy 2 with the psycopg 3 driver (D-005).
- Tests: `test_health.py` (3), `test_config.py` (2), `test_database_connection.py` (1, marked `integration`: it needs PostgreSQL running, so start it with `docker compose up -d` or run `pytest -m "not integration"`).
- Installed libraries: FastAPI 0.159, Pydantic 2.14, pydantic-settings, SQLAlchemy 2.1, psycopg 3, Uvicorn, pytest, httpx, python-dotenv.
- **Extraction agent (added 2026-11-12):** `backend/app/services/extraction/`, tests in `backend/tests/extraction/`. Entry point: `extract_request(text, llm, categories=..., required_fields=...)`, then `to_policy_input(...)`, then `evaluate(...)`. The LLM sits behind the `LLMClient` interface (`llm.py`); the real client is `openai_compatible.py` (Groq by default), tests use `FakeLLMClient`. Settings: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`. Try it with `python -m app.services.extraction.demo --offline` from `backend/` (D-008, D-043).
- **Database schema (2026-11-19):** Alembic migrations in `backend/alembic/`, models in `backend/app/models/`, database tests in `backend/tests/db/` (D-037).
- **Not present yet:** routers, auth, CORS, urgency scoring, clarification loop, logging setup.
- **Policy engine (added 2026-11-08):** `backend/app/policy/` (`types.py`, `rules.py`, `engine.py`), tests in `backend/tests/policy/`. Rules are defined in `docs/POLICY_RULES.md` (approved, D-032).

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
│   ├── urgency/         # PROPOSED: urgency evidence -> proposed priority (pure code, see D-028)
│   ├── clarification/   # PROPOSED: ask-the-requester loop, max rounds (see D-029)
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
- The database is the Compose PostgreSQL. Host port is **5433** (IN REPO, bound to `127.0.0.1`). Connect through `app.db.session` (`get_db` in routers, `get_engine` elsewhere); never build a connection string by hand. Settings come from the `POSTGRES_*` variables (D-005).
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
- Input: a typed, validated extraction plus the organization's rule set (and version). Output: a `PolicyResult` with `outcome` (`CONTINUE` | `BLOCK` | `HUMAN_REVIEW`), `triggered_rules` (each with `rule_id`, its own outcome, a human-readable `reason` and an optional `required_approver_role`), `required_approver_roles`, and `policy_version`. Call it as `app.policy.evaluate(policy_input, config)`.
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

- `backend/requirements.txt` is now UTF-8, but it is still a full `pip freeze`. PROPOSED (D-025): keep only direct dependencies, with `requirements.txt` for runtime and `requirements-dev.txt` for `pytest`/`httpx`.
- Never create or update requirements with `pip freeze > requirements.txt` in Windows PowerShell. Edit the file in an editor saved as UTF-8, or add lines by hand.
- Add a dependency only with a stated reason; pin the version; mention it in your summary.

## 7. Known gaps to handle when first needed

- CORS is not configured. The frontend dev server (`http://localhost:5173` / `http://127.0.0.1:5173`) will be blocked until an allow-list of origins is added, driven by a `Settings` field (Q-003).
- Standard error-envelope handlers do not exist yet (Q-002).
- Alembic is not installed. Install it together with the first model and migration.
