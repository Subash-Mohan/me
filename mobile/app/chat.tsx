import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChatHeader } from "@/components/chat/chat-header";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageList } from "@/components/chat/message-list";
import { MOCK_MESSAGES } from "@/constants/mock-data";
import { useAuth } from "@/lib/auth/auth-store";
import { useAddMemory } from "@/lib/memory-store";
import type { MemoryCard, Message } from "@/lib/types";

const AI_REPLY_DELAY_MS = 400;
const AI_TYPING_MS = 1500;
const MEMORY_TRIGGER_TEXT_LENGTH = 20;

export default function ChatScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const addMemory = useAddMemory();
  const { status } = useAuth();
  const [messages, setMessages] = useState<Message[]>(MOCK_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status !== "authenticated") {
    return <View className="flex-1 bg-[#121212]" />;
  }

  const handleSend = (text: string, images?: string[], date?: Date) => {
    if (!text && (!images || images.length === 0)) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text,
      images,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);

    const looksLikeMemory =
      text.length > MEMORY_TRIGGER_TEXT_LENGTH ||
      (images != null && images.length > 0);

    setTimeout(() => {
      setIsTyping(true);
      setTimeout(() => {
        if (looksLikeMemory) {
          const memory: MemoryCard = {
            id: `m_${Date.now()}`,
            date: date ?? new Date(),
            title:
              text.split(/[.?!]/)[0].slice(0, 30) +
              (text.length > 30 ? "..." : ""),
            excerpt: text || "Visual memory logged.",
            tags: ["journal"],
            images,
            image: images?.[0],
            location: "Near Current Location",
          };
          addMemory(memory);

          const aiMsg: Message = {
            id: (Date.now() + 1).toString(),
            sender: "ai",
            text: "I've filed that away for you. It sounds like a meaningful moment.",
            timestamp: new Date(),
            memoryAdded: memory,
          };
          setMessages((prev) => [...prev, aiMsg]);
        } else {
          const aiMsg: Message = {
            id: (Date.now() + 1).toString(),
            sender: "ai",
            text: "Tell me more about it.",
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, aiMsg]);
        }
        setIsTyping(false);
      }, AI_TYPING_MS);
    }, AI_REPLY_DELAY_MS);
  };

  return (
    <View className="flex-1 bg-[#121212]">
      <MessageList messages={messages} isTyping={isTyping} />
      <ChatHeader
        topInset={insets.top}
        onLogsPress={() => router.push("/logs")}
      />
      <ChatInput onSend={handleSend} bottomInset={insets.bottom} />
    </View>
  );
}
