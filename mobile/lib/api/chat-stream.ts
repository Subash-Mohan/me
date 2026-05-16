/**
 * Chat SSE transport.
 *
 * Sole responsibility: open `POST /chat`, stream the response body, decode
 * to UTF-8, drive the SSE parser, and route each event to the supplied
 * handlers.
 *
 * Uses `expo/fetch` (Expo SDK 52+, shipped with SDK 54) because RN's built-in
 * `fetch` cannot stream `response.body` as a real `ReadableStream` on iOS/Android.
 *
 * No state, no React, no awareness of reducers or query caches. The leaf
 * hook owns those; this module just turns one HTTP call into a sequence of
 * typed handler invocations.
 */

import { fetch } from "expo/fetch";

import { HttpError, NetworkError } from "./errors";
import type { PacketHandlers } from "./packet-router";
import { routePacket } from "./packet-router";
import { splitSseBlocks } from "./sse-parser";

export type StreamChatArgs = {
  sessionId: string;
  clientMessageId: string;
  message: string;
  clientTz: string;
};

export type StreamChatOptions = {
  token: string;
  baseUrl: string;
  signal: AbortSignal;
};

/**
 * Open an SSE stream against `POST /chat` and drive `handlers` until the
 * stream ends. Throws `HttpError` on non-2xx response, `NetworkError` on
 * transport failure. Aborts cleanly when `options.signal` aborts.
 */
export async function streamChat(
  args: StreamChatArgs,
  handlers: PacketHandlers,
  options: StreamChatOptions,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${options.baseUrl}/chat`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
        authorization: `Bearer ${options.token}`,
      },
      body: JSON.stringify({
        session_id: args.sessionId,
        client_message_id: args.clientMessageId,
        message: args.message,
        client_tz: args.clientTz,
      }),
      signal: options.signal,
    });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.text();
    } catch {
      // ignore
    }
    throw new HttpError(response.status, detail);
  }

  if (!response.body) {
    throw new HttpError(response.status, "no response body");
  }

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .getReader();
  let leftover = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const { events, leftover: nextLeftover } = splitSseBlocks(
        value ?? "",
        leftover,
      );
      leftover = nextLeftover;
      for (const event of events) routePacket(event, handlers);
    }
  } finally {
    reader.releaseLock();
  }
}
