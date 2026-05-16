/**
 * Resolve the device's IANA timezone (e.g. "America/New_York").
 *
 * The backend's `ChatRequest.client_tz` and `record_user_message` expect
 * an IANA string — never an abbreviation. `Intl.DateTimeFormat` is available
 * in React Native 0.81 + Hermes.
 */

export function getTimezone(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (typeof tz === "string" && tz.length > 0) return tz;
  } catch {
    // fall through
  }
  return "UTC";
}
