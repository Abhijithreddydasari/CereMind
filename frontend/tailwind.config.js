/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Material-3 cyan-on-navy "war room" palette (see frontend_example.html).
        ink: "#051424", // background / surface
        surface: "#081a2c",
        panel: "#0d1c2d", // surface-container-low
        panel2: "#122131", // surface-container
        elevated: "#1c2b3c", // surface-container-high
        edge: "#26384c", // outline-variant
        edge2: "#3a495d",
        accent: "#22d3ee", // primary cyan
        accent2: "#67e8f9", // primary-fixed (bright cyan)
        cerebras: "#ff7a45", // Cerebras brand orange (speed accents)
        cyan: "#7cc4ff", // secondary blue
        ok: "#34d399",
        warn: "#f4b740",
        bad: "#ff6b6b", // error
        muted: "#89a0bd", // on-surface-variant
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(34,211,238,0.25), 0 8px 40px -12px rgba(34,211,238,0.45)",
        cyanGlow: "0 0 18px rgba(34,211,238,0.35)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 40px -24px rgba(0,0,0,0.85)",
        soft: "0 12px 30px -18px rgba(0,0,0,0.7)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(rgba(124,196,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.035) 1px, transparent 1px)",
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
        pulseNode: {
          "0%,100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.7", transform: "scale(1.08)" },
        },
        progress: {
          "0%": { width: "0%" },
          "100%": { width: "var(--bar-w, 95%)" },
        },
        coreSpin: {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        glowPulse: {
          "0%,100%": { opacity: "0.55", transform: "scale(1)" },
          "50%": { opacity: "0.9", transform: "scale(1.06)" },
        },
      },
      animation: {
        fadein: "fadein 0.28s cubic-bezier(0.2,0.7,0.2,1) both",
        blink: "blink 1s steps(2) infinite",
        "pulse-node": "pulseNode 2s cubic-bezier(0.4,0,0.6,1) infinite",
        progress: "progress 1.6s ease-out forwards",
        "core-spin": "coreSpin 36s linear infinite",
        "glow-pulse": "glowPulse 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
