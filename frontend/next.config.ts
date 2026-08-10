import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js 16.3+ auto-generates AGENTS.md/CLAUDE.md scaffolding on
  // dev/build; this repo has its own hand-maintained CLAUDE.md, so opt out.
  agentRules: false,
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
};

export default nextConfig;
