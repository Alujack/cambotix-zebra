import { Send } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { href, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

// Site footer: brand, link columns, the Telegram call to action, then the ledger chain head and the risk notice.
export default function Footer({ lang, headHash, headSeq }: { lang: Lang; headHash?: string; headSeq?: number }) {
  const d = t(lang);
  const product = [
    { to: "/signals", label: d.nav.signals },
    { to: "/markets", label: "Market analysis" },
    { to: "/app/terminal", label: "Live chart" },
    { to: "/track-record", label: d.nav.record },
    { to: "/calendar", label: "Economic calendar" },
    { to: "/pricing", label: d.nav.pricing },
  ];
  const company = [
    { to: "/method", label: d.nav.method },
    { to: "/verify", label: "Verify the record" },
    { to: "/ledger.json", label: d.footer.ledger },
    { to: "/risk", label: d.footer.risk },
  ];
  const column = (title: string, items: { to: string; label: string }[]) => (
    <div>
      <div className="font-semibold">{title}</div>
      <ul className="mt-4 space-y-3 text-[15px] text-muted">
        {items.map((item) => <li key={item.to}><Link href={href(lang, item.to)} className="hover:text-text">{item.label}</Link></li>)}
        {title === d.footer.company && <li><a href={site.telegram} className="hover:text-text">Telegram</a></li>}
      </ul>
    </div>
  );
  return (
    <footer className="mt-24 border-t border-white/[0.06] bg-black/40">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:grid-cols-2 lg:grid-cols-4 lg:px-6">
        <div>
          <Link href={href(lang, "/")} className="flex items-center gap-3">
            <Image src="/logo.jpg" alt="" width={36} height={36} className="rounded-xl" />
            <span className="font-display text-lg font-bold">{site.name}</span>
          </Link>
          <p className="mt-4 max-w-xs text-[15px] leading-relaxed text-muted">{d.footer.blurb}</p>
        </div>
        {column(d.footer.product, product)}
        {column(d.footer.company, company)}
        <div>
          <div className="font-semibold">{d.footer.start}</div>
          <p className="mt-4 text-[15px] text-muted">{d.footer.startText}</p>
          <a href={site.telegram} className="mt-5 inline-flex h-11 items-center gap-2 rounded-xl bg-white px-5 text-[15px] font-semibold text-black hover:bg-white/90"><Send size={15} /> {d.home.join2}</a>
        </div>
      </div>
      <div className="mx-auto max-w-7xl space-y-2.5 border-t border-white/[0.06] px-4 py-7 text-xs text-muted lg:px-6">
        {headHash !== undefined && (
          <p>
            {d.footer.head} #{headSeq}:{" "}
            {headSeq ? <code className="text-text/80" title={headHash}>{headHash.slice(0, 16)}…{headHash.slice(-8)}</code> : <span>{d.footer.genesis}</span>}
          </p>
        )}
        <p>{d.footer.disclaimer}</p>
        <p>{d.footer.copyright}</p>
      </div>
    </footer>
  );
}
