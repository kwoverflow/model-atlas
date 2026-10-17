/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  distDir: process.env.NEXT_DIST_DIR || ".next",
  devIndicators: false,
  agentRules: false
};

export default nextConfig;
