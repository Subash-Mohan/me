import { useRouter } from "expo-router";
import { MotiView } from "moti";
import { useRef, useState } from "react";
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { Easing } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { PrimaryButton } from "@/components/ui/primary-button";

const EASE_OUT: [number, number, number, number] = [0.22, 1, 0.36, 1];

type RowConfig = {
  placeholder: string;
  keyboardType: "default" | "number-pad";
  autoCapitalize: "none" | "characters";
};

const ROWS: RowConfig[] = [
  { placeholder: "Numbers", keyboardType: "number-pad", autoCapitalize: "none" },
  { placeholder: "UPPERCASE", keyboardType: "default", autoCapitalize: "characters" },
  { placeholder: "lowercase", keyboardType: "default", autoCapitalize: "none" },
  { placeholder: "Alphanumeric", keyboardType: "default", autoCapitalize: "none" },
];

export function LoginScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [phrase, setPhrase] = useState<string[]>(["", "", "", ""]);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const inputsRef = useRef<(TextInput | null)[]>([null, null, null, null]);

  const isComplete = phrase.every((word) => word.trim().length > 0);

  const handleChange = (index: number, value: string) => {
    setPhrase((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
  };

  const handleSubmit = () => {
    if (!isComplete) return;
    router.replace("/chat");
  };

  return (
    <View className="flex-1">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          contentContainerStyle={{
            paddingTop: insets.top + 64,
            paddingBottom: insets.bottom + 48,
            paddingHorizontal: 24,
          }}
          showsVerticalScrollIndicator={false}
        >
          <View className="mx-auto w-full max-w-sm items-center">
            <MotiView
              from={{ opacity: 0, translateY: 20 }}
              animate={{ opacity: 1, translateY: 0 }}
              transition={{
                type: "timing",
                duration: 800,
                easing: Easing.bezier(...EASE_OUT),
              }}
              className="items-center"
            >
              <Text
                className="mb-4 font-serif italic uppercase text-white/40"
                style={{ fontSize: 10, letterSpacing: 3 }}
              >
                Access Identity
              </Text>
              <Text
                className="mb-2 font-serif italic text-white"
                style={{ fontSize: 36, lineHeight: 44 }}
              >
                Recovery.
              </Text>
            </MotiView>

            <MotiView
              from={{ opacity: 0, translateY: 12 }}
              animate={{ opacity: 1, translateY: 0 }}
              transition={{
                type: "timing",
                duration: 700,
                delay: 150,
                easing: Easing.bezier(...EASE_OUT),
              }}
            >
              <Text
                className="mb-10 text-center font-sans text-foreground-muted"
                style={{ fontSize: 14, lineHeight: 20 }}
              >
                Enter your 4-part recovery key to access your private memory
                logs.
              </Text>
            </MotiView>

            <MotiView
              from={{ opacity: 0, translateY: 12 }}
              animate={{ opacity: 1, translateY: 0 }}
              transition={{
                type: "timing",
                duration: 700,
                delay: 300,
                easing: Easing.bezier(...EASE_OUT),
              }}
              style={{ width: "100%", marginBottom: 40 }}
            >
              <View style={{ gap: 12 }}>
                {ROWS.map((row, i) => {
                  const focused = focusedIndex === i;
                  const isLast = i === ROWS.length - 1;
                  return (
                    <View key={row.placeholder} className="relative">
                      <View
                        pointerEvents="none"
                        style={{
                          position: "absolute",
                          left: 0,
                          top: 0,
                          bottom: 0,
                          width: 36,
                          justifyContent: "center",
                          paddingLeft: 12,
                          zIndex: 1,
                        }}
                      >
                        <Text
                          className="font-sans text-foreground-placeholder"
                          style={{
                            fontSize: 10,
                            textAlign: "right",
                            width: 16,
                          }}
                        >
                          {i + 1}.
                        </Text>
                      </View>
                      <TextInput
                        ref={(el) => {
                          inputsRef.current[i] = el;
                        }}
                        value={phrase[i]}
                        onChangeText={(v) => handleChange(i, v)}
                        onFocus={() => setFocusedIndex(i)}
                        onBlur={() => setFocusedIndex(null)}
                        placeholder={row.placeholder}
                        placeholderTextColor="rgba(212,212,206,0.35)"
                        keyboardType={row.keyboardType}
                        autoCapitalize={row.autoCapitalize}
                        autoCorrect={false}
                        spellCheck={false}
                        autoComplete="off"
                        returnKeyType={isLast ? "done" : "next"}
                        onSubmitEditing={() => {
                          if (isLast) {
                            Keyboard.dismiss();
                            handleSubmit();
                          } else {
                            inputsRef.current[i + 1]?.focus();
                          }
                        }}
                        className={`rounded-xl border bg-surface-raised py-4 pl-9 pr-3 font-sans text-foreground ${
                          focused ? "border-border-focus" : "border-border-subtle"
                        }`}
                        style={{ fontSize: 14 }}
                      />
                    </View>
                  );
                })}
              </View>
            </MotiView>

            <MotiView
              from={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{
                type: "timing",
                duration: 600,
                delay: 500,
                easing: Easing.bezier(...EASE_OUT),
              }}
              style={{ width: "100%" }}
            >
              <PrimaryButton
                label="Access Memory"
                onPress={handleSubmit}
                disabled={!isComplete}
              />
            </MotiView>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}
