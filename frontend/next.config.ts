import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  ...((process.env.NEXT_PUBLIC_AEGIS_DEMO === "1" || process.env.AEGIS_PRIVATE_DOCKER_BUILD === "1") ? { output: "standalone" as const } : {}),
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
