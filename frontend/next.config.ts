import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output is what frontend/Dockerfile copies into the runtime image.
  output: "standalone",
  // The Method page reads content/*.md at request time; the standalone tracer cannot see a dynamic path.
  outputFileTracingIncludes: { "/[lang]/(site)/method": ["./content/**/*"] },
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
