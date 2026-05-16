/**
 * Pure server-shape → render-shape mapping for memory cards.
 *
 * The render `MemoryCard` (in `mobile/lib/types.ts`) carries a few fields
 * the server's list-view shape doesn't expose yet (`tags`, `image`,
 * `images`, `title`). All four are unused by the card components or
 * conditionally rendered, so the adapter leaves them empty/undefined for
 * now. When richer detail lands, fetch `MemoryDetail` on tap and adapt
 * that instead.
 */

import type { ServerMemoryCard } from "@/lib/api/types";
import type { MemoryCard } from "@/lib/types";

export function adaptServerMemoryCard(c: ServerMemoryCard): MemoryCard {
  return {
    id: c.id,
    date: new Date(`${c.event_date}T00:00:00`),
    title: "",
    excerpt: c.text_preview,
    location: c.location_label ?? undefined,
    tags: [],
  };
}
