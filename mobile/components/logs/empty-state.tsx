import { Search } from "lucide-react-native";
import { Text, View } from "react-native";

export function EmptyState() {
  return (
    <View className="items-center justify-center py-16">
      <View className="opacity-40">
        <Search size={32} color="#A0A0A0" />
      </View>
      <Text
        className="mt-4 font-sans text-foreground-secondary opacity-50"
        style={{ fontSize: 14 }}
      >
        No logs found matching your search.
      </Text>
    </View>
  );
}
