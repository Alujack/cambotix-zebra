import Link from "next/link";
import { Suspense } from "react";
import TopBar from "@/components/shell/TopBar";
import { SectionCard, Skeleton } from "@/components/ui";
import { getTickers } from "@/lib/api";
import { price } from "@/lib/format";
import { href, isLang, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

async function Watchlist({ lang }: { lang: Lang }) {
  const d = t(lang);
  const tickers = await getTickers();
  return (
    <SectionCard label={d.alerts.watchlist}>
      <ul className="divide-y divide-border">
        {site.markets.map((symbol) => {
          const quote = tickers.find((item) => item.symbol === symbol);
          return (
            <li key={symbol} className="flex items-center justify-between gap-3 py-2.5">
              <div>
                <div className="font-semibold">{symbol}</div>
                <div className="text-xs text-muted">{quote ? `${price(quote.price)} · ${quote.change_24h_pct === null ? "—" : `${quote.change_24h_pct >= 0 ? "+" : ""}${quote.change_24h_pct.toFixed(2)}%`}` : d.ticker.empty}</div>
              </div>
              <Link href={href(lang, `/app/terminal?symbol=${symbol}`)} className="btn-secondary !min-h-8 !py-1 text-xs">{d.alerts.analyze}</Link>
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}

export default async function AlertsPage({ params }: PageProps<"/[lang]/app/alerts">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.alerts} help={d.alerts.help} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Suspense fallback={<Skeleton className="h-48" />}><Watchlist lang={lang} /></Suspense>
        <SectionCard label={d.alerts.form}>
          {/* TODO(accounts): wire to a real alert store once accounts exist. */}
          <form className="grid gap-3">
            <label className="text-sm"><span className="label">{d.alerts.symbol}</span>
              <select className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2" disabled>{site.markets.map((symbol) => <option key={symbol}>{symbol}</option>)}</select></label>
            <label className="text-sm"><span className="label">{d.alerts.condition}</span>
              <select className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2" disabled><option>{d.alerts.above}</option><option>{d.alerts.below}</option></select></label>
            <label className="text-sm"><span className="label">{d.alerts.price}</span>
              <input type="number" className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 num" placeholder="0.00" disabled /></label>
            <button type="button" className="btn-primary" disabled title={d.alerts.todo}>{d.alerts.set}</button>
            <p className="text-xs text-muted">{d.alerts.todo}</p>
          </form>
        </SectionCard>
      </div>
    </>
  );
}
