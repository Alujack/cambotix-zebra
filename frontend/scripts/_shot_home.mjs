// Screenshot the marketing homepage: hero viewport + full page, desktop and mobile, English and Khmer.
import { chromium } from "playwright";
const out = process.argv[2];
const browser = await chromium.launch();
for (const [name, width] of [["desktop", 1440], ["mobile", 390]]) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1, colorScheme: "dark" });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const [label, path] of [["home", "/"], ["km-home", "/km"]]) {
    await page.goto("http://127.0.0.1:3100" + path, { waitUntil: "networkidle", timeout: 45000 });
    await page.waitForTimeout(1500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth);
    await page.screenshot({ path: `${out}/${name}-${label}.png` });
    if (label === "home") await page.screenshot({ path: `${out}/${name}-${label}-full.png`, fullPage: true });
    console.log(name, label, overflow > width ? `OVERFLOW ${overflow}` : "ok");
  }
  console.log(name, "errors:", errors);
  await context.close();
}
await browser.close();
