import { MotiView } from "moti";
import { View } from "react-native";

function Dot({ delay }: { delay: number }) {
  return (
    <MotiView
      from={{ opacity: 0.3 }}
      animate={{ opacity: 1 }}
      transition={{
        type: "timing",
        duration: 600,
        delay,
        loop: true,
        repeatReverse: true,
      }}
      className="h-1.5 w-1.5 rounded-full bg-white/50"
    />
  );
}

export function TypingIndicator() {
  return (
    <View className="mb-2 flex-row items-center gap-1.5 self-start rounded-2xl rounded-tl-none border border-border-subtle bg-surface-raised px-4 py-4">
      <Dot delay={0} />
      <Dot delay={200} />
      <Dot delay={400} />
    </View>
  );
}
