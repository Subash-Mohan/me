import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { MOCK_MEMORIES } from "@/constants/mock-data";
import type { MemoryCard } from "@/lib/types";

type MemoryStore = {
  memories: MemoryCard[];
  addMemory: (memory: MemoryCard) => void;
};

const MemoryContext = createContext<MemoryStore | null>(null);

export function MemoryProvider({ children }: { children: ReactNode }) {
  const [memories, setMemories] = useState<MemoryCard[]>(MOCK_MEMORIES);

  const addMemory = useCallback((memory: MemoryCard) => {
    setMemories((prev) => [memory, ...prev]);
  }, []);

  const value = useMemo(() => ({ memories, addMemory }), [memories, addMemory]);

  return (
    <MemoryContext.Provider value={value}>{children}</MemoryContext.Provider>
  );
}

function useStore(): MemoryStore {
  const ctx = useContext(MemoryContext);
  if (!ctx) {
    throw new Error("useMemories/useAddMemory must be used inside MemoryProvider");
  }
  return ctx;
}

export const useMemories = (): MemoryCard[] => useStore().memories;
export const useAddMemory = (): MemoryStore["addMemory"] => useStore().addMemory;
