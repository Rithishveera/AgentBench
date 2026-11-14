import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#18231f",
        paper: "#f3f5f2",
        forest: "#17664f",
        signal: "#e45c3a",
      },
    },
  },
  plugins: [],
};

export default config;