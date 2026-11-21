import { LayoutDashboard } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import LangToggle from "@/components/LangToggle";
import { href, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

// Marketing-site header: logo, section links, language, and the way into the dashboard.
export default function Nav({ lang }: { lang: Lang }) {
  const d = t(lang);
  const links = [
    { to: "/", label: d.nav.home },
    { to: "/app/signals", label: d.nav.signals },
    { to: "/track-record", label: d.nav.record },
    { to: "/method", label: d.nav.method },
    { to: "/pricing", label: d.nav.pricing },
  ];
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5">
        <Link href={href(lang, "/")} className="flex items-center gap-2.5 font-semibold tracking-tight">
          <Image src="/logo.jpg" alt={site.name} width={36} height={36} className="rounded-lg" priority />
          <span className="leading-tight">
            <span className="block text-gold">{site.name}</span>
            <span className="block text-[11px] font-normal text-muted">{site.tagline}</span>
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {links.map((link) => (
            <Link key={link.to} href={href(lang, link.to)} className="hidden rounded-md px-2.5 py-1.5 text-muted hover:bg-surface-2 hover:text-text md:inline">
              {link.label}
            </Link>
          ))}
          <Suspense fallback={<span className="pill">{d.nav.other}</span>}>
            <LangToggle lang={lang} label={d.nav.other} />
          </Suspense>
          <Link href={href(lang, "/app")} className="btn-primary ml-1 !min-h-9 !py-1.5 text-sm">
            <LayoutDashboard size={15} /> <span className="hidden sm:inline">{d.nav.dashboard}</span>
          </Link>
        </nav>
      </div>
    </header>
  );
}
