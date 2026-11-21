import { notFound } from "next/navigation";
import { Suspense } from "react";
import Footer from "@/components/Footer";
import Nav from "@/components/Nav";
import TickerStrip from "@/components/TickerStrip";
import { getRecord, getTickers } from "@/lib/api";
import { isLang, languages, type Lang } from "@/lib/i18n";

export function generateStaticParams() {
  return languages.map((lang) => ({ lang }));
}

async function Tickers({ lang }: { lang: Lang }) {
  return <TickerStrip tickers={await getTickers()} lang={lang} />;
}

async function ChainFooter({ lang }: { lang: Lang }) {
  const record = await getRecord();
  return <Footer lang={lang} headHash={record.chain.head_hash} headSeq={record.chain.head_seq} />;
}

export default async function LangLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return (
    <div lang={lang} className={`flex min-h-full flex-1 flex-col ${lang === "km" ? "font-khmer" : ""}`}>
      <Nav lang={lang} />
      <Suspense fallback={<div className="h-9 border-b border-line bg-card/60" />}>
        <Tickers lang={lang} />
      </Suspense>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4">{children}</main>
      <Suspense fallback={<Footer lang={lang} />}>
        <ChainFooter lang={lang} />
      </Suspense>
    </div>
  );
}
