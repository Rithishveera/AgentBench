# Design Document

## Overview

This design introduces a **vintage-American-poster design system** to the AgentBench web application and migrates every existing page to it. The scope is styling only: tokens, shared components, and the markup needed to apply them. No behavior, routes, data-fetching logic, API calls, security headers, or test assertions change.

The existing stack is Next.js 15 App Router, TypeScript strict mode, Tailwind CSS v3, and an in-house set of shadcn-pattern components (`Button`, `Badge`, `Input`) that use `cva` and `tailwind-merge`. The design system builds on that foundation without forking the primitive source files.

---

## Architecture

### Token flow

```
apps/web/src/styles/tokens.css      ← single source of truth for all design values
        │
        ▼
apps/web/tailwind.config.ts         ← theme.extend maps tokens to Tailwind utility names
        │
        ▼
apps/web/src/app/globals.css        ← @import tokens.css; Tailwind directives; base styles
        │
        ▼
Component className strings         ← Tailwind utilities (bg-teal, text-paper, …)
```

shadcn-style primitives that need CSS-variable access (e.g. for focus rings applied from globals) continue to reference `var(--color-*)` directly inside `globals.css` base layer rules, so they still work without JS.

### Font flow

```
apps/web/src/lib/fonts.ts           ← loads Bricolage Grotesque and Space Mono via next/font/google
        │
        ▼
apps/web/src/app/layout.tsx         ← applies font CSS variables to <html> and <body>
        │
        ▼
globals.css base layer              ← font-family set on html, pre, code using CSS vars from fonts.ts
```

`next/font/google` self-hosts all font files at build time by embedding them into the Next.js static output. Zero requests to `fonts.googleapis.com` or `fonts.gstatic.com` are made at runtime, which is consistent with the strict `font-src 'self' data:` CSP already in `next.config.ts`.

### Guard and test flow

```
apps/web/scripts/check-tokens.mjs  ← Node ESM guard script; exits non-zero on any violation
apps/web/src/styles/tokens.test.ts ← Vitest unit test for WCAG contrast ratios
        │
        ▼ (after migration)
apps/web/package.json "check" script ← added when PROGRESS.md shows zero violations
.github/workflows/check.yml         ← guard step added in the same PR that records zero count
```

---

## Components and Interfaces

### File layout

```
apps/web/src/
├── styles/
│   ├── tokens.css               # Token_File — all custom properties
│   └── tokens.test.ts           # Contrast_Test — Vitest
├── lib/
│   ├── fonts.ts                 # Font_Module
│   ├── status.ts                # Status_Module
│   └── utils.ts                 # existing cn() helper (unchanged)
├── components/
│   ├── ui/
│   │   ├── button.tsx           # restyled (cva variants updated)
│   │   ├── badge.tsx            # restyled (status-token colors)
│   │   ├── input.tsx            # restyled (Tan border, Ink_Raised bg)
│   │   ├── card.tsx             # new — PosterCard
│   │   ├── stamp-badge.tsx      # new — StampBadge
│   │   ├── vinyl-spinner.tsx    # new — VinylSpinner
│   │   ├── halftone-divider.tsx # new — HalftoneDivider
│   │   └── wordmark.tsx         # new — Wordmark
│   └── ... (existing feature components, migrated in-place)
├── app/
│   ├── globals.css              # updated: imports tokens.css, new base rules
│   ├── layout.tsx               # updated: fonts, paper-grain overlay
│   ├── styleguide/              # dev-only route
│   │   └── page.tsx
│   └── ... (existing routes)
└── scripts/
    └── check-tokens.mjs         # Guard_Script
```

### tokens.css

Defines all CSS custom properties in a single `:root {}` block:

```css
/* Palette */
--color-ink: #1A1A1A;
--color-ink-raised: #1E2323;
--color-teal: #3E6868;
--color-red: #C94E44;
--color-tan: #C1AB85;
--color-paper: #EFE6D2;
--color-teal-glow: #7FAAA5;
--color-red-glow: #E0776D;

/* Derived tints — only via color-mix(), never new hue literals */
--color-teal-subtle: color-mix(in srgb, var(--color-teal) 20%, var(--color-ink));
--color-red-subtle:  color-mix(in srgb, var(--color-red)  20%, var(--color-ink));

/* Geometry */
--radius-card: 28px;
--radius-pill: 9999px;

/* Shadows */
--shadow-teal: 6px 6px 0 var(--color-teal);
--shadow-red:  6px 6px 0 var(--color-red);

/* Type scale (7 distinct steps) */
--text-xs:      11px;
--text-sm:      13px;
--text-base:    15px;
--text-md:      17px;
--text-lg:      20px;
--text-xl:      26px;
--text-display: 40px;
```

### tailwind.config.ts

The theme extension maps token names to their CSS variable references:

```typescript
theme: {
  extend: {
    colors: {
      ink:       "var(--color-ink)",
      "ink-raised": "var(--color-ink-raised)",
      teal:      "var(--color-teal)",
      red:       "var(--color-red)",
      tan:       "var(--color-tan)",
      paper:     "var(--color-paper)",
      "teal-glow": "var(--color-teal-glow)",
      "red-glow":  "var(--color-red-glow)",
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
      xs:      "var(--text-xs)",
      sm:      "var(--text-sm)",
      base:    "var(--text-base)",
      md:      "var(--text-md)",
      lg:      "var(--text-lg)",
      xl:      "var(--text-xl)",
      display: "var(--text-display)",
    },
  },
}
```

This approach means `bg-teal`, `text-paper`, `shadow-teal`, `text-display`, and `rounded-card` all work in component className strings without duplicating any hex value.

### fonts.ts (Font_Module)

```typescript
// apps/web/src/lib/fonts.ts
import { Bricolage_Grotesque, Space_Mono } from "next/font/google";

export const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  axes: ["wght", "wdth", "opsz"],
  variable: "--font-bricolage",
});

export const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
});
```

`layout.tsx` applies `bricolage.variable` and `spaceMono.variable` class names to `<html>`. `globals.css` then sets:

```css
html { font-family: var(--font-bricolage), sans-serif; }
pre, code { font-family: var(--font-space-mono), monospace; }
```

This keeps `font-family` declarations out of every other file, satisfying the guard check in Requirement 3.8.

### status.ts (Status_Module)

A discriminated union represents each known status, with a fallback for unknown strings.

```typescript
// apps/web/src/lib/status.ts
import type { LucideIcon } from "lucide-react";

export type RunStatus =
  | "passed" | "failed" | "timeout"
  | "agent_error" | "infra_error"
  | "running" | "queued";

export type StatusEntry = {
  status: RunStatus | "unknown";
  colorToken: string;        // CSS custom property name, e.g. "--color-teal"
  tailwindBg: string;        // Tailwind class, e.g. "bg-teal"
  icon: LucideIcon;
  label: string;
  hatch?: "red-45deg-4px" | "tan-45deg-4px";
  outline?: boolean;         // true for running/queued (Tan outline, no fill)
};

const STATUS_MAP: Record<RunStatus, StatusEntry> = {
  passed:      { status: "passed",      colorToken: "--color-teal",      tailwindBg: "bg-teal",      icon: CheckIcon,     label: "Passed" },
  failed:      { status: "failed",      colorToken: "--color-red",       tailwindBg: "bg-red",       icon: XIcon,         label: "Failed" },
  timeout:     { status: "timeout",     colorToken: "--color-tan",       tailwindBg: "bg-tan",       icon: ClockIcon,     label: "Timeout" },
  agent_error: { status: "agent_error", colorToken: "--color-red",       tailwindBg: "bg-red",       icon: ZapIcon,       label: "Agent error", hatch: "red-45deg-4px" },
  infra_error: { status: "infra_error", colorToken: "--color-ink-raised",tailwindBg: "bg-ink-raised",icon: WrenchIcon,    label: "Infra error", hatch: "tan-45deg-4px" },
  running:     { status: "running",     colorToken: "--color-tan",       tailwindBg: "bg-transparent", icon: VinylSpinner, label: "Running", outline: true },
  queued:      { status: "queued",      colorToken: "--color-tan",       tailwindBg: "bg-transparent", icon: DotsIcon,     label: "Queued",  outline: true },
};

export const FALLBACK_ENTRY: StatusEntry = {
  status: "unknown", colorToken: "--color-paper", tailwindBg: "bg-paper",
  icon: QuestionMarkIcon, label: "Unknown",
};

export function getStatusEntry(status: string): StatusEntry {
  return STATUS_MAP[status as RunStatus] ?? FALLBACK_ENTRY;
}
```

Icons are Lucide React icons: `Check`, `X`, `Clock`, `Zap`, `Wrench`, `Ellipsis`, `HelpCircle`. The `running` state references `VinylSpinner` as its icon component; callers that need a React element render `<entry.icon />`.

### PosterCard (`components/ui/card.tsx`)

```typescript
type PosterCardProps = {
  shadow?: "teal" | "red";   // default "teal"
  className?: string;
  children: React.ReactNode;
};
```

Implementation uses Tailwind utilities plus CSS custom properties for the double-border via a `::before` pseudo-element:

```css
/* In globals.css @layer components */
.poster-card::before {
  content: "";
  position: absolute;
  inset: 6px;
  border: 1px solid var(--color-tan);
  border-radius: calc(var(--radius-card) - 6px);
  pointer-events: none;
}
```

The outer border and radius come from Tailwind classes `border-2 border-tan rounded-card`. The shadow is applied with `shadow-teal` or `shadow-red`.

### StampBadge (`components/ui/stamp-badge.tsx`)

```typescript
type StampBadgeProps = {
  verdict: "passed" | "failed" | string;
  className?: string;
};
```

The double border is achieved with `outline` + `border` on the same element (outline: `1px solid var(--color-tan)`, outline-offset: `3px`; border: `2px solid var(--color-tan)`). Rotation is `-rotate-[3deg]`. The stamp-in animation is defined in `globals.css`:

```css
@keyframes stamp-in {
  from { transform: rotate(-3deg) scale(1.15); }
  to   { transform: rotate(-3deg) scale(1.0); }
}
.stamp-badge { animation: stamp-in 160ms ease-out forwards; }
@media (prefers-reduced-motion: reduce) {
  .stamp-badge { animation: none; }
}
```

### VinylSpinner (`components/ui/vinyl-spinner.tsx`)

A pure SVG component with no external assets.

```typescript
type VinylSpinnerProps = { size?: number; className?: string };
```

SVG structure: a black filled circle, 3+ concentric `<circle>` strokes in `var(--color-ink-raised)` for grooves, a filled circle in `var(--color-red)` for the center label. Rotation animation in `globals.css`:

```css
@keyframes vinyl-spin {
  to { transform: rotate(360deg); }
}
.vinyl-spinner { animation: vinyl-spin 1818ms linear infinite; transform-origin: center; }
@media (prefers-reduced-motion: reduce) {
  .vinyl-spinner { animation: none; }
}
```

### HalftoneDivider (`components/ui/halftone-divider.tsx`)

```typescript
type HalftoneDividerProps = {
  color: string;   // required: a CSS custom property name, e.g. "var(--color-tan)"
  className?: string;
};
```

Renders a `<div>` whose `background` is a `radial-gradient` composited with the page background:

```css
background: radial-gradient(circle, var(--dot-color) 1.5px, transparent 1.5px);
background-size: 8px 8px;
```

The `--dot-color` CSS variable is set inline via the `color` prop.

### Wordmark (`components/ui/wordmark.tsx`)

Renders a vinyl-record SVG mark alongside the text "AGENTBENCH". No external image file.

```typescript
type WordmarkProps = { className?: string; size?: "sm" | "md" | "lg" };
```

The vinyl SVG is a simplified inline shape (disc, 2–3 grooves, red center). The text uses `font-display text-display font-black uppercase tracking-tight font-stretch-condensed` Tailwind classes.

### Restyled shadcn primitives

**Strategy**: The existing primitives (`button.tsx`, `badge.tsx`, `input.tsx`) are edited in-place — their `cva` variant maps and base classes are updated to reference the new token names. New primitives (`card.tsx`, etc.) are added. No shadcn source files are forked or vendored from an external CLI output.

#### Button

Existing `cva` base class updated from `rounded-md` to `rounded-pill`. Variants:

| Variant | Background | Text | Border |
|---------|-----------|------|--------|
| `solid` | `bg-red` | `text-paper` | — |
| `outline` | transparent | `text-paper` | `border-tan` |
| `quiet` | transparent | `text-teal-glow` | — |
| `danger` | `bg-red` | `text-paper` | — |
| `ghost` | transparent | `text-ink-raised` | — |

Focus ring added in `globals.css` base layer:
```css
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {
  outline: 2px solid var(--color-tan);
  outline-offset: 2px;
}
```

#### Badge

`tone` variants replaced with `status` prop using `getStatusEntry()`:

```typescript
<Badge status="passed" />  →  Teal fill, check icon, "Passed" label
<Badge status="running" />  →  Tan outline, VinylSpinner icon, "Running" label
```

Pill geometry: `rounded-pill`. Hatch overlay for `agent_error` and `infra_error` via a CSS background `repeating-linear-gradient` composited on top of the fill color.

#### Input and Select

Base classes: `border-tan bg-ink-raised text-paper rounded-md`. Focus ring from globals rule above.

#### Table

Header cells: `bg-ink-raised text-paper`. Column dividers: `border-tan`. Numeric cells: detected by content regex at render time (or `data-metric` attribute), apply `font-variant-numeric: tabular-nums` via a Tailwind utility class `tabular-nums`.

#### Tabs, Dialog, Tooltip

New files `tabs.tsx`, `dialog.tsx`, `tooltip.tsx` added to `components/ui/`. All use `bg-ink-raised border-tan text-paper` as their surface tokens.

### Paper grain overlay

Added to `layout.tsx` as an inline SVG appended after `{children}`:

```tsx
<svg
  aria-hidden="true"
  style={{
    position: "fixed", inset: 0, width: "100%", height: "100%",
    opacity: 0.05, pointerEvents: "none", zIndex: 9999,
  }}
>
  <filter id="grain">
    <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />
    <feColorMatrix type="saturate" values="0" />
  </filter>
  <rect width="100%" height="100%" filter="url(#grain)" />
</svg>
```

Using an inline SVG (rather than an external `.svg` file reference) avoids a network request and respects the strict `img-src 'self' data:` CSP. The `z-index: 9999` and `pointer-events: none` ensure it overlays everything but intercepts no input.

### /styleguide route (dev-only)

Located at `apps/web/src/app/styleguide/page.tsx`. Excluded from production builds via a build-time guard at the top of the file:

```typescript
// apps/web/src/app/styleguide/page.tsx
if (process.env.NODE_ENV === "production") {
  notFound();  // next/navigation notFound() — returns 404
}
```

This is the standard Next.js App Router pattern for conditional 404s. It requires no extra environment variable and no changes to `next.config.ts`. The file exists in the build output's server bundle but the route handler immediately invokes `notFound()` in production, which makes the page return 404 to any client request.

The page renders sections:
1. Palette swatches (8 colors, label + hex)
2. Type scale (7 steps, Bricolage Grotesque)
3. All restyled primitives in all variants (Button×5, Badge×7, Input, etc.)
4. Status states (all 7, showing fill + icon + label)
5. Visual components (PosterCard, StampBadge, VinylSpinner, HalftoneDivider, Wordmark)

### Guard script (`scripts/check-tokens.mjs`)

A Node.js ESM script using `fast-glob` to enumerate source files and `fs/promises` to read them:

```javascript
// High-level logic
const files = await glob("src/**/*.{ts,tsx,css,scss}", { cwd: ROOT, absolute: true });
// Exclude Token_File and Font_Module
const toCheck = files.filter(f => !f.endsWith("tokens.css") && !f.endsWith("fonts.ts"));

const violations = [];
for (const file of toCheck) {
  const content = await readFile(file, "utf8");
  if (HEX_RE.test(content))             violations.push({ file, kind: "hex-literal" });
  if (RGB_HSL_RE.test(content))         violations.push({ file, kind: "rgb-hsl-literal" });
  if (ARBITRARY_COLOR_RE.test(content)) violations.push({ file, kind: "tailwind-arbitrary-color" });
  if (FONT_FAMILY_RE.test(content))     violations.push({ file, kind: "font-family-decl" });
  if (CJK_RE.test(content))             violations.push({ file, kind: "cjk-character" });
}

// Also verify Token_File exists and contains all 8 required properties
const tokenFile = await readFile(TOKEN_FILE, "utf8").catch(() => null);
if (!tokenFile) violations.push({ file: TOKEN_FILE, kind: "token-file-missing" });
else {
  for (const prop of REQUIRED_PROPS) {
    if (!tokenFile.includes(prop)) violations.push({ file: TOKEN_FILE, kind: "missing-property", prop });
  }
}

if (violations.length > 0) {
  for (const v of violations) console.error(formatViolation(v));
  process.exit(1);
}
process.exit(0);
```

Regex patterns:
- `HEX_RE`: `/(?<![0-9a-fA-F])#[0-9a-fA-F]{3,8}\b/g`  
- `RGB_HSL_RE`: `/\b(rgb|hsl)a?\s*\(/g`  
- `ARBITRARY_COLOR_RE`: `/(?:bg|text|border|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]/g`  
- `FONT_FAMILY_RE`: `/font-family\s*:/g`  
- `CJK_RE`: `/[\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFFEF]/g`

`fast-glob` is already an indirect dependency of Tailwind CSS, so no new `devDependency` is required. If it is not available directly, the script uses `node:fs` `readdir` recursively as a fallback.

### CI integration

The guard script is added to `package.json` and the GitHub Actions workflow **only after** `PROGRESS.md` documents a zero-violation count for all four categories:

```json
// package.json — added in the "migration complete" PR
"scripts": {
  "check-tokens": "node scripts/check-tokens.mjs"
}
```

```yaml
# .github/workflows/check.yml — new step added in the same PR
- name: Token guard
  run: npm run check-tokens
  working-directory: apps/web
```

The step is placed after `typecheck` and before `test` in the workflow.

---

## Data Models

### StatusEntry

```typescript
type StatusEntry = {
  status: RunStatus | "unknown";
  colorToken: string;        // CSS variable name
  tailwindBg: string;        // Tailwind bg class
  icon: LucideIcon;
  label: string;
  hatch?: "red-45deg-4px" | "tan-45deg-4px";
  outline?: boolean;
};
```

### TokenPair (used in contrast tests)

```typescript
type TokenPair = {
  fg: string;    // hex color
  bg: string;    // hex color
  minRatio: number;
  description: string;
};

const TOKEN_PAIRS: TokenPair[] = [
  { fg: "#EFE6D2", bg: "#1A1A1A", minRatio: 10.0, description: "Paper on Ink" },
  { fg: "#C1AB85", bg: "#1A1A1A", minRatio:  7.0, description: "Tan on Ink" },
  { fg: "#7FAAA5", bg: "#1A1A1A", minRatio:  4.5, description: "Teal_Glow on Ink" },
  { fg: "#E0776D", bg: "#1A1A1A", minRatio:  4.5, description: "Red_Glow on Ink" },
  { fg: "#EFE6D2", bg: "#3E6868", minRatio:  4.5, description: "Paper on Teal" },
];
```

### GuardViolation

```typescript
type GuardViolation = {
  file: string;
  line?: number;
  kind: "hex-literal" | "rgb-hsl-literal" | "tailwind-arbitrary-color"
       | "font-family-decl" | "cjk-character"
       | "token-file-missing" | "missing-property";
  prop?: string;
};
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: WCAG contrast ratios hold for all required token pairs

*For any* `(fg, bg, minRatio)` triple drawn from the five pairs specified in Requirements 2.1–2.5, the WCAG 2.1 relative-luminance formula applied to `fg` and `bg` SHALL produce a contrast ratio that is greater than or equal to `minRatio`.

**Validates: Requirements 1.8, 2.1, 2.2, 2.3, 2.4, 2.5**

### Property 2: Type scale steps are pairwise distinct

*For any* two distinct step names drawn from `{--text-xs, --text-sm, --text-base, --text-md, --text-lg, --text-xl, --text-display}`, the computed size values SHALL differ — no two steps share the same pixel or rem value.

**Validates: Requirements 1.4, 3.4**

### Property 3: Guard script correctly classifies any file as violating or clean

*For any* source file content string, the Guard_Script SHALL exit with a non-zero code if and only if the content contains at least one of: a hex color literal, an `rgb()`/`hsl()` literal, a Tailwind arbitrary-color class `bg-[#...]` / `text-[#...]`, a `font-family` CSS declaration, or a CJK Unicode character in the specified ranges. When the content contains none of these, the script SHALL exit with code 0.

**Validates: Requirements 1.5, 1.6, 1.7, 3.8, 10.2, 10.3, 10.4**

### Property 4: Status module returns a fully-populated entry for every valid status value

*For any* string value in the domain `{passed, failed, timeout, agent_error, infra_error, running, queued}`, `getStatusEntry(status)` SHALL return a `StatusEntry` whose `colorToken`, `icon`, and `label` fields are all non-null and non-empty strings, ensuring no single channel is the sole signal for any run state.

**Validates: Requirements 2.7, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8**

---

## Error Handling

### Guard script

- Missing Token_File: emits `ERROR: tokens.css not found at <path>` and exits 1.
- Missing required property in Token_File: emits `ERROR: tokens.css is missing --color-<name>` per property and exits 1.
- File read error (e.g. permission denied): emits `WARN: could not read <file>, skipping` and continues scanning; does not suppress other violations.
- File scan completes clean: exits 0 with no stdout or stderr output (Requirement 10.2).

### Font loading

- If `next/font/google` cannot fetch the font at build time (e.g. no network), the build fails with a Next.js build error. This is intentional: the design system requires self-hosted fonts and a build that cannot fetch them is a failed build.
- Fallback `font-family` stacks (`sans-serif`, `monospace`) are specified so the page remains readable if a browser somehow fails to load the font.

### Status module

- Unknown status strings are handled by `getStatusEntry()` returning the `FALLBACK_ENTRY` (Paper color, `HelpCircle` icon, "Unknown" label). Components that call `getStatusEntry()` never need to handle `undefined`.
- TypeScript strict mode ensures callers cannot pass `null` or `undefined` to `getStatusEntry()`.

### Migration

- If a page migration introduces a TypeScript error (e.g. a removed class name referenced as a string), `tsc --noEmit` fails the CI typecheck step before the guard script runs.
- Selector updates that break existing tests are tracked in `PROGRESS.md` with old → new pairs before the test file is changed, so the update is auditable.

---

## Testing Strategy

### Vitest unit tests (`src/**/*.test.ts`)

Vitest is already installed (`devDependencies`). Token and status tests are co-located in `src/styles/tokens.test.ts` and `src/lib/status.test.ts`.

**Unit tests cover:**
- `tokens.test.ts`: concrete assertions for each of the five contrast pairs (Property 1); concrete assertion that all seven type-scale CSS variable values are present and parseable.
- `status.test.ts`: concrete assertions for all seven known statuses (all three fields populated) and for an unknown string (fallback returned).
- `fonts.test.ts`: structural check that `fonts.ts` exports two font objects with the required axes/weights.

### Property-based tests (Vitest + fast-check)

`fast-check` is added as a dev dependency. Property tests live alongside unit tests.

**Property tests cover:**

**Property 1 — WCAG contrast ratios**  
Test file: `src/styles/tokens.test.ts`  
Generator: `fc.constantFrom(...TOKEN_PAIRS)` — samples from the five specified pairs.  
Assertion: `computeContrastRatio(pair.fg, pair.bg) >= pair.minRatio`  
Minimum iterations: 100 (each iteration samples a different pair, exercising the formula with all inputs multiple times).  
Tag: `Feature: web-design-system, Property 1: WCAG contrast ratios hold for all required token pairs`

**Property 2 — Type scale distinctness**  
Test file: `src/styles/tokens.test.ts`  
Generator: `fc.uniqueArray(fc.constantFrom(...SCALE_STEP_NAMES), { minLength: 2, maxLength: 2 })` — generates all distinct step pairs.  
Assertion: `parsedSize(steps[0]) !== parsedSize(steps[1])`  
Minimum iterations: 100.  
Tag: `Feature: web-design-system, Property 2: Type scale steps are pairwise distinct`

**Property 3 — Guard script classification**  
Test file: `src/styles/tokens.test.ts` or a dedicated `scripts/check-tokens.test.ts`.  
Generator: `fc.record({ hasViolation: fc.boolean(), content: fc.oneof(cleanString(), violatingString()) })` where `violatingString()` generates a string containing at least one of the five violation patterns.  
Assertion: `runGuardOnContent(content) === (hasViolation ? 1 : 0)`  
Implementation: the guard script's regex detection is extracted into a pure `detectViolations(content: string): GuardViolation[]` function that is importable and testable without spawning a process.  
Minimum iterations: 100.  
Tag: `Feature: web-design-system, Property 3: Guard script correctly classifies any file as violating or clean`

**Property 4 — Status module completeness**  
Test file: `src/lib/status.test.ts`  
Generator: `fc.constantFrom("passed", "failed", "timeout", "agent_error", "infra_error", "running", "queued")` — samples from the seven valid values.  
Assertion: `entry.colorToken.length > 0 && entry.icon != null && entry.label.length > 0`  
Minimum iterations: 100.  
Tag: `Feature: web-design-system, Property 4: Status module returns a fully-populated entry for every valid status value`

### Integration and smoke tests

- **Font self-hosting smoke**: after `next build`, scan `.next/static/` for any string containing `fonts.googleapis.com` or `fonts.gstatic.com`; assert none found. Runs in the existing `test:security` step pattern (Node test runner, not Vitest, consistent with `client-bundle.test.mjs`).
- **Existing test suite**: `vitest run --dir src` must continue to pass with no assertion changes. Selector updates (class name renames only) are tracked in `PROGRESS.md`.
- **Guard script timing smoke**: run `check-tokens.mjs` on the real source tree with `performance.now()` before and after; assert elapsed < 30 000 ms.

### Bundle size measurement

Pre- and post-migration:
1. Run `next build` with `ANALYZE=true` (if `@next/bundle-analyzer` is configured) or use the `.next/server/app` output.
2. Measure total CSS size: `find .next/static/css -name "*.css" | xargs gzip -c | wc -c` and convert to kB (÷ 1024, rounded to 2 decimal places).
3. Record in `PROGRESS.md` under "Bundle sizes" section.
4. SVG paper grain is inline in `layout.tsx` server output — measure its character count in the HTML response (inspect `.next/server/app/page.html` or equivalent).
5. Font payload: sum the sizes of all `.woff2` files in `.next/static/media/` matching the bricolage and space-mono filename prefixes.

### Migration order and selector tracking

Requirement 9 specifies migration order: layout + nav + wordmark → leaderboard (`/`) → agents (`/agents`) → benchmark wizard (`/benchmarks/new`) → benchmark detail (`/benchmarks/[id]`) → run detail (`/runs/[id]`).

After each page migration, run `vitest run --dir src` to catch any broken selectors immediately. Any selector updated due to a removed CSS class is logged in `PROGRESS.md` as:

```
| Old selector | New selector |
|---|---|
| `.surface` | `.poster-card` |
```
