import Constants from "expo-constants";

export function resolveBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  const fromExtra = Constants.expoConfig?.extra?.apiBaseUrl;
  const url =
    fromEnv && fromEnv.length > 0
      ? fromEnv
      : typeof fromExtra === "string" && fromExtra.length > 0
        ? fromExtra
        : undefined;
  if (!url) {
    throw new Error("API base URL not configured (set EXPO_PUBLIC_API_URL).");
  }
  return url.replace(/\/$/, "");
}
