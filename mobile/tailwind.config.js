const { colors } = require("./theme");

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors,
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
