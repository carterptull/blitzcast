import type { NextConfig } from "next";

// No X-Frame-Options here: it can't express multiple allowed origins, and CSP
// frame-ancestors overrides it in every browser that supports both, so setting
// both would just be dead weight. The external origins below are the
// maintainer's portfolio site, which embeds this app in a window; 'self' keeps
// that possible if blitzcast.app ever frames its own pages.
const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value:
      "frame-ancestors 'self' https://cartertull.com https://www.cartertull.com; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
];

const nextConfig: NextConfig = {
  // Next.js 16.3+ auto-generates AGENTS.md/CLAUDE.md scaffolding on
  // dev/build; this repo has its own hand-maintained CLAUDE.md, so opt out.
  agentRules: false,
  poweredByHeader: false,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "a.espncdn.com",
        pathname: "/i/teamlogos/nfl/**",
      },
      {
        protocol: "https",
        hostname: "a.espncdn.com",
        pathname: "/i/teamlogos/ncaa/**",
      },
    ],
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
