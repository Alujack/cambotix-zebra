import type { LucideIcon } from "lucide-react";
import { Activity, Bell, BookOpen, CandlestickChart, Gauge, LayoutDashboard, ListChecks, ScrollText, TerminalSquare } from "lucide-react";

export type NavItem = { to: string; key: "overview" | "terminal" | "signals" | "chart" | "indicators" | "trades" | "alerts" | "record" | "method"; icon: LucideIcon };

export const primaryNav: NavItem[] = [
  { to: "/", key: "overview", icon: LayoutDashboard },
  { to: "/terminal", key: "terminal", icon: TerminalSquare },
  { to: "/signals", key: "signals", icon: Activity },
  { to: "/terminal?view=chart", key: "chart", icon: CandlestickChart },
  { to: "/indicators", key: "indicators", icon: Gauge },
  { to: "/trades", key: "trades", icon: ListChecks },
  { to: "/alerts", key: "alerts", icon: Bell },
];

export const moreNav: NavItem[] = [
  { to: "/track-record", key: "record", icon: ScrollText },
  { to: "/method", key: "method", icon: BookOpen },
];
