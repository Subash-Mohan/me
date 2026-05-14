import { Text, View } from "react-native";

export function EndOfRecords() {
  return (
    <View className="items-center py-6">
      <Text
        className="font-sansMedium uppercase text-foreground"
        style={{ fontSize: 10, letterSpacing: 3, opacity: 0.3 }}
      >
        End of records
      </Text>
    </View>
  );
}
