import Link from "next/link";
import { Suspense } from "react";
import TopBar from "@/components/shell/TopBar";
import { EmptyState, IndicatorTile, Skeleton } from "@/components/ui";
import { getIndicators, type Indicators } from "@/lib/api";
import { decimals, utc } from "@/lib/format";
import { href, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

const TFS = ["5m", "15m", "1h", "4h"];

function tiles(x: Indicators, d: ReturnType<typeof t>, dec: number) {
  const f = (v: number | undefined, n = dec) => (v === undefined ? "—" : v.toFixed(n));
  return [
    { label: d.detail.rsi, value: f(x.rsi.value, 1), reading: x.rsi },
    { label: d.detail.stoch, value: `${f(x.stoch.k, 0)} / ${f(x.stoch.d, 0)}`, reading: x.stoch },
    { label: d.detail.macd, value: f(x.macd_hist.value), reading: x.macd_hist },
    { label: d.detail.adx, value: `${f(x.adx.value, 1)} · +${f(x.adx.plus_di, 0)} / −${f(x.adx.minus_di, 0)}`, reading: x.adx },
    { label: d.detail.bb, value: f(x.bollinger_b.value, 2), reading: x.bollinger_b },
    { label: d.detail.atr, value: `${f(x.atr.value)} (${f(x.atr.percent_of_price, 2)}%)`, reading: x.atr },
    { label: d.detail.ema, value: x.ema.verdict.split("").join(" "), reading: { ...x.ema, verdict: `${f(x.ema.ema20)} · ${f(x.ema.ema50)} · ${f(x.ema.ema200)}` } },
  ];
}

async function Readings({ lang, searchParams }: { lang: Lang; searchParams: Promise<{ symbol?: string; tf?: string }> }) {
  const d = t(lang);
  const query = await searchParams;
  const symbol = (query.symbol ?? site.markets[0]).toUpperCase();
  const tf = TFS.includes(query.tf ?? "") ? (query.tf as string) : "15m";
  const reading = await getIndicators(symbol, tf);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {site.markets.map((item) => <Link key={item} href={href(lang, `/app/indicators?symbol=${item}&tf=${tf}`)} className={`pill ${item === symbol ? "pill-active" : ""}`}>{item}</Link>)}
        <span className="mx-2 text-border">|</span>
        {TFS.map((item) => <Link key={item} href={href(lang, `/app/indicators?symbol=${symbol}&tf=${item}`)} className={`pill ${item === tf ? "pill-active" : ""}`}>{item}</Link>)}
      </div>
      {reading ? (
        <>
          <p className="mb-3 text-xs text-muted">{symbol} · {tf} · {utc(reading.at)} · {reading.bars} bars</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {tiles(reading, d, decimals(reading.close)).map((tile) => <IndicatorTile key={tile.label} label={tile.label} value={tile.value} verdict={tile.reading.verdict} tone={tile.reading.tone} percent={tile.reading.percent} />)}
          </div>
        </>
      ) : (
        <EmptyState title={d.detail.noIndicators} text={d.terminal.noCandles} />
      )}
    </>
  );
}

export default async function IndicatorsPage({ searchParams }: PageProps<"/app/indicators">) {
  const lang: Lang = "en";
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.indicators} help={d.indicators.help} />
      <p className="mb-4 text-sm text-muted">{d.indicators.intro}</p>
      <Suspense fallback={<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>}>
        <Readings lang={lang} searchParams={searchParams as Promise<{ symbol?: string; tf?: string }>} />
      </Suspense>
    </>
  );
}
