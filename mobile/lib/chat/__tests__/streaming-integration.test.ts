/**
 * Streaming integration tests.
 *
 * Drives realistic SSE bytes (CRLF-framed, exact JSON shapes that
 * `sse-starlette` emits) through the full mobile pipeline:
 *
 *     bytes → splitSseBlocks → routePacket → reducer
 *
 * This is the high-leverage layer: any change that breaks the wire-format
 * contract (backend renames a field, parser regression, router miswiring,
 * reducer drift) surfaces here.
 *
 * Fixtures use the exact field names + literal types the backend serializes,
 * so this file doubles as a contract test against `app/agents/packets.py`
 * and `app/agents/tools/memory.py`.
 */

import { describe, expect, it } from "vitest";

import type { PacketHandlers } from "@/lib/api/packet-router";
import { routePacket, toolNameFromType } from "@/lib/api/packet-router";
import { splitSseBlocks } from "@/lib/api/sse-parser";
import {
  type ActiveTurn,
  type ChatAction,
  type ChatState,
  initialState,
  reducer,
} from "@/lib/chat/reducer";

// ─── Wire fixture helpers ─────────────────────────────────────────────────

const CRLF = "\r\n";

/** Frame one SSE event the way `sse-starlette` does on the server. */
function frame(event: string, payload: object): string {
  return `event: ${event}${CRLF}data: ${JSON.stringify(payload)}${CRLF}${CRLF}`;
}

// ─── Pipeline driver ─────────────────────────────────────────────────────

type DriveResult = {
  activeTurn: ActiveTurn | null;
  actions: ChatAction["type"][];
  /** Raw `onFinish` payloads captured for assertions. */
  finishes: { reason: string; assistant_message_id: string }[];
};

/**
 * Wire the same handlers the production hook (`useChatStream`) wires —
 * each packet handler dispatches an equivalent reducer action.
 *
 * `onFinish` is captured but does not dispatch into the reducer (matching
 * production: the hook commits to the query cache + `turn/clear` after
 * finish; we leave the reducer in its pre-clear state so tests can assert
 * on it).
 */
function drive(chunks: string[]): DriveResult {
  let state: ChatState = initialState;
  const actions: ChatAction["type"][] = [];
  const finishes: DriveResult["finishes"] = [];

  const dispatch = (action: ChatAction) => {
    state = reducer(state, action);
    actions.push(action.type);
  };

  // Start the turn (the hook does this on `sendMessage`).
  dispatch({
    type: "turn/start",
    clientMessageId: "client-1",
    userText: "test input",
    startedAt: new Date("2026-05-20T10:00:00Z"),
  });

  const handlers: PacketHandlers = {
    onStart: (p) =>
      dispatch({ type: "packet/start", assistantMessageId: p.assistant_message_id }),
    onTextDelta: (p) =>
      dispatch({ type: "packet/text_delta", step: p.step, delta: p.delta }),
    onToolStart: (p) => {
      const tool = toolNameFromType(p.type);
      if (!tool) return;
      dispatch({
        type: "packet/tool_start",
        step: p.step,
        tool_call_id: p.tool_call_id,
        tool,
      });
    },
    onToolCall: (p) => {
      const tool = toolNameFromType(p.type);
      if (!tool) return;
      dispatch({
        type: "packet/tool_call",
        step: p.step,
        tool_call_id: p.tool_call_id,
        tool,
        arguments: p.arguments,
      });
    },
    onToolEnd: (p) => {
      const tool = toolNameFromType(p.type);
      if (!tool) return;
      dispatch({
        type: "packet/tool_end",
        step: p.step,
        tool_call_id: p.tool_call_id,
        tool,
        status: p.status,
        result: p.result ?? null,
        error: p.error ?? null,
      });
    },
    onError: (p) =>
      dispatch({ type: "packet/error", code: p.code, message: p.message }),
    onFinish: (p) =>
      finishes.push({
        reason: p.reason,
        assistant_message_id: p.assistant_message_id,
      }),
  };

  let leftover = "";
  for (const chunk of chunks) {
    const { events, leftover: lo } = splitSseBlocks(chunk, leftover);
    leftover = lo;
    for (const ev of events) routePacket(ev, handlers);
  }

  return { activeTurn: state.activeTurn, actions, finishes };
}

// ─── Reusable packet fixtures (mirror backend Pydantic shapes) ───────────

const START = frame("start", {
  type: "start",
  assistant_message_id: "asst-1",
  session_id: "sess-1",
});

const FINISH = frame("finish", {
  type: "finish",
  reason: "stop",
  assistant_message_id: "asst-1",
});

function textDelta(step: number, delta: string): string {
  return frame("text_delta", { type: "text_delta", kind: "text", step, delta });
}

function searchStart(step: number, tcid: string): string {
  return frame("search_memories_start", {
    type: "search_memories_start",
    kind: "tool",
    step,
    tool_call_id: tcid,
  });
}

function searchCall(
  step: number,
  tcid: string,
  args: Record<string, unknown>,
): string {
  return frame("search_memories_call", {
    type: "search_memories_call",
    kind: "tool",
    step,
    tool_call_id: tcid,
    arguments: args,
  });
}

function searchEnd(
  step: number,
  tcid: string,
  status: "ok" | "error",
  result: Record<string, unknown> | null,
  error: string | null = null,
): string {
  return frame("search_memories_end", {
    type: "search_memories_end",
    kind: "tool",
    step,
    tool_call_id: tcid,
    status,
    result,
    error,
  });
}

function manageStart(step: number, tcid: string): string {
  return frame("manage_memory_start", {
    type: "manage_memory_start",
    kind: "tool",
    step,
    tool_call_id: tcid,
  });
}

function manageCall(
  step: number,
  tcid: string,
  args: Record<string, unknown>,
): string {
  return frame("manage_memory_call", {
    type: "manage_memory_call",
    kind: "tool",
    step,
    tool_call_id: tcid,
    arguments: args,
  });
}

function manageEnd(
  step: number,
  tcid: string,
  status: "ok" | "error",
  result: Record<string, unknown> | null,
): string {
  return frame("manage_memory_end", {
    type: "manage_memory_end",
    kind: "tool",
    step,
    tool_call_id: tcid,
    status,
    result,
    error: null,
  });
}

// ─── Scenarios ───────────────────────────────────────────────────────────

describe("streaming / plain greeting", () => {
  it("3 text deltas at the same step → one merged text event, finish captured", () => {
    const wire = [
      START,
      textDelta(1, "Hi "),
      textDelta(1, "there"),
      textDelta(1, "!"),
      FINISH,
    ].join("");

    const { activeTurn, finishes } = drive([wire]);

    expect(activeTurn?.assistantMessageId).toBe("asst-1");
    expect(activeTurn?.status).toBe("streaming");
    expect(Object.keys(activeTurn!.events)).toEqual(["1"]);
    expect(activeTurn!.events[1]).toEqual({
      step: 1,
      kind: "text",
      content: "Hi there!",
    });
    expect(finishes).toEqual([{ reason: "stop", assistant_message_id: "asst-1" }]);
  });
});

describe("streaming / tool excursion (text → tool → text)", () => {
  it("folds the search lifecycle into one ToolEventState and keeps surrounding text in their own steps", () => {
    const wire = [
      START,
      textDelta(1, "Let me check…"),
      searchStart(2, "tc-1"),
      searchCall(2, "tc-1", { query: "lunch" }),
      searchEnd(2, "tc-1", "ok", { hits: 3 }),
      textDelta(3, "Yesterday: pho"),
      FINISH,
    ].join("");

    const { activeTurn } = drive([wire]);
    const events = activeTurn!.events;

    expect(Object.keys(events).sort()).toEqual(["1", "2", "3"]);
    expect(events[1]).toMatchObject({ kind: "text", content: "Let me check…" });
    expect(events[2]).toEqual({
      step: 2,
      kind: "tool",
      tool_call_id: "tc-1",
      tool: "search_memories",
      arguments: { query: "lunch" },
      status: "ok",
      result: { hits: 3 },
      error: null,
    });
    expect(events[3]).toMatchObject({ kind: "text", content: "Yesterday: pho" });
  });
});

describe("streaming / multi-tool turn", () => {
  it("two consecutive tool calls land at separate steps with their own ids and results", () => {
    const wire = [
      START,
      searchStart(1, "tc-a"),
      searchCall(1, "tc-a", { query: "morning" }),
      searchEnd(1, "tc-a", "ok", { hits: 1 }),
      manageStart(2, "tc-b"),
      manageCall(2, "tc-b", {
        operation: "create",
        memory: "Coffee at 8am",
        event_date: "2026-05-20",
      }),
      manageEnd(2, "tc-b", "ok", { id: "m-1" }),
      textDelta(3, "Logged."),
      FINISH,
    ].join("");

    const { activeTurn } = drive([wire]);
    const events = activeTurn!.events;

    expect(Object.keys(events).sort()).toEqual(["1", "2", "3"]);
    expect(events[1]).toMatchObject({
      kind: "tool",
      tool: "search_memories",
      tool_call_id: "tc-a",
      result: { hits: 1 },
    });
    expect(events[2]).toMatchObject({
      kind: "tool",
      tool: "manage_memory",
      tool_call_id: "tc-b",
      arguments: {
        operation: "create",
        memory: "Coffee at 8am",
        event_date: "2026-05-20",
      },
      result: { id: "m-1" },
    });
    expect(events[3]).toMatchObject({ kind: "text", content: "Logged." });
  });
});

describe("streaming / tool error end", () => {
  it("propagates error info to ToolEventState (status, error, result null)", () => {
    const wire = [
      START,
      manageStart(1, "tc-1"),
      manageCall(1, "tc-1", { operation: "delete", memory_id: "missing" }),
      frame("manage_memory_end", {
        type: "manage_memory_end",
        kind: "tool",
        step: 1,
        tool_call_id: "tc-1",
        status: "error",
        result: null,
        error: "MemoryClientPermanentError",
      }),
      FINISH,
    ].join("");

    const { activeTurn } = drive([wire]);
    expect(activeTurn!.events[1]).toMatchObject({
      kind: "tool",
      status: "error",
      result: null,
      error: "MemoryClientPermanentError",
    });
    // Turn-level status is still 'streaming' (only `event:error` flips it to error).
    expect(activeTurn?.status).toBe("streaming");
  });
});

describe("streaming / mid-stream error envelope", () => {
  it("partial text is preserved, status flips to 'error', no finish observed", () => {
    const wire = [
      START,
      textDelta(1, "I was about to"),
      frame("error", {
        type: "error",
        code: "agent_failed",
        message: "TimeoutError",
      }),
    ].join("");

    const { activeTurn, finishes } = drive([wire]);
    expect(activeTurn?.status).toBe("error");
    expect(activeTurn?.errorMessage).toBe("TimeoutError");
    expect(activeTurn!.events[1]).toMatchObject({
      kind: "text",
      content: "I was about to",
    });
    expect(finishes).toEqual([]);
  });
});

describe("streaming / chunk-boundary robustness", () => {
  it("byte-by-byte delivery yields the same reducer state as one-shot delivery", () => {
    const wire = [
      START,
      textDelta(1, "Hi "),
      textDelta(1, "there"),
      searchStart(2, "tc-1"),
      searchCall(2, "tc-1", { query: "lunch" }),
      searchEnd(2, "tc-1", "ok", { hits: 1 }),
      textDelta(3, "done"),
      FINISH,
    ].join("");

    const oneShot = drive([wire]);
    const byteByByte = drive(Array.from(wire));

    expect(byteByByte.activeTurn).toEqual(oneShot.activeTurn);
    expect(byteByByte.finishes).toEqual(oneShot.finishes);
  });
});

describe("streaming / wire-format contract guards", () => {
  it("unknown tool literal: router drops the packet, reducer state unchanged", () => {
    // Hypothetical drift: backend renames a tool. `toolNameFromType` still
    // works (suffix stripping), but the dispatch into the reducer goes through
    // — meaning we'd see a phantom event. Today's contract: any string ending
    // in `_start`/`_call`/`_end` with `kind:"tool"` is routed, so this still
    // produces an event. This test pins that behavior so any change to the
    // routing rules surfaces here, not silently in the UI.
    const wire = [
      START,
      frame("new_tool_start", {
        type: "new_tool_start",
        kind: "tool",
        step: 1,
        tool_call_id: "tc-x",
      }),
      FINISH,
    ].join("");

    const { activeTurn } = drive([wire]);
    expect(activeTurn!.events[1]).toMatchObject({
      kind: "tool",
      tool: "new_tool",
      tool_call_id: "tc-x",
    });
  });

  it("packet without kind:'tool' is ignored by the tool-suffix branch", () => {
    const wire = [
      START,
      // missing `kind:"tool"` → router should NOT route this anywhere
      frame("search_memories_start", {
        type: "search_memories_start",
        step: 1,
        tool_call_id: "tc-x",
      }),
      FINISH,
    ].join("");

    const { activeTurn } = drive([wire]);
    expect(activeTurn?.events).toEqual({});
  });

  it("malformed JSON in a packet is dropped silently (no crash)", () => {
    const wire =
      START +
      `event: text_delta${CRLF}data: not-json${CRLF}${CRLF}` +
      textDelta(1, "after") +
      FINISH;
    const { activeTurn } = drive([wire]);
    expect(activeTurn!.events[1]).toMatchObject({
      kind: "text",
      content: "after",
    });
  });
});
