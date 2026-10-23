import colors from "tailwindcss/colors";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // SAT navy - the primary brand colour, taken from the logo.
        brand: {
          50: "#eef4fd",
          100: "#dbe7fa",
          200: "#b9d0f4",
          300: "#8ab0ea",
          400: "#5589dc",
          500: "#1d5bb8",
          600: "#0b3a82",
          700: "#0a2f6b",
          800: "#082657",
          900: "#001c49",
        },
        // SAT gold - the logo's accent, for highlights only (never for body text on white).
        gold: {
          50: "#fff8e1",
          100: "#ffefb8",
          200: "#ffe07a",
          300: "#ffce3d",
          400: "#fbba14",
          500: "#f5a800",
          600: "#d18700",
        },
        // "Good" states (present, approved, paid, success messages). Kept green on purpose so a
        // status never changes meaning when the brand colour does.
        success: {
          50: "#effcf9",
          100: "#c8f6ec",
          200: "#94ecd9",
          300: "#5cd9c1",
          400: "#2fc0a8",
          500: "#149c88",
          600: "#0f7d6e",
          700: "#106459",
          800: "#124f48",
          900: "#11423d",
        },
        // Warm coral - the secondary accent for highlights, due dates,
        // and anything that should feel like a friendly nudge rather
        // than an alert.
        sunset: {
          50: "#fff4ed",
          100: "#ffe4d3",
          200: "#ffc5a3",
          300: "#ff9d68",
          400: "#fd7a3d",
          500: "#f45d1f",
          600: "#e14514",
          700: "#ba3413",
          800: "#942a17",
          900: "#782516",
        },
        // Cool blue-grey neutrals (page grounds, borders, muted fills) to sit with the navy.
        sand: {
          50: "#f6f8fc",
          100: "#eef2f8",
          200: "#dfe6f0",
          300: "#c8d3e3",
          400: "#9fb0c8",
          500: "#7b8ea9",
          600: "#5f7290",
          700: "#4a5b76",
          800: "#33425a",
          900: "#1e293b",
        },
        // Text greys: slate instead of the default warm stone.
        stone: colors.slate,
      },
      fontFamily: {
        display: ["Quicksand", "system-ui", "sans-serif"],
        sans: ["Work Sans", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
    },
  },
  plugins: [],
};
