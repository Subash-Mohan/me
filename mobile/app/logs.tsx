import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { TopFadeMask } from "@/components/chat/top-fade-mask";
import { EmptyState } from "@/components/logs/empty-state";
import { EndOfRecords } from "@/components/logs/end-of-records";
import { LogHeader } from "@/components/logs/log-header";
import { MemoryDetailModal } from "@/components/logs/memory-detail-modal";
import { MemoryGrid } from "@/components/logs/memory-grid";
import { SearchBar } from "@/components/logs/search-bar";
import { filterMemories } from "@/lib/memory-search";
import { useMemories } from "@/lib/memory-store";
import type { MemoryCard } from "@/lib/types";

export default function LogsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const memories = useMemories();

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<MemoryCard | null>(null);

  const filtered = useMemo(
    () => filterMemories(memories, query),
    [memories, query],
  );

  return (
    <View className="flex-1 bg-[#121212]">
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{
          paddingTop: insets.top + 88,
          paddingBottom: insets.bottom + 16,
          paddingHorizontal: 20,
        }}
      >
        <SearchBar value={query} onChange={setQuery} />
        {filtered.length === 0 ? (
          <EmptyState />
        ) : (
          <MemoryGrid memories={filtered} onSelect={setSelected} />
        )}
        <EndOfRecords />
      </ScrollView>
      <TopFadeMask />
      <LogHeader topInset={insets.top} onBack={() => router.back()} />
      <MemoryDetailModal
        memory={selected}
        onClose={() => setSelected(null)}
      />
    </View>
  );
}
