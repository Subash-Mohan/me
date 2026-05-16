/**
 * Open-for-extension registry mapping tool names to render contributions.
 *
 * Adding UI for a new tool means registering one entry here. No other code
 * changes. Tools that are stored server-side but should NOT have UI (today:
 * `search_memories`) are deliberately absent from the registry — the
 * `applyToolRenderers` walker skips unknown tools.
 *
 * Pure: no React, no I/O. The output is plain data the adapter merges into
 * a `RenderMessage`.
 */

import type { MemoryCard } from "@/lib/types";
import type { ServerEvent, ToolEvent } from "@/lib/api/types";

/**
 * The slice of `RenderMessage` a tool renderer is allowed to contribute.
 * Today only `memoryAdded` is exposed — future tools can extend this union
 * by adding fields here.
 */
type RenderableTurnContribution = {
  memoryAdded?: MemoryCard;
};

type ToolRenderer = (event: ToolEvent) => RenderableTurnContribution | null;

const renderers: Record<string, ToolRenderer> = {
  manage_memory: (event) => {
    if (event.status !== "ok" || !event.result) return null;
    const memory = event.result.memory as Record<string, unknown> | undefined;
    if (!memory) return null;
    const card = toMemoryCard(memory);
    return card ? { memoryAdded: card } : null;
  },
  // `search_memories`: deliberately absent. Stored in `events` JSONB
  // server-side; invisible on the client by omission from this registry.
};

/**
 * Walk a turn's events and merge every tool's contribution into one shape.
 * Unknown tools (no registry entry) are no-ops. If multiple registered tools
 * fire in one turn, later contributions override earlier ones on the same
 * field — for `manage_memory` specifically this means "first successful card
 * wins" because the registry only sets `memoryAdded` when status is ok, and
 * the walker visits steps in increasing order.
 */
export function applyToolRenderers(
  events: readonly ServerEvent[],
): RenderableTurnContribution {
  let merged: RenderableTurnContribution = {};
  for (const event of events) {
    if (event.kind !== "tool") continue;
    const renderer = renderers[event.tool];
    if (!renderer) continue;
    const contribution = renderer(event);
    if (!contribution) continue;
    // Preserve the first-set semantics: skip fields already populated.
    merged = { ...contribution, ...merged };
  }
  return merged;
}

// ─── helpers ──────────────────────────────────────────────────────────────

function toMemoryCard(memory: Record<string, unknown>): MemoryCard | null {
  const id = stringField(memory, "id");
  const text = stringField(memory, "text") ?? "";
  const eventDate = stringField(memory, "event_date");
  if (!id || !eventDate) return null;

  const date = new Date(eventDate);
  if (Number.isNaN(date.getTime())) return null;

  const location = stringField(memory, "location_label") ?? undefined;
  return {
    id,
    date,
    title: deriveTitle(text),
    excerpt: text,
    tags: ["journal"],
    location,
  };
}

function stringField(
  obj: Record<string, unknown>,
  key: string,
): string | null {
  const v = obj[key];
  return typeof v === "string" ? v : null;
}

function deriveTitle(text: string): string {
  const head = text.split(/[.?!]/, 1)[0] ?? "";
  return head.length > 30 ? `${head.slice(0, 30)}...` : head;
}
