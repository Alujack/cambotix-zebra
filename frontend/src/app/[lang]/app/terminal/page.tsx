import { Bell, Settings2, Zap } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import AutoRefresh from "@/components/AutoRefresh";
import SignalChart from "@/components/SignalChart";
import TopBar from "@/components/shell/TopBar";
import TerminalPanel from "@/components/TerminalPanel";
import { Badge, Skeleton } from "@/components/ui";
import { getCandles, getNews, getRecord, getSignals, getTickers } from "@/lib/api";
import { decimals, price, utc } from "@/lib/format";
import { href, isLang, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

const TFS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

async function Workspace({ lang, searchParams }: { lang: Lang; searchParams: Promise<{ symbol?: string; tf?: string }> }) {
  const d = t(lang);
  const query = await searchParams;
  const symbol = (query.symbol ?? site.markets[0]).toUpperCase();
  const tf = TFS.includes(query.tf ?? "") ? (query.tf as string) : "15m";
  const [chart, tickers, plans, record, news] = await Promise.all([getCandles(symbol, tf, undefined, 300), getTickers(), getSignals(200), getRecord(), getNews()]);
  const quote = tickers.find((item) => item.symbol === symbol);
  const stamp = record.generated_at ? Date.parse(record.generated_at) / 1000 : 0;
  const marketOpen = quote ? stamp - quote.time < 180 : false;
  const dec = decimals(quote?.price ?? chart.candles.at(-1)?.c ?? 100);
  const mine = plans.filter((plan) => plan.symbol === symbol);
  const markers = mine.map((plan) => ({ time: plan.published_at, direction: plan.direction }));
  const h = record.headline;
  const strip: [string, string, "green" | "red" | "gold" | "neutral"][] = [
    [d.terminal.fear, "—", "neutral"],                                                               // TODO(data): no fear & greed source yet
    [d.terminal.volatility, quote && chart.candles.length ? `${(((chart.candles.at(-1)!.h - chart.candles.at(-1)!.l) / quote.price) * 100).toFixed(2)}%` : "—", "neutral"],
    [d.terminal.regime, h.closed ? d.verdict[h.verdict] ?? h.verdict : d.overview.noHistory, h.verdict === "GO" ? "green" : "neutral"],
    ...tickers.slice(0, 3).map((item) => [`${item.symbol} 24h`, item.change_24h_pct === null ? "—" : `${item.change_24h_pct >= 0 ? "+" : ""}${item.change_24h_pct.toFixed(2)}%`, item.change_24h_pct === null ? "neutral" : item.change_24h_pct >= 0 ? "green" : "red"] as [string, string, "green" | "red" | "neutral"]),
    [d.terminal.desk, `${record.open} open · ${record.journal.evaluated} ${d.overview.evaluatedTotal}`, "gold"],
  ];
  return (
    <>
      <div className="card -mx-6 flex items-stretch overflow-x-auto rounded-none border-x-0 md:mx-0 md:rounded-xl md:border-x">
        {strip.map(([label, value, tone]) => (
          <div key={label} className="flex min-w-[150px] flex-col gap-0.5 border-r border-border px-4 py-2.5 last:border-r-0">
            <span className="label flex items-center gap-1.5"><span className={`dot ${tone === "green" ? "bg-green" : tone === "red" ? "bg-red" : tone === "gold" ? "bg-gold" : "bg-muted"}`} />{label}</span>
            <span className="num text-sm font-semibold">{value}</span>
          </div>
        ))}
        <div className="ml-auto flex items-center gap-2 px-3">
          <a href={site.telegram} className="btn-secondary !min-h-8 !py-1 text-xs">AI</a>
          <span className="btn-icon !h-8 !w-8"><Bell size={14} /></span>
          <span className="btn-icon !h-8 !w-8"><Settings2 size={14} /></span>
        </div>
      </div>

      <div className="tint tone-gold mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span>{d.terminal.banner}</span>
        <a href={site.telegram} className="btn-gold !min-h-8 !py-1 text-xs">{d.terminal.link}</a>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          {site.markets.map((item) => (
            <Link key={item} href={href(lang, `/app/terminal?symbol=${item}&tf=${tf}`)} className={`pill ${item === symbol ? "pill-active" : ""}`}>{item}</Link>
          ))}
        </div>
        <Badge tone={marketOpen ? "green" : "red"} dot>{marketOpen ? d.terminal.open : d.terminal.closed}</Badge>
        {quote && (
          <>
            <span className="price">{price(quote.price)}</span>
            <Badge tone={quote.change_24h_pct !== null && quote.change_24h_pct >= 0 ? "green" : "red"}>{quote.change_24h_pct === null ? "—" : `${quote.change_24h_pct >= 0 ? "+" : ""}${quote.change_24h_pct.toFixed(2)}%`}</Badge>
            <span className="text-xs text-muted">{d.terminal.lastCandle} {utc(quote.time)}</span>
          </>
        )}
        <div className="ml-auto flex gap-2">
          <a href={site.telegram} className="btn-secondary !min-h-8 !py-1 text-xs">{d.nav.aiChat}</a>
          <button type="button" className="btn-secondary !min-h-8 !py-1 text-xs" disabled title={d.terminal.todo}>Trade</button>
          <Link href={href(lang, "/app/alerts")} className="btn-secondary !min-h-8 !py-1 text-xs">{d.nav.alerts}</Link>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {TFS.map((item) => (
          <Link key={item} href={href(lang, `/app/terminal?symbol=${symbol}&tf=${item}`)} className={`pill ${item === tf ? "pill-active" : ""}`}>{item}</Link>
        ))}
        <button type="button" className="btn-primary ml-auto !min-h-8 !py-1 text-xs" disabled title={d.shell.scanTodo}><Zap size={14} /> {d.terminal.scan}</button>
      </div>

      <div className="mt-3 gap-3 lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
      <div className="card relative p-3">
        {!marketOpen && quote && <span className="pill absolute top-12 left-1/2 z-[1] -translate-x-1/2">{d.terminal.opensIn} · {d.terminal.lastCandle} {utc(quote.time)}</span>}
        {chart.candles.length > 0 ? (
          <SignalChart key={`${symbol}-${tf}`} candles={chart.candles} levels={[]} markers={markers} direction="BUY" decimals={dec} watermark={d.terminal.watermark} height={520} labels={{ ema20: "EMA20", ema50: "EMA50", ema200: "EMA200", rsi: "RSI" }} />
        ) : (
          <p className="p-8 text-center text-sm text-muted">{d.terminal.noCandles}</p>
        )}
        <span className="pill absolute right-3 bottom-3">✏️ {d.terminal.drawings}</span>
      </div>

      <TerminalPanel
        symbol={symbol} tf={tf} lang={lang}
        labels={{ analysis: d.terminal.analysis, bot: d.terminal.bot, history: d.terminal.history, news: d.terminal.news, ready: d.terminal.ready, analyze: d.terminal.analyze, best: d.terminal.best, advanced: d.terminal.advanced, hint: d.terminal.hint, todo: d.shell.scanTodo, noHistory: d.terminal.noHistory, newsEmpty: d.overview.newsEmpty }}
        history={mine.slice(0, 8).map((plan) => ({ seq: plan.seq, direction: plan.direction, status: plan.status, published_at: plan.published_at, r: plan.result?.r_tp1 ?? null, href: href(lang, `/app/signals/${plan.seq}`) }))}
        news={news.slice(0, 6)}
      />
      </div>
    </>
  );
}

// URL data (params, searchParams) is read only inside the Suspense boundary, so the route keeps an instant static shell.
async function Terminal({ params, searchParams }: PageProps<"/[lang]/app/terminal">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.terminal} help={d.terminal.help} />
      <Workspace lang={lang} searchParams={searchParams as Promise<{ symbol?: string; tf?: string }>} />
    </>
  );
}

export default function TerminalPage(props: PageProps<"/[lang]/app/terminal">) {
  return (
    <>
      <AutoRefresh seconds={60} />
      <Suspense fallback={<div className="space-y-3"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-12" /><Skeleton className="h-[520px]" /></div>}>
        <Terminal {...props} />
      </Suspense>
    </>
  );
}
