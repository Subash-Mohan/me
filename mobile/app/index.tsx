import { useRouter } from "expo-router";
import { useEffect } from "react";
import { SplashScreen } from "@/components/chat/splash-screen";

export default function SplashRoute() {
  const router = useRouter();

  useEffect(() => {
    const t = setTimeout(() => router.replace("/chat"), 2500);
    return () => clearTimeout(t);
  }, [router]);

  return <SplashScreen />;
}
