# Byte Journal — Product & Functional Plan

> **For implementation:** This document describes *what* the system does and *how the user experiences it*. Technical decisions (schema, endpoints, algorithms) are intentionally left to the implementer. The companion document `personal_memory_layer_guide.pdf` describes the memory architecture in technical depth — read it before implementing the memory pipeline.

---

## 1. Product summary

Byte Journal is a single-user, chat-first personal journaling app with exactly two screens: a chat surface and a memory browser. The user captures thoughts throughout the day by talking to the chat — typed, voice, or image+text. The same chat is where they ask questions about their past, set reminders, and attach pictures to existing memories. Over time the system builds an active memory of who the user is, what is happening in their life, and how their thoughts evolve.

The second screen is a memory browser: a visual feed of every memory the system has stored, with any attached images shown inline. It is read-and-edit, not capture — capture only ever happens through chat.

The product is for the user themselves, not as a multi-user service. Privacy, data ownership, and zero-friction capture take precedence over feature breadth.

---

## 2. Stack

| Layer | Choice |
|---|---|
| Mobile app | **React Native** (iOS + Android, single codebase) |
| Backend API | **FastAPI** (Python, async) |
| Database | **Postgres** (via **Supabase**) |
| Auth | **Supabase Auth** (email + Google OAuth) |
| Object storage | **Supabase Storage** (image attachments from MVP; audio attachments for voice transcription) |
| LLM access | **OpenAI SDK** pointed at **OpenRouter** (lets us swap models without code changes) |
| Push notifications | **Firebase Cloud Messaging (FCM)** |
| Backend hosting | **Fly.io** |
| Deployment | **Docker** (single image for FastAPI + worker; orchestrated via `fly.toml`) |
| Background jobs | Polling worker process (same Docker image, different entrypoint) + `pg_cron` for scheduled jobs |
| Vector search | **pgvector** extension in Supabase Postgres |
| Full-text search | Postgres `tsvector` + GIN index |

**Why these specifically:**
- OpenRouter lets the user (or developer) switch between Claude, GPT, Gemini, Llama, etc. by changing one config value — no SDK swaps, no provider lock-in.
- Supabase consolidates auth + DB + storage so the React Native app can hit it directly for plain CRUD, reserving FastAPI for AI/agent work only.
- Single Docker image with two entrypoints (`api`, `worker`) keeps deployment simple — one build, two Fly.io processes.

---

## 3. User personas and primary jobs

There is one user: the developer/owner of the app. Their primary jobs are:

1. **Capture** thoughts quickly throughout the day with minimal friction — including images alongside text.
2. **Recall** — ask questions about their own past ("what was I working on this day last year") and get accurate, contextual answers.
3. **Notice patterns** — periodic surfacing of recurring themes, mood trends, unfinished thoughts.
4. **Be reminded** — set reminders that arrive as push notifications.
5. **Browse** — visually scan stored memories and their attached images on the second screen.

Jobs 1–4 all happen through the chat surface; the user never picks a "mode" — the agent classifies intent. Job 5 is served by the memory browser. Anything that doesn't serve one of these five jobs is out of scope.

---

## 4. Functional scope — feature inventory

Each feature below has a brief description, a list of behaviors, and acceptance criteria. Features are tagged as **MVP** (build first), **V2** (next), or **V3** (later). See §9 for the phased rollout.

A note on terminology used throughout the rest of this doc:
- **Memory** — the user-facing word for anything the system has stored. The memory browser shows memories.
- **Entry** — internal data-model term for the raw chat-message log row that produced a memory.
- **Fact** — internal data-model term for an atomic claim extracted from one or more entries by the memory pipeline.

The user never sees the words "entry" or "fact" — they only see "memory" in the UI.

### 4.1 Authentication & onboarding — MVP

- User signs up with email/password or Google.
- First-time onboarding: optional 3-card intro explaining the app, then straight to the chat surface with the cursor focused.
- Session persists indefinitely; no auto-logout.
- Single device at a time is fine for MVP; multi-device sync is V2.

**Acceptance:** User can sign up, sign in, and remain logged in across app restarts. Sign-out works and clears local data.

### 4.2 Chat surface — MVP

The single primary screen of the app. Everything the user does, except passive browsing, happens here. Friction here kills the product.

**Behaviors:**
- Default screen on app open is the chat. Cursor is focused on the input.
- Standard chat UI: scrollable thread, input box at bottom, streaming agent responses, attachment button next to the input.
- The input accepts: typed text, voice (tap-and-hold to record; transcribed via device speech recognition; transcript editable before sending), and image attachments (one or more) with optional accompanying text.
- The agent classifies each user turn into one of five intents: **capture**, **recall**, **reminder**, **image-attach** (attach an image to an existing memory), or **meta** (e.g. profile edit, settings change). The user never picks a mode — see §7 for intent rules.
- **Capture flow:** sending a non-question message creates a memory. Optional mood (inferred or asked) and tags. The memory record stores `created_at` (when sent) and `event_date` (defaults to today; user can say "yesterday I…" and the agent backdates). The agent acknowledges with a short confirmation ("saved.") rather than a full prose reply.
- **Recall flow:** the agent searches memories using the tools in §7.2 and streams an answer that cites memories by date.
- **Reminder flow:** the agent parses the request, restates the parsed time/recurrence, and on confirmation schedules it (see §4.6).
- **Image-attach flow:** when a message includes an image plus text like "add this to my Yosemite trip memory," the agent finds the target memory by natural-language match, restates the target, and on confirmation attaches the image to it. If the target is ambiguous, the agent asks a single clarifying question before acting.
- **Image+text capture:** when a message includes an image with no "attach to existing" intent, the image becomes part of a new memory along with whatever text was sent.
- The agent **streams** responses token-by-token (SSE).
- When the agent calls a tool, the UI shows a status indicator ("Searching your memory…", "Saving…").
- Sending is **instant** — the API records the chat message and acks in under 200ms. All LLM processing (intent classification, fact extraction, embeddings) is asynchronous and does not block the send. Image upload is async with an immediate placeholder/thumbnail.
- Drafts (text + selected images) auto-persist locally every few seconds.
- Conversation history persists per-user. Long histories are trimmed/summarized over time (the agent does not see all past turns verbatim — only the last N plus a rolling summary).
- "New conversation" clears the active thread without deleting prior threads.

**Acceptance:** A typed capture takes under 5 seconds end-to-end; a voice capture under 15. First-token latency for recall under 1 second on typical queries. Sending never fails due to network or AI issues — messages and images written offline sync on reconnect. Tool calls are visible. The agent correctly answers all five LongMemEval-style categories (single-hop, multi-hop, temporal, knowledge-update, open-domain — see §10).

### 4.3 Memory browser — MVP

The second screen of the app. Read-and-edit only — capture never happens here.

**Behaviors:**
- Reachable via a single navigation action from the chat (e.g. a header icon or swipe).
- Reverse-chronological grid/list of memories. Each card shows: date, first ~3 lines of memory text, thumbnail of attached image(s) if any, mood (if set), tags (if set).
- Tap a memory to view full text and full-resolution images.
- The detail view supports: editing text, mood, tags, and `event_date`; adding more images; removing or reordering existing images; deleting the memory entirely.
- Cannot change `created_at`.
- Deleting a memory is permanent (after confirmation) and invalidates any facts derived from its underlying entry.
- Filter bar: date range and tag. There is no separate keyword/semantic search bar here — semantic and keyword search are reached by asking in chat.

**Acceptance:** User can scroll their entire history smoothly. Edits propagate to derived facts (deletes invalidate derived facts). Image add/remove updates the memory record and Supabase Storage references atomically.

### 4.4 Memory pipeline (background) — MVP

Invisible to the user but is the system's most important machinery. **Read `personal_memory_layer_guide.pdf` before implementing.**

**Behaviors:**
- When a new chat-message entry is saved (capture intent), it is queued for extraction.
- A background worker picks up pending entries and runs:
  1. **Embedding generation** — for the entry text (used for entry-level semantic search by the recall tools).
  2. **Fact extraction** — an LLM extracts atomic facts. Each fact has: text, event_time, entities, category, confidence.
  3. **Consolidation** — for each new fact, retrieve similar existing facts and decide ADD / UPDATE / DELETE / NOOP.
  4. **Fact embedding** — each new or updated fact gets its own embedding.
- Bi-temporal model: every fact has `valid_at`, `invalid_at`, `created_at`, `expired_at`. Old facts are never hard-deleted; they are marked invalid.
- Image-bearing entries: the memory record points at the image blob in Supabase Storage by stable ID. Image embedding (CLIP or similar for visual recall) is deferred to V2 — see §13.
- Failed extractions retry with exponential backoff. After 5 failures, the entry is marked `extraction_failed` and surfaced in a small "needs attention" section in settings.
- Extraction failures **never** affect the user's ability to see or browse their memory — the entry table is the source of truth.

**Acceptance:** New entries become queryable as facts within 60 seconds of being saved (95th percentile). Extraction quality is measured against the eval set (§10) and exceeds plain-RAG baseline by at least 10 points on LLM-as-judge.

### 4.5 Standing user profile — MVP

A small, regularly-updated summary of who the user is and what's currently going on in their life. Used to give context to the extractor and the chat agent.

**Behaviors:**
- Stored as a single ~300–500 token text blob per user.
- Regenerated weekly by a `pg_cron`-scheduled job.
- The job reads the last 30 days of entries and a sample of older facts, then asks the LLM to write the profile.
- The profile is read on every fact extraction and prepended to the chat agent's system prompt.
- The user can view their profile in Settings, edit it manually, or trigger a regeneration.

**Acceptance:** Profile is regenerated weekly without user intervention. User can read and edit it.

### 4.6 Reminders — MVP

The chat is the only place reminders are created and the primary place they are managed. A flat list view in Settings exists for bulk management.

**Behaviors:**
- Reminders have: message, fire-at datetime, optional recurrence (none, daily, weekly).
- Created in chat ("remind me to call Mom on Saturday at 6pm"). The agent restates the parsed time and waits for confirmation before scheduling.
- Listed and edited via chat ("show me my reminders," "cancel the one about Mom") or via the Settings → Reminders list.
- A `pg_cron` job runs every minute to find undelivered reminders and dispatch via FCM.
- Delivered reminders are marked complete; recurring ones are rescheduled.
- Reminders the user marks as "snooze" reschedule for a user-chosen interval.

**Acceptance:** Reminders fire within 60 seconds of their scheduled time. Push notification is delivered to the device. Recurring reminders work correctly across timezones.

### 4.7 Weekly review — V2

A guided once-a-week ritual where the user reviews recent patterns and clarifies vague memories. Delivered through the chat surface, not a dedicated screen.

**Behaviors:**
- A push notification on Sunday evenings invites the user to open the chat for their weekly review.
- Tapping the notification opens the chat with a fresh agent message containing:
  1. A 3–5 sentence weekly summary.
  2. A mood trend snippet (rendered as a compact inline chart).
  3. 3–5 low-confidence facts surfaced as inline confirm/edit/discard prompts within the thread.
  4. 1–2 surfaced patterns ("you mentioned 'tired' 6 times this week" or "you've been writing about Sarah a lot").
- The user can ignore it; nothing is blocking.

**Acceptance:** Weekly review notification fires once a week at user-configurable time. The chat message renders within 2 seconds of opening. User-confirmed facts have confidence raised to "high"; discarded facts are deleted.

### 4.8 "On this day" — V2

A passive recall feature delivered through the chat surface plus an optional push notification. No separate screen.

**Behaviors:**
- Optional daily push notification at user-configurable time (default 9am).
- Tapping the notification opens the chat with a fresh agent message showing memories from this date 1, 2, and 5 years ago, with tap-through links into the memory browser detail view.
- If there are no prior-year memories on this date, no notification is sent (no empty pings).
- The user can also ask the chat at any time ("what was I doing on this day last year?").

**Acceptance:** Notification fires at the configured time. The chat message shows only memories from prior years on this exact local date.

### 4.9 Settings & data control — MVP

Settings is reachable via a header icon from either the chat surface or the memory browser. It is not a third bottom-tab — it is a modal-style screen.

Contents:
- Profile view and edit (see §4.5).
- Notification preferences (which notifications are enabled, what time).
- Model selection (which LLM to use via OpenRouter — Claude, GPT, etc.). Default is set by developer; user can override.
- Reminders list (flat view of upcoming and recurring reminders, with edit/delete).
- "Needs attention" — entries whose extraction failed.
- Export all data (entries + facts + image references) as a JSON download.
- Delete account — permanently erases all data after confirmation.

**Acceptance:** User can export their full data. Account deletion removes everything within 24 hours and cannot be undone.

### 4.10 Offline support — MVP-light, V2-full

- **MVP:** Capture works offline. Chat messages and image attachments are queued locally and synced when online. Sending never fails due to lack of connectivity.
- **V2:** Memory browser caches the last N memories (with thumbnails) for offline browsing. Chat recall still requires online (the agent and tools are server-side).

**Acceptance:** User can capture (text and image) on an airplane and the captures sync correctly on reconnect. No duplicates, no lost messages, no lost images.

---

## 5. User flows (step-by-step)

### 5.1 First-time use
1. Open app → welcome screen.
2. Sign up with Google or email.
3. 3-card intro (skippable): "talk to your journal," "ask anything back," "your data, your control."
4. Land on chat with cursor focused. Placeholder text: "What's on your mind?"

### 5.2 Daily capture (text or voice)
1. Open app → chat is the default screen.
2. User types or holds-to-record. (Voice: hold the mic, release to transcribe; transcript is editable in the input before sending.)
3. Tap send. Within 200ms, the message appears in the thread and the agent acknowledges with a brief "saved." (No spinner.)
4. Input clears. Cursor stays focused. User can send another message immediately.
5. In the background: fact extraction queues. User does not wait.

### 5.3 Capturing with an image
1. In chat, user taps the attachment button, picks one or more photos, optionally types text ("hike with Anna at Ridge Trail"), and sends.
2. The message appears immediately with image thumbnails. Upload progresses in the background.
3. Agent acknowledges "saved." The new memory bundles the text and image(s).
4. Once upload completes, the memory and its images are visible in the memory browser.

### 5.4 Asking the journal a question
1. In chat, user types a question, e.g., "What was I working on this time last year?"
2. Agent responds: "Searching your memory…" (visible tool indicator) → streams an answer that cites specific memories by date.
3. User can tap a cited date to open that memory in the memory browser detail view.
4. User asks a follow-up in the same thread. Conversation persists.

### 5.5 Setting a reminder via chat
1. User: "Remind me to call Mom on Saturday at 6pm."
2. Agent confirms in plain language: "Got it — I'll remind you Saturday May 9 at 6:00pm to call Mom. Sound right?"
3. User: "yep."
4. Agent confirms it's scheduled.
5. Saturday at 6pm: push notification fires.

### 5.6 Attaching an image to an existing memory
1. User sends an image in chat with the message: "Add this to my Yosemite trip memory."
2. Agent searches for a matching memory, finds the most likely match, and replies: "Found a memory from April 12 about the Yosemite trip — attaching this photo to it. Right one?"
3. User: "yes."
4. Agent confirms attached. Opening that memory in the browser now shows the new image.
5. If the agent finds more than one plausible match, it lists 2–3 candidates and asks the user to pick.

### 5.7 Browsing memory
1. User taps the memory browser icon in the chat header.
2. Sees a reverse-chronological grid of memories with thumbnails for any with images.
3. Taps a memory to open its detail view.
4. Edits a typo, adds a tag, or attaches another image picked from the photo library.
5. Backs out — chat thread is right where they left it.

### 5.8 Weekly review
1. Sunday 7pm: push notification "Your week, in review."
2. User taps → opens chat with a fresh agent message: a short weekly summary, a small mood-trend chart, a few low-confidence facts presented inline.
3. User taps confirm/edit/discard on each surfaced fact directly in the thread.
4. Conversation continues as normal afterwards.

### 5.9 Recovering after offline period
1. User opens app after a flight. 4 unsynced messages and 2 image uploads queued locally.
2. App detects connection, syncs in background.
3. Toast: "4 messages, 2 images synced."
4. Extraction queues each on the backend; memories appear in the browser as they finalize.

---

## 6. System behaviors and rules

These are non-feature behaviors that govern how the system works overall.

### 6.1 Synchronous vs asynchronous boundary
- **Synchronous (user waits):** chat-message persistence (capture or otherwise), memory edit, memory delete, memory-browser list/detail read, profile read.
- **Asynchronous (user does not wait):** intent classification on the message, fact extraction, embedding generation, image upload, profile regeneration, reminder dispatch, weekly review generation.
- The synchronous path **must not** depend on any LLM call. The chat send returns as soon as the message row is written; the agent's reply (including capture acknowledgment) streams asynchronously.
- Image upload is async after the chat message is recorded. The UI shows a placeholder/thumbnail immediately; the memory record is updated with the storage reference once upload completes.
- LLM outages must never block the user from sending or browsing.

### 6.2 Source of truth
- The `entries` table — one row per user chat turn — is the source of truth. All other data (memories-as-shown, facts, embeddings, profile, image references) is derived and rebuildable, except the image blobs themselves (stored in Supabase Storage with stable IDs).
- Any bug in the extraction or intent-classification pipeline is recoverable by re-running over existing entries. Build a "reprocess all entries" admin command from day one.

### 6.3 Idempotency
- Sending the same chat message twice (due to network retries) must not create duplicates. The mobile app generates a client-side UUID per message and the backend uses it for upsert.
- Image uploads use a content hash to dedupe identical attachments — re-uploading the same image returns the existing storage reference rather than creating a duplicate blob.
- Re-running extraction on an entry must not duplicate facts. The extraction worker checks if facts already exist for an entry and skips or replaces them based on a versioning strategy.

### 6.4 Privacy and data handling
- All user data is encrypted at rest (Supabase default), including images in Storage.
- The OpenRouter API call is made from the FastAPI backend, never from the client. The client never holds an LLM API key.
- Logs do not contain message content or image bytes. Only IDs, timestamps, and error types.
- Image URLs are signed and short-lived; blobs are not publicly readable.
- The user can export and delete all their data (§4.9).

### 6.5 Rate limiting and cost control
- Each user has a soft daily LLM budget (tracked in the database). Default: 200 LLM calls per day.
- If the budget is exceeded, the chat continues but the agent uses cheaper models until the budget resets.
- Extraction is essentially unlimited — it's cheap and async.

### 6.6 Failure modes
- **Backend down:** mobile app shows offline mode. Messages and image uploads queue locally.
- **LLM provider down:** writes succeed. Extractions queue. Chat endpoint returns a friendly error.
- **Database down:** backend returns 503; mobile app retries with backoff.
- **FCM down:** reminders queue and fire when service recovers.

### 6.7 Time and timezone handling
- All timestamps stored in UTC.
- The mobile app sends the user's current timezone with each API call.
- Reminders are stored with timezone information and fire correctly across DST changes.
- "This day last year" uses the user's local date, not UTC.

---

## 7. The chat agent — behavioral specification

The agent is the user-facing personality of the app. It does capture, recall, reminders, and image-to-memory routing, in addition to setting tone.

### 7.1 Tone
- Warm but not saccharine. A thoughtful friend, not a chipper assistant.
- Concise. The user is on a phone, not at a desk.
- Honest about uncertainty. If memory doesn't contain enough context, says so rather than fabricating.
- Never therapeutic-overreach. Does not diagnose, does not push the user toward "feelings work" they didn't ask for.

### 7.2 Intent classification
Each user turn is routed into one of five intents before any tool is called:

1. **capture** — the user is sharing a thought, event, or observation. Default for any message that is not clearly a question, command, or attachment-routing request.
2. **recall** — the user is asking a question about their past ("what was…", "when did…", "tell me about…").
3. **reminder** — the user wants something scheduled ("remind me to…", "ping me at…").
4. **image-attach** — the message contains an image AND the text references an existing memory ("add this to…", "this goes with…", "for my X memory").
5. **meta** — settings, profile edits, or chat-control commands ("change the model," "edit my profile").

Rules:
- A message with an image and no clear "attach to existing" wording is **capture**, not image-attach.
- Ambiguous messages default to **capture** (it's reversible — the user can edit or delete the memory). If the message looks like a question phrased as a statement, the agent may ask one short clarifying turn before saving.
- No more than one clarifying question per intent.

### 7.3 Tools
The agent has the following tools available:

**Capture / write tools:**
- `save_memory(text, image_refs?, mood?, tags?, event_date?)` — primary capture tool. Creates a new memory from the current chat turn.
- `attach_image_to_memory(image_ref, target_memory_id_or_query)` — attach an image to an existing memory by id or natural-language description; returns the matched target so the agent can confirm before committing.
- `set_reminder(message, when, recurrence?)` — schedule a push.
- `clarify_fact(fact_id, new_text)` — when the user corrects something the system extracted.
- `update_profile(new_text)` — edit the standing user profile.

**Recall / read tools:**
- `search_facts(query, date_range?)` — distilled facts; primary lookup tool.
- `search_entries(query, date_range?)` — full original entries; for narrative context.
- `list_memories(filters?)` — returns memory cards for chat queries like "show me memories from last March." Used to surface candidates the user can tap into.
- `get_entries_around(date, window_days)` — temporal context.
- `get_timeline(entity)` — chronological facts about a specific entity.
- `get_user_profile()` — standing summary.

The agent prefers `search_facts` first, falling back to `search_entries` for richer context. It never calls more than 5 tools per turn.

### 7.4 Response format
- For **capture**: a short acknowledgment ("saved.") rather than full prose. If the agent inferred mood or tags, it states them in one short line so the user can correct.
- For **recall**: plain prose, mobile-friendly length (≤ 3 short paragraphs by default). Cites memories with dates the UI can detect and make tappable.
- For **reminder** and **image-attach**: a single restatement of the parsed action plus a yes/no confirmation prompt.
- No tables, no headers, no bullet lists unless the user explicitly asks for them or the answer is genuinely list-shaped.

### 7.5 Memory of the chat itself
- The agent remembers the current conversation thread.
- It does NOT have persistent memory across new conversations — each "new conversation" starts fresh, except for the user profile.
- Patterns the user repeatedly asks about should naturally show up in the user profile over time, not in chat memory.

---

## 8. Out of scope (explicit non-goals)

Listing things we are *not* building helps prevent scope creep.

- **Multi-user features.** No sharing, no friends, no public posts. Single-user app.
- **Multi-modal beyond text + voice + images.** No video, no drawings, no document attachments, no audio attachments beyond voice transcription.
- **A third screen.** The app is exactly two screens: chat and memory browser. Settings is a modal accessed from a header icon, not a tab. Anything that wants its own bottom-tab is out of scope.
- **A capture surface outside chat.** The composer-as-its-own-screen model is explicitly rejected. All capture goes through chat.
- **Coaching or therapy framing.** The app is a journal, not a wellness coach.
- **Social or gamification.** No streaks, no badges, no shame mechanics.
- **Cross-app integrations** (calendar, fitness, music). Pure journaling. Maybe V4.
- **Web app.** Mobile-only (RN handles iOS + Android).
- **Custom mood scales, custom categories, custom dashboards.** Defaults are fine.
- **End-to-end encryption.** Server-readable is acceptable for V1; the LLM needs to read entries to extract facts. E2EE is a separate, much larger problem.
- **Self-hosting for end users.** It's the developer's app for the developer's use. Other users are not a concern.

---

## 9. Phased delivery

The shape of the app — chat is the entire capture surface — means chat must ship in MVP. There is no "search-only" or "memory-pipeline-only" version that the developer can use, because there is no other surface to capture into. The phasing reflects that.

### Phase 1 (MVP) — chat and memory browser, end-to-end
**Deliverables:** Auth, chat surface (text + voice + image capture, intent classification, basic recall, capture acknowledgment), memory pipeline at minimum (embeddings + fact extraction + bi-temporal storage), standing profile, reminders via chat with FCM, memory browser screen, settings (with reminders list, profile edit, export, account delete), offline queue for messages and image uploads.
**Definition of done:** the developer uses it daily for 2 weeks. Captures, recalls, and reminders all work. Memory browser shows captures including images. No missing features the developer expects from this two-screen shape.

### Phase 2 — memory pipeline maturity and visual recall
**Deliverables:** Consolidation (ADD/UPDATE/DELETE/NOOP) tuned, bi-temporal queries used by recall tools, eval set built and ≥60% on LLM-as-judge across all five question categories, image embeddings for visual recall ("show me photos that look like the beach trip"), reprocess-all-entries admin command.
**Definition of done:** Eval ≥ 60%. Visual search returns plausible image matches. Re-extraction over the entire entry log produces stable facts.

### Phase 3 — proactive surfaces
**Deliverables:** Weekly review delivered as a chat message with inline confirm/edit/discard, "on this day" delivered via push + chat message, low-confidence fact confirmation flow, model selection UI in settings.
**Definition of done:** Scheduled jobs run reliably for 2 weeks. Eval ≥ 70%.

### Phase 4 — polish
**Deliverables:** Offline memory-browser caching, multi-device sync, performance tuning, accessibility audit.

---

## 10. Quality bar — how we know it works

### 10.1 Eval set
Before Phase 2 ships, build an eval set of 30 questions written against the developer's own real journal entries. Cover five categories:
- 10 single-hop ("when did X happen")
- 5 multi-hop ("what was I doing when Y started")
- 5 temporal ("this day last year," "before the move")
- 5 knowledge-update ("current opinion of Z" where opinion changed)
- 5 open-domain ("what kind of week was March")

Each question has an ideal answer written by the developer. The eval runner queries the system, compares against the ideal answer using LLM-as-judge, and reports a score per category and overall.

### 10.2 Performance bars
- Chat send (message persisted, ack returned): < 200ms p95 server-side
- Chat first token (recall responses): < 1s p95
- Memory browser initial render: < 500ms p95 for 1000 memories
- Memory detail view open: < 300ms p95
- Image upload: < 5s p95 for ≤ 5MB images on a 4G connection
- Fact extraction lag (message sent → facts queryable): < 60s p95
- Reminder firing accuracy: within 60s of scheduled time

### 10.3 Reliability bars
- Zero message losses tolerated. Ever.
- Zero image losses tolerated once upload has been acked.
- Extraction failures < 1% of entries.
- Reminder delivery success > 99%.

---

## 11. Deployment

### 11.1 Environments
- **Development:** local Docker Compose (FastAPI + worker + local Postgres for testing).
- **Staging:** Fly.io with a separate Supabase project.
- **Production:** Fly.io with the production Supabase project.

### 11.2 Single Docker image, two processes
The same image runs the FastAPI API server (`api` entrypoint) and the background worker (`worker` entrypoint). `fly.toml` defines two processes from this single image. This keeps deployment simple and ensures the worker always runs the same code as the API.

### 11.3 Configuration
All configuration is via environment variables. Required:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_DEFAULT_MODEL` (e.g., `anthropic/claude-3.5-sonnet`)
- `FCM_SERVER_KEY` (or service account JSON)
- `JWT_SECRET` (for backend-issued tokens if needed)

### 11.4 CI/CD
- Push to `main` branch → Docker build → deploy to staging.
- Manual promotion to production via `fly deploy`.
- Database migrations: managed via Supabase CLI, applied before deploy.

---

## 12. References

- `personal_memory_layer_guide.pdf` — implementation-level memory architecture, schemas, prompts. Read this before working on Phase 2 (memory pipeline).
- Mem0 paper: arXiv:2504.19413
- Zep/Graphiti paper: arXiv:2501.13956
- Mem0 reference implementation: github.com/mem0ai/mem0
- Graphiti reference implementation: github.com/getzep/graphiti

---

## 13. Open questions for the implementer

These are decisions deferred to implementation, not specified here:
- Exact Postgres schema (covered in `personal_memory_layer_guide.pdf` §7).
- Specific OpenAI SDK / OpenRouter wrapper structure.
- React Native navigation library choice (React Navigation is conventional).
- Local storage on the mobile app for offline (MMKV, SQLite, AsyncStorage — pick one).
- Specific extraction model (start with `anthropic/claude-3.5-haiku` via OpenRouter for cost; can switch later).
- Specific embedding model (OpenAI's `text-embedding-3-small` is the default; can switch).
- Image embedding strategy for V2 visual recall: CLIP for true visual similarity, vs. embedding the user's caption / agent-generated description text only. Trade-off: CLIP costs more and adds a dependency; caption-only is cheaper but loses the ability to search images by visual content alone.
- Image storage: bucket layout, signed-URL TTL for memory-browser thumbnails vs. detail views, thumbnail generation (server-side or on-the-fly transform).
- Whether photos sent without any accompanying text are valid captures (probably yes, with a default caption like "photo on 2026-05-02"; the agent should also try to auto-generate a one-line description with a vision model).
- Exact retry/backoff parameters for the worker.
- Specific eval-runner implementation (a script that calls the API and writes scores to a CSV is sufficient).
- Navigation pattern between the two screens (header icon, swipe gesture, or both) — decide based on RN ergonomics.

The implementer should make pragmatic choices for these and document them in a `DECISIONS.md` file in the repo.
