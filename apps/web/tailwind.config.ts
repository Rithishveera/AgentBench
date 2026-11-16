import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink:          "var(--color-ink)",
        "ink-raised": "var(--color-ink-raised)",
        teal:         "var(--color-teal)",
        red:          "var(--color-red)",
        tan:          "var(--color-tan)",
        paper:        "var(--color-paper)",
        "teal-glow":  "var(--color-teal-glow)",
        "red-glow":   "var(--color-red-glow)",
        // shadcn aliases
        background: "var(--background)",
        foreground: "var(--foreground)",
        border:     "var(--border)",
        input:      "var(--input)",
        ring:       "var(--ring)",
        primary: {
          DEFAULT:    "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT:    "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT:    "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT:    "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: {
          DEFAULT:    "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        card: {
          DEFAULT:    "var(--card)",
          foreground: "var(--card-foreground)",
        },
      },
      borderRadius: {
        card: "var(--radius-card)",
        pill: "var(--radius-pill)",
      },
      boxShadow: {
        teal: "var(--shadow-teal)",
        red:  "var(--shadow-red)",
      },
      fontSize: {
        xs:      ["var(--text-xs)",      { lineHeight: "1.4" }],
        sm:      ["var(--text-sm)",      { lineHeight: "1.4" }],
        base:    ["var(--text-base)",    { lineHeight: "1.5" }],
        md:      ["var(--text-md)",      { lineHeight: "1.5" }],
        lg:      ["var(--text-lg)",      { lineHeight: "1.4" }],
        xl:      ["var(--text-xl)",      { lineHeight: "1.3" }],
        display: ["var(--text-display)", { lineHeight: "1.1" }],
      },
      fontFamily: {
        sans: ["var(--font-bricolage)", "sans-serif"],
        mono: ["var(--font-space-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
