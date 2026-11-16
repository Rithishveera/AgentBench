# Requirements Document

## Introduction

The AgentBench web application (`apps/web`) already ships with M11 (leaderboard, agents panel, new-benchmark wizard, benchmark status table) and M12 (run timeline inspector, verdict panel, diff view) built with default styling. This feature introduces a **vintage-American-poster design system** and migrates every existing page to it.

The scope is **styling only**: tokens, shared components, and the markup needed to apply them. No behavior, routes, data-fetching logic, API calls, security headers/CSP, or test assertions change.

---

## Glossary

- **Design_System**: The set of tokens, shared components, guard scripts, and contrast tests defined by this feature.
- **Token_File**: `apps/web/src/styles/tokens.css` — the single source for every color, radius, shadow, and type-scale value as CSS custom properties.
- **Font_Module**: `apps/web/src/lib/fonts.ts` — the single point of font loading via `next/font/google` for Bricolage Grotesque and Space Mono.
- **Status_Module**: `apps/web/src/lib/status.ts` — the single source of truth mapping run-status strings to color token, icon, and label.
- **Guard_Script**: A Node.js script (`apps/web/scripts/check-tokens.mjs`) that fails if any hex literal, `rgb()`/`hsl()` literal, Tailwind arbitrary-color class, `font-family` declaration, or CJK character appears outside Token_File and Font_Module.
- **Contrast_Test**: An automated test (`apps/web/src/styles/tokens.test.ts`) that asserts WCAG contrast ratios for all specified token pairs.
- **Styleguide_Route**: A Next.js route (`/styleguide`) included in development builds only, rendering palette, type scale, every restyled primitive, and every status state.
- **PosterCard**: A shared card component with radius 28 px, 2 px tan outer border, and 1 px tan inner hairline 6 px inset.
- **StampBadge**: A verdict badge styled as a rubber stamp (slight −3 deg rotation, double border, stamp-in animation on first render).
- **VinylSpinner**: A loading indicator rendered as a spinning vinyl-record SVG with a black disc, groove rings, and a red center label.
- **HalftoneDivider**: A section divider or error-region overlay using a CSS `radial-gradient` halftone dot pattern.
- **Wordmark**: A logo component displaying "AGENTBENCH" in display style alongside a vinyl-record mark.
- **Ink**: Background color `#1A1A1A` (page background).
- **Ink_Raised**: Raised-surface color `#1E2323` (ink mixed with 12 % teal).
- **Teal**: Primary fill color `#3E6868` — used for surfaces, pass state, and primary cards only, never for text or thin borders on Ink.
- **Red**: Accent color `#C94E44` — used for primary CTA, failure, fault events; text on Red must be bold and ≥ 19 px.
- **Tan**: Border/frame and secondary-text color `#C1AB85`, also used for warning/timeout state.
- **Paper**: Main text color `#EFE6D2`.
- **Teal_Glow**: `#7FAAA5` — teal for small text, icons, and lines on Ink.
- **Red_Glow**: `#E0776D` — red for small text and icons on Ink.
- **Bricolage_Grotesque**: Variable font (wght 200–800, wdth 75–100, opsz), self-hosted via `next/font/google`.
- **Space_Mono**: Monospace font used exclusively inside `pre`/`code` blocks.
- **PROGRESS_md**: `apps/web/PROGRESS.md` — documents the pre-migration audit counts, any test-selector updates, and bundle CSS sizes before and after.

---

## Requirements

### Requirement 1: Brand Palette Tokens

**User Story:** As a developer, I want all brand colors defined once as CSS custom properties, so that every component references tokens and no component hard-codes color values.

#### Acceptance Criteria

1. THE Token_File SHALL define CSS custom properties for the eight palette colors: `--color-ink` (`#1A1A1A`), `--color-ink-raised` (`#1E2323`), `--color-teal` (`#3E6868`), `--color-red` (`#C94E44`), `--color-tan` (`#C1AB85`), `--color-paper` (`#EFE6D2`), `--color-teal-glow` (`#7FAAA5`), and `--color-red-glow` (`#E0776D`).
2. THE Token_File SHALL map every token to both a Tailwind theme extension and a shadcn CSS variable alias so that Tailwind utility classes (e.g. `bg-teal`, `text-paper`) work without duplicating hex values.
3. THE Token_File SHALL define derived tints exclusively by mixing the eight palette colors with Ink or Paper via CSS `color-mix()`, never introducing new hue values.
4. THE Token_File SHALL define CSS custom properties for border-radius (`--radius-card: 28px`, `--radius-pill: 9999px`), shadow offsets (`--shadow-teal: 6px 6px 0 var(--color-teal)`, `--shadow-red: 6px 6px 0 var(--color-red)`), and a seven-step type scale (`--text-xs` through `--text-display`) where each step's value is a fixed pixel or rem size such that no two steps share the same computed size.
5. THE Guard_Script SHALL exit with a non-zero code when any file under `apps/web/src` (excluding Token_File and Font_Module) contains a hex color literal, an `rgb()` or `hsl()` literal, a Tailwind arbitrary-color class of the form `bg-[#...]` or `text-[#...]`, or a `font-family` CSS declaration.
6. THE Guard_Script SHALL exit with a non-zero code when any file under `apps/web/src` contains a CJK Unicode character (U+4E00–U+9FFF, U+3000–U+303F, U+FF00–U+FFEF).
7. THE Guard_Script SHALL exit with code 0 when no violations are present across all checks defined in criteria 5 and 6.
8. FOR ALL token pairs listed in Requirement 2 (Contrast), THE Contrast_Test SHALL assert the computed contrast ratio meets or exceeds the minimum specified ratio.
9. IF the Token_File is absent or defines fewer than the eight required palette custom properties at build time, THEN THE Guard_Script SHALL exit with a non-zero code and emit an error message indicating which properties are missing.
10. WHEN the Guard_Script is invoked, THE Guard_Script SHALL complete execution and produce its exit code within 30 seconds regardless of the number of files scanned under `apps/web/src`.

---

### Requirement 2: Contrast and Accessibility Rules

**User Story:** As a user, I want text and icons to always meet WCAG contrast minimums and be distinguished by more than color alone, so that the UI is readable under any accessibility need.

#### Acceptance Criteria

1. THE Contrast_Test SHALL assert that Paper (`#EFE6D2`) on Ink (`#1A1A1A`) achieves a contrast ratio ≥ 10.0:1.
2. THE Contrast_Test SHALL assert that Tan (`#C1AB85`) on Ink (`#1A1A1A`) achieves a contrast ratio ≥ 7.0:1.
3. THE Contrast_Test SHALL assert that Teal_Glow (`#7FAAA5`) on Ink (`#1A1A1A`) achieves a contrast ratio ≥ 4.5:1.
4. THE Contrast_Test SHALL assert that Red_Glow (`#E0776D`) on Ink (`#1A1A1A`) achieves a contrast ratio ≥ 4.5:1.
5. THE Contrast_Test SHALL assert that Paper (`#EFE6D2`) on Teal (`#3E6868`) achieves a contrast ratio ≥ 4.5:1.
6. THE Design_System SHALL prohibit use of Teal (`#3E6868`) as a text color or as a border narrower than 2 px on an Ink background, enforced by a lint rule in the Token_File that causes the Contrast_Test suite to fail when either prohibited use is detected.
7. WHEN a status indicator component renders a run state of passed, failed, timeout, agent_error, infra_error, running, or queued, THE Design_System SHALL render a color fill, a distinct icon shape, and a text label simultaneously for that state, so that no single channel (color, icon, or label) is the sole signal.
8. WHEN an interactive element of type button, link, text input, or select receives keyboard focus, THE Design_System SHALL render a focus ring of 2 px width in the Tan color with a 2 px offset around that element.

---

### Requirement 3: Typography

**User Story:** As a developer, I want all type settings (family, weight, scale) defined centrally, so that no component introduces ad-hoc font sizes or family declarations.

#### Acceptance Criteria

1. THE Font_Module SHALL load Bricolage Grotesque via `next/font/google` with axes `wght` (200–800), `wdth` (75–100), and `opsz` (8–144), producing self-hosted font files at build time.
2. THE Font_Module SHALL load Space Mono via `next/font/google` with weight `400` and `700`, producing self-hosted font files at build time.
3. THE Design_System SHALL set Bricolage Grotesque as the `font-family` on the `html` element and SHALL set Space Mono as the `font-family` on `pre` and `code` elements only.
4. THE Token_File SHALL define exactly seven type-scale steps as CSS custom properties: `--text-xs`, `--text-sm`, `--text-base`, `--text-md`, `--text-lg`, `--text-xl`, `--text-display`.
5. THE Design_System SHALL apply the following styles to `h1`, `h2`, `h3`, `h4`, `h5`, and `h6` elements: `text-transform: uppercase`, `font-weight: 800`, `font-stretch: 75%`, and `letter-spacing: -0.01em`.
6. THE Design_System SHALL apply `font-variant-numeric: tabular-nums` to every `td` element and every element carrying the `data-metric` attribute that renders a numeric value.
7. WHEN the production build is served, THE Font_Module SHALL emit zero network requests to `fonts.googleapis.com` or `fonts.gstatic.com` at runtime (all font files served from `'self'`).
8. THE Guard_Script SHALL exit with a non-zero exit code and emit an error message identifying the offending file and line number WHEN any file under `apps/web/src` whose path does not match the Font_Module file pattern contains a `font-family` CSS declaration.

---

### Requirement 4: Visual Language Components

**User Story:** As a developer, I want a set of reusable visual components that embody the vintage-American-poster aesthetic, so that all pages share a consistent look without duplicating styles.

#### Acceptance Criteria

1. THE PosterCard SHALL render with `border-radius: var(--radius-card)`, a 2 px outer border in Tan, and a 1 px inner hairline in Tan inset 6 px from the outer border.
2. THE PosterCard SHALL render a hard-offset shadow of `6px 6px 0` using either `var(--color-teal)` (default) or `var(--color-red)` (error emphasis), with no blur radius.
3. THE StampBadge SHALL render with a double border in Tan consisting of a 2 px outer stroke and a 1 px inner stroke separated by a 3 px gap, and a rotation of −3 deg.
4. WHEN the StampBadge first renders, THE StampBadge SHALL play a stamp-in animation that scales from 1.15 to 1.0 over exactly 160 ms.
5. WHEN the user has enabled `prefers-reduced-motion`, THE StampBadge SHALL skip the stamp-in animation and render the badge at scale 1.0 immediately.
6. THE VinylSpinner SHALL render as an SVG with a black disc, a minimum of 3 concentric groove rings evenly spaced, and a Red center label.
7. WHEN the VinylSpinner is visible and `prefers-reduced-motion` is not enabled, THE VinylSpinner SHALL rotate continuously at 33 rpm (one full rotation every 1818 ms) using a linear CSS animation.
8. WHEN the user has enabled `prefers-reduced-motion`, THE VinylSpinner SHALL render statically without rotation.
9. THE HalftoneDivider SHALL accept a palette color token as a required prop and render a CSS `radial-gradient` dot pattern compositing that token with Ink.
10. THE Wordmark SHALL render the text "AGENTBENCH" in display style (Bricolage Grotesque, weight 800, condensed) alongside a vinyl-record SVG mark.
11. THE Design_System SHALL render a full-page, fixed SVG `feTurbulence` paper-grain overlay at exactly 5% opacity (±0.5%) with `pointer-events: none`, rendered once per page load.
12. THE Design_System SHALL apply pill-shaped geometry (`border-radius: var(--radius-pill)`) to all Button and Badge/chip components.

---

### Requirement 5: Status Mapping

**User Story:** As a developer, I want a single module that maps every run status to its color token, icon, and label, so that status presentation is consistent across all pages and no page hard-codes status colors.

#### Acceptance Criteria

1. THE Status_Module SHALL export a mapping covering exactly these seven status values: `passed`, `failed`, `timeout`, `agent_error`, `infra_error`, `running`, `queued`.
2. THE Status_Module SHALL map `passed` to Teal fill, a check icon, and the label "Passed".
3. THE Status_Module SHALL map `failed` to Red, a cross icon, and the label "Failed".
4. THE Status_Module SHALL map `timeout` to Tan, a clock icon, and the label "Timeout".
5. THE Status_Module SHALL map `agent_error` to Red with a hatched overlay pattern of 45-degree lines at 4 px spacing, a bolt icon, and the label "Agent error".
6. THE Status_Module SHALL map `infra_error` to Ink_Raised with a Tan hatched overlay pattern of 45-degree lines at 4 px spacing, a wrench icon, and the label "Infra error".
7. THE Status_Module SHALL map `running` to a Tan outline, the VinylSpinner icon, and the label "Running".
8. THE Status_Module SHALL map `queued` to a Tan outline, an ellipsis/dots icon, and the label "Queued".
9. IF a status value is not in the mapping, THEN THE Status_Module SHALL return a fallback entry using Paper color, a question-mark icon, and the label "Unknown".

---

### Requirement 6: Restyled Shadcn Primitives

**User Story:** As a developer, I want shadcn/ui primitives (Button, Card, Badge, Table, Input, Select, Tabs, Dialog, Tooltip) restyled to the design system tokens, so that all composed pages automatically inherit the vintage-poster aesthetic.

#### Acceptance Criteria

1. THE Design_System SHALL restyle the Button primitive with pill geometry (`border-radius: var(--radius-pill)`) and the following variant tokens: solid (Red background, Paper text); outline (Tan border, transparent background, Paper text); quiet (Teal_Glow text, transparent background); danger (Red background, Paper text); ghost (Ink_Raised text, transparent background).
2. THE Design_System SHALL apply a 2 px Tan focus ring with 2 px offset to the Button primitive on keyboard focus.
3. THE Design_System SHALL restyle the Card primitive to match PosterCard geometry (radius, double border, hard-offset shadow).
4. THE Design_System SHALL restyle the Badge primitive with pill geometry and status-token colors sourced from Status_Module.
5. THE Design_System SHALL restyle the Table primitive with Paper text on Ink_Raised header cells, Tan column dividers between cells, and `font-variant-numeric: tabular-nums` applied to cells whose content consists entirely of digits, decimal points, or numeric separators.
6. THE Design_System SHALL restyle Input and Select primitives with Tan border, Ink_Raised background, Paper text, and a 2 px Tan focus ring with 2 px offset on keyboard focus.
7. THE Design_System SHALL restyle Tabs, Dialog, and Tooltip primitives to use Ink_Raised surfaces, Tan borders, and Paper text.

---

### Requirement 7: Styleguide Route

**User Story:** As a developer, I want a `/styleguide` page that shows every design token and component in one place, so that I can verify the design system is correctly applied without opening every page.

#### Acceptance Criteria

1. WHEN the `/styleguide` page is rendered, THE Styleguide_Route SHALL display all eight palette color swatches, each labeled with its token name and hex value.
2. WHEN the `/styleguide` page is rendered, THE Styleguide_Route SHALL display the full seven-step type scale rendered in Bricolage Grotesque, with each step labeled by its scale identifier.
3. WHEN the `/styleguide` page is rendered, THE Styleguide_Route SHALL display every restyled shadcn primitive (Button, Card, Badge, Table, Input, Select, Tabs, Dialog, Tooltip), with each primitive shown in all variants defined in Token_File; each variant SHALL be labeled with its variant name.
4. WHEN the `/styleguide` page is rendered, THE Styleguide_Route SHALL display all seven Status_Module states, each showing the color fill, icon, and label defined for that state.
5. WHEN the `/styleguide` page is rendered, THE Styleguide_Route SHALL display PosterCard, StampBadge, VinylSpinner, HalftoneDivider, and Wordmark components.
6. WHEN the production build is generated, THE Styleguide_Route SHALL be absent from the build output such that a request to `/styleguide` returns a 404 response.
7. WHEN a CSS property scan is performed on the computed styles of all elements on the rendered `/styleguide` page, THE Styleguide_Route SHALL contain no `color`, `background-color`, or `border-color` values whose hue is outside the eight palette colors and their ink/paper mix variants defined in Token_File.

---

### Requirement 8: Pre-Migration Audit

**User Story:** As a developer, I want a documented count of all hardcoded colors, font declarations, and status-to-color mappings in the existing source before migration begins, so that I know what must be replaced and can verify the audit count reaches zero after migration.

#### Acceptance Criteria

1. WHEN the pre-migration audit is run, THE PROGRESS_md SHALL record the count of hardcoded hex color literals (strings matching the pattern `#[0-9a-fA-F]{3,8}`) found in all `.ts`, `.tsx`, `.css`, and `.scss` files under `apps/web/src`, excluding test files (`*.test.*`, `*.spec.*`).
2. WHEN the pre-migration audit is run, THE PROGRESS_md SHALL record the count of `rgb()` and `hsl()` color literals found in all `.ts`, `.tsx`, `.css`, and `.scss` files under `apps/web/src`, excluding test files.
3. WHEN the pre-migration audit is run, THE PROGRESS_md SHALL record the count of `font-family` declarations found in all `.ts`, `.tsx`, `.css`, and `.scss` files under `apps/web/src`, excluding Font_Module and test files.
4. WHEN the pre-migration audit is run, THE PROGRESS_md SHALL record the count of inline status-to-color mappings (direct assignments of a color value to a status string key outside Status_Module) found in all `.ts` and `.tsx` files under `apps/web/src`, excluding test files.
5. WHEN migration is complete and the Guard_Script audit is run, THE PROGRESS_md SHALL document that the Guard_Script reports a count of 0 for each of the four categories recorded in criteria 1–4.

---

### Requirement 9: Page Migration

**User Story:** As a user, I want every existing page to render with the vintage-poster design system, so that the visual experience is consistent across the whole application.

#### Acceptance Criteria

1. WHEN page migration begins, THE Design_System migration SHALL proceed in this order: layout and nav and wordmark, then leaderboard (`/`), then agents (`/agents`), then benchmark wizard (`/benchmarks/new`), then benchmark detail (`/benchmarks/[id]`), then run detail (`/runs/[id]`).
2. WHEN any page is migrated, THE Design_System SHALL replace every hardcoded status color identified in the Requirement 8 pre-migration audit with the corresponding Status_Module color, icon, and label for that status.
3. WHEN the run timeline page (`/runs/[id]`) is migrated, THE Design_System SHALL render LLM, tool, and retry step cards as PosterCard variants, each distinguished by a unique icon and label; fault markers SHALL use the Red palette color with HalftoneDivider and a reaction label; the proportional time ruler SHALL use Teal_Glow for LLM segments, Tan for tool segments, and Red with a distinct hatch pattern for retry and fault segments; the verdict panel SHALL use StampBadge; the diff view SHALL use Tan for context lines, Teal_Glow for addition lines, and Red_Glow for deletion lines with `+` and `-` gutter symbols respectively; payload `pre` blocks SHALL use Space Mono on the Ink_Raised background token.
4. WHEN the run timeline page (`/runs/[id]`) is migrated, THE Design_System SHALL preserve virtualization, lazy payload loading, and keyboard navigation such that a timeline of 1,000 steps scrolls without the main thread blocking for more than 50 ms per frame as measured by a browser performance trace.
5. WHEN any page is migrated, THE Design_System SHALL not alter any route path, data-fetching call, API endpoint, security header, or CSP directive.
6. WHEN any test selector is updated to remove a deleted CSS class during migration, THE PROGRESS_md SHALL record each such update as a pair showing the old selector and the new selector.

---

### Requirement 10: CI Guard Integration

**User Story:** As a CI engineer, I want the Guard_Script integrated into the CI pipeline only after migration is complete, so that the pipeline does not fail mid-migration but does prevent regressions once the system is clean.

#### Acceptance Criteria

1. THE Guard_Script SHALL be added to the CI check pipeline (`apps/web/package.json` scripts) only after PROGRESS_md documents that the Guard_Script audit count is 0 for all four categories defined in Requirement 8.
2. WHEN the Guard_Script is active in CI and all source files comply, THE Guard_Script SHALL exit with code 0 and produce no output on stdout or stderr.
3. WHEN the Guard_Script is active and a file under `apps/web/src` (outside Token_File and Font_Module) contains any hex color literal matching `#[0-9a-fA-F]{3,8}`, THE Guard_Script SHALL exit with a non-zero code.
4. WHEN the Guard_Script is active and a file under `apps/web/src` contains any Unicode character in the CJK Unified Ideographs block (U+4E00–U+9FFF), THE Guard_Script SHALL exit with a non-zero code.

---

### Requirement 11: Bundle and Performance Documentation

**User Story:** As a developer, I want the page-weight impact of the paper-grain SVG and new fonts documented, so that the team can make an informed decision about performance trade-offs.

#### Acceptance Criteria

1. WHEN the pre-migration production build is generated, THE PROGRESS_md SHALL record the total combined size of all CSS files in the build output, measured in kB rounded to two decimal places at gzip compression.
2. WHEN the post-migration production build is generated, THE PROGRESS_md SHALL record the total combined size of all CSS files in the build output, measured in kB rounded to two decimal places at gzip compression.
3. WHEN the post-migration production build is generated, THE PROGRESS_md SHALL record the uncompressed file size of the paper-grain SVG overlay asset in bytes.
4. WHEN the post-migration production build is generated, THE PROGRESS_md SHALL record the total self-hosted font payload size for the Bricolage Grotesque and Space Mono subsets combined, measured in kB rounded to two decimal places.
5. WHEN the production build is complete, THE Design_System SHALL reference only locally hosted font files such that loading any page in the application generates zero network requests to domains outside the application's own origin for font resources.

---

### Requirement 12: Existing Tests Preservation

**User Story:** As a QA engineer, I want all M11 and M12 tests to pass after the migration without changes to their assertions, so that the migration introduces no regressions.

#### Acceptance Criteria

1. WHEN the design-system migration is applied, THE existing test suite (`apps/web/src/**/*.test.*`) SHALL pass with no changes to any test assertion logic; only CSS class name selectors that reference a class removed during migration MAY be updated to the replacement class name as specified in Requirement 9 criterion 6.
2. WHERE a test file references a CSS class name that was removed during migration, THE test selector SHALL be updated to the replacement class name, and each such update SHALL be listed in PROGRESS_md per the format defined in Requirement 9 criterion 6.
3. THE client-bundle security test (`apps/web/tests/client-bundle.test.mjs`) SHALL pass without any modification after the migration.
4. WHEN the production build is generated, THE build output SHALL contain no changes to API route handlers, server-side data-fetching logic, or the structure of any response returned by a backend-for-frontend endpoint.
