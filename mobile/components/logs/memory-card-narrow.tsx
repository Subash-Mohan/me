import { Image } from "expo-image";
import { MapPin } from "lucide-react-native";
import { Pressable, Text, View } from "react-native";
import { formatGridDateShort } from "@/lib/format";
import type { MemoryCard as MemoryCardType } from "@/lib/types";

type Props = {
  memory: MemoryCardType;
  onPress: () => void;
};

export function MemoryCardNarrow({ memory, onPress }: Props) {
  const thumb = memory.images?.[0] ?? memory.image;
  const hasMultiple = (memory.images?.length ?? 0) > 1;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => ({
        width: "48%",
        transform: [{ scale: pressed ? 0.985 : 1 }],
      })}
    >
      <View className="min-h-[140px] rounded-2xl border border-border-subtle bg-surface p-5">
        <View className="mb-3 flex-row items-start justify-between">
          <View className="gap-1">
            <Text
              className="font-sansMedium uppercase text-foreground opacity-40"
              style={{ fontSize: 9, letterSpacing: 1.5 }}
            >
              {formatGridDateShort(memory.date)}
            </Text>
            {memory.location ? (
              <View className="flex-row items-center gap-1">
                <View className="opacity-50">
                  <MapPin size={8} color="#A0A0A0" />
                </View>
                <Text
                  className="font-sansMedium uppercase text-foreground opacity-30"
                  style={{ fontSize: 8, letterSpacing: 1.4 }}
                  numberOfLines={1}
                >
                  {memory.location}
                </Text>
              </View>
            ) : null}
          </View>
          {thumb ? (
            <View className="rounded-md border border-border bg-surface-highlight p-1">
              <View className="relative h-4 w-4 overflow-hidden rounded-sm">
                <Image
                  source={{ uri: thumb }}
                  style={{ width: "100%", height: "100%" }}
                  contentFit="cover"
                />
                {hasMultiple ? (
                  <View className="absolute inset-0 items-center justify-center bg-black/50">
                    <View
                      className="bg-white"
                      style={{
                        width: 2,
                        height: 2,
                        borderRadius: 1,
                        marginBottom: 1,
                      }}
                    />
                    <View
                      className="bg-white"
                      style={{ width: 2, height: 2, borderRadius: 1 }}
                    />
                  </View>
                ) : null}
              </View>
            </View>
          ) : null}
        </View>

        <View className="mt-auto">
          <Text
            className="font-serif italic text-foreground-secondary opacity-80"
            style={{ fontSize: 13, lineHeight: 19 }}
          >
            {memory.excerpt}
          </Text>
        </View>
      </View>
    </Pressable>
  );
}
