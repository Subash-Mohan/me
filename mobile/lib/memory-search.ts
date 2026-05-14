import type { MemoryCard } from "@/lib/types";

export function filterMemories(
  items: MemoryCard[],
  query: string,
): MemoryCard[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;

  return items.filter((m) => {
    if (m.title && m.title.toLowerCase().includes(q)) return true;
    if (m.excerpt && m.excerpt.toLowerCase().includes(q)) return true;
    if (m.tags?.some((t) => t.toLowerCase().includes(q))) return true;
    if (m.location && m.location.toLowerCase().includes(q)) return true;

    const long = m.date
      .toLocaleDateString("en-US", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
      .toLowerCase();
    const short = m.date
      .toLocaleDateString("en-US", { day: "2-digit", month: "short" })
      .toLowerCase();

    return long.includes(q) || short.includes(q);
  });
}
