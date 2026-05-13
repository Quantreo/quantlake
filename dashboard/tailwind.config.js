/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Terminal / Bloomberg-pro palette
        bg: {
          DEFAULT: "#0a0a0b",
          panel: "#111113",
          elevated: "#16161a",
        },
        border: {
          DEFAULT: "#1f1f23",
          strong: "#2a2a30",
        },
        fg: {
          DEFAULT: "#e4e4e7",
          muted: "#71717a",
          dim: "#52525b",
        },
        accent: {
          DEFAULT: "#f59e0b", // amber — matches Oryon
          hover: "#fbbf24",
          dim: "#78350f",
        },
        series: {
          1: "#f59e0b",
          2: "#06b6d4",
          3: "#22c55e",
          4: "#e879f9",
          5: "#f87171",
          6: "#a78bfa",
          7: "#fb923c",
          8: "#34d399",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["0.6875rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};
