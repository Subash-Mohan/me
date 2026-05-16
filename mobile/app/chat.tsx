import { useRouter } from "expo-router";
import { useCallback, useEffect } from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChatHeader } from "@/components/chat/chat-header";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageList } from "@/components/chat/message-list";
import { useAuth } from "@/lib/auth/auth-store";
import { useChat } from "@/lib/chat/use-chat";

export default function ChatScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { status: authStatus } = useAuth();
  const chat = useChat();

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      router.replace("/login");
    }
  }, [authStatus, router]);

  const handleSend = useCallback(
    (text: string) => {
      chat.sendMessage(text);
    },
    [chat],
  );

  if (authStatus !== "authenticated") {
    return <View className="flex-1 bg-[#121212]" />;
  }

  return (
    <View className="flex-1 bg-[#121212]">
      <MessageList
        messages={chat.messages}
        onScrollTopReached={chat.hasOlder ? chat.fetchOlder : undefined}
      />
      <ChatHeader
        topInset={insets.top}
        onLogsPress={() => router.push("/logs")}
      />
      <ChatInput onSend={handleSend} bottomInset={insets.bottom} />
    </View>
  );
}
