import { useEffect, useRef } from "react";
import { type NativeScrollEvent, type NativeSyntheticEvent, ScrollView, View } from "react-native";
import { MessageBubble } from "@/components/chat/message-bubble";
import { TopFadeMask } from "@/components/chat/top-fade-mask";
import type { Message } from "@/lib/types";

const SCROLL_TOP_THRESHOLD = 80;

type Props = {
  messages: Message[];
  /**
   * Called once the user scrolls within `SCROLL_TOP_THRESHOLD` of the top.
   * The caller is expected to debounce / no-op when there's nothing more to
   * load — this component just fires the trigger.
   */
  onScrollTopReached?: () => void;
};

export function MessageList({ messages, onScrollTopReached }: Props) {
  const scrollRef = useRef<ScrollView>(null);
  const firedTopRef = useRef(false);

  useEffect(() => {
    const t = setTimeout(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    }, 60);
    return () => clearTimeout(t);
  }, [messages.length]);

  const handleScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (!onScrollTopReached) return;
    const y = e.nativeEvent.contentOffset.y;
    if (y <= SCROLL_TOP_THRESHOLD) {
      if (firedTopRef.current) return;
      firedTopRef.current = true;
      onScrollTopReached();
    } else {
      firedTopRef.current = false;
    }
  };

  return (
    <View className="relative flex-1">
      <ScrollView
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
        onScroll={handleScroll}
        scrollEventThrottle={120}
        contentContainerStyle={{
          paddingHorizontal: 20,
          paddingTop: 120,
          paddingBottom: 160,
          gap: 24,
        }}
      >
        {messages.map((m, i) => (
          <MessageBubble key={m.id} message={m} index={i} />
        ))}
      </ScrollView>
      <TopFadeMask />
    </View>
  );
}
