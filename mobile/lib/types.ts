/**
 * Render-only shapes used by chat UI components (`MessageBubble`,
 * `MessageList`, `MemoryCard`).
 *
 * These are NOT the server wire shapes. The server's typed mirrors live in
 * `mobile/lib/api/types.ts` (`ServerMessage`, `ToolEvent`, etc.). The
 * adapter at `mobile/lib/chat/adapter.ts` flattens server messages into
 * the `Message` shape below before they reach a component.
 */

export type MessageSender = "user" | "ai";

export type Message = {
  id: string;
  sender: MessageSender;
  text: string;
  images?: string[];
  timestamp: Date;
  memoryAdded?: MemoryCard;
  /**
   * True only for the in-flight assistant turn while text is still
   * streaming. The `MessageBubble` shows an inline three-dot indicator
   * when this is set and `text` is empty.
   */
  isStreaming?: boolean;
};

export type MemoryCard = {
  id: string;
  date: Date;
  title: string;
  excerpt: string;
  image?: string;
  images?: string[];
  tags: string[];
  location?: string;
};
