import { Calendar, X } from "lucide-react-native";
import { Pressable, Text, View } from "react-native";
import { formatDateMedium } from "@/lib/format";

type Props = {
  date: Date;
  onClear: () => void;
};

export function DateChip({ date, onClear }: Props) {
  return (
    <View className="flex-row items-center justify-between px-3 pb-2 pt-2">
      <View className="flex-row items-center gap-1.5">
        <Calendar size={10} color="#A0A0A0" />
        <Text
          className="font-sansMedium uppercase text-foreground-muted"
          style={{ fontSize: 10, letterSpacing: 1.5 }}
        >
          {formatDateMedium(date)}
        </Text>
      </View>
      <Pressable
        onPress={onClear}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel="Clear date"
      >
        <X size={12} color="#A0A0A0" />
      </Pressable>
    </View>
  );
}
