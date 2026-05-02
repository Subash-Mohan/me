# Phase 04 — Custom auth endpoints

## Goal
Sign up, sign in, refresh, and identity introspection — all backed by our own users table and JWTs. Same code path will run unchanged against Supabase Postgres in prod.

## Functional requirements
Endpoints:
- `POST /auth/signup` — body: `{email, password}`. Creates user; rejects duplicate email; returns access + refresh tokens + user shape.
- `POST /auth/signin` — body: `{email, password}`. Returns access + refresh tokens + user shape on success; 401 otherwise; rate-limited per IP+email.
- `POST /auth/refresh` — body: `{refresh_token}`. Returns a new access token (and rotates refresh token).
- `POST /auth/signout` — invalidates the current refresh token (server-side denylist or rotation marker).
- `GET /auth/me` — returns the authenticated user.

Behaviours:
- Password hashing with Argon2id (preferred) or bcrypt — record choice in `DECISIONS.md`.
- Access token: short-lived JWT (~15 min). Refresh token: long-lived (~30 days), rotated on every refresh.
- `current_user` FastAPI dependency that decodes the access token and loads the user.
- Tokens signed with `JWT_SECRET` (HS256). Document JWKS upgrade path but don't build it.
- Email is normalized (trimmed, lowercased) before write/lookup.
- Password policy: min length 10, no other constraints.
- All endpoints return JSON; errors follow a consistent `{detail: "..."}` shape.

## Out of scope
- No email verification, no password reset, no OAuth (master plan mentions Google but defer to a later phase that we'll add when needed).
- No multi-factor auth.
- No session listing / device management.

## Depends on
- 03

## Verification
- pytest integration tests cover: signup happy path, duplicate email 409, signin wrong password 401, refresh rotates the refresh token, expired access token rejected, `current_user` blocks unauthenticated calls.
- `curl -X POST /auth/signup …` followed by `curl -H "Authorization: Bearer …" /auth/me` returns the user.
- Rate limit kicks in after N failed signins from the same source.

## Master-plan refs
- §4.1 (auth & onboarding), §6.4 (privacy — no message bodies in logs; same applies to passwords).
