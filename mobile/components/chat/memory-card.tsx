import { Image } from "expo-image";
import { MapPin, Sparkles } from "lucide-react-native";
import { MotiView } from "moti";
import { Text, View } from "react-native";
import { Tag } from "@/components/ui/tag";
import { formatDateShort } from "@/lib/format";
import type { MemoryCard as MemoryCardType } from "@/lib/types";

type Props = {
  memory: MemoryCardType;
};

export function MemoryCard({ memory }: Props) {
  const hero = memory.images?.[0] ?? memory.image;
  return (
    <MotiView
      from={{ opacity: 0, scale: 0.95, translateY: 5 }}
      animate={{ opacity: 1, scale: 1, translateY: 0 }}
      transition={{ type: "timing", duration: 500, delay: 300 }}
      className="mt-3 overflow-hidden rounded-2xl border border-border bg-surface"
      style={{ width: 260 }}
    >
      {hero ? (
        <View className="h-20 w-full border-b border-border-subtle">
          <Image
            source={{ uri: hero }}
            style={{ width: "100%", height: "100%" }}
            contentFit="cover"
          />
        </View>
      ) : null}
      <View className="p-3">
        <View className="mb-2 flex-row items-center gap-1.5">
          <Sparkles size={10} color="#34d399" />
          <Text
            className="font-sansMedium uppercase text-foreground opacity-60"
            style={{ fontSize: 8, letterSpacing: 1.5 }}
          >
            Logged · {formatDateShort(memory.date)}
          </Text>
          {memory.location ? (
            <>
              <Text
                className="text-foreground opacity-40"
                style={{ fontSize: 8 }}
              >
                ·
              </Text>
              <View className="opacity-80">
                <MapPin size={10} color="#D4D4CE" />
              </View>
              <Text
                className="font-sansMedium uppercase text-foreground opacity-60"
                style={{ fontSize: 8, letterSpacing: 1.5 }}
              >
                {memory.location}
              </Text>
            </>
          ) : null}
        </View>
        <Text
          className="font-serif italic text-foreground-secondary opacity-80"
          style={{ fontSize: 13, lineHeight: 19 }}
        >
          {memory.excerpt}
        </Text>
        {memory.tags.length > 0 ? (
          <View className="mt-3 flex-row flex-wrap gap-1.5">
            {memory.tags.map((t) => (
              <Tag key={t} label={t} />
            ))}
          </View>
        ) : null}
      </View>
    </MotiView>
  );
}
