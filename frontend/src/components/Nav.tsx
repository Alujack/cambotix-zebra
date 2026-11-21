import Image from "next/image";
import Link from "next/link";
import LangToggle from "@/components/LangToggle";
import { href, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

export default function Nav({ lang }: { lang: Lang }) {
  const d = t(lang);
  const links = [
    { to: "/", label: d.nav.home },
    { to: "/signals", label: d.nav.signals },
    { to: "/track-record", label: d.nav.record },
    { to: "/method", label: d.nav.method },
    { to: "/pricing", label: d.nav.pricing },
  ];
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5">
        <Link href={href(lang, "/")} className="flex items-center gap-2.5 font-semibold tracking-tight">
          <Image src="/logo.jpg" alt={site.name} width={36} height={36} className="rounded-lg" priority />
          <span className="leading-tight">
            <span className="block text-accent">{site.name}</span>
            <span className="block text-[11px] font-normal text-muted">{site.tagline}</span>
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {links.map((link) => (
            <Link key={link.to} href={href(lang, link.to)} className="rounded-md px-2.5 py-1.5 text-muted hover:bg-card hover:text-fg">
              {link.label}
            </Link>
          ))}
          <LangToggle lang={lang} label={d.nav.other} />
          <a href={site.telegram} className="ml-1 hidden rounded-md bg-accent px-3 py-1.5 font-medium text-bg hover:opacity-90 lg:inline">
            {d.nav.telegram}
          </a>
        </nav>
      </div>
    </header>
  );
}
