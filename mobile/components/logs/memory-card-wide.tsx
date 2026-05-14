import { Image } from "expo-image";
import { MapPin } from "lucide-react-native";
import { Pressable, Text, View } from "react-native";
import { Tag } from "@/components/ui/tag";
import { formatGridDateShort } from "@/lib/format";
import type { MemoryCard as MemoryCardType } from "@/lib/types";

type Props = {
  memory: MemoryCardType;
  onPress: () => void;
};

export function MemoryCardWide({ memory, onPress }: Props) {
  const hero = memory.images?.[0] ?? memory.image;
  const extra =
    memory.images && memory.images.length > 1 ? memory.images.length - 1 : 0;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => ({
        width: "100%",
        transform: [{ scale: pressed ? 0.985 : 1 }],
      })}
    >
      <View className="rounded-2xl border border-border-subtle bg-surface p-5">
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
                >
                  {memory.location}
                </Text>
              </View>
            ) : null}
          </View>
        </View>

        {hero ? (
          <View className="relative mb-4 h-32 w-full overflow-hidden rounded-xl border border-border-subtle">
            <Image
              source={{ uri: hero }}
              style={{ width: "100%", height: "100%" }}
              contentFit="cover"
            />
            {extra > 0 ? (
              <View className="absolute right-2 top-2 rounded-md border border-white/10 bg-black/60 px-2 py-1">
                <Text
                  className="font-sansMedium uppercase text-white"
                  style={{ fontSize: 9, letterSpacing: 1.2 }}
                >
                  +{extra} visual{extra > 1 ? "s" : ""}
                </Text>
              </View>
            ) : null}
          </View>
        ) : null}

        <Text
          className="font-sans text-foreground-secondary opacity-90"
          style={{ fontSize: 14, lineHeight: 21 }}
        >
          {memory.excerpt}
        </Text>

        {memory.tags.length > 0 ? (
          <View className="mt-4 flex-row flex-wrap gap-2">
            {memory.tags.map((t) => (
              <Tag key={t} label={t} />
            ))}
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}
