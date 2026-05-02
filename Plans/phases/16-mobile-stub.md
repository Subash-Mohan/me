# Phase 16 — Mobile (React Native) — placeholder

This phase is **not for implementation yet**. It exists so the backend phases (00–15) can ship without forgetting that a mobile app is the eventual consumer.

When the user is ready to start mobile work, we'll expand this single placeholder into multiple per-feature mobile plans (one per file, same template as the backend phases).

## Mobile chunks to plan later

- **M0 — RN app shell**: project scaffold (Expo or bare RN — to be decided), navigation library, env config for the API base URL, JWT storage in secure keychain, login/signup screens.
- **M1 — Chat surface**: scrollable thread, input box, SSE streaming, attachment button, voice-to-text, drafts auto-persist, tool-status indicators.
- **M2 — Memory browser**: reverse-chronological grid, date + tag filters, detail view with edit/attach/delete, image gallery.
- **M3 — Offline queue**: local persistence (MMKV vs SQLite vs AsyncStorage — decide here), outbound queue for messages and image uploads, idempotency on retry, sync indicator.
- **M4 — Push notifications**: FCM device-token registration, reminder notification handling, deep-link from notification → chat thread.
- **M5 — Settings screen**: profile read/edit, notification prefs, model selection, export, delete account.
- **M6 — Polish**: weekly review chat surface, "on this day" notification + chat surface, accessibility audit, performance.

## Acceptance for **this** stub
- Confirms the order of mobile chunks above is the order we'll plan later.
- Lists the questions to resolve at the start of M0 (Expo vs bare RN, navigation lib, local-storage lib).

## Master-plan refs
- §4.2 (chat surface UX), §4.3 (memory browser UX), §4.10 (offline), §5 (user flows), §13 (open mobile-side questions).
