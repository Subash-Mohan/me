import { LinearGradient } from "expo-linear-gradient";
import { MotiView } from "moti";
import { Text, View } from "react-native";

export function SplashScreen() {
  return (
    <View className="relative flex-1 items-center justify-center overflow-hidden bg-[#121212]">
      <LinearGradient
        colors={["rgba(26,26,26,1)", "transparent"]}
        style={{
          position: "absolute",
          width: 640,
          height: 640,
          borderRadius: 320,
          opacity: 0.5,
        }}
      />
      <MotiView
        from={{ opacity: 0, scale: 0.9, translateY: 20 }}
        animate={{ opacity: 1, scale: 1, translateY: 0 }}
        transition={{
          type: "timing",
          duration: 1200,
          delay: 300,
        }}
        className="z-10 items-center"
      >
        <Text
          className="mb-4 font-sansMedium uppercase text-white/40"
          style={{ fontSize: 10, letterSpacing: 3.5 }}
        >
          Breathe & Record
        </Text>
        <Text
          className="font-serif italic text-white"
          style={{ fontSize: 72, lineHeight: 80 }}
        >
          Me.
        </Text>
        <MotiView
          from={{ scaleY: 0 }}
          animate={{ scaleY: 1 }}
          transition={{ type: "timing", duration: 800, delay: 1000 }}
          className="mt-8 bg-foreground-secondary opacity-20"
          style={{
            width: 1,
            height: 64,
            transformOrigin: "top",
          }}
        />
      </MotiView>
    </View>
  );
}
