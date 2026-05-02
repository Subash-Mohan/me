# Phase 00 — Python environment & project skeleton

## Goal
Stand up the Python project skeleton with toolchain, lint/format/type-check, and a `pyproject.toml` so every later phase has a stable place to add code.

## Functional requirements
- Python 3.12+ enforced (`python_requires` in `pyproject.toml`).
- Dependency manager set up (`uv` recommended; record the choice in `DECISIONS.md`).
- Top-level layout per `CLAUDE.md` exists: `app/`, `migrations/`, `tests/`, `docker/`, `Plans/`.
- `app/main.py` exposes a FastAPI `app` object — empty for now, no routes.
- Lint/format: `ruff check` and `ruff format` configured; both pass on a fresh checkout.
- Type-check: `ty check` on `app/` passes (empty package counts). [Replaces mypy — see `DECISIONS.md`.]
- Test runner: `pytest` configured; one trivial test (`assert True`) passes.
- `pre-commit` config runs ruff and ty on staged files.
- `.env.example` lists every env var the project will use across phases (placeholders only).
- `.gitignore` ignores `.env`, `var/`, `__pycache__`, `.venv`, build artefacts.
- README has a 5-line quick-start: clone → install deps → run tests.

## Out of scope
- No database, no Docker, no FastAPI routes yet.
- No CI workflows yet (phase 15).

## Depends on
- nothing

## Verification
- `uv sync` (or chosen equivalent) succeeds on a clean machine.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check app`, `uv run pytest` all exit 0.
- `python -c "from app.main import app; print(app)"` prints a `FastAPI` instance.

## Master-plan refs
- §2 (Stack), §11.3 (Configuration env vars).
