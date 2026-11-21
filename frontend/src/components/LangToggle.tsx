"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Lang } from "@/lib/i18n";

// Links to the same page in the other language. English URLs carry no prefix; Khmer ones start with /km.
export default function LangToggle({ lang, label }: { lang: Lang; label: string }) {
  const pathname = usePathname() ?? "/";
  const bare = pathname.replace(/^\/(en|km)(?=\/|$)/, "") || "/";
  const target = lang === "en" ? `/km${bare === "/" ? "" : bare}` || "/km" : bare;
  return (
    <Link href={target} className="rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:bg-card hover:text-fg" aria-label="Switch language">
      {label}
    </Link>
  );
}
