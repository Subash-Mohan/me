# Supermemory setup

Operator guide for provisioning Supermemory for a deployment of this app. Run through this once per environment (dev laptop, staging, prod).

## 1. Sign up

Go to **https://supermemory.ai** and create an account. The free tier (1M tokens / 10K queries per month) is enough for a single-user dev deployment.

## 2. Generate an API key

In the dashboard, create a new API key and copy it immediately — the dashboard only shows the secret once. If you lose it, you have to generate a new one and rotate.

## 3. Smoke-test the key from your terminal

```bash
curl -i \
  -H "Authorization: Bearer $SUPERMEMORY_API_KEY" \
  -H "Content-Type: application/json" \
  -X POST https://api.supermemory.ai/v3/documents/list \
  -d '{"limit": 1}'
```

Expected: `HTTP/2 200` with a JSON body (likely `"memories": []` for a fresh account).

| Status | Meaning | Fix |
|---|---|---|
| `200` | Key works | proceed |
| `401` | Wrong key | re-copy from dashboard |
| `403` | Key lacks scope | regenerate with full scope |

## 4. Populate environment variables

Set these in the deployment's environment (e.g. `.env` for local, secret manager for prod). All three are required.

| Variable | Value | Notes |
|---|---|---|
| `SUPERMEMORY_API_KEY` | `sk_…` from step 2 | Treat as a secret. Never commit. |
| `SUPERMEMORY_BASE_URL` | `https://api.supermemory.ai` | No trailing slash. |
| `SUPERMEMORY_TIMEOUT_MS` | `2000` | Per-request timeout in milliseconds. Tune later from real-traffic measurements. |

Mirror the same variable **names** (with placeholder values, not the real key) in `.env.example` so the next operator knows what to set.

## 5. Verify the app picks them up

Start the app. If `SUPERMEMORY_API_KEY` is missing or empty, startup fails at import with a `pydantic_core.ValidationError` — that is the intended fail-fast behaviour. Set the key, restart, boot succeeds.

The app does not probe Supermemory at boot (it's a soft dependency with a local-FTS fallback), so a successful boot does not by itself prove the key is valid. Trust the curl smoke test in step 3 for that.

## 6. Set `entityContext` (run AFTER the first memory is created)

Container tags don't exist in Supermemory until at least one document is created with that tag — the dashboard's "Container Tags" page will be empty until then. The API also only accepts a **specific** tag (e.g. `user_abc123`), not a wildcard like `user_*`.

So this step can only be done **after** the owner has logged their first journal entry through the app. Once that's done, find the owner's container tag (it's `user_<owner_uuid_no_dashes>`) and set its `entityContext` via the API:

```bash
curl -X PATCH "https://api.supermemory.ai/v3/container-tags/user_<OWNER_UUID_HEX>" \
  -H "Authorization: Bearer $SUPERMEMORY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "entityContext": "This is a personal journal entry from a single-user reflective journaling app. Preserve first-person voice. Extract durable facts: emotional state, plans, observations, relationships, decisions."
  }'
```

Replace `<OWNER_UUID_HEX>` with the owner's UUID with dashes stripped (e.g. `abc123de4567...`). You can also do this in the dashboard once the tag appears under "Container Tags".

This shapes how Supermemory extracts memories from each entry. Skipping it gives lower-fidelity extraction (first-person voice gets flattened, emotional facts get dropped).
