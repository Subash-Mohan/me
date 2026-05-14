import { BlurView } from "expo-blur";
import { Image } from "expo-image";
import { MapPin, X } from "lucide-react-native";
import { AnimatePresence, MotiView } from "moti";
import {
  Pressable,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Easing } from "react-native-reanimated";
import { formatClockTime, formatDateLong } from "@/lib/format";
import type { MemoryCard } from "@/lib/types";

type Props = {
  memory: MemoryCard | null;
  onClose: () => void;
};

export function MemoryDetailModal({ memory, onClose }: Props) {
  const { height: screenHeight } = useWindowDimensions();
  const maxCardHeight = screenHeight * 0.82;

  return (
    <AnimatePresence>
      {memory ? (
        <View
          className="absolute inset-0 z-50 items-center justify-center px-5"
          pointerEvents="box-none"
        >
          <MotiView
            from={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: "timing", duration: 250 }}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            }}
          >
            <Pressable
              onPress={onClose}
              accessibilityLabel="Close detail"
              className="flex-1"
            >
              <BlurView
                intensity={25}
                tint="dark"
                style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.78)" }}
              />
            </Pressable>
          </MotiView>

          <MotiView
            from={{ opacity: 0, scale: 0.95, translateY: 10 }}
            animate={{ opacity: 1, scale: 1, translateY: 0 }}
            exit={{ opacity: 0, scale: 0.95, translateY: 10 }}
            transition={{
              type: "timing",
              duration: 320,
              easing: Easing.bezier(0.22, 1, 0.36, 1),
            }}
            style={{ width: "100%", maxWidth: 380, maxHeight: maxCardHeight }}
            className="overflow-hidden rounded-3xl border border-border bg-surface"
          >
            <ScrollView
              showsVerticalScrollIndicator={false}
              contentContainerStyle={{ padding: 24 }}
            >
              <View className="mb-4 flex-row items-start justify-between">
                <Text
                  className="font-sansMedium uppercase text-foreground opacity-50"
                  style={{ fontSize: 10, letterSpacing: 1.6, flexShrink: 1 }}
                >
                  {formatDateLong(memory.date)}
                  <Text style={{ opacity: 0.4 }}>  ·  </Text>
                  {formatClockTime(memory.date)}
                </Text>
                {memory.location ? (
                  <View
                    className="ml-3 flex-row items-center gap-1"
                    style={{ maxWidth: 140 }}
                  >
                    <View className="opacity-60">
                      <MapPin size={10} color="#A0A0A0" />
                    </View>
                    <Text
                      className="font-sansMedium uppercase text-foreground opacity-50"
                      style={{ fontSize: 10, letterSpacing: 1.6 }}
                      numberOfLines={1}
                    >
                      {memory.location}
                    </Text>
                  </View>
                ) : null}
              </View>

              <Text
                className="mb-6 font-serif italic text-foreground"
                style={{ fontSize: 17, lineHeight: 26 }}
              >
                {`“${memory.excerpt}”`}
              </Text>

              {memory.tags.length > 0 ? (
                <View className="mb-6 flex-row flex-wrap gap-2">
                  {memory.tags.map((tag) => (
                    <View
                      key={tag}
                      className="rounded-full border border-border bg-surface-highlight px-3 py-1.5"
                    >
                      <Text
                        className="font-sansMedium uppercase text-foreground-muted"
                        style={{ fontSize: 9, letterSpacing: 1.6 }}
                      >
                        {tag}
                      </Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {memory.images && memory.images.length > 0 ? (
                <View className="gap-3">
                  {memory.images.map((uri, idx) => (
                    <View
                      key={`${uri}-${idx}`}
                      className="w-full overflow-hidden rounded-xl border border-border-subtle"
                      style={{ aspectRatio: 16 / 10 }}
                    >
                      <Image
                        source={{ uri }}
                        style={{ width: "100%", height: "100%" }}
                        contentFit="cover"
                      />
                    </View>
                  ))}
                </View>
              ) : memory.image ? (
                <View
                  className="w-full overflow-hidden rounded-xl border border-border-subtle"
                  style={{ aspectRatio: 16 / 10 }}
                >
                  <Image
                    source={{ uri: memory.image }}
                    style={{ width: "100%", height: "100%" }}
                    contentFit="cover"
                  />
                </View>
              ) : null}
            </ScrollView>
          </MotiView>

          <MotiView
            from={{ opacity: 0, scale: 0.8, translateY: -8 }}
            animate={{ opacity: 1, scale: 1, translateY: 0 }}
            exit={{ opacity: 0, scale: 0.8, translateY: -8 }}
            transition={{
              type: "timing",
              duration: 320,
              delay: 80,
              easing: Easing.bezier(0.22, 1, 0.36, 1),
            }}
            style={{ marginTop: 12 }}
          >
            <Pressable
              onPress={onClose}
              accessibilityRole="button"
              accessibilityLabel="Close"
              hitSlop={10}
              style={({ pressed }) => ({
                width: 48,
                height: 48,
                transform: [{ scale: pressed ? 0.92 : 1 }],
              })}
              className="items-center justify-center rounded-full border border-white/10 bg-black/60"
            >
              <X size={16} color="#fff" />
            </Pressable>
          </MotiView>
        </View>
      ) : null}
    </AnimatePresence>
  );
}
