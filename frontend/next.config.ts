import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  ...(process.env.AEGIS_DOCKER_BUILD === "1"
    ? { output: "standalone" as const }
    : {}),
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
