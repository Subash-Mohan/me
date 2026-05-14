import { Search, X } from "lucide-react-native";
import { Pressable, TextInput, View } from "react-native";

type Props = {
  value: string;
  onChange: (next: string) => void;
};

export function SearchBar({ value, onChange }: Props) {
  return (
    <View className="mb-5 w-full items-center">
      <View
        className="w-full flex-row items-center rounded-full border border-border bg-surface-raised px-4"
        style={{ maxWidth: 380, paddingVertical: 10 }}
      >
        <Search size={16} color="#A0A0A0" />
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder="Search logs by date, tag, or text..."
          placeholderTextColor="rgba(102,102,102,1)"
          className="ml-3 flex-1 font-sans text-foreground"
          style={{ fontSize: 14, paddingVertical: 0 }}
          returnKeyType="search"
          autoCapitalize="none"
          autoCorrect={false}
        />
        {value.length > 0 ? (
          <Pressable
            onPress={() => onChange("")}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Clear search"
            className="ml-2"
          >
            <X size={14} color="#A0A0A0" />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}
