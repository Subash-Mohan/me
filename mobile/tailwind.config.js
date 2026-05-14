/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        background: "#050505",
        surface: {
          DEFAULT: "#151515",
          raised: "#1A1A1A",
          highlight: "#222222",
        },
        border: {
          subtle: "#2A2A2A",
          DEFAULT: "#333333",
          focus: "#444444",
        },
        foreground: {
          DEFAULT: "#E2E2E2",
          secondary: "#D4D4CE",
          muted: "#A0A0A0",
          placeholder: "#666666",
        },
        status: {
          listening: "#10b981",
        },
      },
      fontFamily: {
        sans: ["Outfit_400Regular"],
        sansMedium: ["Outfit_500Medium"],
        serif: ["CormorantGaramond_300Light_Italic"],
      },
      borderRadius: {
        lg: "8px",
        xl: "12px",
        "2xl": "20px",
        "3xl": "24px",
      },
      letterSpacing: {
        wider: "0.05em",
        widest: "0.1em",
        tracked: "0.2em",
        mega: "0.3em",
      },
    },
  },
  plugins: [],
};
