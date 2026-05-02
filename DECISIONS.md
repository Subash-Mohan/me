# Decisions

Append-only log of implementer judgment calls. Never edit a past entry — supersede it with a new one referencing the old.

---

## 2026-05-02 — Dependency manager: `uv`
**Choice:** Use `uv` (Astral) for dependency management, lockfile, and Python toolchain version pin.
**Why:** Fast resolver, single tool covers env + deps + Python version. Astral-aligned with the rest of the toolchain (`ruff`, `ty`). Standard for new Python projects in 2026.
**Alternatives considered:** Poetry (slower, larger footprint, but more conservative); pip-tools + venv (most explicit, most manual).

---

## 2026-05-02 — Lint + format: `ruff`
**Choice:** Use `ruff` for both linting and formatting (no `black`, no `flake8`, no `isort`).
**Why:** A single Rust-backed tool replaces black/flake8/isort/pyupgrade/autoflake/pydocstyle and runs orders of magnitude faster. No serious 2026 competitor; configuration lives in one block in `pyproject.toml`.
**Alternatives considered:** `black` + `ruff` (lint only) — more conservative but redundant given ruff's formatter is now stable.
**Initial rule selection:** `E, F, I, B, UP, SIM, RUF`. Line length 100. Target `py312`.

---

## 2026-05-02 — Type checker: `ty` (Astral) instead of `mypy`
**Choice:** Use `ty` as the type checker for `app/`. The phase 00 file's stated `mypy --strict` is replaced.
**Why:**
- Same authors as `ruff`/`uv` → unified Astral toolchain and editor LSP.
- 10–60× faster than mypy; fast feedback in pre-commit and editor.
- Beta as of Dec 2025, stable 1.0 targeted in 2026; Astral uses it for their own projects in production.
- Plugin gap is not a blocker here: Pydantic v2 ships native type info, and SQLAlchemy 2.x uses native `Mapped[T]` annotations (its mypy plugin is legacy for 2.x codebases).
**Alternatives considered:**
- `mypy` — most mature, best ecosystem; slower; the phase's stated default.
- `pyrefly` (Meta) — battle-tested at Instagram (20M LOC), beta, 90% spec conformance.
- `pyright` (Microsoft) — stable for years, fast, used by Pylance; Python-side config story is weaker than ty's.
**Pinned version:** `ty==0.0.34` (the version installed by `uv sync` at the time of this entry). Treat the pin tightly while ty is in beta.
**Pre-commit:** `ty` does not yet ship an official pre-commit hook repo. Wired as a `local` hook calling `uv run ty check app` so the pinned version in `pyproject.toml` stays the single source of truth.
**Fallback rule:** if `ty` blocks development before its 1.0, swap to `mypy` and add a superseding entry here. Do not silently revert.

---

## 2026-05-02 — `app/main.py` exposes a bare `FastAPI` instance
**Choice:** Phase 00's `app/main.py` instantiates `FastAPI(title="Byte Journal")` with no routes.
**Why:** Phase 01 adds the first route on top of this object. Having the instance present from day one means later phases never need to scaffold the app factory — they just register routers.
**Alternatives considered:** App-factory pattern (`def create_app() -> FastAPI`) — deferred to whenever multi-environment config makes it valuable; not needed for a single-user app yet.

---

## 2026-05-02 — Application name: "Me" (renamed from "Byte Journal")
**Choice:** Application name is "Me". Package slug `me`, FastAPI title `"Me"`, dev DB user/pass/db `me`, Supabase bucket prefix `me-images-*`.
**Why:** "Byte Journal" was the working title carried through phase 00 scaffolding and the master plan; the user confirmed the actual product name is "Me". Renaming now (one phase in, no migrations or buckets created yet) is far cheaper than after they exist.
**Supersedes:** the 2026-05-02 entry above naming the FastAPI instance `title="Byte Journal"` — read it as `title="Me"` going forward.
**Alternatives considered:** keeping the package slug as `byte-journal` for stability — rejected because nothing depends on it externally yet.
