import type { NextConfig } from "next";

const basePath = process.env.CALC_BASE_PATH || "";

const nextConfig: NextConfig = {
  agentRules: false,
  output: "export",
  images: { unoptimized: true },
  ...(basePath ? { basePath } : {}),
};

export default nextConfig;
