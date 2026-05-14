import { LinearGradient } from "expo-linear-gradient";
import { View } from "react-native";

type Props = {
  height?: number;
};

export function TopFadeMask({ height = 80 }: Props) {
  return (
    <View
      pointerEvents="none"
      className="absolute left-0 right-0 top-0 z-10"
      style={{ height }}
    >
      <LinearGradient
        colors={["#121212", "rgba(18,18,18,0.85)", "transparent"]}
        locations={[0, 0.6, 1]}
        style={{ flex: 1 }}
      />
    </View>
  );
}
