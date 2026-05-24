import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useCallback, useEffect } from "react";
import { StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AsteroidField } from "@/components/chat/asteroid-field";
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
      <LinearGradient
        colors={["#1f1f1f", "#141414", "#070707"]}
        locations={[0, 0.5, 1]}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 1 }}
        style={StyleSheet.absoluteFillObject}
        pointerEvents="none"
      />
      <AsteroidField />
      <MessageList
        messages={chat.messages}
        onScrollTopReached={chat.hasOlder ? chat.fetchOlder : undefined}
      />
      <ChatHeader
        topInset={insets.top}
        onLogsPress={() => router.push("/logs")}
        onNewSessionPress={chat.newSession}
      />
      <ChatInput onSend={handleSend} bottomInset={insets.bottom} />
    </View>
  );
}
