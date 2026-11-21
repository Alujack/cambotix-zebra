import { Activity, ArrowRight, Crown, Flame, Gauge, Layers, Newspaper, Target, Trophy, Zap } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import SignalCard from "@/components/SignalCard";
import TopBar from "@/components/shell/TopBar";
import { Badge, EmptyState, SectionCard, Skeleton, StatCard } from "@/components/ui";
import { getNews, getRecord, getSignals } from "@/lib/api";
import { percent, r, utc } from "@/lib/format";
import { greeting, guest } from "@/lib/guest";
import { href, isLang, t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

async function Hero({ lang }: { lang: Lang }) {
  const d = t(lang);
  const [record, plans] = await Promise.all([getRecord(), getSignals(20)]);
  const open = plans.filter((plan) => plan.status === "open").length;
  // "Now" is the API's stamp, so this component stays pure and agrees with the numbers it shows.
  const now = record.generated_at ? new Date(record.generated_at) : new Date(0);
  const phnomPenhHour = (now.getUTCHours() + 7) % 24;
  return (
    <section className="card-lg relative overflow-hidden p-5 md:p-6" style={{ backgroundImage: "linear-gradient(135deg, var(--surface) 55%, color-mix(in srgb, var(--gold) 9%, var(--surface)))" }}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            {record.generated_at && <span className="label">{utc(Math.floor(now.getTime() / 1000), false)}</span>}
            <Badge tone="green" dot>{d.overview.engineLive}</Badge>
          </div>
          <h2 className="hero-text mt-3">{greeting(phnomPenhHour)}, {guest.name}</h2>
          <p className="mt-2 text-sm text-muted">
            {open > 0 ? `${open} ${d.overview.activeNow}` : d.overview.noActive} · {record.journal.evaluated} {d.overview.evaluatedTotal}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link href={href(lang, "/app/signals")} className="btn-primary"><Zap size={16} /> {d.overview.ctaSignals}</Link>
            <Link href={href(lang, "/app/trades")} className="btn-secondary">{d.nav.trades}</Link>
          </div>
        </div>
        <div className="grid h-14 w-14 place-items-center rounded-xl border-2 border-gold/70 bg-surface-2 text-xl font-bold text-gold">{guest.initials}</div>
      </div>
    </section>
  );
}

async function Stats({ lang }: { lang: Lang }) {
  const d = t(lang);
  const [record, plans] = await Promise.all([getRecord(), getSignals(60)]);
  const h = record.headline;
  const open = plans.filter((plan) => plan.status === "open").length;
  const stamp = record.generated_at ? Date.parse(record.generated_at) / 1000 : 0;
  const dayStart = Math.floor(stamp / 86400) * 86400;
  const today = plans.filter((plan) => plan.published_at >= dayStart).length;
  const best = Object.entries(record.by_symbol).sort((a, b) => b[1].total_r_tp1 - a[1].total_r_tp1)[0];
  const none = d.overview.noHistory;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <StatCard label={d.overview.active} value={String(open)} caption={open ? d.overview.activeCaption : d.overview.activeNone} icon={Activity} tone={open ? "green" : undefined} />
      <StatCard label={d.tiles.winRate} value={h.closed ? percent(h.win_rate) : "—"} caption={h.closed ? `${h.wins} / ${h.closed} · ${d.tiles.winHint}` : none} icon={Trophy} />
      <StatCard label={d.overview.signalsLeft} value={String(guest.signalsLeftToday)} caption={`${d.overview.resets} ${guest.resetsAt} · ${d.shell.guestNote}`} icon={Gauge} />
      <StatCard label={d.overview.tradesToday} value={String(today)} caption={today ? d.overview.publishedToday : d.overview.nothingToday} icon={Target} />
      <StatCard label={d.overview.bestSymbol} value={best ? best[0] : "—"} caption={best ? `${r(best[1].total_r_tp1)} · ${best[1].closed} ${d.tiles.closedTrades}` : none} icon={Flame} tone={best && best[1].total_r_tp1 > 0 ? "green" : undefined} />
      <StatCard label={d.overview.plan} value={guest.plan} caption={d.shell.guestNote} icon={Layers} tone="gold" />
    </div>
  );
}

async function News({ lang }: { lang: Lang }) {
  const d = t(lang);
  const items = await getNews();
  return (
    <SectionCard>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="label">{d.overview.news}</span>
          <span className="pill pill-active">{d.overview.newsCalendar}</span>
        </div>
        <Badge tone="green" dot>LIVE</Badge>
      </div>
      {items.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{d.overview.newsEmpty}</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {items.slice(0, 8).map((item) => (
            <li key={item.time + item.title} className="py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={item.severity === "HIGH" ? "red" : item.severity === "MEDIUM" ? "gold" : "neutral"}>{item.severity}</Badge>
                <span className="font-semibold">{item.title}</span>
                <span className="pill">{item.country}</span>
                {item.affects.map((symbol) => <span key={symbol} className="text-xs text-muted">{symbol}</span>)}
              </div>
              <div className="mt-1 text-xs text-muted">
                {utc(item.time)} {item.blocks_setups && <span className="text-gold">· ⚡ {d.overview.newsBlocks}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

async function Recent({ lang }: { lang: Lang }) {
  const d = t(lang);
  const plans = (await getSignals(4)).slice(0, 4);
  if (plans.length === 0) {
    return <EmptyState title={d.signals.empty} action={<Link href={href(lang, "/method")} className="btn-secondary">{d.nav.method}</Link>} />;
  }
  return <div className="grid gap-4 md:grid-cols-2">{plans.map((plan) => <SignalCard key={plan.event_id} plan={plan} lang={lang} />)}</div>;
}

const grid = (n: number, h: string) => <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: n }).map((_, i) => <Skeleton key={i} className={h} />)}</div>;

export default async function Overview({ params }: PageProps<"/[lang]/app">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <TopBar lang={lang} title={d.nav.overview} help={d.overview.help} />
      <div className="space-y-6">
        <Suspense fallback={<Skeleton className="h-44" />}><Hero lang={lang} /></Suspense>
        <Suspense fallback={grid(6, "h-28")}><Stats lang={lang} /></Suspense>
        <Suspense fallback={<Skeleton className="h-56" />}><News lang={lang} /></Suspense>
        <section>
          <div className="mb-3 flex items-end justify-between">
            <div><div className="label">{d.overview.recentLabel}</div><h2 className="text-lg font-semibold">{d.overview.recent}</h2></div>
            <Link href={href(lang, "/app/signals")} className="flex items-center gap-1 text-sm text-gold">{d.overview.viewAll} <ArrowRight size={14} /></Link>
          </div>
          <Suspense fallback={<div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-72" /><Skeleton className="h-72" /></div>}><Recent lang={lang} /></Suspense>
        </section>
        <section className="tint tone-gold flex flex-wrap items-center justify-between gap-4 !p-5">
          <div>
            <div className="flex items-center gap-2 font-semibold"><Zap size={16} className="text-gold" /> {d.overview.ctaTitle}</div>
            <div className="mt-1 text-sm text-muted">{d.overview.ctaText}</div>
          </div>
          <a href={site.telegram} className="btn-primary"><Newspaper size={16} /> {d.nav.telegram}</a>
        </section>
        <SectionCard>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="label">{d.overview.usage}</div>
              <div className="mt-1 text-sm">{guest.signalsLeftToday} {d.overview.signalsLeftText} · {guest.plan}</div>
              <div className="mt-2 h-1.5 w-56 max-w-full overflow-hidden rounded-full bg-surface-2"><div className="h-full w-1/3 bg-gold" /></div>
            </div>
            <Link href={href(lang, "/pricing")} className="btn-gold"><Crown size={16} /> {d.nav.upgrade}</Link>
          </div>
        </SectionCard>
      </div>
    </>
  );
}
