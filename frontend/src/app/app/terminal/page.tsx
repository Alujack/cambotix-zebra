import { BarChart3, Bell, CalendarClock, Check, Eye, History, Settings2, Zap } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import AutoRefresh from "@/components/AutoRefresh";
import HelpModal from "@/components/shell/HelpModal";
import TopBar from "@/components/shell/TopBar";
import SignalChart from "@/components/SignalChart";
import { MarketClock, Until } from "@/components/terminal/Clocks";
import LivePrice from "@/components/terminal/LivePrice";
import SetupTable from "@/components/terminal/SetupTable";
import TrendTable from "@/components/terminal/TrendTable";
import TerminalFrame from "@/components/terminal/TerminalFrame";
import MarketIcon from "@/components/MarketIcon";
import Watchlist from "@/components/terminal/Watchlist";
import TerminalPanel from "@/components/TerminalPanel";
import TradingViewWidget from "@/components/TradingViewWidget";
import { Skeleton } from "@/components/ui";
import { getCandles, getIndicators, getNews, getRecord, getSentiment, getSetups, getSignals, getTickers, getTrend } from "@/lib/api";
import { decimals, price } from "@/lib/format";
import { href, t, type Lang } from "@/lib/i18n";
import { market, site, tvSource } from "@/lib/site";

const TFS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];
const TF_SECONDS: { [tf: string]: number } = { "1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400 };
// Candles loaded per timeframe (the API caps at 1500): about a day of 1m, ten days of 15m, half a year of 4h. The chart opens
// on the newest bars and the rest is there to scroll back through.
const TF_BARS: { [tf: string]: number } = { "1m": 1440, "5m": 1000, "15m": 1000, "30m": 1000, "1h": 1000, "4h": 1000, "1d": 365 };
type Tone = "green" | "red" | "gold" | "neutral";
const dotTone = (tone: Tone) => (tone === "green" ? "bg-green" : tone === "red" ? "bg-red" : tone === "gold" ? "bg-gold" : "bg-muted");
const textTone = (tone: Tone) => (tone === "green" ? "text-green" : tone === "red" ? "text-red" : tone === "gold" ? "text-gold" : "text-text");
const pct = (value: number | null) => (value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`);

async function Workspace({ lang, searchParams }: { lang: Lang; searchParams: Promise<{ symbol?: string; tf?: string; view?: string }> }) {
  const d = t(lang);
  const k = d.terminal;
  const query = await searchParams;
  const symbol = (query.symbol ?? site.watchlist[0]).toUpperCase();
  const tf = TFS.includes(query.tf ?? "") ? (query.tf as string) : "15m";
  // Broker (default) = our Exness candles, live price, every plan flagged and our indicator; live = TradingView's embed on their feed.
  const view = query.view === "live" ? "live" : "broker";
  const link = (s: string, f: string, v: string) => href(lang, `/app/terminal?symbol=${s}&tf=${f}&view=${v}`);

  const [chart, tickers, plans, record, news, sentiment, reading, setups, trend] = await Promise.all([
    view === "broker" ? getCandles(symbol, tf, undefined, TF_BARS[tf]) : Promise.resolve({ symbol, tf, candles: [] }),
    getTickers(), getSignals(200), getRecord(), getNews(), getSentiment(), getIndicators(symbol, tf),
    view === "broker" ? getSetups(symbol, 1000) : Promise.resolve(null),
    view === "broker" ? getTrend(symbol, tf, Math.min(TF_BARS[tf], 1000)) : Promise.resolve(null),
  ]);
  // Our indicator: a dot per 15m setup; the newest one's entry/SL/TP lines while it is recent (the Pine script draws them 48 bars long).
  const setupMarks = (setups?.candidates ?? []).map((item) => ({ time: item.t, direction: item.direction }));
  const recent = setups?.candidates.at(-1);
  const setupLevels = recent && setups?.at && setups.at - recent.t <= 48 * 900 ? [
    { label: `Z ${recent.direction} ${price(recent.entry)}`, price: recent.entry, tone: "white" as const },
    { label: `Z SL ${price(recent.stop, recent.entry)}`, price: recent.stop, tone: "red" as const, dashed: true },
    ...recent.targets.map((target, i) => ({ label: `Z TP${i + 1} +${target.r}R`, price: target.price, tone: "green" as const, dotted: true })),
  ] : [];
  const info = market(symbol);
  const quote = tickers.find((item) => item.symbol === symbol);
  const stamp = record.generated_at ? Date.parse(record.generated_at) / 1000 : 0;
  const feedFresh = quote ? stamp - quote.time < 180 : false;
  const dec = decimals(quote?.price ?? chart.candles.at(-1)?.c ?? 100);
  const mine = plans.filter((plan) => plan.symbol === symbol);
  const openHere = mine.filter((plan) => plan.status === "open").length;
  const nextEvent = news.find((item) => item.severity === "HIGH" && item.time > stamp);

  // Status strip: only numbers we can stand behind. A missing source shows "—", never a placeholder value.
  const fg = sentiment.crypto_fear_greed;
  const fgTone: Tone = !fg ? "neutral" : fg.value < 25 ? "red" : fg.value < 45 ? "gold" : fg.value > 55 ? "green" : "neutral";
  const strip: [string, string, Tone][] = [
    [k.fearGreed, fg ? `${fg.value} · ${fg.label}` : "—", fgTone],
    [k.volatility, reading ? reading.atr.verdict : "—", reading?.atr.verdict === "volatile" ? "red" : reading?.atr.verdict === "quiet" ? "neutral" : reading ? "green" : "neutral"],
    [k.trend, reading ? reading.ema.verdict.toLowerCase() : "—", reading ? reading.ema.tone : "neutral"],
    // The desk's other markets (in watchlist order), not whichever tickers sort first.
    ...site.markets.filter((item) => item !== symbol).map((item) => tickers.find((row) => row.symbol === item)).filter((item) => item !== undefined).slice(0, 2).map((item): [string, string, Tone] => [`${item.symbol} 24h`, pct(item.change_24h_pct), item.change_24h_pct === null ? "neutral" : item.change_24h_pct >= 0 ? "green" : "red"]),
    [k.desk, record.open > 0 ? `${record.open} ${k.openPlans}` : feedFresh ? k.scanning : k.paused, record.open > 0 ? "gold" : feedFresh ? "green" : "neutral"],
  ];

  const watchRows = site.watchlist.map((item) => {
    const tick = tickers.find((row) => row.symbol === item);
    return { symbol: item, name: market(item).name, category: market(item).category, price: tick ? price(tick.price) : null, change: tick?.change_24h_pct ?? null, price24h: tick?.price_24h ?? null, href: link(item, tf, view), active: item === symbol };
  });

  const panelProps = {
    symbol, tf, lang,
    labels: { analysis: k.analysis, bot: k.bot, history: k.history, news: k.news, ready: k.ready, analyze: k.analyze, best: k.best, advanced: k.advanced, hint: k.hint, todo: d.shell.scanTodo, noHistory: k.noHistory, newsEmpty: d.overview.newsEmpty },
    history: mine.slice(0, 8).map((plan) => ({ seq: plan.seq, direction: plan.direction, status: plan.status, published_at: plan.published_at, r: plan.result?.r_tp1 ?? null, href: href(lang, `/app/signals/${plan.seq}`) })),
    news: news.slice(0, 6),
  };

  const stripNode = (
    <div className="flex items-stretch border-b border-border">
      <div className="flex min-w-0 flex-1 overflow-x-auto">
        {strip.map(([label, value, tone]) => (
          <div key={label} className="flex min-w-[130px] flex-[1_0_auto] flex-col justify-center gap-1 border-r border-border px-4 py-3 whitespace-nowrap xl:px-5">
            <span className="label flex items-center gap-1.5"><span className={`dot ${dotTone(tone)}`} />{label}</span>
            <span className={`num text-[17px] leading-tight font-semibold capitalize ${textTone(tone)}`}>{value}</span>
          </div>
        ))}
      </div>
      <div className="hidden flex-none items-center gap-2 px-3 lg:flex">
        <a href={site.telegram} className="btn-secondary !min-h-10 !rounded-xl !py-1 text-[15px]"><Zap size={16} /> AI</a>
        <Link href={href(lang, "/app/alerts")} className="grid h-10 w-10 place-items-center text-muted hover:text-text" aria-label={d.nav.alerts}><Bell size={18} /></Link>
        <Link href={href(lang, "/app/settings")} className="grid h-10 w-10 place-items-center text-muted hover:text-text" aria-label={d.nav.settings}><Settings2 size={18} /></Link>
      </div>
    </div>
  );

  const headerNode = (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-4 py-3">
        <Link href={href(lang, "/app")} className="hidden items-center gap-1.5 text-[15px] text-muted hover:text-text min-[1400px]:flex"><History size={16} /> {k.back}</Link>
        <span className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2" title={info.name}>
          <MarketIcon symbol={symbol} size={24} />
          <span className="text-[15px] font-semibold">{symbol}</span>
          <Check size={15} className="text-green" />
        </span>
        <span className="text-sm tracking-wide text-muted">{view === "live" ? tvSource(symbol) : symbol.endsWith("USDT") ? "BINANCE" : "EXNESS"}</span>
        <MarketClock hours={info.hours} labels={{ open: k.marketOpen, closed: k.marketClosed, closesIn: k.closesIn, opensIn: k.opensAt, always: k.always }} />
        <LivePrice symbol={symbol} hours={info.hours} showEmpty={view === "broker"} labels={{ paused: k.paused, closed: k.marketClosedBadge, noQuote: k.noQuote }}
          initial={quote ? { price: quote.price, time: quote.time, change: quote.change_24h_pct, price24h: quote.price_24h ?? null } : null} />
        <div className="ml-auto flex gap-2">
          <a href={site.telegram} aria-label={k.askAi} className="btn-secondary !min-h-10 !rounded-xl !py-1 text-[15px]"><Zap size={16} /> <span className="sm:hidden min-[1400px]:inline">{k.askAi}</span></a>
          <button type="button" className="btn-secondary !min-h-10 !rounded-xl !py-1 text-[15px] disabled:opacity-60" disabled title={k.todo} aria-label={k.trade}><BarChart3 size={16} /> <span className="sm:hidden min-[1400px]:inline">{k.trade}</span></button>
          <Link href={href(lang, "/app/alerts")} aria-label={k.alert} className="btn-secondary !min-h-10 !rounded-xl !py-1 text-[15px]"><Eye size={16} className="text-blue" /> <span className="sm:hidden min-[1400px]:inline">{k.alert}</span></Link>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-2 lg:border-b-0">
        <div className="flex items-center gap-1">
          {TFS.map((item) => (
            <Link key={item} href={link(symbol, item, view)} className={`rounded-lg border px-3 py-1.5 text-[15px] ${item === tf ? "border-border bg-surface font-semibold text-text" : "border-transparent text-muted hover:text-text"}`}>{item}</Link>
          ))}
        </div>
        <span className="hidden items-center gap-2 rounded-full border border-gold/50 px-4 py-1.5 text-sm whitespace-nowrap text-text md:flex" title={d.shell.scanTodo}><Zap size={15} className="text-gold" /> {k.scanSoon}</span>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <Link href={link(symbol, tf, "live")} className={`flex items-center gap-1.5 ${view === "live" ? "text-text" : "text-muted hover:text-text"}`}><span className={`dot ${view === "live" ? "bg-green" : "bg-muted"}`} /> {k.liveChart}</Link>
          <Link href={link(symbol, tf, "broker")} className={`flex items-center gap-1.5 ${view === "broker" ? "text-text" : "text-muted hover:text-text"}`}><span className={`dot ${view === "broker" ? "bg-gold" : "bg-muted"}`} /> {k.brokerChart}</Link>
          <HelpModal title={d.nav.terminal} text={`${k.help} ${k.liveNote}`} label={d.shell.help} close={d.shell.close} compact buttonClass="grid h-8 w-8 place-items-center rounded-lg border border-gold/40 bg-gold/10 text-gold hover:bg-gold/20" />
        </div>
      </div>
    </>
  );

  // Next high-impact release, pinned inside the chart. On the Live view it sits below TradingView's toolbar and legend.
  const eventPill = nextEvent && (
    <span className="absolute z-[2] flex max-w-[calc(100%-5rem)] items-center gap-2 rounded-full border border-blue/40 bg-[#0b1a2b]/90 px-3.5 py-1.5 text-sm whitespace-nowrap backdrop-blur" style={view === "live" ? { top: 124, left: 64 } : { top: 44, left: 12 }}>
      <CalendarClock size={15} className="flex-none text-blue" />
      <span className="truncate font-semibold">{nextEvent.title}</span>
      <span className="flex-none font-semibold">{k.eventIn} <Until at={nextEvent.time} /></span>
      <span className="hidden flex-none text-muted sm:inline">· {k.highImpact}</span>
    </span>
  );

  const chartBody = view === "live" ? (
    <TradingViewWidget symbol={symbol} tf={tf} locale="en" height="100%" />
  ) : chart.candles.length > 0 ? (
    <SignalChart key={`${symbol}-${tf}`} fill live={{ symbol, period: TF_SECONDS[tf] }} candles={chart.candles} levels={[]} markers={mine.map((plan) => ({ time: plan.published_at, direction: plan.direction }))} direction="BUY" decimals={dec} watermark={k.watermark} setups={setups ? setupMarks : undefined} setupLevels={setupLevels} trend={trend ?? undefined} labels={{ ema20: "EMA20", ema50: "EMA50", ema200: "EMA200", rsi: "RSI", setups: k.setups.pill, trend: k.atrTrend.pill }} />
  ) : (
    <p className="grid h-full place-items-center p-8 text-center text-sm text-muted">{k.noCandles}</p>
  );
  // Indicator tables, folded, stacked at the chart's top right.
  const tables = view === "broker" && (trend?.table || setups?.table) && (
    <div className="absolute top-11 right-20 z-[2] hidden flex-col items-end gap-1.5 lg:flex">
      {trend?.table && <TrendTable data={trend} labels={k.atrTrend} />}
      {setups?.table && <SetupTable data={setups} labels={k.setups} />}
    </div>
  );
  const chartNode = <>{chartBody}{eventPill}{tables}</>;

  const mobileMarkets = (
    <div className="flex gap-1.5 overflow-x-auto px-4 pb-2.5">
      {site.watchlist.map((item) => <Link key={item} href={link(item, tf, view)} className={`pill ${item === symbol ? "pill-active" : ""}`}>{item}</Link>)}
    </div>
  );

  return (
    <TerminalFrame
      watchlist={<Watchlist rows={watchRows} openHere={openHere} upgradeHref={href(lang, "/pricing")} signalsHref={href(lang, "/app/signals")} labels={{ mainList: k.mainList, mySignals: k.mySignals, mySignalsNone: k.mySignalsNone, search: k.search, all: k.all, crypto: k.crypto, forex: k.forex, metals: k.metals, watchlist: k.watchlist, freePlan: k.freePlan, upgrade: k.upgrade, deskTitle: k.deskTitle, deskEvery: k.deskEvery, deskNone: k.deskNone, deskOpen: k.deskOpen, deskLink: k.deskLink, noQuote: k.noQuote }} />}
      strip={stripNode}
      header={headerNode}
      chart={chartNode}
      panel={<TerminalPanel {...panelProps} className="w-full rounded-xl border border-border bg-surface/95 backdrop-blur" />}
      mobileMarkets={mobileMarkets}
      labels={{ keys: k.keys, terminalName: k.terminalName, shortDisclaimer: k.shortDisclaimer, banner: k.banner, link: k.link, dismiss: k.dismiss }}
      telegram={site.telegram}
      otherViewHref={link(symbol, tf, view === "live" ? "broker" : "live")}
      live={view === "live" || feedFresh}
      panelLeft={view === "live" ? 56 : 12}
    />
  );
}

// URL data (params, searchParams) is read only inside the Suspense boundary, so the route keeps an instant static shell.
async function Terminal({ searchParams }: PageProps<"/app/terminal">) {
  const lang: Lang = "en";
  const d = t(lang);
  return (
    <>
      <div className="lg:hidden"><TopBar lang={lang} title={d.nav.terminal} help={d.terminal.help} /></div>
      <Workspace lang={lang} searchParams={searchParams as Promise<{ symbol?: string; tf?: string; view?: string }>} />
    </>
  );
}

export default function TerminalPage(props: PageProps<"/app/terminal">) {
  return (
    <>
      {/* Prices and the last candle stream live (LivePrice, Watchlist, SignalChart); this refresh brings each newly closed bar's
          indicator lines and labels (they act on closed bars, down to 1m), plus new plans and news. */}
      <AutoRefresh seconds={60} />
      <Suspense fallback={<div className="space-y-3"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-12" /><Skeleton className="h-[520px]" /></div>}>
        <Terminal {...props} />
      </Suspense>
    </>
  );
}
