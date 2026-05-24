import { BlurView } from "expo-blur";
import type { LucideIcon } from "lucide-react-native";
import { Pressable, View } from "react-native";
import { colors } from "@/theme";

type Props = {
  icon: LucideIcon;
  accessibilityLabel: string;
  onPress?: () => void;
};

export function PillIconButton({ icon: Icon, accessibilityLabel, onPress }: Props) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => ({
        transform: [{ scale: pressed ? 0.95 : 1 }],
      })}
      className="overflow-hidden rounded-full"
    >
      <BlurView
        intensity={30}
        tint="dark"
        className="items-center justify-center rounded-full border border-border bg-surface-raised/80 p-2.5"
      >
        <View className="opacity-80">
          <Icon size={14} color={colors.foreground.secondary} />
        </View>
      </BlurView>
    </Pressable>
  );
}
