import { Suspense } from "react";
import Footer from "@/components/Footer";
import Nav from "@/components/Nav";
import TickerStrip from "@/components/TickerStrip";
import { getRecord, getTickers } from "@/lib/api";
import { isLang, type Lang } from "@/lib/i18n";

async function Tickers({ lang }: { lang: Lang }) {
  return <TickerStrip tickers={await getTickers()} lang={lang} />;
}

async function ChainFooter({ lang }: { lang: Lang }) {
  const record = await getRecord();
  return <Footer lang={lang} headHash={record.chain.head_hash} headSeq={record.chain.head_seq} />;
}

// Marketing pages: top navigation, broker ticker strip, footer with the chain head.
export default async function SiteLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  return (
    <>
      <Nav lang={lang} />
      <Suspense fallback={<div className="h-9 border-b border-border bg-surface/60" />}>
        <Tickers lang={lang} />
      </Suspense>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4">{children}</main>
      <Suspense fallback={<Footer lang={lang} />}>
        <ChainFooter lang={lang} />
      </Suspense>
    </>
  );
}
