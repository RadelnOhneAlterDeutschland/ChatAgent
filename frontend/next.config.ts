import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Phase 6 (prod deploy): traces only the files `next start` actually needs into
  // `.next/standalone`, so the production image doesn't need the full `node_modules`
  // tree — smaller image, less RAM on the single EC2 box. See frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
