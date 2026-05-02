# Phase 09 — Image upload + image-attach intent + image-bearing capture

## Goal
The user can send images in chat. With "attach to" wording → image attaches to an existing memory. Without it → new memory bundles text + images.

## Functional requirements
Storage (dev):
- `IMAGE_STORAGE_BACKEND=local` writes blobs under `./var/images/<user_id>/<sha256>.<ext>`.
- A `Storage` protocol (`put`, `get_signed_url`, `delete`) with a `LocalStorage` implementation. Supabase implementation is phase 14.

Endpoints:
- `POST /images` — multipart upload. Server computes content hash; if `(user_id, hash)` exists, returns the existing image row instead of writing a new blob. Stores mime, dimensions, byte size. Returns image id + a signed URL (short-lived even in dev for parity).
- `GET /images/{id}` — returns metadata + a fresh signed URL.

Chat agent updates:
- Intent classifier extended with `image-attach`: triggered only when the message contains an image **and** the text references an existing memory ("add this to…", "this goes with…", "for my X memory"). Image + no such wording → `capture`.
- Tool: `attach_image_to_memory(image_id, target_memory_query_or_id)` — natural-language match returns top candidates by entry/memory text similarity (tsvector for now; vector after phase 11). Agent restates the matched memory ("memory from April 12 about the Yosemite trip") and waits for confirmation. If multiple plausible matches, lists 2–3 and asks the user to pick.
- `save_memory` upgraded to accept `image_ids?: list[str]` and writes `memory_images` rows. Capture-with-image path uses this.

Behaviours:
- Image upload is async from the user's POV: `POST /messages` (phase 06) accepts a list of image ids that may already be uploaded — the chat ack does **not** wait on upload completion.
- Mobile uploads images first to `/images`, then sends the message with the resulting ids. Backend tolerates "send first, upload finishes later" via deferred attach (record approach in `DECISIONS.md`).
- Validate mime (jpeg/png/heic/webp), max size (e.g., 15MB), reject otherwise.
- Privacy: blobs are not publicly readable; only signed URLs.

## Out of scope
- Image embeddings / visual search (V2 / later phase).
- Server-side thumbnail generation (defer; client uses the same blob with a transform query param hint, or thumbnails added in phase 14).
- Image deletion blob-level: rows can be dereferenced now; reaping orphan blobs is a later admin job.

## Depends on
- 03, 04, 05, 06, 07

## Verification
- pytest: upload same bytes twice → second call returns the existing image id, no second blob written.
- Send an image with "add this to my Yosemite trip memory" → agent finds a candidate, restates, on "yes" the `memory_images` row exists.
- Send an image + caption with no attach wording → new memory created with the image attached.
- Memory detail (phase 05) returns the new image with a signed URL that 200s.
- Reject upload of a `.txt` file → 415.

## Master-plan refs
- §4.2 image-attach + image+text capture flows, §5.6 attach flow, §6.3 image content-hash dedup, §6.4 signed URLs, §7.3 (attach_image_to_memory tool).
