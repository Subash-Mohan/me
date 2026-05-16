import { useRouter } from "expo-router";
import { useEffect, useRef } from "react";
import { SplashScreen } from "@/components/chat/splash-screen";
import { useAuth } from "@/lib/auth/auth-store";

const MIN_SPLASH_MS = 1500;

export default function SplashRoute() {
  const router = useRouter();
  const { status } = useAuth();
  const mountedAt = useRef(Date.now());

  useEffect(() => {
    if (status === "loading") return;
    const target = status === "authenticated" ? "/chat" : "/login";
    const elapsed = Date.now() - mountedAt.current;
    const wait = Math.max(0, MIN_SPLASH_MS - elapsed);
    const t = setTimeout(() => router.replace(target), wait);
    return () => clearTimeout(t);
  }, [status, router]);

  return <SplashScreen />;
}
