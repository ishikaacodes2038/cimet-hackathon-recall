/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0a0d1d",
        surface: "#161a30",
        "surface-container": "#1c1f2f",
        "surface-container-low": "#141727",
        "surface-container-high": "#26293a",
        "surface-container-highest": "#313445",
        "border-hairline": "#2a2f4d",
        "text-primary": "#e8e9f3",
        "text-muted": "#9095b8",
        primary: "#ffb4a3",
        "primary-container": "#ff5a36",
        secondary: "#c0c4e9",
        tertiary: "#4ae08d",
        success: "#35d07f",
        warning: "#f5b942",
        error: "#ff5a5a",
        "accent-glow": "rgba(255, 90, 54, 0.18)",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["Space Mono", "monospace"],
      },
      borderRadius: {
        xl: "0.75rem",
        "2xl": "1rem",
      },
      keyframes: {
        orbFloat1: {
          "0%,100%": { transform: "translate(0,0) scale(1)" },
          "50%": { transform: "translate(60px,-40px) scale(1.12)" },
        },
        orbFloat2: {
          "0%,100%": { transform: "translate(0,0) scale(1)" },
          "50%": { transform: "translate(-50px,50px) scale(1.08)" },
        },
        eqBounce: {
          "0%,100%": { height: "6px" },
          "50%": { height: "22px" },
        },
        sonarPulse: {
          "0%": { transform: "scale(0.95)", opacity: "0.9" },
          "50%": { transform: "scale(1.4)", opacity: "0.2" },
          "100%": { transform: "scale(0.95)", opacity: "0.9" },
        },
      },
      animation: {
        "orb-1": "orbFloat1 18s ease-in-out infinite",
        "orb-2": "orbFloat2 22s ease-in-out infinite",
        "eq-bounce": "eqBounce 1s ease-in-out infinite",
        sonar: "sonarPulse 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
