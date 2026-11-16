import { Bricolage_Grotesque, Space_Mono } from "next/font/google";

/**
 * Font_Module — single point of font loading.
 * Both fonts are self-hosted at build time via next/font/google.
 * No runtime requests to fonts.googleapis.com or fonts.gstatic.com.
 *
 * RULE: font-family declarations belong here only.
 */

export const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  axes: ["wdth", "opsz"],
  variable: "--font-bricolage",
  display: "swap",
});

export const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
  display: "swap",
});
