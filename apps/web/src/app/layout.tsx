import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { bricolage, spaceMono } from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgentBench | Evaluation workspace",
  description: "Benchmark AI agents across tasks, cost, latency, and resilience.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${bricolage.variable} ${spaceMono.variable}`}>
      <body>
        <Providers>{children}</Providers>
        {/* Paper-grain overlay — fixed, pointer-events none, renders once per page load */}
        <svg
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            width: "100%",
            height: "100%",
            opacity: 0.05,
            pointerEvents: "none",
            zIndex: 9999,
          }}
        >
          <filter id="grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <rect width="100%" height="100%" filter="url(#grain)" />
        </svg>
      </body>
    </html>
  );
}
