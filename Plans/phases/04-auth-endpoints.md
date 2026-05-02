# Phase 04 — Custom auth endpoints

> **Note:** The original spec for this phase described multi-user signup/signin/refresh/signout with email + password. During implementation it was redesigned to a single-user passphrase model. The pivot and its rationale are recorded in `DECISIONS.md` (six entries dated **2026-05-02**: passphrase + JWT design; step-up auth via `X-Confirm-Passphrase`; rate-limiter add+drop; owner-via-CLI seeding; and the test-infra split). What follows reflects what shipped.

## Goal
Sign in to the single-user app with a memorable passphrase, get a JWT, and introspect identity. Reused unchanged against Supabase Postgres in prod.

## Functional requirements

### Endpoints
- `POST /auth/login` — body: `{passphrase}`. Returns `{access_token, token_type, expires_at}` on success; `401 {detail: "invalid_credentials"}` otherwise.
- `GET /auth/me` — returns `{id, created_at}` for the JWT-bearing user.
- `POST /auth/verify-passphrase` — JWT-protected. Body: `{passphrase}`. `204` on match, `401` otherwise. Used by mobile to validate a typed passphrase before showing a destructive-action UI.

### Behaviours
- **Hashing.** Argon2id via `argon2-cffi` defaults. Unique salt per call.
- **JWT.** HS256, signed with `JWT_SECRET` (`SecretStr`, no default — fail-fast if missing). Single 30-day token; no refresh, no signout, no denylist. Rotation = bump `JWT_SECRET`.
- **`current_user` dependency** decodes the bearer token (rejects missing/malformed/expired/wrong-secret) and loads the user row.
- **Step-up dependency.** `confirm_passphrase` reads `X-Confirm-Passphrase` and verifies against the stored Argon2id hash. Future destructive routes (delete-memory, delete-account, …) use `Depends(confirm_passphrase)` alongside `Depends(current_user)`. Header rather than body so DELETE-without-body endpoints work; `X-` prefix is conventional despite RFC 6648.
- **Logging.** Login and verify-passphrase events log `user_id` + `ip` only — never the passphrase or the JWT. `client_ip()` reads `X-Forwarded-For` first hop, falls back to `request.client.host`.

### Owner seeding (out-of-band)
- `app/cli.py` ships a `me` admin CLI: `uv run python -m app.cli create-owner [phrase]`.
  - Positional arg form for non-interactive setup; omit it to be prompted via `getpass` with confirm-twice.
  - Exit codes: `0` success / `1` owner already exists / `2` empty or mismatched input.
- The lifespan startup body does **not** seed the owner — `OWNER_PASSPHRASE` is intentionally absent from settings/`.env.example`. The passphrase never lives in env.

## Out of scope
- No signup, no email column, no password reset, no OAuth.
- No refresh tokens, no signout endpoint, no device tracking.
- No in-process rate limiting (DDoS lives at Fly's edge proxy; failed-auth events are still logged for anomaly search). See DECISIONS 2026-05-02 "drop the rate limiter".
- No `rotate-passphrase` CLI command yet — operator drops the user row + re-runs `create-owner`. Add the command when the need is concrete.

## Depends on
- 03

## Verification
- `make up && make test-db-migrate && make test` — full pytest suite green (8 test files: `tests/api/test_auth_{authenticated,unauthenticated,no_log_leak}.py`, `tests/api/test_{owner,cli}.py`, `tests/unit/test_security_{passphrase,jwt}.py`, `tests/unit/test_cli_prompt.py`).
- `uv run python -m app.cli create-owner "test phrase"` then `curl -X POST localhost:8000/auth/login -d '{"passphrase":"test phrase"}' -H 'content-type: application/json'` returns a token; `curl -H "Authorization: Bearer …" /auth/me` returns the user.
- Passphrase appears in zero log lines across success and failure paths (covered by `test_auth_no_log_leak.py`).

## Master-plan refs
- §4.1 (auth & onboarding), §6.4 (privacy — same rule used to keep message bodies out of logs is applied to passphrases here).
