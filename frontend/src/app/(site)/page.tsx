import { ArrowRight, BarChart3, Calculator, CandlestickChart, ChevronDown, Cpu, Fingerprint, Link2, Newspaper, Ruler, Send, ShieldCheck, Trophy, Waypoints, Zap } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import HeroBackdrop from "@/components/home/HeroBackdrop";
import NextClose from "@/components/home/NextClose";
import MarketIcon from "@/components/MarketIcon";
import { StatCard } from "@/components/ui";
import { getRecord, getSignals } from "@/lib/api";
import { modelName, percent, r, utc } from "@/lib/format";
import { href, t, type Lang } from "@/lib/i18n";
import { market, site } from "@/lib/site";

// Section heading: gold kicker, title, optional line of text.
function Head({ kicker, title, text, center }: { kicker: string; title: string; text?: string; center?: boolean }) {
  return (
    <div className={center ? "mx-auto max-w-2xl text-center" : "max-w-2xl"}>
      <span className="inline-block rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase">{kicker}</span>
      <h2 className="font-display mt-4 text-3xl font-bold tracking-tight md:text-[44px] md:leading-[1.1]">{title}</h2>
      {center && <div className="mx-auto mt-4 h-px w-40 bg-gradient-to-r from-transparent via-gold/60 to-transparent" />}
      {text && <p className="mt-4 text-[15px] text-muted md:text-base">{text}</p>}
    </div>
  );
}

// Hero proof line: real counts from the ledger, never a sign-up number we can't back.
async function Proof({ lang }: { lang: Lang }) {
  const d = t(lang);
  const record = await getRecord();
  return (
    <div className="mt-10 flex flex-wrap items-center gap-4">
      <div className="flex -space-x-3">
        {site.markets.map((symbol) => <span key={symbol} className="rounded-full ring-4 ring-bg"><MarketIcon symbol={symbol} size={40} /></span>)}
      </div>
      {record.published === 0 ? (
        <p className="text-[15px] text-muted"><b className="text-text">{d.home.markets}</b> — {d.home.scanned}</p>
      ) : (
        <p className="text-[15px] text-muted">
          <b className="num text-text">{record.published}</b> {d.home.published} · <b className="num text-text">{record.journal.evaluated}</b> {d.home.checked} · <b className="text-text">0</b> {d.home.deleted}
        </p>
      )}
    </div>
  );
}

// The glass card beside the headline: the latest plans exactly as the ledger has them, and the chain status.
async function RecordCard({ lang }: { lang: Lang }) {
  const d = t(lang);
  const [record, plans] = await Promise.all([getRecord(), getSignals(3)]);
  const h = record.headline;
  return (
    <div className="rounded-3xl border border-white/10 bg-black/55 p-4 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)] backdrop-blur-xl">
      <div className="flex items-center gap-3 px-1 pb-3">
        <span className="flex gap-1.5"><span className="h-3 w-3 rounded-full bg-[#ff5f57]" /><span className="h-3 w-3 rounded-full bg-[#febc2e]" /><span className="h-3 w-3 rounded-full bg-[#28c840]" /></span>
        <Trophy size={16} className="ml-2 text-gold" />
        <span className="text-xs font-semibold tracking-[0.16em] text-gold uppercase">{d.home.card}</span>
        <span className={`ml-auto flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${record.chain.valid ? "bg-green/10 text-green" : "bg-red/10 text-red"}`}>
          <span className={`dot ${record.chain.valid ? "bg-green" : "bg-red"}`} /> {record.chain.valid ? `${d.home.verified} #${record.chain.head_seq}` : d.home.broken}
        </span>
      </div>
      <div className="space-y-2.5">
        {plans.length === 0 && site.markets.map((symbol) => (
          <div key={symbol} className="flex items-center gap-3.5 rounded-2xl border border-white/[0.06] bg-white/[0.025] p-3.5">
            <MarketIcon symbol={symbol} size={44} />
            <span className="min-w-0 flex-1">
              <span className="block text-[17px] font-semibold">{symbol}</span>
              <span className="block truncate text-sm text-muted">{market(symbol).name} · 15m rules</span>
            </span>
            <span className="flex items-center gap-1.5 rounded-full bg-white/[0.05] px-3 py-1.5 text-xs font-semibold text-text/80"><span className="dot animate-pulse bg-gold" /> {d.home.watching}</span>
          </div>
        ))}
        {plans.map((plan) => {
          const result = plan.result?.r_tp1;
          return (
            <Link key={plan.seq} href={href(lang, `/app/signals/${plan.seq}`)} className="flex items-center gap-3.5 rounded-2xl border border-white/[0.06] bg-white/[0.025] p-3.5 transition-colors hover:border-white/15">
              <MarketIcon symbol={plan.symbol} size={44} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="text-[17px] font-semibold">{plan.symbol}</span>
                  <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${plan.direction === "BUY" ? "bg-green/15 text-green" : "bg-red/15 text-red"}`}>{plan.direction}</span>
                </span>
                <span className="block truncate text-sm text-muted">{modelName[plan.model] ?? plan.model} · {plan.timeframe} · #{plan.seq} · {utc(plan.published_at).slice(5, 16)}</span>
              </span>
              {plan.status === "open" ? (
                <span className="rounded-full bg-gold/10 px-3 py-1.5 text-xs font-semibold text-gold">{d.home.onTelegram}</span>
              ) : plan.status === "not_filled" ? (
                <span className="rounded-full bg-surface-2 px-3 py-1.5 text-xs font-semibold text-muted">{d.home.notFilled}</span>
              ) : (
                <span className={`num rounded-full px-3 py-1.5 text-sm font-bold ${result !== undefined && result > 0 ? "bg-green/10 text-green" : "bg-red/10 text-red"}`}>{r(result)}</span>
              )}
            </Link>
          );
        })}
      </div>
      <div className="mt-3 flex items-center justify-between px-1 text-xs text-muted">
        {h.closed === 0 ? (
          <span>{d.home.nextClose} <b className="text-text"><NextClose /></b></span>
        ) : (
          <span>{d.home.verdict}: <b className={h.verdict === "GO" ? "text-green" : h.verdict === "NO-GO" ? "text-red" : "text-text"}>{d.verdict[h.verdict] ?? h.verdict}</b></span>
        )}
        <span>{h.closed}/{h.min_trades} {d.tiles.closedTrades}{h.closed > 0 && ` · ${percent(h.win_rate)}`}</span>
      </div>
    </div>
  );
}

async function Tiles({ lang }: { lang: Lang }) {
  const d = t(lang);
  const record = await getRecord();
  const h = record.headline;
  const verdictTone = h.verdict === "GO" ? "green" : h.verdict === "NO-GO" ? "red" : "neutral";
  // Before the first closed trade a grid of zeros says nothing; show where the test stands and what it will measure.
  if (h.closed === 0) {
    const share = Math.min(100, (h.closed / Math.max(1, h.min_trades)) * 100);
    return (
      <div className="grid gap-4 rounded-3xl border border-border bg-gradient-to-br from-surface to-bg p-6 md:grid-cols-[1.3fr_1fr] md:p-8">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-green"><span className="dot animate-pulse bg-green" /> {d.home.startedTitle}</div>
          <p className="mt-3 max-w-xl leading-relaxed text-muted">{d.home.startedText}</p>
          <div className="mt-6">
            <div className="flex items-baseline justify-between text-sm">
              <span><b className="num text-2xl text-text">{h.closed}</b> <span className="text-muted">/ {h.min_trades} {d.home.progress}</span></span>
              <span className="text-xs text-muted">{d.tiles.chain}: <b className={record.chain.valid ? "text-green" : "text-red"}>{record.chain.valid ? d.tiles.chainValid : d.tiles.broken}</b></span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-2"><div className="h-full rounded-full bg-gradient-to-r from-gold/60 to-gold" style={{ width: `${Math.max(share, 1.5)}%` }} /></div>
            <div className="mt-2 text-xs text-muted">{record.open} {d.tiles.open} · {record.journal.evaluated} {d.tiles.evaluated.toLowerCase()} · {record.journal.rejected} {d.tiles.rejected}</div>
          </div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-black/30 p-5">
          <div className="label">{d.home.measured}</div>
          <ul className="mt-3 space-y-2.5 text-sm">
            {d.home.measures.map((item) => <li key={item} className="flex items-center gap-2.5"><ShieldCheck size={15} className="text-gold" /> {item}</li>)}
          </ul>
        </div>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard label={d.tiles.closed} value={String(h.closed)} caption={`${record.open} ${d.tiles.open} · ${record.not_filled} ${d.tiles.neverFilled}`} />
      <StatCard label={d.tiles.winRate} value={percent(h.win_rate)} caption={d.tiles.winHint} />
      <StatCard label={d.tiles.total} value={r(h.total_r_tp1)} caption={`${d.tiles.expectancy} ${r(h.expectancy_r, 3)} ${d.tiles.perTrade}`} tone={h.total_r_tp1 > 0 ? "green" : h.total_r_tp1 < 0 ? "red" : undefined} />
      <StatCard label={d.tiles.drawdown} value={`${h.max_drawdown_r.toFixed(2)}R`} caption={`${d.tiles.limit} ${h.max_drawdown_limit_r}R`} />
      <StatCard label={d.tiles.verdict} value={d.verdict[h.verdict] ?? h.verdict} caption={`${d.tiles.needs} ${h.min_trades} ${d.tiles.closedTrades}`} tone={verdictTone} />
      <StatCard label={d.tiles.evaluated} value={String(record.journal.evaluated)} caption={`${record.journal.rejected} ${d.tiles.rejected}`} />
      <StatCard label={d.tiles.published} value={String(record.published)} caption={d.tiles.publishedHint} />
      <StatCard label={d.tiles.chain} value={record.chain.valid ? `#${record.chain.head_seq}` : d.tiles.broken} caption={record.chain.valid ? d.tiles.chainOk : `${d.tiles.chainBroken} ${record.chain.broken_at}`} tone={record.chain.valid ? undefined : "red"} />
    </div>
  );
}

const featureIcons = [Cpu, Waypoints, Calculator, Newspaper, Ruler, BarChart3, Link2, Send];

const skeleton = (className: string) => <div className={`skeleton ${className}`} />;

export default async function Home() {
  const lang: Lang = "en";
  const d = t(lang);
  const whyIcons = [ShieldCheck, Link2, Fingerprint];
  return (
    <>
      {/* Full-bleed hero: breaks out of the page column (the layout clips horizontal overflow). */}
      <section className="relative ml-[calc(50%-50vw)] w-screen overflow-hidden">
        <HeroBackdrop />
        <div className="relative mx-auto grid min-h-[calc(100svh-7rem)] max-w-7xl grid-cols-[minmax(0,1fr)] items-center gap-12 px-4 py-16 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:px-6 lg:py-20">
          <div>
            <span className="inline-flex items-center gap-2.5 rounded-full border border-white/15 bg-black/40 px-4 py-2 text-xs font-semibold tracking-[0.2em] uppercase backdrop-blur">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-green" /></span>
              {d.home.live}
            </span>
            <h1 className="font-display mt-7 text-[44px] leading-[1.04] font-extrabold tracking-[-0.035em] sm:text-5xl xl:text-[64px]">
              {d.home.titleA} <span className="text-fade-gold">{d.home.titleB}</span>
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-relaxed text-text/75 md:text-xl">{d.hero.text}</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link href={href(lang, "/app")} className="inline-flex h-14 items-center gap-2.5 rounded-2xl bg-white px-7 text-[17px] font-semibold text-black transition-colors hover:bg-white/90">{d.home.dashboard} <Zap size={18} /></Link>
              <Link href={href(lang, "/signals")} className="inline-flex h-14 items-center gap-2.5 rounded-2xl border border-white/12 bg-black/40 px-7 text-[17px] font-semibold backdrop-blur hover:bg-white/[0.06]"><BarChart3 size={18} className="text-muted" /> {d.home.signals}</Link>
            </div>
            <Suspense fallback={<div className="mt-10 h-10" />}>
              <Proof lang={lang} />
            </Suspense>
          </div>
          <Suspense fallback={skeleton("h-[380px] !rounded-3xl")}>
            <RecordCard lang={lang} />
          </Suspense>
        </div>
        <ChevronDown className="scroll-cue absolute bottom-5 left-1/2 -translate-x-1/2 text-muted" size={22} aria-hidden />
      </section>

      {/* Facts band: what is true of every plan, not counters that start at zero. */}
      <section className="ml-[calc(50%-50vw)] w-screen border-y border-white/[0.06] bg-[linear-gradient(90deg,rgba(6,7,7,1),rgba(24,19,8,0.7),rgba(6,7,7,1))]">
        <dl className="mx-auto grid max-w-7xl grid-cols-2 gap-y-8 px-4 py-10 sm:grid-cols-3 lg:grid-cols-5 lg:px-6">
          {d.home.stats.map(([value, label]) => (
            <div key={label} className="text-center">
              <dt className="font-display text-3xl font-bold tracking-tight md:text-4xl">{value}</dt>
              <dd className="mt-1.5 text-sm text-muted">{label}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="reveal mt-24">
        <Head kicker={d.home.recordKicker} title={d.home.recordTitle} text={d.hero.kicker} />
        <div className="mt-8">
          <Suspense fallback={<div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="skeleton h-24" />)}</div>}>
            <Tiles lang={lang} />
          </Suspense>
        </div>
        <Link href={href(lang, "/track-record")} className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">{d.hero.cta1} <ArrowRight size={15} /></Link>
      </section>

      <section className="reveal mt-28">
        <Head kicker={d.home.processKicker} title={d.how.title} />
        <ol className="mt-8 grid gap-3 md:grid-cols-5">
          {d.how.steps.map(([title, text], index) => (
            <li key={title} className="group relative overflow-hidden rounded-2xl border border-border bg-surface p-5 transition-colors hover:border-gold/40">
              <span className="num absolute -top-3 -right-1 text-[72px] font-extrabold text-white/[0.04] transition-colors group-hover:text-gold/10">{index + 1}</span>
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-gold/10 text-sm font-bold text-gold">{index + 1}</span>
              <div className="mt-4 text-lg font-semibold">{title}</div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="reveal mt-28">
        <Head center kicker={d.home.featuresKicker} title={d.home.featuresTitle} text={d.home.featuresText} />
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {d.home.features.map(([title, text], index) => {
            const Icon = featureIcons[index % featureIcons.length];
            return (
              <div key={title} className="group rounded-2xl border border-white/[0.08] bg-gradient-to-b from-white/[0.035] to-transparent p-6 transition-colors hover:border-gold/30">
                <span className="grid h-11 w-11 place-items-center rounded-xl border border-white/10 bg-white/[0.04] text-text/85 transition-colors group-hover:border-gold/40 group-hover:text-gold"><Icon size={20} /></span>
                <div className="mt-5 font-semibold">{title}</div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="reveal relative mt-28 overflow-hidden rounded-3xl border border-gold/20 bg-[radial-gradient(ellipse_at_top_right,rgba(232,201,100,0.12),transparent_60%)] p-6 md:p-10">
        <Head kicker={d.home.proofKicker} title={d.why.title} />
        <ul className="mt-8 grid gap-6 md:grid-cols-3">
          {d.why.items.map(([lead, text], index) => {
            const Icon = whyIcons[index % whyIcons.length];
            return (
              <li key={lead}>
                <span className="grid h-11 w-11 place-items-center rounded-xl border border-gold/30 bg-gold/10 text-gold"><Icon size={20} /></span>
                <div className="mt-4 font-semibold">{lead}</div>
                <p className="mt-1 text-sm leading-relaxed text-muted">{text}</p>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="reveal mt-28">
        <Head center kicker={d.home.marketsKicker} title={d.home.marketsTitle} text={d.home.marketsText} />
        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {d.home.marketCards.map(([symbol, kind, text]) => (
            <div key={symbol} className="flex flex-col rounded-3xl border border-white/[0.08] bg-gradient-to-b from-surface to-bg p-6">
              <div className="flex items-center gap-3.5">
                <MarketIcon symbol={symbol} size={48} />
                <div>
                  <div className="text-xl font-bold">{symbol}</div>
                  <div className="text-sm text-muted">{market(symbol).name} · {kind}</div>
                </div>
              </div>
              <p className="mt-4 flex-1 text-sm leading-relaxed text-muted">{text}</p>
              <Link href={href(lang, `/app/terminal?symbol=${symbol}`)} className="mt-6 inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] text-sm font-semibold transition-colors hover:border-gold/40 hover:bg-white/[0.06]">
                {d.home.openChart} <CandlestickChart size={16} className="text-gold" />
              </Link>
            </div>
          ))}
        </div>
      </section>

      <section className="reveal relative mt-28 overflow-hidden rounded-[28px] border border-white/10 px-6 py-16 text-center md:py-20">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(232,201,100,0.16),transparent_60%),radial-gradient(ellipse_at_bottom_right,rgba(42,171,238,0.1),transparent_55%)]" aria-hidden />
        <div className="relative">
          <span className="inline-block rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[11px] font-semibold tracking-[0.2em] text-gold uppercase">{d.home.ctaKicker}</span>
          <h2 className="font-display mx-auto mt-5 max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">{d.home.finalTitleA} <span className="text-fade-gold">{d.home.finalTitleB}</span></h2>
          <p className="mx-auto mt-5 max-w-xl text-muted md:text-lg">{d.home.finalText}</p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <a href={site.telegram} className="inline-flex h-14 items-center gap-2.5 rounded-2xl bg-white px-7 text-[17px] font-semibold text-black hover:bg-white/90"><Send size={18} /> {d.home.join2}</a>
            <Link href={href(lang, "/track-record")} className="inline-flex h-14 items-center gap-2.5 rounded-2xl border border-white/12 bg-black/40 px-7 text-[17px] font-semibold hover:bg-white/[0.06]">{d.hero.cta1} <ArrowRight size={18} /></Link>
          </div>
          <p className="mt-4 text-xs text-muted">{d.home.finalNote}</p>
        </div>
      </section>
    </>
  );
}
