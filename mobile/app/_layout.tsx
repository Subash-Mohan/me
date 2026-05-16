import "../global.css";
import "react-native-reanimated";

import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useAppFonts } from "@/hooks/use-app-fonts";
import { MemoryProvider } from "@/lib/memory-store";

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function RootLayout() {
  const ready = useAppFonts();

  useEffect(() => {
    if (ready) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [ready]);

  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: "#121212" }}>
      <SafeAreaProvider>
        <MemoryProvider>
          <Stack
            screenOptions={{
              headerShown: false,
              animation: "fade",
              contentStyle: { backgroundColor: "#121212" },
            }}
          >
            <Stack.Screen name="index" />
            <Stack.Screen name="login" />
            <Stack.Screen name="chat" />
            <Stack.Screen
              name="logs"
              options={{ animation: "slide_from_right" }}
            />
          </Stack>
          <StatusBar style="light" />
        </MemoryProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
