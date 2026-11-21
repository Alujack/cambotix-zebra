import AppShell from "@/components/shell/AppShell";
import { isLang } from "@/lib/i18n";

// The dashboard: sidebar rail, content column, disclaimer on every page.
export default async function DashboardLayout({ children, params }: LayoutProps<"/[lang]/app">) {
  const { lang } = await params;
  if (!isLang(lang)) return null;
  return <AppShell lang={lang}>{children}</AppShell>;
}
