import { describe, it, expect } from "vitest";

/**
 * WCAG 2.1 relative luminance from hex color.
 */
function hexToLinear(hex: string): number {
  const val = parseInt(hex, 16) / 255;
  return val <= 0.04045 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex: string): number {
  const r = hexToLinear(hex.slice(1, 3));
  const g = hexToLinear(hex.slice(3, 5));
  const b = hexToLinear(hex.slice(5, 7));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function computeContrastRatio(fg: string, bg: string): number {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Palette from tokens.css
const INK        = "#1A1A1A";
const TEAL       = "#3E6868";
const TAN        = "#C1AB85";
const PAPER      = "#EFE6D2";
const TEAL_GLOW  = "#7FAAA5";
const RED_GLOW   = "#E0776D";

const TOKEN_PAIRS = [
  { fg: PAPER,     bg: INK,   minRatio: 10.0, label: "Paper on Ink" },
  { fg: TAN,       bg: INK,   minRatio:  7.0, label: "Tan on Ink" },
  { fg: TEAL_GLOW, bg: INK,   minRatio:  4.5, label: "Teal-Glow on Ink" },
  { fg: RED_GLOW,  bg: INK,   minRatio:  4.5, label: "Red-Glow on Ink" },
  { fg: PAPER,     bg: TEAL,  minRatio:  4.5, label: "Paper on Teal" },
];

describe("Token contrast ratios (WCAG 2.1)", () => {
  for (const { fg, bg, minRatio, label } of TOKEN_PAIRS) {
    it(`${label} >= ${minRatio}:1`, () => {
      const ratio = computeContrastRatio(fg, bg);
      expect(ratio).toBeGreaterThanOrEqual(minRatio);
    });
  }
});

describe("Type scale — 7 distinct sizes", () => {
  const SCALE_VALUES = [11, 13, 15, 17, 20, 26, 40]; // px values from tokens.css
  it("all 7 steps have unique pixel values", () => {
    expect(new Set(SCALE_VALUES).size).toBe(7);
  });
  it("values are strictly increasing", () => {
    for (let i = 1; i < SCALE_VALUES.length; i++) {
      expect(SCALE_VALUES[i]).toBeGreaterThan(SCALE_VALUES[i - 1]);
    }
  });
});
