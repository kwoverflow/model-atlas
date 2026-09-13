import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#202124",
        canvas: "#f6f7f8",
        panel: "#ffffff",
        line: "#d8dee4",
        teal: "#0f766e",
        amber: "#b45309",
        rose: "#be123c",
        violet: "#6d28d9"
      },
      boxShadow: {
        soft: "0 10px 30px rgba(32, 33, 36, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
