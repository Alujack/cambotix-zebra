import { Suspense } from "react";
import Footer from "@/components/Footer";
import JoinTelegram from "@/components/home/JoinTelegram";
import Nav from "@/components/Nav";
import TickerStrip from "@/components/TickerStrip";
import { getRecord, getTickers } from "@/lib/api";
import { t, type Lang } from "@/lib/i18n";
import { site } from "@/lib/site";

async function Tickers({ lang }: { lang: Lang }) {
  return <TickerStrip tickers={await getTickers()} lang={lang} />;
}

async function ChainFooter({ lang }: { lang: Lang }) {
  const record = await getRecord();
  return <Footer lang={lang} headHash={record.chain.head_hash} headSeq={record.chain.head_seq} />;
}

// Marketing pages: top navigation, broker ticker strip, footer with the chain head.
export default async function SiteLayout({ children }: LayoutProps<"/">) {
  const lang: Lang = "en";
  const d = t(lang);
  // overflow-x-clip lets the home hero bleed edge to edge without a horizontal scrollbar.
  return (
    <div className="flex min-h-full flex-col overflow-x-clip">
      <Nav lang={lang} />
      <Suspense fallback={<div className="h-9 border-b border-border bg-surface/60" />}>
        <Tickers lang={lang} />
      </Suspense>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 lg:px-6">{children}</main>
      <Suspense fallback={<Footer lang={lang} />}>
        <ChainFooter lang={lang} />
      </Suspense>
      <JoinTelegram href={site.telegram} title={d.home.join} sub={d.home.joinSub} />
    </div>
  );
}
