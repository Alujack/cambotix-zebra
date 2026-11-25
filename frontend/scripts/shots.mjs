// Screenshots at desktop (1280) and mobile (390) widths for every page, so layout problems are visible.
//   node scripts/shots.mjs [baseUrl] [outDir]
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://127.0.0.1:3000";
const out = process.argv[3] ?? "shots";
const pages = ["/", "/track-record", "/pricing", "/method", "/app", "/app/signals", "/app/signals/1", "/app/terminal", "/app/trades"];
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const [name, width] of [["desktop", 1280], ["mobile", 390]]) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: "dark", deviceScaleFactor: 1 });
  const page = await context.newPage();
  for (const path of pages) {
    const file = `${out}/${name}${path.replaceAll("/", "_") || "_home"}.png`;
    try {
      await page.goto(base + path, { waitUntil: "networkidle", timeout: 30000 });
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`${name} ${path} -> ${file}${scrollWidth > width ? `  HORIZONTAL OVERFLOW ${scrollWidth}px` : ""}`);
    } catch (error) {
      console.log(`${name} ${path} FAILED: ${error.message.split("\n")[0]}`);
    }
  }
  await context.close();
}
await browser.close();
