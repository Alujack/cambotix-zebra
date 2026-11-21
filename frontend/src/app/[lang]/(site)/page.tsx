import { LayoutDashboard } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import { StatCard } from "@/components/ui";
import { getRecord } from "@/lib/api";
import { percent, r } from "@/lib/format";
import { href, isLang, t, type Lang } from "@/lib/i18n";
import { site, team } from "@/lib/site";

async function Tiles({ lang }: { lang: Lang }) {
  const d = t(lang);
  const record = await getRecord();
  const h = record.headline;
  const verdictTone = h.verdict === "GO" ? "green" : h.verdict === "NO-GO" ? "red" : "neutral";
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label={d.tiles.closed} value={String(h.closed)} caption={`${record.open} ${d.tiles.open} · ${record.not_filled} ${d.tiles.neverFilled}`} />
        <StatCard label={d.tiles.winRate} value={percent(h.win_rate)} caption={d.tiles.winHint} />
        <StatCard label={d.tiles.total} value={r(h.total_r_tp1)} caption={`${d.tiles.expectancy} ${r(h.expectancy_r, 3)} ${d.tiles.perTrade}`} tone={h.total_r_tp1 > 0 ? "green" : h.total_r_tp1 < 0 ? "red" : undefined} />
        <StatCard label={d.tiles.drawdown} value={`${h.max_drawdown_r.toFixed(2)}R`} caption={`${d.tiles.limit} ${h.max_drawdown_limit_r}R`} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label={d.tiles.verdict} value={d.verdict[h.verdict] ?? h.verdict} caption={`${d.tiles.needs} ${h.min_trades} ${d.tiles.closedTrades}`} tone={verdictTone} />
        <StatCard label={d.tiles.evaluated} value={String(record.journal.evaluated)} caption={`${record.journal.rejected} ${d.tiles.rejected}`} />
        <StatCard label={d.tiles.published} value={String(record.published)} caption={d.tiles.publishedHint} />
        <StatCard label={d.tiles.chain} value={record.chain.valid ? `#${record.chain.head_seq}` : d.tiles.broken} caption={record.chain.valid ? d.tiles.chainOk : `${d.tiles.chainBroken} ${record.chain.broken_at}`} tone={record.chain.valid ? undefined : "red"} />
      </div>
    </>
  );
}

function TilesFallback() {
  return <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="skeleton h-24" />)}</div>;
}

export default async function Home({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  const d = t(lang);
  return (
    <>
      <section className="py-14 md:py-20">
        <div className="label !text-gold">{d.hero.kicker}</div>
        <h1 className="mt-3 max-w-3xl text-4xl font-bold tracking-tight md:text-5xl">{d.hero.title}</h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">{d.hero.text}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href={href(lang, "/app")} className="btn-primary"><LayoutDashboard size={16} /> {d.nav.dashboard}</Link>
          <Link href={href(lang, "/track-record")} className="btn-secondary">{d.hero.cta1}</Link>
        </div>
      </section>

      <section>
        <Suspense fallback={<TilesFallback />}>
          <Tiles lang={lang} />
        </Suspense>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl font-semibold">{d.how.title}</h2>
        <ol className="mt-6 grid gap-4 md:grid-cols-5">
          {d.how.steps.map(([title, text], index) => (
            <li key={title} className="card p-4">
              <div className="text-xs text-gold">{index + 1}</div>
              <div className="mt-1 font-semibold">{title}</div>
              <p className="mt-1 text-sm text-muted">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl font-semibold">{d.models.title}</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {d.models.items.map(([title, text]) => (
            <div key={title} className="card p-4">
              <div className="font-semibold">{title}</div>
              <p className="mt-1 text-sm text-muted">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-sm text-muted">{d.models.note}</p>
      </section>

      <section className="card-lg mt-16 p-6 md:p-8">
        <h2 className="text-2xl font-semibold">{d.why.title}</h2>
        <ul className="mt-4 grid gap-3 text-sm text-muted md:grid-cols-3">
          {d.why.items.map(([lead, text]) => <li key={lead}><b className="text-text">{lead}</b> {text}</li>)}
        </ul>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl font-semibold">{d.team.title}</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted">{d.team.text}</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {team.map((member) => (
            <div key={member.name} className="card flex gap-4 p-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-gold/15 text-lg font-semibold text-gold">{member.name.slice(0, 1)}</div>
              <div>
                <div className="font-semibold">{member.name}</div>
                <div className="text-xs text-muted">{member.role}</div>
                {member.blurb && <p className="mt-1 text-sm text-muted">{member.blurb}</p>}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="tint tone-gold mt-16 flex flex-wrap items-center justify-between gap-4 !p-6">
        <div>
          <div className="text-xl font-semibold">{d.cta.title}</div>
          <div className="text-sm text-muted">{d.cta.text}</div>
        </div>
        <a href={site.telegram} className="btn-primary">{d.cta.button}</a>
      </section>
    </>
  );
}
