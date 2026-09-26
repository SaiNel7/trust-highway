import type { NextConfig } from "next";

// GitHub Pages serves project sites from a subpath (e.g. /trust-highway).
// The deploy workflow sets PAGES_BASE_PATH from actions/configure-pages;
// it is empty during local development.
const nextConfig: NextConfig = {
  output: "export",
  basePath: process.env.PAGES_BASE_PATH,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;