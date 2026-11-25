import { ArrowRight, BarChart3, ChevronDown, Fingerprint, Link2, ShieldCheck, Trophy, Zap } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import HeroBackdrop from "@/components/home/HeroBackdrop";
import MarketIcon from "@/components/MarketIcon";
import { StatCard } from "@/components/ui";
import { getRecord, getSignals } from "@/lib/api";
import { modelName, percent, r, utc } from "@/lib/format";
import { href, isLang, t, type Lang } from "@/lib/i18n";
import { site, team } from "@/lib/site";

// Section heading: gold kicker, title, optional line of text.
function Head({ kicker, title, text }: { kicker: string; title: string; text?: string }) {
  return (
    <div className="max-w-2xl">
      <div className="text-xs font-semibold tracking-[0.18em] text-gold uppercase">{kicker}</div>
      <h2 className="mt-2 text-3xl font-bold tracking-tight md:text-4xl">{title}</h2>
      {text && <p className="mt-3 text-muted">{text}</p>}
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
      <p className="text-[15px] text-muted">
        <b className="num text-text">{record.published}</b> {d.home.published} · <b className="num text-text">{record.journal.evaluated}</b> {d.home.checked} · <b className="text-text">0</b> {d.home.deleted}
      </p>
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
        {plans.length === 0 && <p className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5 text-sm text-muted">{d.home.noPlans}</p>}
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
        <span>{d.home.verdict}: <b className={h.verdict === "GO" ? "text-green" : h.verdict === "NO-GO" ? "text-red" : "text-text"}>{d.verdict[h.verdict] ?? h.verdict}</b></span>
        <span>{h.closed}/{h.min_trades} · {percent(h.win_rate)}</span>
      </div>
    </div>
  );
}

async function Tiles({ lang }: { lang: Lang }) {
  const d = t(lang);
  const record = await getRecord();
  const h = record.headline;
  const verdictTone = h.verdict === "GO" ? "green" : h.verdict === "NO-GO" ? "red" : "neutral";
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

const skeleton = (className: string) => <div className={`skeleton ${className}`} />;

export default async function Home({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
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
            <h1 className={`mt-7 font-extrabold tracking-[-0.035em] ${lang === "km" ? "text-4xl leading-[1.35] md:text-6xl" : "text-5xl leading-[1.02] md:text-7xl"}`}>
              {d.home.titleA} <span className="text-fade-gold">{d.home.titleB}</span>
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-relaxed text-text/75 md:text-xl">{d.hero.text}</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link href={href(lang, "/app")} className="inline-flex h-14 items-center gap-2.5 rounded-2xl bg-white px-7 text-[17px] font-semibold text-black transition-colors hover:bg-white/90">{d.home.dashboard} <Zap size={18} /></Link>
              <Link href={href(lang, "/app/signals")} className="inline-flex h-14 items-center gap-2.5 rounded-2xl border border-white/12 bg-black/40 px-7 text-[17px] font-semibold backdrop-blur hover:bg-white/[0.06]"><BarChart3 size={18} className="text-muted" /> {d.home.signals}</Link>
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

      <section className="mt-20">
        <Head kicker={d.home.recordKicker} title={d.home.recordTitle} text={d.hero.kicker} />
        <div className="mt-8">
          <Suspense fallback={<div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="skeleton h-24" />)}</div>}>
            <Tiles lang={lang} />
          </Suspense>
        </div>
        <Link href={href(lang, "/track-record")} className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">{d.hero.cta1} <ArrowRight size={15} /></Link>
      </section>

      <section className="mt-24">
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

      <section className="mt-24">
        <Head kicker={d.home.modelsKicker} title={d.models.title} text={d.models.note} />
        <div className="mt-8 grid gap-3 md:grid-cols-3">
          {d.models.items.map(([title, text]) => (
            <div key={title} className="rounded-2xl border border-border bg-gradient-to-b from-surface to-bg p-5 transition-colors hover:border-white/20">
              <div className="flex items-center gap-2 font-semibold"><span className="dot bg-gold" /> {title}</div>
              <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="relative mt-24 overflow-hidden rounded-3xl border border-gold/20 bg-[radial-gradient(ellipse_at_top_right,rgba(232,201,100,0.12),transparent_60%)] p-6 md:p-10">
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

      <section className="mt-24">
        <Head kicker={d.home.peopleKicker} title={d.team.title} text={d.team.text} />
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {team.map((member) => (
            <div key={member.name} className="flex gap-4 rounded-2xl border border-border bg-surface p-5">
              <div className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-gradient-to-b from-gold/30 to-gold/5 text-xl font-bold text-gold ring-1 ring-gold/30">{member.name.slice(0, 1)}</div>
              <div>
                <div className="text-lg font-semibold">{member.name}</div>
                <div className="text-sm text-muted">{member.role}</div>
                {member.blurb && <p className="mt-2 text-sm leading-relaxed text-muted">{member.blurb}</p>}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="relative mt-24 overflow-hidden rounded-3xl border border-white/10 p-8 md:p-12">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_left,rgba(232,201,100,0.16),transparent_55%),radial-gradient(ellipse_at_right,rgba(42,171,238,0.12),transparent_55%)]" aria-hidden />
        <div className="relative flex flex-wrap items-center justify-between gap-6">
          <div>
            <div className="text-xs font-semibold tracking-[0.18em] text-gold uppercase">{d.home.ctaKicker}</div>
            <div className="mt-2 text-3xl font-bold tracking-tight">{d.cta.title}</div>
            <div className="mt-2 max-w-xl text-muted">{d.cta.text}</div>
          </div>
          <a href={site.telegram} className="inline-flex h-14 items-center gap-2.5 rounded-2xl bg-white px-7 text-[17px] font-semibold text-black hover:bg-white/90">{d.cta.button} <ArrowRight size={18} /></a>
        </div>
      </section>
    </>
  );
}
