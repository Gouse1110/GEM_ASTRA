/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // GeM Astra light-theme design tokens
        gem: {
          // Page & structure
          bg:          "#F8FAFC",   // main page background
          card:        "#FFFFFF",   // card / sidebar surface
          border:      "#E2E8F0",   // default border
          // Text
          text:        "#0F172A",   // primary text
          muted:       "#64748B",   // secondary / caption text
          subtle:      "#94A3B8",   // placeholder, tertiary
          // Emerald accent
          emerald:     "#059669",   // primary action / active
          "emerald-hover": "#047857",
          "emerald-soft":  "#D1FAE5",
          "emerald-nav":   "#ECFDF5",   // active nav bg
          "emerald-text":  "#047857",   // active nav text
        },
        // Risk band colours — must stay distinct from emerald
        risk: {
          low:       "#16A34A",   // green (distinct shade)
          moderate:  "#D97706",   // amber
          elevated:  "#EA580C",   // orange
          high:      "#DC2626",   // red
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card:     "0 1px 3px 0 rgba(15,23,42,0.07), 0 1px 2px -1px rgba(15,23,42,0.05)",
        elevated: "0 4px 12px 0 rgba(15,23,42,0.10)",
        sidebar:  "1px 0 0 0 #E2E8F0",
      },
    },
  },
  plugins: [],
};
