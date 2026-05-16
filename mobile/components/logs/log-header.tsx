import { ArrowLeft } from "lucide-react-native";
import { MotiView } from "moti";
import { Text, View } from "react-native";
import { PillButton } from "@/components/ui/pill-button";

type Props = {
  onBack?: () => void;
  topInset?: number;
};

export function LogHeader({ onBack, topInset = 0 }: Props) {
  return (
    <MotiView
      from={{ opacity: 0, translateY: -10 }}
      animate={{ opacity: 1, translateY: 0 }}
      transition={{ type: "timing", duration: 280 }}
      pointerEvents="box-none"
      className="absolute left-0 right-0 z-20 flex-row items-center justify-center px-6"
      style={{ top: topInset, paddingTop: 12, paddingBottom: 12 }}
    >
      <View className="absolute bottom-0 left-6 top-0 justify-center">
        <PillButton icon={ArrowLeft} label="Back" onPress={onBack} />
      </View>
      <Text
        className="font-serif italic text-foreground"
        style={{ fontSize: 24, lineHeight: 30, marginTop: -6 }}
      >
        Log.
      </Text>
    </MotiView>
  );
}
