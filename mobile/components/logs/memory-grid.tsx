import { MotiView } from "moti";
import { Easing } from "react-native-reanimated";
import { View } from "react-native";
import { MemoryCardNarrow } from "@/components/logs/memory-card-narrow";
import { MemoryCardWide } from "@/components/logs/memory-card-wide";
import type { MemoryCard } from "@/lib/types";

type Props = {
  memories: MemoryCard[];
  onSelect: (memory: MemoryCard) => void;
};

export function MemoryGrid({ memories, onSelect }: Props) {
  return (
    <View
      style={{
        flexDirection: "row",
        flexWrap: "wrap",
        gap: 12,
        paddingBottom: 16,
      }}
    >
      {memories.map((memory, index) => {
        const isWide = index % 3 === 0;
        return (
          <MotiView
            key={memory.id}
            from={{ opacity: 0, scale: 0.95, translateY: 10 }}
            animate={{ opacity: 1, scale: 1, translateY: 0 }}
            transition={{
              type: "timing",
              duration: 420,
              delay: Math.min(index * 50, 400),
              easing: Easing.bezier(0.22, 1, 0.36, 1),
            }}
            style={{ width: isWide ? "100%" : "48%" }}
          >
            {isWide ? (
              <MemoryCardWide memory={memory} onPress={() => onSelect(memory)} />
            ) : (
              <MemoryCardNarrow
                memory={memory}
                onPress={() => onSelect(memory)}
              />
            )}
          </MotiView>
        );
      })}
    </View>
  );
}
