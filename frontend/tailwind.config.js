/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0e14",
        panel: "#11151f",
        panel2: "#161b26",
        edge: "#232a39",
        accent: "#7c5cff",
        cerebras: "#ff7a45",
        ok: "#2ea043",
        warn: "#f0883e",
        bad: "#f85149",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
