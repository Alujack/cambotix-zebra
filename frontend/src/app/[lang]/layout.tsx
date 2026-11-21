import { notFound } from "next/navigation";
import { isLang, languages } from "@/lib/i18n";

// Only the language check lives here. The marketing site ((site) group) and the dashboard (app/) have their own shells.
export function generateStaticParams() {
  return languages.map((lang) => ({ lang }));
}

export default async function LangLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return <div lang={lang} className={`flex min-h-full flex-1 flex-col ${lang === "km" ? "font-khmer" : ""}`}>{children}</div>;
}
