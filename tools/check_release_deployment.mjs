// Read-only smoke test of the clean Docker EvalOps deployment.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  receipt: { type: "string" }, output: { type: "string" },
  "playwright-module": { type: "string", default: "playwright" },
} });
assert(values.receipt && values.output);
const api = JSON.parse(await readFile(values.receipt, "utf8"));
assert.equal(api.status, "passed");
const { chromium } = createRequire(import.meta.url)(values["playwright-module"]);
await mkdir(values.output);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [], observations = [];
page.on("pageerror", error => errors.push(error.message));
try {
  for (const route of ["/", `/deployment-gates/${api.gate_evaluation_id}`, `/release-decisions/${api.release_decision_id}`]) {
    const response = await page.goto("http://localhost:13000" + route);
    assert.equal(response.status(), 200);
    await page.locator("h1").waitFor();
    assert(!await page.getByText("Application error", { exact: true }).count());
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert(await page.evaluate(() => [...document.querySelectorAll('a[aria-current="page"]')].every(el => getComputedStyle(el).color === "rgb(255, 255, 255)")));
    observations.push({ route, status: response.status(), heading: await page.locator("h1").innerText() });
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: path.join(values.output, `desktop-${observations.length}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page.evaluate(() => scrollTo(0, 0));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: path.join(values.output, "mobile-release.png"), fullPage: true });
  assert.deepEqual(errors, []);
  await writeFile(path.join(values.output, "deployment-ui.json"), JSON.stringify({ status: "passed", model_calls: 0, read_only: true, observations, mobile_width: 390, page_errors: errors }, null, 2));
  console.log(JSON.stringify({ status: "passed", pages: observations.length, model_calls: 0 }));
} finally {
  await browser.close();
}
