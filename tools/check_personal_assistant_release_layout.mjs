// Read-only layout verification of persisted synthetic QA reviews; no model calls.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  output: { type: "string" },
  "playwright-module": { type: "string", default: "playwright" },
} });
assert(values.output);
const { chromium } = createRequire(import.meta.url)(values["playwright-module"]);
await mkdir(values.output);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const errors = [], observations = [];
page.on("pageerror", error => errors.push(error.message));
try {
  const response = await page.request.get("http://localhost:18001/api/v1/personal-assistant/reviews");
  assert.equal(response.status(), 200);
  const reviews = await response.json();
  const target = reviews.find(r => r.metadata.release_explanation?.policy === "neutral_decision_only");
  assert(target);
  for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844], ["narrow", 320, 740]]) {
    await page.setViewportSize({ width, height });
    await page.goto("http://localhost:3001/personal-assistant");
    await page.waitForFunction(() => !document.querySelector('button[title="새로고침"]')?.disabled);
    await page.locator('section[aria-label="검토 기록"]').getByRole("button").filter({ hasText: target.request }).click();
    await page.getByTestId("assistant-evidence").getByText("판정만 요약 · 의미 미검증", { exact: true }).waitFor();
    await page.evaluate(() => scrollTo(0, 0));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const layout = await page.evaluate(() => {
      const heading = document.querySelector("h1").getBoundingClientRect();
      const header = document.querySelector("header");
      const headerRect = header.getBoundingClientRect();
      return {
        document_width: document.documentElement.scrollWidth,
        viewport_width: innerWidth,
        heading_top: heading.top,
        header_bottom: getComputedStyle(header).display === "none" ? 0 : headerRect.bottom,
        evidence_width: document.querySelector('[data-testid="assistant-evidence"]').getBoundingClientRect().width,
        active_navigation_color: getComputedStyle(document.querySelector('a[aria-current="page"]')).color,
        primary_button_size: getComputedStyle([...document.querySelectorAll("button")].find(el => el.textContent.includes("초안 생성"))).fontSize,
        overflowing_buttons: [...document.querySelectorAll("button")].filter(el => el.offsetParent && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent),
      };
    });
    assert(layout.document_width <= layout.viewport_width);
    assert(layout.heading_top >= layout.header_bottom);
    assert.deepEqual(layout.overflowing_buttons, []);
    assert.equal(layout.active_navigation_color, "rgb(255, 255, 255)");
    assert.equal(layout.primary_button_size, "14px");
    const screenshot = path.join(values.output, `${name}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    observations.push({ name, width, height, layout, screenshot });
  }
  assert.deepEqual(errors, []);
  await writeFile(path.join(values.output, "layout.json"), JSON.stringify({ status: "passed", model_calls: 0, observations, page_errors: errors }, null, 2));
  console.log(JSON.stringify({ status: "passed", model_calls: 0, viewports: observations.length }));
} finally {
  await browser.close();
}
