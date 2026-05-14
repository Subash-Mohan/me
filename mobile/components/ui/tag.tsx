import { Text, View } from "react-native";

type Props = {
  label: string;
  className?: string;
};

export function Tag({ label, className }: Props) {
  return (
    <View
      className={`rounded-full bg-surface-highlight px-2 py-0.5 ${className ?? ""}`}
    >
      <Text
        className="font-sansMedium uppercase text-foreground-muted"
        style={{ fontSize: 8, letterSpacing: 1.2 }}
      >
        {label}
      </Text>
    </View>
  );
}
