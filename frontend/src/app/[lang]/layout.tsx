import { notFound } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import { isLang, languages } from "@/lib/i18n";

export function generateStaticParams() {
  return languages.map((lang) => ({ lang }));
}

export default async function LangLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return <AppShell lang={lang}>{children}</AppShell>;
}
