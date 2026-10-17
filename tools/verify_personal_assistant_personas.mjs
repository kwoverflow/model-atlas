// Ten real-browser flows. Oracle-assisted corrections are explicitly NOT model accuracy.
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
assert(values.protocol && values.output, "Exclusive output and protocol paths required");
assert.equal(new URL(values.url).hostname, "localhost");
assert.equal(new URL(values.api).hostname, "localhost");
const protocolBytes = await readFile(values.protocol);
const protocol = JSON.parse(protocolBytes);
assert.equal(protocol.version, "personal-assistant-persona-v1");
assert.equal(protocol.cases.length, 10);
await mkdir(values.output); // Never overwrite/reuse earlier results.
await writeFile(path.join(values.output, "protocol.json"), protocolBytes);
const protocolHash = createHash("sha256").update(protocolBytes).digest("hex");
const scriptBytes = await readFile(new URL(import.meta.url));
await writeFile(path.join(values.output, "browser-source.mjs"), scriptBytes);
const scriptHash = createHash("sha256").update(scriptBytes).digest("hex");
const { chromium } = createRequire(import.meta.url)(values["playwright-module"]);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(20000);
const observations = [], pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));
const binding = (r) => ({ revision: r.revision, content_hash: r.content_hash });
async function api(suffix, method = "GET", body) {
  const response = await context.request.fetch(values.api + suffix, {
    method, headers: { "x-model-atlas-lab-action": "1", origin: new URL(values.url).origin },
    ...(body === undefined ? {} : { data: body }),
  });
  return { status: response.status(), data: await response.json() };
}
async function state() {
  const response = await api("/workspace");
  assert.equal(response.status, 200);
  return response.data.state;
}
async function ready() {
  await page.waitForFunction(() => !document.querySelector('button[title="새로고침"]')?.disabled);
}
async function clickRecord(name, method, suffix, expected = 200) {
  const promise = page.waitForResponse((r) => r.url() === values.api + suffix && r.request().method() === method, { timeout: 65000 });
  await page.getByRole("button", { name, exact: true }).click();
  const response = await promise;
  assert.equal(response.status(), expected, await response.text());
  const record = await response.json();
  await ready();
  return record;
}
async function create(request) {
  await page.getByLabel("요청", { exact: true }).fill(request);
  const record = await clickRecord("초안 생성", "POST", "/reviews", 201);
  assert.equal(record.metadata.model, "qwen3.5:9b");
  assert(record.metadata.schema_requested && record.raw_output);
  return record;
}
async function edit(record, fields) {
  const labels = { title: "제목", priority: "우선순위", local_due: "현지 마감 시각", local_start: "현지 시작 시각",
    source_timezone: "시간대", duration_minutes: "길이(분)", source: "원본 파일", destination: "대상 파일", path: "파일", task_id: "할 일 ID" };
  if (record.fields.operation !== fields.operation) await page.getByLabel("작업", { exact: true }).selectOption(fields.operation);
  const target = { ...fields };
  if (fields.operation === "todo.create") Object.assign(target, { local_due: fields.local_due ?? null, priority: fields.priority ?? null });
  if (fields.operation === "todo.complete") target.title = null;
  for (const [key, value] of Object.entries(target).filter(([k]) => k !== "operation")) {
    const label = key === "title" && fields.operation === "todo.complete" ? "할 일 제목" : labels[key];
    const control = page.getByLabel(label, { exact: true });
    if (["priority", "source_timezone"].includes(key)) await control.selectOption(value ?? "");
    else await control.fill(value === null ? "" : String(value));
  }
  if (!await page.getByRole("button", { name: "수정 저장", exact: true }).isEnabled()) return record;
  const saved = await clickRecord("수정 저장", "PUT", `/reviews/${record.id}`);
  assert.equal(saved.raw_output, record.raw_output);
  return saved;
}
async function confirm(record, expected = 200) {
  await page.getByRole("checkbox", { name: "수정한 내용과 실행 대상을 확인했습니다." }).check();
  return clickRecord("확정 및 미리보기", "POST", `/reviews/${record.id}/confirm`, expected);
}
async function approve(record) { return clickRecord("승인하고 실행", "POST", `/reviews/${record.id}/approve`); }
async function capture(name) {
  await page.evaluate(() => window.scrollTo(0, 0));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "Horizontal overflow");
  await page.screenshot({ path: path.join(values.output, name), fullPage: true });
}
async function saveProgress() {
  await writeFile(path.join(values.output, "progress.json"), JSON.stringify({ observations, page_errors: pageErrors }, null, 2));
}
function assertEffect(item, before, after, fields) {
  if (fields.operation.startsWith("todo")) {
    assert.deepEqual(after.events, before.events); assert.deepEqual(after.files, before.files);
    if (fields.operation === "todo.complete") {
      const expected = structuredClone(before.tasks);
      expected.find((t) => t.task_id === fields.task_id).status = "complete";
      assert.deepEqual(after.tasks, expected);
    } else {
      const ids = new Set(before.tasks.map((t) => t.task_id));
      const added = after.tasks.filter((t) => !ids.has(t.task_id));
      assert.equal(added.length, 1); assert.equal(after.tasks.length, before.tasks.length + 1);
      assert.deepEqual(after.tasks.filter((t) => ids.has(t.task_id)), before.tasks);
      const expected = { task_id: added[0].task_id, title: fields.title, status: "open" };
      if (item.id === "M01") Object.assign(expected, { due_at: "2026-12-22T09:00:00+09:00", priority: "low" });
      assert.deepEqual(added[0], expected);
    }
  } else if (fields.operation === "calendar.create") {
    assert.deepEqual(after.tasks, before.tasks); assert.deepEqual(after.files, before.files);
    const ids = new Set(before.events.map((e) => e.event_id));
    const added = after.events.filter((e) => !ids.has(e.event_id));
    assert.equal(added.length, 1); assert.equal(after.events.length, before.events.length + 1);
    assert.deepEqual(after.events.filter((e) => ids.has(e.event_id)), before.events);
    const times = item.id === "M03" ? ["2026-12-23T10:00:00+09:00", "2026-12-23T10:40:00+09:00"] : ["2026-12-24T22:30:00+09:00", "2026-12-24T23:15:00+09:00"];
    assert.deepEqual(added[0], { event_id: added[0].event_id, title: fields.title, start_at: times[0], end_at: times[1] });
  } else {
    assert.deepEqual(after.tasks, before.tasks); assert.deepEqual(after.events, before.events);
    assert(!after.files["files/Inbox/review-demo.txt"]);
    const keys = Object.keys(after.files); assert.equal(keys.length, 1);
    if (fields.operation === "files.move") assert.equal(keys[0], "files/Archive/review-demo.txt");
    else assert(keys[0].startsWith("trash/"));
    assert.deepEqual(after.files[keys[0]], before.files["files/Inbox/review-demo.txt"]);
  }
}
try {
  await page.goto(values.url);
  await page.getByRole("heading", { name: "개인 비서 검토", exact: true }).waitFor();
  await ready();
  const initial = await state();
  assert.equal(initial.tasks.length + initial.events.length, 0);
  assert.deepEqual(Object.keys(initial.files), ["files/Inbox/review-demo.txt"]);
  assert.deepEqual((await api("/reviews")).data, []);
  // Expiry runs last: no other workspace mutations can explain its rejection.
  const expiryCase = protocol.cases.find((c) => c.id === "M10");
  for (const item of protocol.cases.filter((c) => c.id !== "M10")) {
    const before = await state();
    const fields = { ...item.fields };
    let request = item.request;
    if (item.id === "M02") {
      const target = before.tasks.find((t) => t.title === "수동점검 준비");
      assert(target); fields.task_id = target.task_id;
      request = request.replace("{task_id}", target.task_id);
    }
    const raw = await create(request);
    assert.deepEqual(await state(), before);
    const observation = { case_id: item.id, request, initial_record: raw, goal_fields: { ...fields }, before };
    observations.push(observation);
    if (item.id === "M06" && !raw.metadata.generation_error && ["clarify", "no_change"].includes(raw.metadata.decision)) {
      observation.outcome = "model_no_effect";
    } else {
      let saved = await edit(raw, fields);
      observation.saved_record = saved;
      assert.deepEqual(await state(), before);
      let pending = await confirm(saved, item.id === "M06" ? 409 : 200);
      assert.deepEqual(await state(), before);
      if (item.id === "M06") {
        assert.equal(pending.detail, "duplicate_task"); observation.outcome = "code_duplicate_guard";
      } else if (item.id === "M07") {
        const cancelled = await clickRecord("취소", "POST", `/reviews/${pending.id}/cancel`);
        assert.equal(cancelled.status, "cancelled"); assert.deepEqual(await state(), before);
        await page.reload(); await ready();
        assert.equal((await api(`/reviews/${pending.id}`)).data.status, "cancelled");
        observation.outcome = "cancelled_unchanged";
      } else {
        if (item.id === "M05") {
          const old = pending;
          fields.title = "수동점검 수정 후";
          saved = await edit(saved, fields); // Saved binding refreshed from the UI response.
          const stale = await api(`/reviews/${old.id}/approve`, "POST", { ...binding(old), plan_hash: old.preview.plan_hash });
          assert.equal(stale.status, 409); assert.equal(stale.data.detail, "stale_review_revision");
          assert.deepEqual(await state(), before);
          pending = await confirm(saved);
          observation.planned_user_changes = 1;
        }
        if (item.id === "M04") await capture("desktop-preview.png");
        const executed = await approve(pending);
        const after = await state();
        assertEffect(item, before, after, fields);
        const replay = await api(`/reviews/${executed.id}/approve`, "POST", { ...binding(executed), plan_hash: executed.preview.plan_hash });
        assert.equal(replay.status, 200); assert.deepEqual(await state(), after);
        assert.equal(replay.data.events.at(-1).event, "execution_replayed");
        if (item.flow === "restore") {
          const restore = await clickRecord("복구 미리보기", "POST", `/reviews/${executed.id}/restore`);
          assert.equal(restore.parent_id, executed.id); assert.deepEqual(await state(), after);
          await approve(restore); assert.deepEqual(await state(), before);
        }
        await page.reload(); await ready();
        assert.equal((await api(`/reviews/${executed.id}`)).data.status, "executed");
        observation.outcome = "flow_passed";
      }
    }
    observation.after = await state(); observation.preapproval_unchanged = true;
    await saveProgress();
    console.log(JSON.stringify({ case: item.id, outcome: observation.outcome }));
  }
  await capture("desktop-executed.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await capture("mobile-executed.png");
  await page.getByRole("tab", { name: "파일", exact: true }).click();
  await capture("mobile-files.png");
  const expiryBefore = await state();
  const expiryRaw = await create(expiryCase.request);
  assert.deepEqual(await state(), expiryBefore);
  const expirySaved = await edit(expiryRaw, expiryCase.fields);
  const expiryPending = await confirm(expirySaved);
  assert.deepEqual(await state(), expiryBefore);
  const expiryStarted = performance.now();
  const expiryObservation = { case_id: "M10", request: expiryCase.request, initial_record: expiryRaw,
    goal_fields: expiryCase.fields, saved_record: expirySaved, before: expiryBefore, expiry_mode: "real_wall_clock" };
  observations.push(expiryObservation);
  await saveProgress();
  const remaining = Math.max(0, expiryPending.preview.expires_at * 1000 - Date.now() + 1500);
  console.log(JSON.stringify({ phase: "waiting_real_expiry", remaining_ms: remaining }));
  await new Promise((resolve) => setTimeout(resolve, remaining));
  const beforeExpiryAttempt = await state();
  await page.reload(); await ready();
  await page.locator('section[aria-label="검토 기록"]').getByRole("button").filter({ hasText: expiryCase.request }).click();
  await page.getByText("승인 만료", { exact: true }).last().waitFor();
  assert.equal(await page.getByRole("button", { name: "승인하고 실행", exact: true }).count(), 0);
  const expired = (await api(`/reviews/${expiryPending.id}`)).data;
  assert.equal(expired.status, "expired");
  const rejected = await api(`/reviews/${expired.id}/approve`, "POST", { ...binding(expired), plan_hash: expired.preview.plan_hash });
  assert.equal(rejected.status, 409); assert.equal(rejected.data.detail, "approval_expired_or_state_changed");
  assert.deepEqual(await state(), beforeExpiryAttempt);
  assert.deepEqual(beforeExpiryAttempt, expiryBefore);
  assert(!(await state()).tasks.some((t) => t.title === expiryCase.fields.title));
  assert(performance.now() - expiryStarted >= 300000);
  Object.assign(expiryObservation, { outcome: "real_expiry_blocked", preapproval_unchanged: true,
    before_approval_attempt: beforeExpiryAttempt, rejection: rejected,
    after: await state(), elapsed_ms: performance.now() - expiryStarted, expired_record: expired });
  await capture("mobile-expired.png");
  assert.deepEqual(pageErrors, []);
  const result = { version: protocol.version, status: "passed", browser_flows: 10,
    protocol_sha256: protocolHash, browser_source_sha256: scriptHash,
    automated_user_actions: true, independent_human_attestation: false, reviewer_uses_goal_oracle: true,
    observations, page_errors: pageErrors, final_state: await state() };
  await writeFile(path.join(values.output, "browser-e2e.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ status: "passed", browser_flows: 10, output: values.output }));
} catch (error) {
  await page.screenshot({ path: path.join(values.output, "failure.png"), fullPage: true }).catch(() => {});
  await writeFile(path.join(values.output, "failure.json"), JSON.stringify({ error: String(error), observations, page_errors: pageErrors }, null, 2));
  throw error;
} finally { await browser.close(); }
