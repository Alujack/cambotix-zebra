import { readFileSync } from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { t, type Lang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Method", description: "The ideas behind the rules: liquidity, sweeps, structure shifts, fair value gaps, sessions and risk." };

// A short English summary of the method (content/method.en.md), shipped with the image.
const content = (lang: string) => readFileSync(path.join(process.cwd(), "content", `method.${lang}.md`), "utf8");

export default async function MethodPage() {
  const lang: Lang = "en";
  const d = t(lang);
  const markdown = content(lang).replace(/^<!--[\s\S]*?-->\n/, "");
  return (
    <>
      <section className="py-10">
        <h1 className="text-3xl font-semibold">{d.method.title}</h1>
        <p className="mt-2 max-w-2xl text-muted">{d.method.intro}</p>
      </section>
      <article className="prose-zebra max-w-3xl">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </article>
    </>
  );
}
