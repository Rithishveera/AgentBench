#!/usr/bin/env node
/**
 * check-tokens.mjs — Token Guard Script
 *
 * Fails (exit 1) if any file under apps/web/src (excluding:
 *   - tokens.css, fonts.ts  (the two authorized hex sources)
 *   - *.test.ts, *.test.tsx (contrast tests must reference hex values)
 *   - styleguide/page.tsx   (must display hex values as documentation)
 * ) contains:
 *   - Hex color literals (#abc or #aabbcc or #aabbccdd)
 *   - rgb() / hsl() color literals
 *   - Tailwind arbitrary-color classes (bg-[#...], text-[#...] etc.)
 *   - font-family CSS declarations
 *   - CJK Unicode characters (U+4E00-U+9FFF, U+3000-U+303F, U+FF00-U+FFEF)
 *
 * Also verifies tokens.css defines all 8 required --color-* custom properties.
 */

import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";

const SRC_DIR = new URL("../src", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const TOKEN_FILE_REL = "styles/tokens.css";
const FONT_FILE_REL  = "lib/fonts.ts";
const TOKEN_FILE = join(SRC_DIR, TOKEN_FILE_REL);
const FONT_FILE  = join(SRC_DIR, FONT_FILE_REL);

const REQUIRED_COLORS = [
  "--color-ink",
  "--color-ink-raised",
  "--color-teal",
  "--color-red",
  "--color-tan",
  "--color-paper",
  "--color-teal-glow",
  "--color-red-glow",
];

const EXTENSIONS = new Set([".ts", ".tsx", ".css", ".scss"]);

/** Exempt files (relative to SRC_DIR, forward slashes) */
const EXEMPT = new Set([
  TOKEN_FILE_REL,
  FONT_FILE_REL,
]);

/** @type {Array<{pattern: RegExp, message: string, skipTestFiles?: boolean}>} */
const CHECKS = [
  {
    pattern: /(?<![0-9a-fA-F])#[0-9a-fA-F]{3,8}\b/g,
    message: "hex color literal",
  },
  {
    pattern: /\b(rgb|hsl)a?\s*\(/g,
    message: "rgb()/hsl() literal",
  },
  {
    pattern: /(?:bg|text|border|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]/g,
    message: "Tailwind arbitrary-color class",
  },
  {
    pattern: /font-family\s*:/g,
    message: "font-family declaration",
  },
  {
    pattern: /[\u4E00-\u9FFF\u3000-\u303F\uFF00-\uFFEF]/g,
    message: "CJK character",
  },
];

/**
 * @param {string} content
 * @param {string} filePath
 * @returns {string[]} violation messages
 */
export function detectViolations(content, filePath) {
  const violations = [];
  for (const { pattern, message } of CHECKS) {
    const regex = new RegExp(pattern.source, pattern.flags);
    let match;
    while ((match = regex.exec(content)) !== null) {
      const lineNo = content.slice(0, match.index).split("\n").length;
      violations.push(`${filePath}:${lineNo}: ${message} "${match[0]}"`);
    }
  }
  return violations;
}

async function walk(dir) {
  const files = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") continue;
      files.push(...await walk(full));
    } else if (EXTENSIONS.has(entry.name.slice(entry.name.lastIndexOf(".")))) {
      files.push(full);
    }
  }
  return files;
}

async function main() {
  const start = Date.now();
  let exitCode = 0;
  const allViolations = [];

  // 1. Verify tokens.css exists and has all 8 required properties
  try {
    const tokenContent = await readFile(TOKEN_FILE, "utf8");
    for (const prop of REQUIRED_COLORS) {
      if (!tokenContent.includes(prop)) {
        console.error(`tokens.css: missing required property "${prop}"`);
        exitCode = 1;
      }
    }
  } catch {
    console.error(`tokens.css not found at: ${TOKEN_FILE}`);
    exitCode = 1;
  }

  // 2. Scan source files
  const files = await walk(SRC_DIR);
  for (const file of files) {
    const relPath = relative(SRC_DIR, file).replace(/\\/g, "/");

    // Skip exempt files (tokens.css, fonts.ts)
    if (EXEMPT.has(relPath)) continue;

    // Skip test/spec files and styleguide (they intentionally reference hex values)
    if (relPath.includes(".test.") || relPath.includes(".spec.") || relPath.includes("styleguide/")) continue;

    const content = await readFile(file, "utf8");
    const violations = detectViolations(content, relPath);
    allViolations.push(...violations);
  }

  if (allViolations.length > 0) {
    for (const v of allViolations) {
      console.error(v);
    }
    exitCode = 1;
  }

  const elapsed = Date.now() - start;
  if (elapsed > 30000) {
    console.error(`Guard script exceeded 30 second limit (${elapsed}ms)`);
    exitCode = 1;
  }

  // Exit 0 produces no output (requirement 10.2)
  process.exit(exitCode);
}

await main();
