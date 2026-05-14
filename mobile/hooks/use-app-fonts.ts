import { useFonts } from "expo-font";
import {
  Outfit_400Regular,
  Outfit_500Medium,
} from "@expo-google-fonts/outfit";
import { CormorantGaramond_300Light_Italic } from "@expo-google-fonts/cormorant-garamond";

export function useAppFonts(): boolean {
  const [loaded] = useFonts({
    Outfit_400Regular,
    Outfit_500Medium,
    CormorantGaramond_300Light_Italic,
  });
  return loaded;
}
