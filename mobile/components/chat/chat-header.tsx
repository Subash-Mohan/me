import { LayoutGrid, SquarePen } from "lucide-react-native";
import { MotiView } from "moti";
import { Text, View } from "react-native";
import { AvatarMark } from "@/components/ui/avatar-mark";
import { PillButton } from "@/components/ui/pill-button";
import { PillIconButton } from "@/components/ui/pill-icon-button";
import { StatusDot } from "@/components/ui/status-dot";

type Props = {
  onLogsPress?: () => void;
  onNewSessionPress?: () => void;
  topInset?: number;
};

export function ChatHeader({
  onLogsPress,
  onNewSessionPress,
  topInset = 0,
}: Props) {
  return (
    <MotiView
      from={{ opacity: 0, translateY: -10 }}
      animate={{ opacity: 1, translateY: 0 }}
      transition={{ type: "timing", duration: 280 }}
      pointerEvents="box-none"
      className="absolute left-0 right-0 z-20 flex-row items-center justify-between px-6 pb-3"
      style={{ top: topInset, paddingTop: 12 }}
    >
      <View className="flex-row items-center gap-3">
        <AvatarMark />
        <View className="flex-row items-center gap-2">
          <StatusDot />
          <Text
            className="font-sansMedium uppercase text-foreground opacity-50"
            style={{ fontSize: 9, letterSpacing: 1.8 }}
          >
            Listening
          </Text>
        </View>
      </View>
      <View className="flex-row items-center gap-2">
        <PillIconButton
          icon={SquarePen}
          accessibilityLabel="New session"
          onPress={onNewSessionPress}
        />
        <PillButton icon={LayoutGrid} label="Logs" onPress={onLogsPress} />
      </View>
    </MotiView>
  );
}
