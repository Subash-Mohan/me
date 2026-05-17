import { useEffect, useMemo } from "react";
import {
  AppState,
  type AppStateStatus,
  StyleSheet,
  useWindowDimensions,
  View,
} from "react-native";
import Animated, {
  type SharedValue,
  useAnimatedStyle,
  useFrameCallback,
  useReducedMotion,
  useSharedValue,
} from "react-native-reanimated";
import Svg, { Defs, LinearGradient, Path, Stop } from "react-native-svg";
import { colors } from "@/theme";

const STAR_COUNT = 10;
const BASE_ANGLE_RAD = Math.PI / 6;
const ANGLE_VARIANCE_RAD = 0.14;
const MIN_SPEED_PX_S = 45;
const MAX_SPEED_PX_S = 95;
const MIN_TAIL_PX = 55;
const MAX_TAIL_PX = 100;
const MIN_HEAD_RADIUS_PX = 2.5;
const MAX_HEAD_RADIUS_PX = 3.75;
const MIN_OPACITY = 0.75;
const MAX_OPACITY = 1;
// Head's vertical extent as a ratio of its horizontal extent. <1 flattens
// the head into a half-ellipse so it doesn't bulb above the tail line.
const HEAD_HEIGHT_RATIO = 0.55;
// Quadratic-curve control-point lift, as a ratio of the head's half-height.
// Roughly the tail's max thickness midway between tip and head.
const TAIL_TAPER_RATIO = 0.35;
const SEED = 0xa57e801d;

type FallingStar = {
  id: number;
  tailLengthPx: number;
  headRadiusPx: number;
  angleRad: number;
  cosAngle: number;
  sinAngle: number;
  speedPxPerSec: number;
  opacity: number;
  phase: number;
  originX: number;
  originY: number;
};

// Deterministic PRNG keeps layout stable across renders without pulling
// in a crypto-grade randomness source.
function mulberry32(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildStars(
  width: number,
  height: number,
  travelDistance: number,
): FallingStar[] {
  const rand = mulberry32(SEED);
  const lerp = (a: number, b: number) => a + rand() * (b - a);
  return Array.from({ length: STAR_COUNT }, (_, id) => {
    const angleRad =
      BASE_ANGLE_RAD + (rand() - 0.5) * 2 * ANGLE_VARIANCE_RAD;
    const cosAngle = Math.cos(angleRad);
    const sinAngle = Math.sin(angleRad);
    // The motion axis is (cosAngle, sinAngle); the perpendicular axis is
    // (-sinAngle, cosAngle). A meteor's perpendicular coordinate is invariant
    // along its trajectory. Distributing this perpendicular offset uniformly
    // across the screen's projected perpendicular span spreads spawn points
    // along both the top edge and the left edge, instead of every meteor
    // entering through the left.
    const perpMin = -width * sinAngle * 0.85;
    const perpMax = height * cosAngle * 0.9;
    const perpPos = perpMin + rand() * (perpMax - perpMin);
    // Place the spawn so the envelope peak (distance = travelDistance / 2)
    // lines up with the meteor crossing the screen-center perpendicular line.
    const screenMidAlong = (width / 2) * cosAngle + (height / 2) * sinAngle;
    const spawnAlong = screenMidAlong - travelDistance / 2;
    return {
      id,
      tailLengthPx: lerp(MIN_TAIL_PX, MAX_TAIL_PX),
      headRadiusPx: lerp(MIN_HEAD_RADIUS_PX, MAX_HEAD_RADIUS_PX),
      angleRad,
      cosAngle,
      sinAngle,
      speedPxPerSec: lerp(MIN_SPEED_PX_S, MAX_SPEED_PX_S),
      opacity: lerp(MIN_OPACITY, MAX_OPACITY),
      phase: rand() * travelDistance,
      originX: spawnAlong * cosAngle - perpPos * sinAngle,
      originY: spawnAlong * sinAngle + perpPos * cosAngle,
    };
  });
}

type FallingStarViewProps = {
  star: FallingStar;
  progress: SharedValue<number>;
  travelDistance: number;
};

function FallingStarView({
  star,
  progress,
  travelDistance,
}: FallingStarViewProps) {
  const r = star.headRadiusPx;
  const headHalfHeight = r * HEAD_HEIGHT_RATIO;
  const tailLength = star.tailLengthPx;
  const svgWidth = tailLength;
  const svgHeight = headHalfHeight * 2;
  const midY = svgHeight / 2;
  const headCx = tailLength - r;
  const controlX = tailLength * 0.5;
  const controlOffset = headHalfHeight * TAIL_TAPER_RATIO;
  // Single closed teardrop: tail point at (0, midY), quadratic taper into a
  // half-ellipse head ending at (tailLength, midY). One Path means one fill,
  // which is the only way head + tail look like one continuous shape.
  const pathD =
    `M 0 ${midY} ` +
    `Q ${controlX} ${midY - controlOffset}, ${headCx} ${midY - headHalfHeight} ` +
    `A ${r} ${headHalfHeight} 0 0 1 ${headCx} ${midY + headHalfHeight} ` +
    `Q ${controlX} ${midY + controlOffset}, 0 ${midY} ` +
    `Z`;
  const bodyGradId = `body-${star.id}`;

  const animatedStyle = useAnimatedStyle(() => {
    "worklet";
    const distance =
      (progress.value * star.speedPxPerSec + star.phase) % travelDistance;
    const translateX = star.originX + star.cosAngle * distance;
    const translateY = star.originY + star.sinAngle * distance;
    // Brightness envelope across one cycle: invisible at spawn, peaks mid-
    // trajectory, fades to invisible at the wrap point — so the wrap itself
    // is hidden and each pass reads as a discrete "shooting" event.
    const lifeT = distance / travelDistance;
    const envelope = Math.sin(lifeT * Math.PI);
    return {
      opacity: star.opacity * envelope,
      transform: [
        { translateX },
        { translateY },
        { rotate: `${star.angleRad}rad` },
      ],
    };
  });

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.star,
        animatedStyle,
        { width: svgWidth, height: svgHeight },
      ]}
    >
      <Svg width={svgWidth} height={svgHeight}>
        <Defs>
          <LinearGradient id={bodyGradId} x1="0" y1="0" x2="1" y2="0">
            <Stop offset="0" stopColor={colors.particle} stopOpacity="0" />
            <Stop
              offset="0.55"
              stopColor={colors.particle}
              stopOpacity="0.4"
            />
            <Stop
              offset="0.85"
              stopColor={colors.particle}
              stopOpacity="0.9"
            />
            <Stop offset="1" stopColor={colors.particle} stopOpacity="1" />
          </LinearGradient>
        </Defs>
        <Path d={pathD} fill={`url(#${bodyGradId})`} />
      </Svg>
    </Animated.View>
  );
}

export function AsteroidField() {
  const { width, height } = useWindowDimensions();
  const reduced = useReducedMotion();
  const progress = useSharedValue(0);

  const travelDistance = useMemo(
    () => Math.hypot(width, height) * 0.9,
    [width, height],
  );
  const stars = useMemo(
    () => buildStars(width, height, travelDistance),
    [width, height, travelDistance],
  );

  const frame = useFrameCallback((info) => {
    progress.value += (info.timeSincePreviousFrame ?? 0) / 1000;
  }, !reduced);

  useEffect(() => {
    if (reduced) {
      frame.setActive(false);
      return;
    }
    frame.setActive(AppState.currentState === "active");
    const sub = AppState.addEventListener(
      "change",
      (state: AppStateStatus) => {
        frame.setActive(state === "active");
      },
    );
    return () => sub.remove();
  }, [frame, reduced]);

  if (reduced) return null;

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFillObject}>
      {stars.map((star) => (
        <FallingStarView
          key={star.id}
          star={star}
          progress={progress}
          travelDistance={travelDistance}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  star: {
    position: "absolute",
    top: 0,
    left: 0,
  },
});
