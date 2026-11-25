import AppShell from "@/components/shell/AppShell";
import type { Lang } from "@/lib/i18n";

// The dashboard: sidebar rail, content column, disclaimer on every page.
export default async function DashboardLayout({ children }: LayoutProps<"/app">) {
  const lang: Lang = "en";
  return <AppShell lang={lang}>{children}</AppShell>;
}
