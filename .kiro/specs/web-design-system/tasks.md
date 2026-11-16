# Implementation Plan: Web Design System (Vintage-American-Poster)

## Overview

Migrate the AgentBench web app (`apps/web`) from its current default styling to a vintage-American-poster design system. The work is entirely about styling: tokens, shared components, and the markup needed to apply them. No behavior, routes, data-fetching logic, API calls, security headers, or test assertions change. Work proceeds in four broad phases: foundation → components & utilities → page migration → guard & documentation.

---

## Tasks

- [x] 1. Pre-migration audit — record baseline counts in PROGRESS.md
  - Create `apps/web/PROGRESS.md` with a "Pre-migration audit" section.
  - In that section, record counts (using `grep -rn` or ripgrep across `.ts`, `.tsx`, `.css`, `.scss` under `apps/web/src`, excluding `*.test.*` and `*.spec.*`):
    - Number of hex color literals matching `#[0-9a-fA-F]{3,8}`
    - Number of `rgb()` / `hsl()` literals
    - Number of `font-family` declarations (excluding `src/lib/fonts.ts`)
    - Number of inline status-to-color mappings outside any future `status.ts`
  - Leave a "Post-migration" section placeholder with four zero-target rows.
  - Leave a "Bundle sizes" section placeholder (pre/post CSS kB, paper-grain SVG bytes, font payload kB).
  - Leave a "Selector updates" section placeholder with the markdown table header.
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 2. Design system foundation
  - [x] 2.1 Create `apps/web/src/styles/tokens.css` with all CSS custom properties
    - Define eight palette custom properties: `--color-ink`, `--color-ink-raised`, `--color-teal`, `--color-red`, `--color-tan`, `--color-paper`, `--color-teal-glow`, `--color-red-glow` with the exact hex values specified in the requirements.
    - Define two derived tints using `color-mix()` only (no new hue literals): `--color-teal-subtle` and `--color-red-subtle`.
    - Define geometry tokens: `--radius-card: 28px`, `--radius-pill: 9999px`.
    - Define shadow tokens: `--shadow-teal: 6px 6px 0 var(--color-teal)`, `--shadow-red: 6px 6px 0 var(--color-red)`.
    - Define exactly seven type-scale steps with distinct pixel values: `--text-xs: 11px`, `--text-sm: 13px`, `--text-base: 15px`, `--text-md: 17px`, `--text-lg: 20px`, `--text-xl: 26px`, `--text-display: 40px`.
    - _Requirements: 1.1, 1.3, 1.4, 3.4_

  - [x] 2.2 Update `apps/web/tailwind.config.ts` to extend theme with token references
    - Add `colors` extension mapping `ink`, `ink-raised`, `teal`, `red`, `tan`, `paper`, `teal-glow`, `red-glow` to their respective `var(--color-*)` references.
    - Add `borderRadius` extension: `card: "var(--radius-card)"`, `pill: "var(--radius-pill)"`.
    - Add `boxShadow` extension: `teal: "var(--shadow-teal)"`, `red: "var(--shadow-red)"`.
    - Add `fontSize` extension for all seven scale steps pointing to their `var(--text-*)` references.
    - Also add shadcn CSS variable aliases (e.g. `--background`, `--foreground`, `--border`) pointing to the matching palette tokens so shadcn primitives continue to work.
    - _Requirements: 1.2_

  - [x] 2.3 Create `apps/web/src/lib/fonts.ts` (Font_Module)
    - Import `Bricolage_Grotesque` and `Space_Mono` from `next/font/google`.
    - Configure `Bricolage_Grotesque` with `subsets: ["latin"]`, `axes: ["wght", "wdth", "opsz"]`, `variable: "--font-bricolage"`.
    - Configure `Space_Mono` with `subsets: ["latin"]`, `weight: ["400", "700"]`, `variable: "--font-space-mono"`.
    - Export both font objects as named exports `bricolage` and `spaceMono`.
    - _Requirements: 3.1, 3.2, 3.7_

  - [x] 2.4 Update `apps/web/src/app/globals.css` with design system base rules
    - Add `@import "../styles/tokens.css";` at the top (before Tailwind directives).
    - In `@layer base`, set `html { font-family: var(--font-bricolage), sans-serif; }` and `pre, code { font-family: var(--font-space-mono), monospace; }`.
    - In `@layer base`, apply to `h1`–`h6`: `text-transform: uppercase`, `font-weight: 800`, `font-stretch: 75%`, `letter-spacing: -0.01em`.
    - In `@layer base`, apply `font-variant-numeric: tabular-nums` to `td` and `[data-metric]`.
    - In `@layer base`, add focus-ring rule: `button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--color-tan); outline-offset: 2px; }`.
    - In `@layer components`, add `.poster-card::before` pseudo-element rule for the inner hairline (1 px Tan border, `inset: 6px`, `border-radius: calc(var(--radius-card) - 6px)`, `pointer-events: none`).
    - In `@layer components`, add `.stamp-badge` animation `stamp-in` (scale 1.15 → 1.0, 160 ms `ease-out`), and `@media (prefers-reduced-motion: reduce) { .stamp-badge { animation: none; } }`.
    - In `@layer components`, add `@keyframes vinyl-spin` (0° → 360°) and `.vinyl-spinner { animation: vinyl-spin 1818ms linear infinite; }` with reduced-motion override.
    - Remove all old `:root` custom properties and hard-coded colors from the existing `globals.css` content.
    - _Requirements: 1.2, 2.8, 3.3, 3.5, 3.6, 4.4, 4.5, 4.7, 4.8_

  - [x] 2.5 Update `apps/web/src/app/layout.tsx` to apply font variables
    - Import `bricolage` and `spaceMono` from `../lib/fonts`.
    - Apply `${bricolage.variable} ${spaceMono.variable}` class names to the `<html>` element.
    - Ensure no `font-family` inline style is added (the CSS variables do the work).
    - _Requirements: 3.3, 3.7_

- [x] 3. New shared visual components
  - [x] 3.1 Create `apps/web/src/components/ui/card.tsx` (PosterCard)
    - Export `PosterCard` accepting props: `shadow?: "teal" | "red"` (default `"teal"`), `className?: string`, `children: React.ReactNode`.
    - Apply Tailwind classes: `relative`, `rounded-card`, `border-2`, `border-tan`, plus `shadow-teal` or `shadow-red` based on the `shadow` prop.
    - Add `position: relative` so the `::before` pseudo-element (defined in `globals.css`) renders correctly.
    - Use `cn()` from `../lib/utils` to merge classes.
    - _Requirements: 4.1, 4.2_

  - [x] 3.2 Create `apps/web/src/components/ui/stamp-badge.tsx` (StampBadge)
    - Export `StampBadge` accepting `verdict: string`, `className?: string`.
    - Apply `-rotate-[3deg]`, `border-2 border-tan`, `outline outline-1 outline-tan outline-offset-[3px]`, and `stamp-badge` class (triggers stamp-in animation from `globals.css`).
    - Text label derived from `verdict` prop rendered in `uppercase font-black`.
    - _Requirements: 4.3, 4.4, 4.5_

  - [x] 3.3 Create `apps/web/src/components/ui/vinyl-spinner.tsx` (VinylSpinner)
    - Export `VinylSpinner` accepting `size?: number` (default 32), `className?: string`.
    - Render a pure SVG: outer black filled circle, at least 3 concentric `<circle>` strokes in `var(--color-ink-raised)` evenly spaced for grooves, a Red filled circle centered for the label.
    - Apply `vinyl-spinner` class to the top-level `<svg>` (triggers spin animation from `globals.css`).
    - Set `transform-origin: center` as an inline style.
    - _Requirements: 4.6, 4.7, 4.8_

  - [x] 3.4 Create `apps/web/src/components/ui/halftone-divider.tsx` (HalftoneDivider)
    - Export `HalftoneDivider` accepting `color: string` (required, e.g. `"var(--color-tan)"`), `className?: string`.
    - Render a `<div>` whose inline style sets `--dot-color` to the `color` prop and `background` to `radial-gradient(circle, var(--dot-color) 1.5px, transparent 1.5px)` with `background-size: 8px 8px`.
    - _Requirements: 4.9_

  - [x] 3.5 Create `apps/web/src/components/ui/wordmark.tsx` (Wordmark)
    - Export `Wordmark` accepting `size?: "sm" | "md" | "lg"`, `className?: string`.
    - Render an inline vinyl-record SVG (disc, 2–3 grooves, Red center circle) alongside the text "AGENTBENCH".
    - Apply `text-display font-black uppercase tracking-tight` Tailwind classes to the text; use `font-stretch: 75%` via inline style or a Tailwind utility.
    - _Requirements: 4.10_

- [x] 4. Create `apps/web/src/lib/status.ts` (Status_Module)
  - [x] 4.1 Define types and the STATUS_MAP constant
    - Define the `RunStatus` union type: `"passed" | "failed" | "timeout" | "agent_error" | "infra_error" | "running" | "queued"`.
    - Define the `StatusEntry` type with fields: `status`, `colorToken: string`, `tailwindBg: string`, `icon: LucideIcon`, `label: string`, `hatch?: "red-45deg-4px" | "tan-45deg-4px"`, `outline?: boolean`.
    - Define `STATUS_MAP` covering all seven values with the exact colors, Lucide icons, and labels specified: passed→Teal/Check/"Passed", failed→Red/X/"Failed", timeout→Tan/Clock/"Timeout", agent_error→Red+hatch/Zap/"Agent error", infra_error→Ink_Raised+hatch/Wrench/"Infra error", running→Tan outline/VinylSpinner/"Running", queued→Tan outline/Ellipsis/"Queued".
    - Define `FALLBACK_ENTRY` using Paper/HelpCircle/"Unknown".
    - Export `getStatusEntry(status: string): StatusEntry`.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [ ]* 4.2 Write property test for Status_Module completeness (Property 4)
    - Add `src/lib/status.test.ts` (or extend it if it exists).
    - Use `fast-check` (add as devDependency if absent): `fc.constantFrom("passed", "failed", "timeout", "agent_error", "infra_error", "running", "queued")`.
    - Assert for each sampled value that `getStatusEntry(status)` returns an entry where `colorToken.length > 0`, `icon != null`, and `label.length > 0`.
    - Run for at least 100 iterations.
    - Tag: `Feature: web-design-system, Property 4: Status module returns a fully-populated entry for every valid status value`
    - Also add unit tests for the fallback: `getStatusEntry("unknown_xyz")` returns `FALLBACK_ENTRY`.
    - _Requirements: 2.7, 5.1–5.9_

- [x] 5. Restyle shadcn primitives
  - [x] 5.1 Update `apps/web/src/components/ui/button.tsx`
    - Change `cva` base class `rounded-md` → `rounded-pill`.
    - Add/update variants: `solid` (`bg-red text-paper`), `outline` (`border-tan text-paper bg-transparent`), `quiet` (`text-teal-glow bg-transparent`), `danger` (`bg-red text-paper`), `ghost` (`text-ink-raised bg-transparent`).
    - Remove any hardcoded hex or `rgb()` values from the file.
    - Focus ring is handled globally via `globals.css`; no per-component ring code needed.
    - _Requirements: 6.1, 6.2_

  - [x] 5.2 Update `apps/web/src/components/ui/badge.tsx`
    - Replace existing tone/variant color classes with token-based classes sourced from `getStatusEntry()`.
    - Apply `rounded-pill` geometry.
    - For `agent_error` and `infra_error`, add a `repeating-linear-gradient` overlay via inline style to render 45-degree hatch lines at 4 px spacing.
    - _Requirements: 6.4_

  - [x] 5.3 Update `apps/web/src/components/ui/input.tsx`
    - Change base classes to `border-tan bg-ink-raised text-paper rounded-md`.
    - Remove any hardcoded color values.
    - Focus ring handled via `globals.css`.
    - _Requirements: 6.6_

  - [x] 5.4 Create `apps/web/src/components/ui/select.tsx`
    - If a `select.tsx` primitive does not exist, create one that wraps a native `<select>` with a styled container.
    - Apply `border-tan bg-ink-raised text-paper rounded-md` base classes. Focus ring from `globals.css`.
    - _Requirements: 6.6_

  - [x] 5.5 Create `apps/web/src/components/ui/table.tsx`
    - Create (or update) a Table primitive with subcomponents `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`.
    - Apply `bg-ink-raised text-paper` to header cells.
    - Apply `border-tan` as column dividers between cells.
    - Apply `tabular-nums` (Tailwind class `tabular-nums`) to cells containing only digits, decimal points, or numeric separators; also honor the `data-metric` attribute.
    - _Requirements: 6.5_

  - [x] 5.6 Create `apps/web/src/components/ui/tabs.tsx`, `dialog.tsx`, and `tooltip.tsx`
    - Create Tabs, Dialog, and Tooltip primitives (or update existing shadcn stubs if present).
    - Apply `bg-ink-raised border-tan text-paper` as surface tokens across all three.
    - _Requirements: 6.7_

- [x] 6. Add paper-grain overlay to `apps/web/src/app/layout.tsx`
  - Append an inline SVG after `{children}` with: `position: fixed`, `inset: 0`, `width: "100%"`, `height: "100%"`, `opacity: 0.05` (±0.5%), `pointerEvents: "none"`, `zIndex: 9999`, `aria-hidden: "true"`.
  - SVG body: a `<filter id="grain">` containing `<feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch"/>` and `<feColorMatrix type="saturate" values="0"/>`, plus a `<rect width="100%" height="100%" filter="url(#grain)"/>`.
  - Use an inline SVG (not an external file reference) to avoid a network request and satisfy the `img-src 'self'` CSP.
  - _Requirements: 4.11_

- [x] 7. Checkpoint — foundation complete
  - Ensure `apps/web` builds without TypeScript errors: `tsc --noEmit`.
  - Ensure no existing tests are broken: `vitest run --dir src`.
  - Ask the user if any questions arise before proceeding to contrast tests and guard.

- [x] 8. Contrast tests and token validation
  - [x] 8.1 Create `apps/web/src/styles/tokens.test.ts` with unit and property tests
    - Import `computeContrastRatio` (implement as a pure helper in the same file or a sibling `contrast.ts`): implements the WCAG 2.1 relative luminance formula.
    - Add unit tests for each of the five token pairs: Paper/Ink ≥ 10.0, Tan/Ink ≥ 7.0, Teal_Glow/Ink ≥ 4.5, Red_Glow/Ink ≥ 4.5, Paper/Teal ≥ 4.5.
    - Add a unit test asserting all seven type-scale CSS variable values are present in `tokens.css` and each is parseable as a positive number (read the file contents via `fs/promises`).
    - _Requirements: 1.8, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 8.2 Write property test for WCAG contrast ratios (Property 1)
    - Use `fast-check`: `fc.constantFrom(...TOKEN_PAIRS)` sampling from the five pairs.
    - Assert `computeContrastRatio(pair.fg, pair.bg) >= pair.minRatio` for each sampled pair.
    - Run for at least 100 iterations.
    - Tag: `Feature: web-design-system, Property 1: WCAG contrast ratios hold for all required token pairs`
    - _Requirements: 1.8, 2.1–2.5_

  - [ ]* 8.3 Write property test for type scale distinctness (Property 2)
    - Use `fast-check`: `fc.uniqueArray(fc.constantFrom(...SCALE_STEP_NAMES), { minLength: 2, maxLength: 2 })`.
    - Assert `parsedSize(steps[0]) !== parsedSize(steps[1])` for each pair.
    - Run for at least 100 iterations.
    - Tag: `Feature: web-design-system, Property 2: Type scale steps are pairwise distinct`
    - _Requirements: 1.4, 3.4_

- [x] 9. Guard script
  - [x] 9.1 Create `apps/web/scripts/check-tokens.mjs`
    - Export a pure `detectViolations(content: string, filePath: string): GuardViolation[]` function that checks for: hex literals (`/(?<![0-9a-fA-F])#[0-9a-fA-F]{3,8}\b/g`), rgb/hsl literals (`/\b(rgb|hsl)a?\s*\(/g`), Tailwind arbitrary-color classes (`/(?:bg|text|border|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]/g`), `font-family` declarations (`/font-family\s*:/g`), CJK characters (`/[\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFFEF]/g`).
    - Main script body: use `fast-glob` (or recursive `fs/promises.readdir`) to enumerate all `.ts`, `.tsx`, `.css`, `.scss` under `apps/web/src`, excluding `tokens.css` and `fonts.ts`.
    - Also verify Token_File exists and contains all eight required `--color-*` custom properties; emit specific error messages for missing ones.
    - Print one error line per violation (file + line number where possible).
    - Exit 0 if no violations, exit 1 otherwise.
    - Entire scan must complete within 30 seconds.
    - _Requirements: 1.5, 1.6, 1.7, 1.9, 1.10, 3.8_

  - [ ]* 9.2 Write property test for Guard_Script classification (Property 3)
    - Add `apps/web/src/styles/check-tokens.test.ts` (or `scripts/check-tokens.test.ts`).
    - Define `cleanString()` and `violatingString()` fast-check generators.
    - `violatingString()` generates a string containing at least one of the five violation patterns.
    - Assert `detectViolations(content, "test.ts").length > 0` iff the content has a violation, and `=== 0` for clean strings.
    - Run for at least 100 iterations.
    - Tag: `Feature: web-design-system, Property 3: Guard script correctly classifies any file as violating or clean`
    - _Requirements: 1.5, 1.6, 1.7, 10.2, 10.3, 10.4_

- [x] 10. Styleguide route (`/styleguide`)
  - Create `apps/web/src/app/styleguide/page.tsx`.
  - At the top of the file, call `notFound()` from `next/navigation` when `process.env.NODE_ENV === "production"`.
  - Render five sections:
    1. Palette: 8 color swatches, each labeled with token name and hex value.
    2. Type scale: 7 steps in Bricolage Grotesque, each labeled with its step identifier.
    3. Primitives: every restyled shadcn component (Button×5 variants, Badge×7 status states, Input, Select, Table, Tabs, Dialog, Tooltip), each labeled with its variant name.
    4. Status states: all 7 entries from `STATUS_MAP`, showing color fill, icon, and label.
    5. Visual components: PosterCard, StampBadge, VinylSpinner, HalftoneDivider, Wordmark.
  - Apply only token-based Tailwind classes; no hardcoded colors on this page.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 11. Checkpoint — components and styleguide complete
  - Run `tsc --noEmit` to verify no TypeScript errors.
  - Run `vitest run --dir src` and confirm all existing tests still pass.
  - Visually verify `/styleguide` renders all sections correctly in development.
  - Ask the user if any questions arise before beginning page migration.

- [x] 12. Migration: layout, navigation, and Wordmark
  - Open `apps/web/src/app/layout.tsx` and `apps/web/src/components/app-shell.tsx`.
  - Replace the `<html>` background color and `<body>` color with Tailwind token classes (`bg-ink text-paper`).
  - Replace the sidebar/nav background, text, and border colors with token classes.
  - Replace the existing logo/name with the `<Wordmark>` component.
  - Replace any hardcoded status colors in nav-level indicators.
  - Update any removed CSS class selectors in test files and log old→new pairs in `PROGRESS.md`.
  - _Requirements: 9.1, 9.2, 9.5, 9.6_

- [x] 13. Migration: leaderboard page (`/`)
  - Open `apps/web/src/app/page.tsx` and `apps/web/src/components/leaderboard.tsx`.
  - Replace the leaderboard table component with the new `Table` primitive (token classes).
  - Replace any status color indicators with `getStatusEntry()` + token classes.
  - Replace any hardcoded color values with token-based Tailwind classes.
  - Wrap leaderboard cards in `PosterCard` where appropriate.
  - Log any CSS class selector changes in `PROGRESS.md`.
  - Run `vitest run --dir src` after this migration step.
  - _Requirements: 9.1, 9.2, 9.5, 9.6_

- [x] 14. Migration: agents page (`/agents`)
  - Open `apps/web/src/app/agents/` route files and `apps/web/src/components/agents-panel.tsx`.
  - Apply token-based classes throughout; replace hardcoded colors.
  - Replace any status indicators with `getStatusEntry()` outputs.
  - Wrap agent cards in `PosterCard`.
  - Log selector changes in `PROGRESS.md`.
  - Run `vitest run --dir src` after this step.
  - _Requirements: 9.1, 9.2, 9.5, 9.6_

- [x] 15. Migration: benchmark wizard (`/benchmarks/new`)
  - Open `apps/web/src/app/benchmarks/new/` and `apps/web/src/components/benchmark-wizard.tsx`.
  - Replace all hardcoded colors with token classes.
  - Replace form inputs with the restyled `Input` and `Select` primitives.
  - Wrap wizard panels in `PosterCard`.
  - Log selector changes in `PROGRESS.md`.
  - Run `vitest run --dir src` after this step.
  - _Requirements: 9.1, 9.2, 9.5, 9.6_

- [x] 16. Migration: benchmark detail page (`/benchmarks/[id]`)
  - Open `apps/web/src/app/benchmarks/[benchmarkId]/` and `apps/web/src/components/benchmark-monitor.tsx`.
  - Apply token-based classes throughout; replace any hardcoded status colors with `getStatusEntry()`.
  - Replace benchmark result cards with `PosterCard`.
  - Log selector changes in `PROGRESS.md`.
  - Run `vitest run --dir src` after this step.
  - _Requirements: 9.1, 9.2, 9.5, 9.6_

- [x] 17. Migration: run detail page (`/runs/[id]`) — timeline, verdict, diff, payload
  - [x] 17.1 Migrate run step cards and time ruler
    - Open `apps/web/src/components/run-step-card.tsx`, `run-timeline-island.tsx`, and `time-ruler.tsx`.
    - Render LLM, tool, and retry step cards as `PosterCard` variants, each with a unique icon and label.
    - Add `HalftoneDivider` to fault markers; apply `text-red` to fault marker text with reaction label.
    - Apply time-ruler segment colors: `text-teal-glow` / `bg-teal-glow` for LLM segments, `text-tan` / `bg-tan` for tool segments, `bg-red` with hatch pattern for retry and fault segments.
    - Preserve virtualization — do not replace the virtual scroller or its scroll event handler; only change className strings.
    - _Requirements: 9.3, 9.4, 9.5_

  - [x] 17.2 Migrate verdict panel and diff view
    - Open `apps/web/src/components/run-verdict-panel.tsx`.
    - Replace the existing verdict indicator with `StampBadge`, passing the verdict string as the `verdict` prop.
    - Open `apps/web/src/components/payload-view.tsx` and any diff-view subcomponent.
    - Apply `text-tan` to context lines, `text-teal-glow` to addition lines, `text-red-glow` to deletion lines.
    - Ensure `+` and `-` gutter symbols are present (not color-only signaling).
    - Apply `font-space-mono bg-ink-raised` (via Space Mono CSS variable) to payload `pre`/`code` blocks.
    - _Requirements: 9.3, 9.5_

  - [x] 17.3 Migrate run header and inspector
    - Open `apps/web/src/components/run-header.tsx` and `run-inspector.tsx`.
    - Replace all hardcoded colors with token classes; replace status indicators with `getStatusEntry()`.
    - Log selector changes in `PROGRESS.md`.
    - Run `vitest run --dir src` after completing the full `/runs/[id]` migration.
    - _Requirements: 9.2, 9.5, 9.6_

- [x] 18. Checkpoint — migration complete
  - Run `tsc --noEmit` and confirm zero TypeScript errors.
  - Run `vitest run --dir src` and confirm every test passes.
  - Visually inspect each migrated route in development.
  - Ask the user if any questions arise before activating the guard script.

- [x] 19. Activate Guard Script in CI
  - Add `"check-tokens": "node scripts/check-tokens.mjs"` to `apps/web/package.json` `"scripts"`.
  - Add a "Token guard" step to `.github/workflows/check.yml`, placed after the `typecheck` step and before `test`, with `working-directory: apps/web`.
  - Confirm the guard exits 0 on the current source tree before committing.
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 20. Dead CSS cleanup and bundle size measurement
  - Remove all old `:root` custom properties and legacy CSS rules that are no longer referenced (the ones replaced by tokens).
  - Run `next build` with `ANALYZE=true` (if `@next/bundle-analyzer` is configured) to measure CSS output.
  - Measure total CSS size: sum all files under `.next/static/css/`, compress with gzip, convert to kB (÷ 1024, two decimal places).
  - Measure font payload: sum all `.woff2` files in `.next/static/media/` matching `bricolage` and `space-mono` filename prefixes, in kB.
  - Measure paper-grain SVG: record the character count of the inline SVG in the HTML output from `.next/server/app/`.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 21. Final PROGRESS.md update
  - Run the guard script and confirm exit code 0 for all four categories (hex literals, rgb/hsl literals, font-family declarations, inline status-to-color mappings).
  - Fill in the "Post-migration" section of `PROGRESS.md` with the guard's zero counts.
  - Fill in the "Bundle sizes" section with the values from task 20 (pre-migration CSS kB, post-migration CSS kB, paper-grain SVG bytes, font payload kB).
  - Confirm the "Selector updates" table is complete with all old→new pairs logged during migration.
  - _Requirements: 8.5, 11.1, 11.2, 11.3, 11.4_

- [x] 22. Final checkpoint — Ensure all tests pass
  - Run `vitest run --dir src`.
  - Run `node scripts/check-tokens.mjs` and confirm exit code 0.
  - Run `tsc --noEmit` and confirm zero errors.
  - Ask the user if any questions arise.

---

## Notes

- Tasks marked with `*` are optional property-based tests that can be skipped for a faster MVP. The core implementation tasks are not optional.
- Each migration task (12–17) ends with a `vitest run` to catch regressions immediately, keeping the feedback loop tight.
- The Guard Script (task 19) is intentionally activated after migration is confirmed complete; running it earlier would cause false CI failures.
- `fast-check` must be added to `devDependencies` in `apps/web/package.json` before any property tests are run (`npm install -D fast-check` in `apps/web`).
- Tabs, Dialog, and Tooltip (task 5.6) may not have existing stubs; create them from scratch following the same `cva` + `tailwind-merge` pattern used by `button.tsx`.
- The `/styleguide` page returns 404 in production via `notFound()` — no `next.config.ts` changes needed.
- Virtualization in `run-timeline-island.tsx` must not be altered; only `className` strings change.
- Property tests reference design document properties by number and tag for traceability.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.3"] },
    { "id": 1, "tasks": ["2.2", "2.4", "2.5"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "4.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6"] },
    { "id": 4, "tasks": ["6", "8.1", "9.1", "10"] },
    { "id": 5, "tasks": ["8.2", "8.3", "9.2"] },
    { "id": 6, "tasks": ["12", "13", "14", "15", "16"] },
    { "id": 7, "tasks": ["17.1", "17.2", "17.3"] },
    { "id": 8, "tasks": ["19", "20"] },
    { "id": 9, "tasks": ["21"] }
  ]
}
```
