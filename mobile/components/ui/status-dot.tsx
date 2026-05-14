import { MotiView } from "moti";

export function StatusDot() {
  return (
    <MotiView
      from={{ opacity: 0.35 }}
      animate={{ opacity: 1 }}
      transition={{
        type: "timing",
        duration: 1400,
        loop: true,
        repeatReverse: true,
      }}
      className="h-1.5 w-1.5 rounded-full bg-status-listening"
    />
  );
}
