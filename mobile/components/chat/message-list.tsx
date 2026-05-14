import { useEffect, useRef } from "react";
import { ScrollView, View } from "react-native";
import { MessageBubble } from "@/components/chat/message-bubble";
import { TopFadeMask } from "@/components/chat/top-fade-mask";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import type { Message } from "@/lib/types";

type Props = {
  messages: Message[];
  isTyping: boolean;
};

export function MessageList({ messages, isTyping }: Props) {
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    }, 60);
    return () => clearTimeout(t);
  }, [messages.length, isTyping]);

  return (
    <View className="relative flex-1">
      <ScrollView
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
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
        {isTyping ? <TypingIndicator /> : null}
      </ScrollView>
      <TopFadeMask />
    </View>
  );
}
