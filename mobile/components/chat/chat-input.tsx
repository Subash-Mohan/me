import { BlurView } from "expo-blur";
import * as ImagePicker from "expo-image-picker";
import { Mic, Plus } from "lucide-react-native";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  TextInput,
  View,
} from "react-native";
import { ImagePreviewRow } from "@/components/chat/image-preview-row";
import { IconButton } from "@/components/ui/icon-button";

type Props = {
  onSend: (text: string, images?: string[]) => void;
  bottomInset?: number;
};

export function ChatInput({ onSend, bottomInset = 0 }: Props) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]);

  const hasContent = text.trim().length > 0 || images.length > 0;

  const reset = () => {
    setText("");
    setImages([]);
  };

  const handleSend = () => {
    if (!hasContent) return;
    onSend(text.trim(), images.length > 0 ? images : undefined);
    reset();
  };

  const pickImages = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsMultipleSelection: true,
      quality: 0.8,
      selectionLimit: 6,
    });
    if (!result.canceled) {
      setImages((prev) => [...prev, ...result.assets.map((a) => a.uri)]);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={0}
      pointerEvents="box-none"
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        paddingBottom: bottomInset + 16,
      }}
    >
      <View className="mx-4 overflow-hidden rounded-[32px] border border-border">
        <BlurView intensity={40} tint="dark" className="bg-surface-raised/85">
          <View className="p-2.5">
            {images.length > 0 ? (
              <ImagePreviewRow
                images={images}
                onRemove={(idx) =>
                  setImages((prev) => prev.filter((_, i) => i !== idx))
                }
              />
            ) : null}
            <View className="flex-row items-center gap-3 px-2 py-1.5">
              <IconButton
                onPress={pickImages}
                variant="muted"
                size={48}
                accessibilityLabel="Attach image"
              >
                <Plus size={24} color="#FFFFFF" strokeWidth={2} />
              </IconButton>
              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="Recall a moment..."
                placeholderTextColor="rgba(212,212,206,0.45)"
                className="flex-1 font-sans text-foreground-secondary"
                style={{ fontSize: 16, paddingVertical: 8 }}
                onSubmitEditing={handleSend}
                returnKeyType="send"
                multiline={false}
              />
              {hasContent ? (
                <IconButton
                  onPress={handleSend}
                  variant="filled-light"
                  size={48}
                  accessibilityLabel="Send"
                >
                  <View
                    className="bg-black"
                    style={{
                      width: 12,
                      height: 12,
                      transform: [{ rotate: "45deg" }],
                    }}
                  />
                </IconButton>
              ) : (
                <IconButton
                  variant="muted"
                  size={48}
                  accessibilityLabel="Record audio"
                >
                  <Mic size={22} color="#FFFFFF" />
                </IconButton>
              )}
            </View>
          </View>
        </BlurView>
      </View>
    </KeyboardAvoidingView>
  );
}
