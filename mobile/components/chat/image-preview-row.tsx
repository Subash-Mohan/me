import { Image } from "expo-image";
import { X } from "lucide-react-native";
import { Pressable, ScrollView, View } from "react-native";

type Props = {
  images: string[];
  onRemove: (idx: number) => void;
};

export function ImagePreviewRow({ images, onRemove }: Props) {
  if (images.length === 0) return null;
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: 8, paddingHorizontal: 8, paddingTop: 6, paddingBottom: 4 }}
    >
      {images.map((uri, idx) => (
        <View
          key={`${uri}-${idx}`}
          className="relative h-16 w-16 overflow-hidden rounded-xl border border-border"
        >
          <Image
            source={{ uri }}
            style={{ width: "100%", height: "100%" }}
            contentFit="cover"
          />
          <Pressable
            onPress={() => onRemove(idx)}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Remove image"
            className="absolute right-1 top-1 rounded-full bg-black/70 p-0.5"
          >
            <X size={12} color="#fff" />
          </Pressable>
        </View>
      ))}
    </ScrollView>
  );
}
