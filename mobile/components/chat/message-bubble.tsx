import { Image } from "expo-image";
import { MotiView } from "moti";
import { memo } from "react";
import { Text, View } from "react-native";
import { MemoryCard } from "@/components/chat/memory-card";
import { formatTime } from "@/lib/format";
import type { Message } from "@/lib/types";

function StreamingDot({ delay }: { delay: number }) {
  return (
    <MotiView
      from={{ opacity: 0.3 }}
      animate={{ opacity: 1 }}
      transition={{
        type: "timing",
        duration: 600,
        delay,
        loop: true,
        repeatReverse: true,
      }}
      className="h-1.5 w-1.5 rounded-full bg-white/50"
    />
  );
}

type Props = {
  message: Message;
  index: number;
};

/**
 * Memoised with the default shallow prop comparator. During a streaming
 * turn the in-flight assistant message's `Message` reference changes on
 * every render, so that bubble re-renders. Every other (stable history)
 * bubble's reference stays identical across renders and is skipped.
 */
export const MessageBubble = memo(function MessageBubble({
  message,
  index,
}: Props) {
  const isUser = message.sender === "user";
  const stagger = Math.min(index * 30, 200);

  return (
    <MotiView
      from={{ opacity: 0, translateY: 10 }}
      animate={{ opacity: 1, translateY: 0 }}
      transition={{ type: "timing", duration: 400, delay: stagger }}
      className={`max-w-[85%] ${isUser ? "self-end items-end" : "self-start items-start"}`}
    >
      {message.images && message.images.length > 0 ? (
        <View
          className={`mb-2 w-full max-w-[240px] flex-row flex-wrap gap-2 ${isUser ? "justify-end" : "justify-start"}`}
        >
          {message.images.map((uri, idx) => {
            const single = message.images!.length === 1;
            return (
              <View
                key={`${uri}-${idx}`}
                className="overflow-hidden rounded-2xl border border-border-subtle"
                style={{
                  width: single ? "100%" : "48%",
                  aspectRatio: 1,
                }}
              >
                <Image
                  source={{ uri }}
                  style={{ width: "100%", height: "100%" }}
                  contentFit="cover"
                />
              </View>
            );
          })}
        </View>
      ) : null}

      {!isUser ? (
        <Text
          className="px-1 font-sansMedium uppercase italic text-foreground opacity-60"
          style={{
            fontSize: 10,
            letterSpacing: 1.5,
            marginBottom: 4,
          }}
        >
          {formatTime(message.timestamp)}
        </Text>
      ) : null}

      {message.text ? (
        <View
          className={
            isUser
              ? "rounded-2xl rounded-br-none bg-foreground-secondary px-4 py-3"
              : "rounded-2xl rounded-tl-none border border-border-subtle bg-surface-raised px-4 py-3"
          }
        >
          <Text
            className={`font-sans ${isUser ? "text-black" : "text-foreground-secondary"}`}
            style={{
              fontSize: 14,
              lineHeight: 21,
              textAlign: isUser ? "right" : "left",
            }}
          >
            {message.text}
          </Text>
        </View>
      ) : message.isStreaming ? (
        <View className="flex-row items-center gap-1.5 rounded-2xl rounded-tl-none border border-border-subtle bg-surface-raised px-4 py-4">
          <StreamingDot delay={0} />
          <StreamingDot delay={200} />
          <StreamingDot delay={400} />
        </View>
      ) : null}

      {message.memoryAdded ? <MemoryCard memory={message.memoryAdded} /> : null}

      {isUser ? (
        <Text
          className="px-1 font-sansMedium uppercase italic text-foreground opacity-60"
          style={{
            fontSize: 10,
            letterSpacing: 1.5,
            marginTop: 4,
          }}
        >
          {formatTime(message.timestamp)}
        </Text>
      ) : null}
    </MotiView>
  );
});
