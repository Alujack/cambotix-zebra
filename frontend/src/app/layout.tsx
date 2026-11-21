import type { Metadata } from "next";
import { Geist_Mono, Inter, Noto_Sans_Khmer } from "next/font/google";
import { site } from "@/lib/site";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const khmer = Noto_Sans_Khmer({ variable: "--font-khmer", subsets: ["khmer"], weight: ["400", "600"] });

export const metadata: Metadata = {
  title: { default: `${site.name} — verified gold signals`, template: `%s · ${site.name}` },
  description:
    "Gold, forex and crypto setups published with entry, stop and targets, then graded on broker candles. A record nothing is ever removed from.",
  openGraph: { title: site.name, images: ["/logo.jpg"] },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${geistMono.variable} ${khmer.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
