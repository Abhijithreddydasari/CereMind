/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070a12",
        surface: "#0c1018",
        panel: "#10151f",
        panel2: "#161c28",
        elevated: "#1b2230",
        edge: "#222b3b",
        edge2: "#2c374a",
        accent: "#7c5cff",
        accent2: "#9d7bff",
        cerebras: "#ff7a45",
        cyan: "#38bdf8",
        ok: "#34d399",
        warn: "#fbbf24",
        bad: "#fb5b5b",
        muted: "#8a97ad",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(124,92,255,0.25), 0 8px 40px -12px rgba(124,92,255,0.45)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 40px -24px rgba(0,0,0,0.8)",
        soft: "0 12px 30px -18px rgba(0,0,0,0.7)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
      },
      keyframes: {
        fadein: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        blink: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.2" },
        },
      },
      animation: {
        fadein: "fadein 0.28s cubic-bezier(0.2,0.7,0.2,1) both",
        blink: "blink 1s steps(2) infinite",
      },
    },
  },
  plugins: [],
};
