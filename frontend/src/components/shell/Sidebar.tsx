"use client";

import { Crown, LifeBuoy, Menu, MoreHorizontal, Settings, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { guest } from "@/lib/guest";
import { href, type Dict, type Lang } from "@/lib/i18n";
import { moreNav, primaryNav } from "@/lib/nav";
import { site } from "@/lib/site";

// Fixed 64px rail on desktop; a slide-out drawer on mobile. Active item: surface-2, gold left bar, white text.
export default function Sidebar({ lang, labels }: { lang: Lang; labels: Dict["nav"] }) {
  const pathname = usePathname() ?? "/";
  const bare = pathname.replace(/^\/(en|km)(?=\/|$)/, "") || "/";
  const [open, setOpen] = useState(false);
  const [more, setMore] = useState(false);
  useEffect(() => setOpen(false), [pathname]);

  const active = (to: string) => {
    const path = to.split("?")[0];
    return path === "/" ? bare === "/" : bare.startsWith(path);
  };
  const item = (to: string, key: keyof Dict["nav"], Icon: React.ComponentType<{ size?: number; strokeWidth?: number }>, tone?: "gold") => (
    <Link
      key={to + key}
      href={href(lang, to)}
      aria-current={active(to) ? "page" : undefined}
      className={`relative flex min-h-[52px] w-full flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-[10px] leading-none transition-colors
        ${active(to) ? "bg-surface-2 text-text" : tone === "gold" ? "text-gold hover:bg-surface-2" : "text-muted hover:bg-surface-2 hover:text-text"}`}
    >
      {active(to) && <span className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-gold" aria-hidden />}
      <Icon size={18} strokeWidth={1.6} />
      <span className="max-w-full truncate">{labels[key]}</span>
    </Link>
  );

  const rail = (
    <div className="flex h-full w-16 flex-col items-center gap-1 border-r border-border bg-bg px-1.5 py-3">
      <Link href={href(lang, "/")} className="mb-2 block" aria-label={site.name}>
        <Image src="/logo.jpg" alt="" width={40} height={40} className="rounded-xl" priority />
      </Link>
      {primaryNav.map((entry) => item(entry.to, entry.key, entry.icon))}
      <div className="relative w-full">
        <button type="button" onClick={() => setMore((value) => !value)} className="flex min-h-[52px] w-full flex-col items-center justify-center gap-1 rounded-lg py-2 text-[10px] text-muted hover:bg-surface-2 hover:text-text" aria-expanded={more}>
          <MoreHorizontal size={18} strokeWidth={1.6} />
          <span>{labels.more}</span>
        </button>
        {more && (
          <div className="absolute top-0 left-full z-30 ml-2 w-44 rounded-xl border border-border bg-surface p-1.5 shadow-none">
            {moreNav.map((entry) => (
              <Link key={entry.key} href={href(lang, entry.to)} className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-surface-2" onClick={() => setMore(false)}>
                <entry.icon size={16} strokeWidth={1.6} /> {labels[entry.key]}
              </Link>
            ))}
            {(["aiChat", "backtest", "refer"] as const).map((key) => (
              <span key={key} className="flex items-center justify-between rounded-lg px-2.5 py-2 text-sm text-muted" title="TODO(accounts): not built yet">
                {labels[key]} <span className="pill">{labels.soon}</span>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="mt-auto flex w-full flex-col items-center gap-1">
        {item("/pricing", "upgrade", Crown, "gold")}
        {item("/settings", "settings", Settings)}
        <a href={site.telegram} className="flex min-h-[52px] w-full flex-col items-center justify-center gap-1 rounded-lg py-2 text-[10px] text-muted hover:bg-surface-2 hover:text-text">
          <LifeBuoy size={18} strokeWidth={1.6} />
          <span>{labels.support}</span>
        </a>
        <div className="mt-1 grid h-9 w-9 place-items-center rounded-lg border border-gold/60 bg-surface-2 text-sm font-semibold text-gold" title={`${guest.name} · ${guest.plan}`}>
          {guest.initials}
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-20 hidden md:block">{rail}</aside>
      <button type="button" onClick={() => setOpen(true)} className="btn-icon fixed top-2.5 left-3 z-30 md:hidden" aria-label="Open menu">
        <Menu size={18} />
      </button>
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute inset-y-0 left-0 flex">
            {rail}
            <button type="button" onClick={() => setOpen(false)} className="btn-icon m-3 self-start" aria-label="Close menu">
              <X size={18} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
