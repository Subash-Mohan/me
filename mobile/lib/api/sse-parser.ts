/**
 * Pure SSE wire parser. One responsibility: turn a streaming-text byte stream
 * (already decoded to UTF-8) into discrete `{event, data}` pairs.
 *
 * Knows nothing about packet types, knows nothing about transport, knows
 * nothing about React. Trivially unit-testable with string fixtures.
 *
 * Wire format produced by `sse-starlette` on the server:
 *
 *     event: <name>
 *     data: <json>
 *     <blank line>
 *
 * Keep-alive comment lines starting with `:` are ignored. Lines that don't
 * fit either shape are skipped — we never throw on malformed input, the
 * upstream stream is the source of truth.
 */

export type SseEvent = {
  event: string;
  data: string;
};

/**
 * Drives the running parse: append `chunk` to `leftover`, yield every fully
 * received `event:`/`data:` block, and return the new leftover for the
 * caller to thread into the next call.
 *
 * The blank-line separator is `\n\n`. Anything before the first `\n\n`
 * stays in `leftover` until the rest of the block arrives.
 */
export function splitSseBlocks(
  chunk: string,
  leftover: string,
): { events: SseEvent[]; leftover: string } {
  // SSE spec allows any of LF, CRLF, or lone CR as line terminators. The
  // server (sse-starlette over uvicorn) emits CRLF, so without normalization
  // the `\n\n` block separator is never found and every event sits in the
  // leftover until EOF — the stream appears to "hang" client-side.
  const buffer = (leftover + chunk).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const events: SseEvent[] = [];

  let cursor = 0;
  while (true) {
    const sep = buffer.indexOf("\n\n", cursor);
    if (sep < 0) break;
    const block = buffer.slice(cursor, sep);
    cursor = sep + 2;
    const parsed = parseBlock(block);
    if (parsed) events.push(parsed);
  }

  return { events, leftover: buffer.slice(cursor) };
}

function parseBlock(block: string): SseEvent | null {
  let event: string | null = null;
  let data: string | null = null;

  for (const line of block.split("\n")) {
    if (line.length === 0) continue;
    if (line.startsWith(":")) continue; // keep-alive comment
    if (line.startsWith("event: ")) {
      event = line.slice("event: ".length).trim();
    } else if (line.startsWith("data: ")) {
      data = line.slice("data: ".length);
    }
  }

  if (event === null || data === null) return null;
  return { event, data };
}
