/**
 * SSE parser unit tests.
 *
 * The parser sees raw decoded text chunks from the network — chunk boundaries
 * are arbitrary and the backend (sse-starlette) frames events with CRLF.
 * The most important regression to catch here is "stream appears to hang":
 * if CRLF normalization or `leftover` threading regresses, every event sits
 * in the leftover buffer forever and the chat UI shows nothing.
 */

import { describe, expect, it } from "vitest";

import { splitSseBlocks } from "@/lib/api/sse-parser";

function feed(chunks: string[]): { events: { event: string; data: string }[] } {
  const out: { event: string; data: string }[] = [];
  let leftover = "";
  for (const c of chunks) {
    const { events, leftover: lo } = splitSseBlocks(c, leftover);
    leftover = lo;
    out.push(...events);
  }
  return { events: out };
}

const CRLF = "\r\n";

describe("splitSseBlocks", () => {
  it("parses a single complete CRLF event", () => {
    const wire = `event: text_delta${CRLF}data: {"delta":"hi"}${CRLF}${CRLF}`;
    const { events } = feed([wire]);
    expect(events).toEqual([{ event: "text_delta", data: '{"delta":"hi"}' }]);
  });

  it("parses multiple events in one chunk", () => {
    const wire =
      `event: start${CRLF}data: {"type":"start"}${CRLF}${CRLF}` +
      `event: text_delta${CRLF}data: {"delta":"hi"}${CRLF}${CRLF}` +
      `event: finish${CRLF}data: {"type":"finish"}${CRLF}${CRLF}`;
    const { events } = feed([wire]);
    expect(events.map((e) => e.event)).toEqual(["start", "text_delta", "finish"]);
  });

  it("preserves the trailing partial block in leftover until the next chunk", () => {
    const a = `event: start${CRLF}data: {"type":"start"}${CRLF}${CRLF}event: text_delta`;
    const b = `${CRLF}data: {"delta":"hi"}${CRLF}${CRLF}`;
    const { events } = feed([a, b]);
    expect(events.map((e) => e.event)).toEqual(["start", "text_delta"]);
    expect(events[1].data).toBe('{"delta":"hi"}');
  });

  it("survives byte-by-byte chunking (every split point)", () => {
    // Same wire bytes delivered one character at a time. This is the worst
    // case for chunk-boundary handling; if leftover threading is right, we
    // still see exactly the same events as the single-chunk delivery.
    const wire =
      `event: start${CRLF}data: {"type":"start","id":"a"}${CRLF}${CRLF}` +
      `event: text_delta${CRLF}data: {"delta":"hello"}${CRLF}${CRLF}` +
      `event: finish${CRLF}data: {"type":"finish"}${CRLF}${CRLF}`;
    const oneAtATime = Array.from(wire);
    const { events } = feed(oneAtATime);
    expect(events.map((e) => e.event)).toEqual(["start", "text_delta", "finish"]);
    expect(events[1].data).toBe('{"delta":"hello"}');
  });

  it("normalizes bare LF line endings (some proxies strip CR)", () => {
    const wire = `event: text_delta\ndata: {"delta":"x"}\n\n`;
    const { events } = feed([wire]);
    expect(events).toEqual([{ event: "text_delta", data: '{"delta":"x"}' }]);
  });

  it("does NOT split on bare CR (CR is reserved for partial-CRLF detection across chunks)", () => {
    // Classic-Mac bare-CR SSE is explicitly unsupported — see the comment in
    // splitSseBlocks. The block never has a `\n\n` separator, so no event
    // is emitted. This pins the contract; flipping it would re-introduce
    // the chunk-boundary "phantom \n\n" bug.
    const wire = `event: text_delta\rdata: {"delta":"x"}\r\r`;
    const { events } = feed([wire]);
    expect(events).toEqual([]);
  });

  it("ignores keep-alive comment lines starting with ':'", () => {
    const wire =
      `: ping${CRLF}${CRLF}` +
      `event: text_delta${CRLF}data: {"delta":"a"}${CRLF}${CRLF}`;
    const { events } = feed([wire]);
    expect(events).toEqual([{ event: "text_delta", data: '{"delta":"a"}' }]);
  });

  it("skips malformed blocks (no data line)", () => {
    const wire =
      `event: nothing${CRLF}${CRLF}` +
      `event: text_delta${CRLF}data: {"delta":"a"}${CRLF}${CRLF}`;
    const { events } = feed([wire]);
    expect(events.map((e) => e.event)).toEqual(["text_delta"]);
  });

  it("handles an empty chunk without losing state", () => {
    const a = `event: text_delta${CRLF}data: {"delta":"a"}${CRLF}`;
    const b = "";
    const c = `${CRLF}`;
    const { events } = feed([a, b, c]);
    expect(events).toEqual([{ event: "text_delta", data: '{"delta":"a"}' }]);
  });

  it("does not produce events when given only a partial block", () => {
    const partial = `event: text_delta${CRLF}data: {"delta":"a"}${CRLF}`;
    const { events } = feed([partial]);
    expect(events).toEqual([]);
  });
});
