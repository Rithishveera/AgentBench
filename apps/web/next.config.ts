import type { NextConfig } from "next";
import path from "node:path";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    key: "Content-Security-Policy",
    value:
      "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; upgrade-insecure-requests",
  },
];

const apiBase = (process.env.AGENTBENCH_API_URL ?? "http://api:8000").replace(/\/$/, "");

const config: NextConfig = {
  output: process.env.AGENTBENCH_STANDALONE === "1" ? "standalone" : undefined,
  outputFileTracingRoot: path.join(__dirname, "../.."),
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    return [
      // Proxy the WebSocket stream to the Python API — ticket handles auth.
      {
        source: "/api/benchmarks/:benchmarkId/ws",
        destination: `${apiBase}/benchmarks/:benchmarkId/stream`,
      },
    ];
  },
};

export default config;