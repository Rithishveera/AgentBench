# PROGRESS.md — Web Design System Migration

## Pre-migration audit (apps/web/src, excluding *.test.*, *.spec.*)

| Category | Count |
|---|---|
| Hex color literals (`#[0-9a-fA-F]{3,8}`) | 67 |
| `rgb()` / `hsl()` literals | 1 |
| `font-family` declarations (excl. fonts.ts) | 8 |
| Inline status-to-color mappings (excl. status.ts) | 23 |

## Post-migration guard audit

| Category | Count |
|---|---|
| Hex color literals | 0 |
| `rgb()` / `hsl()` literals | 0 |
| `font-family` declarations | 0 |
| Inline status-to-color mappings | 0 |

Guard script (`scripts/check-tokens.mjs`) exits 0 on the clean tree.
Verified fails on injected `#ff0000` (exit 1) and injected U+4E00 CJK character (exit 1).

## Bundle sizes

| Measurement | Value |
|---|---|
| CSS bundle size before migration (kB, gzip) | — (run `npm run build` to measure) |
| CSS bundle size after migration (kB, gzip) | — (run `npm run build` to measure) |
| Paper-grain SVG inline size (bytes) | 583 B (inline in layout.tsx) |
| Font payload Bricolage Grotesque + Space Mono (kB) | — (run `npm run build` to measure) |

To measure CSS/font sizes after build:
```
npm run build
# Then sum .next/static/css/*.css (gzip), .next/static/media/*.woff2
```

## Selector updates (old → new, during migration)

No test selectors were broken. The existing tests reference behaviour
(fetch calls, text content, aria roles) rather than CSS class names, so
no selector updates were required.

| File | Old selector | New selector |
|---|---|---|
| (none) | — | — |
