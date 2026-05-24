/**
 * Reducer unit tests.
 *
 * The reducer owns the in-flight assistant turn. Bugs here show up as
 * mis-rendered or duplicated/dropped chat content. The trickiest invariants:
 *
 *   - Consecutive text deltas at the same `step` MUST concatenate into one
 *     content string (not create two separate events).
 *   - A tool's `_start` → `_call` → `_end` at the same `step` MUST fold into
 *     one ToolEventState that picks up `arguments`, then `status`/`result`.
 *   - text → tool → text uses three distinct steps; the reducer must not
 *     overwrite an earlier text event when a later text event arrives at a
 *     different step.
 *   - Packets received with no active turn are silently dropped (no crashes).
 */

import { describe, expect, it } from "vitest";

import {
  type ChatAction,
  type ChatState,
  initialState,
  reducer,
} from "@/lib/chat/reducer";

function apply(state: ChatState, actions: ChatAction[]): ChatState {
  return actions.reduce((s, a) => reducer(s, a), state);
}

const startedAt = new Date("2026-05-20T10:00:00Z");
const TURN_START: ChatAction = {
  type: "turn/start",
  clientMessageId: "client-1",
  userText: "hi",
  startedAt,
};

describe("reducer / lifecycle", () => {
  it("initialState has no active turn", () => {
    expect(initialState.activeTurn).toBeNull();
  });

  it("turn/start initializes a streaming turn with no events", () => {
    const next = reducer(initialState, TURN_START);
    expect(next.activeTurn).toMatchObject({
      clientMessageId: "client-1",
      assistantMessageId: null,
      userText: "hi",
      startedAt,
      events: {},
      status: "streaming",
      errorMessage: null,
    });
  });

  it("packet/start sets assistantMessageId", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/start", assistantMessageId: "asst-1" },
    ]);
    expect(next.activeTurn?.assistantMessageId).toBe("asst-1");
  });

  it("turn/clear resets to initialState", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/start", assistantMessageId: "asst-1" },
      { type: "turn/clear" },
    ]);
    expect(next).toEqual(initialState);
  });

  it("drops packets when there is no active turn", () => {
    const stray: ChatAction[] = [
      { type: "packet/start", assistantMessageId: "x" },
      { type: "packet/text_delta", step: 1, delta: "x" },
      {
        type: "packet/tool_start",
        step: 1,
        tool_call_id: "x",
        tool: "search_memories",
      },
      { type: "packet/error", code: "x", message: "x" },
    ];
    for (const a of stray) {
      expect(reducer(initialState, a)).toBe(initialState);
    }
  });
});

describe("reducer / text deltas", () => {
  it("merges consecutive deltas at the same step into one content string", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/text_delta", step: 1, delta: "Hello " },
      { type: "packet/text_delta", step: 1, delta: "world" },
      { type: "packet/text_delta", step: 1, delta: "!" },
    ]);
    expect(next.activeTurn?.events).toEqual({
      1: { step: 1, kind: "text", content: "Hello world!" },
    });
  });

  it("creates a new event when the step changes", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/text_delta", step: 1, delta: "before" },
      { type: "packet/text_delta", step: 3, delta: "after" },
    ]);
    expect(next.activeTurn?.events).toEqual({
      1: { step: 1, kind: "text", content: "before" },
      3: { step: 3, kind: "text", content: "after" },
    });
  });

  it("treats an empty delta as a no-op-ish append (idempotent for ''+x)", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/text_delta", step: 1, delta: "x" },
      { type: "packet/text_delta", step: 1, delta: "" },
      { type: "packet/text_delta", step: 1, delta: "y" },
    ]);
    expect(next.activeTurn?.events[1]).toEqual({
      step: 1,
      kind: "text",
      content: "xy",
    });
  });
});

describe("reducer / tool lifecycle", () => {
  it("folds start → call → end into one ToolEventState at the same step", () => {
    const next = apply(initialState, [
      TURN_START,
      {
        type: "packet/tool_start",
        step: 2,
        tool_call_id: "tc-1",
        tool: "search_memories",
      },
      {
        type: "packet/tool_call",
        step: 2,
        tool_call_id: "tc-1",
        tool: "search_memories",
        arguments: { query: "lunch" },
      },
      {
        type: "packet/tool_end",
        step: 2,
        tool_call_id: "tc-1",
        tool: "search_memories",
        status: "ok",
        result: { hits: 3 },
      },
    ]);
    expect(next.activeTurn?.events[2]).toEqual({
      step: 2,
      kind: "tool",
      tool_call_id: "tc-1",
      tool: "search_memories",
      arguments: { query: "lunch" },
      status: "ok",
      result: { hits: 3 },
      error: null,
    });
  });

  it("captures error info on tool_end status='error'", () => {
    const next = apply(initialState, [
      TURN_START,
      {
        type: "packet/tool_start",
        step: 1,
        tool_call_id: "tc-1",
        tool: "manage_memory",
      },
      {
        type: "packet/tool_end",
        step: 1,
        tool_call_id: "tc-1",
        tool: "manage_memory",
        status: "error",
        error: "MemoryClientPermanentError",
      },
    ]);
    expect(next.activeTurn?.events[1]).toMatchObject({
      kind: "tool",
      status: "error",
      error: "MemoryClientPermanentError",
      result: null,
    });
  });

  it("two consecutive tool calls land at different steps (no overwrite)", () => {
    const next = apply(initialState, [
      TURN_START,
      {
        type: "packet/tool_start",
        step: 1,
        tool_call_id: "tc-1",
        tool: "search_memories",
      },
      {
        type: "packet/tool_end",
        step: 1,
        tool_call_id: "tc-1",
        tool: "search_memories",
        status: "ok",
        result: { hits: 1 },
      },
      {
        type: "packet/tool_start",
        step: 2,
        tool_call_id: "tc-2",
        tool: "manage_memory",
      },
      {
        type: "packet/tool_end",
        step: 2,
        tool_call_id: "tc-2",
        tool: "manage_memory",
        status: "ok",
        result: { created: 1 },
      },
    ]);
    expect(Object.keys(next.activeTurn!.events).sort()).toEqual(["1", "2"]);
    expect(next.activeTurn!.events[1]).toMatchObject({
      tool_call_id: "tc-1",
      result: { hits: 1 },
    });
    expect(next.activeTurn!.events[2]).toMatchObject({
      tool_call_id: "tc-2",
      result: { created: 1 },
    });
  });

  it("tool_call without prior tool_start still creates a ToolEventState (defensive)", () => {
    // Order shouldn't matter — server normally sends start first, but the
    // reducer must not crash or skip if a packet arrives standalone.
    const next = apply(initialState, [
      TURN_START,
      {
        type: "packet/tool_call",
        step: 1,
        tool_call_id: "tc-1",
        tool: "search_memories",
        arguments: { query: "x" },
      },
    ]);
    expect(next.activeTurn?.events[1]).toMatchObject({
      kind: "tool",
      tool_call_id: "tc-1",
      tool: "search_memories",
      arguments: { query: "x" },
      status: null,
    });
  });
});

describe("reducer / interleaving (text → tool → text)", () => {
  it("creates three distinct events at three different steps", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/text_delta", step: 1, delta: "Let me check" },
      {
        type: "packet/tool_start",
        step: 2,
        tool_call_id: "tc-1",
        tool: "search_memories",
      },
      {
        type: "packet/tool_call",
        step: 2,
        tool_call_id: "tc-1",
        tool: "search_memories",
        arguments: { query: "lunch" },
      },
      {
        type: "packet/tool_end",
        step: 2,
        tool_call_id: "tc-1",
        tool: "search_memories",
        status: "ok",
        result: { hits: 2 },
      },
      { type: "packet/text_delta", step: 3, delta: "Yesterday: pho" },
    ]);
    const events = next.activeTurn!.events;
    expect(Object.keys(events).sort()).toEqual(["1", "2", "3"]);
    expect(events[1]).toMatchObject({ kind: "text", content: "Let me check" });
    expect(events[2]).toMatchObject({ kind: "tool", tool_call_id: "tc-1" });
    expect(events[3]).toMatchObject({ kind: "text", content: "Yesterday: pho" });
  });
});

describe("reducer / error path", () => {
  it("packet/error sets status='error' and records the message", () => {
    const next = apply(initialState, [
      TURN_START,
      { type: "packet/text_delta", step: 1, delta: "thinking..." },
      { type: "packet/error", code: "agent_failed", message: "TimeoutError" },
    ]);
    expect(next.activeTurn?.status).toBe("error");
    expect(next.activeTurn?.errorMessage).toBe("TimeoutError");
    // partial content preserved so the UI can show what we got before failure
    expect(next.activeTurn?.events[1]).toMatchObject({
      kind: "text",
      content: "thinking...",
    });
  });
});
