import { useRouter } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  ScrollView,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { TopFadeMask } from "@/components/chat/top-fade-mask";
import { EmptyState } from "@/components/logs/empty-state";
import { EndOfRecords } from "@/components/logs/end-of-records";
import { LogHeader } from "@/components/logs/log-header";
import { MemoryDetailModal } from "@/components/logs/memory-detail-modal";
import { MemoryGrid } from "@/components/logs/memory-grid";
import { SearchBar } from "@/components/logs/search-bar";
import { useAuth } from "@/lib/auth/auth-store";
import { useMemories } from "@/lib/memories/use-memories";
import { filterMemories } from "@/lib/memory-search";
import type { MemoryCard } from "@/lib/types";

const NEAR_BOTTOM_THRESHOLD = 120;

export default function LogsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { status: authStatus } = useAuth();
  const { memories, fetchOlder, hasOlder, isLoading } = useMemories();

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<MemoryCard | null>(null);
  const firedBottomRef = useRef(false);

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      router.replace("/login");
    }
  }, [authStatus, router]);

  const filtered = useMemo(
    () => filterMemories(memories, query),
    [memories, query],
  );

  const handleScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (!hasOlder) return;
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    const distanceFromBottom =
      contentSize.height - (contentOffset.y + layoutMeasurement.height);
    if (distanceFromBottom <= NEAR_BOTTOM_THRESHOLD) {
      if (firedBottomRef.current) return;
      firedBottomRef.current = true;
      fetchOlder();
    } else {
      firedBottomRef.current = false;
    }
  };

  if (authStatus !== "authenticated") {
    return <View className="flex-1 bg-[#121212]" />;
  }

  const showEmpty = !isLoading && filtered.length === 0;
  const showEndOfRecords = !hasOlder && memories.length > 0;

  return (
    <View className="flex-1 bg-[#121212]">
      <ScrollView
        showsVerticalScrollIndicator={false}
        onScroll={handleScroll}
        scrollEventThrottle={120}
        contentContainerStyle={{
          paddingTop: insets.top + 88,
          paddingBottom: insets.bottom + 16,
          paddingHorizontal: 20,
        }}
      >
        <SearchBar value={query} onChange={setQuery} />
        {showEmpty ? (
          <EmptyState />
        ) : (
          <MemoryGrid memories={filtered} onSelect={setSelected} />
        )}
        {showEndOfRecords ? <EndOfRecords /> : null}
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
