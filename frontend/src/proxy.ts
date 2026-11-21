import { NextResponse, type NextRequest } from "next/server";

// English is served at the clean URL by rewriting it to /en; Khmer lives under /km.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/en" || pathname.startsWith("/en/") || pathname === "/km" || pathname.startsWith("/km/")) {
    return NextResponse.next();
  }
  return NextResponse.rewrite(new URL(`/en${pathname === "/" ? "" : pathname}`, request.url));
}

export const config = {
  // Everything except static assets, Next internals and the raw ledger route.
  matcher: ["/((?!_next|ledger\\.json|logo\\.jpg|icon\\.png|apple-icon\\.png|favicon\\.ico|robots\\.txt|sitemap\\.xml).*)"],
};
