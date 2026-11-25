import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output is what frontend/Dockerfile copies into the runtime image.
  output: "standalone",
  // The Method page reads content/*.md at request time; the standalone tracer cannot see a dynamic path.
  outputFileTracingIncludes: { "/**/method": ["./content/**/*"] },
  // English only since 2026-11-25. Old /km and /en links land on the same page at its clean URL.
  // Temporary (307) on purpose, so a language could come back without browsers having cached the redirect.
  async redirects() {
    return ["km", "en"].flatMap((lang) => [
      { source: `/${lang}`, destination: "/", permanent: false },
      { source: `/${lang}/:path*`, destination: "/:path*", permanent: false },
    ]);
  },
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
