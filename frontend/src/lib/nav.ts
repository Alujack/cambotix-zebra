import type { LucideIcon } from "lucide-react";
import { Activity, Bell, BookOpen, CandlestickChart, Gauge, Globe, LayoutDashboard, ListChecks, ScrollText, TerminalSquare } from "lucide-react";

export type NavKey = "overview" | "terminal" | "signals" | "chart" | "indicators" | "trades" | "alerts" | "record" | "method" | "site";
export type NavItem = { to: string; key: NavKey; icon: LucideIcon };

// Dashboard rail. Everything lives under /app; the marketing site is reachable from the "More" menu.
export const primaryNav: NavItem[] = [
  { to: "/app", key: "overview", icon: LayoutDashboard },
  { to: "/app/terminal", key: "terminal", icon: TerminalSquare },
  { to: "/app/signals", key: "signals", icon: Activity },
  { to: "/app/terminal?view=chart", key: "chart", icon: CandlestickChart },
  { to: "/app/indicators", key: "indicators", icon: Gauge },
  { to: "/app/trades", key: "trades", icon: ListChecks },
  { to: "/app/alerts", key: "alerts", icon: Bell },
];

export const moreNav: NavItem[] = [
  { to: "/track-record", key: "record", icon: ScrollText },
  { to: "/method", key: "method", icon: BookOpen },
  { to: "/", key: "site", icon: Globe },
];
