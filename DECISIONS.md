# Decisions

Append-only log of implementer judgment calls. Never edit a past entry — supersede it with a new one referencing the old.

Format:

```
## YYYY-MM-DD — <topic>
**Choice:** ...
**Why:** ...
**Alternatives considered:** ...
```

## 2026-05-09 — `memories.search_tsv` config = `'simple'`
**Choice:** The generated `tsvector` on the `memories` table uses Postgres FTS config `'simple'` (no stemming, no stopword removal).
**Why:** The local FTS path is a fallback only — Supermemory is the primary search. `'simple'` is multilingual-safe and avoids stemming surprises in personal-text journaling (e.g. `'running'` → `'run'`). If/when local FTS becomes the primary path, revisit and consider `'english'` or per-row language detection.
**Alternatives considered:** `'english'` (better English ranking, worse for non-English entries); language-detection at insert time (extra dep, more complexity for a fallback path).

## 2026-05-09 — Drop `'failed'` from `memories.external_status` v1
**Choice:** The CHECK on `external_status` allows only `('synced','unsynced','pending_delete')`. No `'failed'` terminal state.
**Why:** No code path on the inline-sync model emits `'failed'` — transient errors set `'unsynced'`, delete failures set `'pending_delete'`. Adding `'failed'` to the schema before defining the trigger condition (retry counter? operator action?) encodes a state nothing writes. Reintroduce when a retry-counter/terminal-state policy is defined.
**Alternatives considered:** Keep `'failed'` reserved for future use (rejected — adds enum value with no writer; ENUM additions are cheap when needed via a migration).

## 2026-05-09 — DB-level CHECK constraints on `memories` for hash, lat/lng
**Choice:** Migration adds four table-level CHECKs: `octet_length(content_hash) = 32`; `(location_lat IS NULL) = (location_lng IS NULL)`; `location_lat IS NULL OR location_lat BETWEEN -90 AND 90`; `location_lng IS NULL OR location_lng BETWEEN -180 AND 180`.
**Why:** Defense-in-depth at the DB boundary. Catches accidental MD5/truncated hashes (16 bytes), out-of-range coords, and unpaired lat/lng — all of which the service should already 422 on, but the DB is the last line. Cheap (no measurable write overhead at this scale).
**Alternatives considered:** Service-only validation (rejected — single failure point); CHECKs in a domain type (rejected — over-engineered for one table).

## 2026-05-09 — `Memory.search_tsv` omitted from the ORM
**Choice:** The `search_tsv` generated column lives in the migration but is NOT mapped on the `Memory` SQLAlchemy class.
**Why:** It is read only by hand-written SQL in the local-FTS fallback (planned in 05d); ORM code never touches it. Mapping a `Computed(...)` generated tsvector adds SQLAlchemy version-sensitivity and autogenerate quirks for zero benefit. If a future path needs to read it through the ORM, add it then.
**Alternatives considered:** Map with `sa.Computed(..., persisted=True)` (rejected for the reasons above); map as `server_default=FetchedValue()` (older pattern, even more brittle).
**Superseded by:** 2026-05-09 — `Memory.search_tsv` mapped with Computed.

## 2026-05-09 — `Memory.search_tsv` mapped with Computed
**Choice:** Map `search_tsv` on the `Memory` class as `Mapped[str]` with `Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True)`. The full `__table_args__` (5 CHECK constraints + 4 indexes) also moved onto the model.
**Why:** Adding `__table_args__` to mirror the migration's constraints/indexes exposed that omitting `search_tsv` from the model causes `alembic check` to flag a (false) drop. SQLAlchemy 2.x handles `Computed(..., persisted=True)` cleanly — the speculative "version risk" cited in the prior decision didn't materialise. ORM code still doesn't read or write `search_tsv`; the column is just declared so model and DB tell the same story.
**Alternatives considered:** Add an `include_object` filter in `migrations/env.py` to hide the column from autogenerate (rejected — scatters one column's special-casing into env.py); leave the drift and document it (rejected — `alembic check` is now part of our drift-detection toolbox and shouldn't be permanently red).
**Supersedes:** 2026-05-09 — `Memory.search_tsv` omitted from the ORM.

## 2026-05-09 — Local Postgres dev port moved from 5434 to 5435
**Choice:** `docker/docker-compose.yml`, the `Makefile` (`up` echo + `test-db-migrate`), `.env`, and `tests/conftest.py` now use host port `5435`.
**Why:** Port `5434` is occupied on this dev machine by an unrelated long-running container (`deployment-relational_db-1`). `5435` is free and the change is contained to local config.
**Alternatives considered:** Stop the conflicting container (rejected — affects unrelated work); make the port a configurable env var (rejected — over-engineered for a one-machine adjustment, can revisit if multiple devs hit this).
