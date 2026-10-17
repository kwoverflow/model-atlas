// No-correction UI checks: two refusals and a separately approved safe move/restore.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://localhost:3000/personal-assistant" },
  api: { type: "string", default: "http://localhost:18000/api/v1/personal-assistant" },
  protocol: { type: "string" }, output: { type: "string" },
  "playwright-module": { type: "string", default: "playwright" },
} });
assert(values.protocol && values.output);
assert.equal(new URL(values.url).hostname, "localhost");
assert.equal(new URL(values.api).hostname, "localhost");
const protocolBytes = await readFile(values.protocol);
const protocol = JSON.parse(protocolBytes);
assert.equal(protocol.draft_strategy, "compact-path-grounded-v3");
assert.equal(protocol.boundary_checks.length, 3);
await mkdir(values.output);
await writeFile(path.join(values.output, "protocol.json"), protocolBytes);
const source = await readFile(new URL(import.meta.url));
await writeFile(path.join(values.output, "browser-source.mjs"), source);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const { chromium } = createRequire(import.meta.url)(values["playwright-module"]);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(20000);
const rows = [], errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const binding = (r) => ({ revision: r.revision, content_hash: r.content_hash });
async function api(suffix, method = "GET", data) {
  const response = await context.request.fetch(values.api + suffix, {
    method, headers: { origin: new URL(values.url).origin, "x-model-atlas-lab-action": "1" },
    ...(data === undefined ? {} : { data }),
  });
  return { status: response.status(), data: await response.json() };
}
async function state() {
  const result = await api("/workspace");
  assert.equal(result.status, 200);
  assert.equal(result.data.draft_strategy, protocol.draft_strategy);
  return result.data.state;
}
async function ready() {
  await page.waitForFunction(() => !document.querySelector('button[title="새로고침"]')?.disabled);
}
async function click(name, suffix, expected = 200) {
  const waiting = page.waitForResponse((r) => r.url() === values.api + suffix && r.request().method() === "POST", { timeout: 65000 });
  await page.getByRole("button", { name, exact: true }).click();
  const response = await waiting;
  assert.equal(response.status(), expected, await response.text());
  const record = await response.json();
  await ready();
  return record;
}
async function screenshot(name) {
  await page.evaluate(() => window.scrollTo(0, 0));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: path.join(values.output, name), fullPage: true });
}
try {
  await page.goto(values.url);
  await page.getByRole("heading", { name: "개인 비서 검토", exact: true }).waitFor();
  await ready();
  for (const item of protocol.boundary_checks) {
    const before = await state();
    await page.getByLabel("요청", { exact: true }).fill(item.request);
    const record = await click("초안 생성", "/reviews", 201);
    assert.equal(record.metadata.strategy, protocol.draft_strategy);
    assert(record.metadata.schema_valid && !record.metadata.generation_error);
    assert.deepEqual(await state(), before);
    const raw = JSON.parse(record.raw_output);
    assert.equal(raw.decision, item.decision);
    const row = { case_id: item.id, request: item.request, initial_record: record, before, preapproval_unchanged: true };
    rows.push(row);
    if (item.decision === "refuse") {
      assert.equal(raw.intent, null);
      assert.deepEqual(record.fields, {});
      assert.equal(await page.getByRole("button", { name: "승인하고 실행", exact: true }).count(), 0);
      const rejected = await api(`/reviews/${record.id}/confirm`, "POST", { ...binding(record), acknowledged: true });
      assert.equal(rejected.status, 409);
      assert.equal(rejected.data.detail, "invalid_review_fields");
      const approval = await api(`/reviews/${record.id}/approve`, "POST", { ...binding(record), plan_hash: "0".repeat(64) });
      assert.equal(approval.status, 409);
      assert.equal(approval.data.detail, "confirmation_required");
      assert.deepEqual(await state(), before);
      Object.assign(row, { confirm_rejection: rejected, approval_rejection: approval, after: await state() });
      if (item.id === "B11") await screenshot("desktop-refusal.png");
      if (item.id === "B12") {
        await page.setViewportSize({ width: 390, height: 844 });
        await screenshot("mobile-refusal.png");
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
    } else {
      assert.deepEqual(raw.intent, item.fields);
      assert.deepEqual(record.initial_fields, item.fields);
      await page.getByRole("checkbox", { name: "수정한 내용과 실행 대상을 확인했습니다." }).check();
      const pending = await click("확정 및 미리보기", `/reviews/${record.id}/confirm`);
      assert.deepEqual(await state(), before);
      const executed = await click("승인하고 실행", `/reviews/${record.id}/approve`);
      const moved = await state();
      const expected = structuredClone(before);
      expected.files["files/Archive/review-demo.txt"] = expected.files["files/Inbox/review-demo.txt"];
      delete expected.files["files/Inbox/review-demo.txt"];
      assert.deepEqual(moved, expected);
      const restore = await click("복구 미리보기", `/reviews/${executed.id}/restore`);
      assert.equal(restore.parent_id, executed.id);
      assert.deepEqual(await state(), moved);
      await click("승인하고 실행", `/reviews/${restore.id}/approve`);
      assert.deepEqual(await state(), before);
      Object.assign(row, { pending, executed, restore, after: await state() });
    }
    console.log(JSON.stringify({ case: item.id, decision: raw.decision, status: "passed" }));
  }
  assert.deepEqual(errors, []);
  await writeFile(path.join(values.output, "browser-e2e.json"), JSON.stringify({
    status: "passed", draft_strategy: protocol.draft_strategy,
    protocol_sha256: hash(protocolBytes), browser_source_sha256: hash(source),
    model_corrections: 0, human_attestation: false, observations: rows, page_errors: errors,
  }, null, 2));
} catch (error) {
  await writeFile(path.join(values.output, "failure.json"), JSON.stringify({ error: String(error), observations: rows, page_errors: errors }, null, 2));
  await page.screenshot({ path: path.join(values.output, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
