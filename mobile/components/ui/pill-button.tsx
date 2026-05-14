import { BlurView } from "expo-blur";
import type { LucideIcon } from "lucide-react-native";
import { Pressable, Text, View } from "react-native";

type Props = {
  icon?: LucideIcon;
  label: string;
  onPress?: () => void;
};

export function PillButton({ icon: Icon, label, onPress }: Props) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => ({
        transform: [{ scale: pressed ? 0.95 : 1 }],
      })}
      className="overflow-hidden rounded-full"
    >
      <BlurView
        intensity={30}
        tint="dark"
        className="flex-row items-center gap-2 rounded-full border border-border bg-surface-raised/80 px-4 py-2.5"
      >
        {Icon ? (
          <View className="opacity-80">
            <Icon size={14} color="#D4D4CE" />
          </View>
        ) : null}
        <Text
          className="font-sansMedium uppercase text-foreground-secondary opacity-80"
          style={{ fontSize: 9, letterSpacing: 1.5 }}
        >
          {label}
        </Text>
      </BlurView>
    </Pressable>
  );
}
