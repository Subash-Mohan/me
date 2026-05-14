import { Text, View } from "react-native";

export function AvatarMark() {
  return (
    <View className="h-10 w-10 items-center justify-center rounded-full border border-border-subtle bg-surface-raised">
      <Text
        className="font-serif text-foreground"
        style={{ fontSize: 20, lineHeight: 22, marginTop: 2 }}
      >
        M.
      </Text>
    </View>
  );
}
