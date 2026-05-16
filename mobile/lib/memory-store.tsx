import { createContext, type ReactNode, useContext } from "react";
import { MOCK_MEMORIES } from "@/constants/mock-data";
import type { MemoryCard } from "@/lib/types";

/**
 * Read-only memory list for the logs screen. Currently sourced from
 * `MOCK_MEMORIES`; the next phase will wire it to `GET /memories`.
 *
 * Memory creation now happens server-side via the agent's `manage_memory`
 * tool — there's no FE-side `addMemory` anymore.
 */
const MemoryContext = createContext<MemoryCard[] | null>(null);

export function MemoryProvider({ children }: { children: ReactNode }) {
  return (
    <MemoryContext.Provider value={MOCK_MEMORIES}>
      {children}
    </MemoryContext.Provider>
  );
}

export function useMemories(): MemoryCard[] {
  const ctx = useContext(MemoryContext);
  if (!ctx) {
    throw new Error("useMemories must be used inside MemoryProvider");
  }
  return ctx;
}
