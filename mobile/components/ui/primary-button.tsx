import { Pressable, Text } from "react-native";

type Props = {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  accessibilityLabel?: string;
};

export function PrimaryButton({
  label,
  onPress,
  disabled = false,
  accessibilityLabel,
}: Props) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      accessibilityLabel={accessibilityLabel ?? label}
      style={({ pressed }) => ({
        transform: [{ scale: pressed && !disabled ? 0.97 : 1 }],
        opacity: disabled ? 0.5 : 1,
        shadowColor: "#FFFFFF",
        shadowOpacity: disabled ? 0 : 0.1,
        shadowRadius: 20,
        shadowOffset: { width: 0, height: 0 },
        elevation: disabled ? 0 : 4,
      })}
      className={`w-full items-center justify-center rounded-xl py-4 ${
        disabled ? "bg-surface-highlight" : "bg-white"
      }`}
    >
      <Text
        className={`font-sansMedium uppercase ${
          disabled ? "text-foreground-placeholder" : "text-black"
        }`}
        style={{ fontSize: 13, letterSpacing: 2 }}
      >
        {label}
      </Text>
    </Pressable>
  );
}
