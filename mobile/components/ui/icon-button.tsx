import type { ReactNode } from "react";
import { Pressable } from "react-native";

type Variant = "filled-light" | "muted" | "ghost" | "raised";

const variantClass: Record<Variant, string> = {
  "filled-light": "bg-foreground-secondary",
  muted: "bg-surface-highlight",
  ghost: "bg-transparent",
  raised: "bg-surface-raised border border-border-subtle",
};

type Props = {
  children: ReactNode;
  onPress?: () => void;
  variant?: Variant;
  size?: number;
  className?: string;
  accessibilityLabel?: string;
  disabled?: boolean;
};

export function IconButton({
  children,
  onPress,
  variant = "muted",
  size = 32,
  className,
  accessibilityLabel,
  disabled,
}: Props) {
  const muteOpacity = variant === "muted" ? "opacity-80" : "";
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      hitSlop={6}
      style={({ pressed }) => ({
        width: size,
        height: size,
        transform: [{ scale: pressed ? 0.92 : 1 }],
      })}
      className={`items-center justify-center rounded-full ${variantClass[variant]} ${muteOpacity} ${className ?? ""}`}
    >
      {children}
    </Pressable>
  );
}
