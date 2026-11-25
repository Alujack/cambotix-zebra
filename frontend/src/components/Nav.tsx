import { LayoutDashboard } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
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
    { to: "/app/terminal", label: d.nav.terminal },
  ];
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[linear-gradient(90deg,rgba(6,7,7,0.92),rgba(24,19,8,0.88),rgba(6,7,7,0.92))] backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 lg:px-6">
        <Link href={href(lang, "/")} className="flex flex-none items-center gap-3">
          <Image src="/logo.jpg" alt="" width={40} height={40} className="rounded-xl ring-1 ring-gold/30" priority />
          <span className="leading-tight">
            <span className="block text-lg font-bold tracking-tight">{site.name}</span>
            <span className="block text-[11px] text-muted">{site.tagline}</span>
          </span>
        </Link>
        <nav className="hidden items-center gap-1 text-[15px] lg:flex">
          {links.map((link) => (
            <Link key={link.to} href={href(lang, link.to)} className="rounded-lg px-3 py-2 text-text/75 transition-colors hover:text-text">{link.label}</Link>
          ))}
        </nav>
        <div className="flex flex-none items-center gap-2">
          <Link href={href(lang, "/app")} className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 text-[15px] font-semibold hover:bg-white/[0.08]">
            <LayoutDashboard size={16} className="text-gold" /> <span className="hidden sm:inline">{d.nav.dashboard}</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
