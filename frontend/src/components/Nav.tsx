import { LayoutDashboard, Menu, Send, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { href, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

// Marketing-site header: logo, section links, the way into the dashboard and the Telegram join button.
// Under xl (1280px) the 8 links fold into a <details> menu, so it works without client JavaScript.
export default function Nav({ lang }: { lang: Lang }) {
  const d = t(lang);
  const links = [
    { to: "/", label: d.nav.home },
    { to: "/signals", label: d.nav.signals },
    { to: "/track-record", label: d.nav.record },
    { to: "/markets", label: "Markets" },
    { to: "/calendar", label: "Calendar" },
    { to: "/verify", label: "Verify" },
    { to: "/method", label: d.nav.method },
    { to: "/pricing", label: d.nav.pricing },
  ];
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[rgba(6,7,7,0.82)] backdrop-blur-xl">
      {/* Reading-progress bar; driven by scroll position in CSS (see .scroll-progress). */}
      <div className="scroll-progress absolute inset-x-0 top-0 h-[2px] origin-left bg-gradient-to-r from-gold via-gold to-green" aria-hidden />
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 lg:px-6">
        <Link href={href(lang, "/")} className="flex flex-none items-center gap-3">
          <Image src="/logo.jpg" alt="" width={38} height={38} className="rounded-xl" priority />
          <span className="font-display text-lg font-bold tracking-tight">{site.name}</span>
        </Link>
        <nav className="hidden items-center gap-0.5 text-[15px] xl:flex">
          {links.map((link) => (
            <Link key={link.to} href={href(lang, link.to)} className="rounded-lg px-3 py-2 text-text/70 transition-colors hover:text-text">{link.label}</Link>
          ))}
        </nav>
        <div className="flex flex-none items-center gap-2">
          <Link href={href(lang, "/app")} className="hidden h-10 items-center gap-2 rounded-xl px-3 text-[15px] font-medium text-text/80 hover:text-text sm:inline-flex">
            <LayoutDashboard size={16} className="text-gold" /> {d.nav.dashboard}
          </Link>
          <a href={site.telegram} className="inline-flex h-10 items-center gap-2 rounded-xl bg-white px-4 text-[15px] font-semibold text-black transition-colors hover:bg-white/90">
            <Send size={15} /> {d.home.join2}
          </a>
          <details className="nav-menu relative xl:hidden">
            <summary className="grid h-10 w-10 cursor-pointer list-none place-items-center rounded-xl border border-white/10 bg-white/[0.04]" aria-label="Menu">
              <Menu size={18} className="nav-open" />
              <X size={18} className="nav-close" />
            </summary>
            <div className="absolute right-0 mt-2 w-60 rounded-2xl border border-white/10 bg-[#0c0d10]/95 p-2 shadow-2xl backdrop-blur-xl">
              {links.map((link) => (
                <Link key={link.to} href={href(lang, link.to)} className="block rounded-xl px-3.5 py-2.5 text-[15px] text-text/85 hover:bg-white/[0.06]">{link.label}</Link>
              ))}
              <Link href={href(lang, "/app")} className="mt-1 flex items-center gap-2 rounded-xl border-t border-white/[0.06] px-3.5 py-2.5 text-[15px] font-semibold hover:bg-white/[0.06]">
                <LayoutDashboard size={16} className="text-gold" /> {d.nav.dashboard}
              </Link>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
