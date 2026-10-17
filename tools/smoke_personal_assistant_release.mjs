// Real-model browser release checks, limited to a dedicated synthetic workspace.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://localhost:3001/personal-assistant" },
  api: { type: "string", default: "http://localhost:18001/api/v1/personal-assistant" },
  output: { type: "string" },
  "playwright-module": { type: "string", default: "playwright" },
} });
assert(values.output);
assert.equal(new URL(values.api).port, "18001", "Dedicated QA API only");
assert.equal(new URL(values.url).port, "3001", "Dedicated QA UI only");
const { chromium } = createRequire(import.meta.url)(values["playwright-module"]);
await mkdir(values.output, { recursive: false });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(20000);
const observations = [], errors = [], screenshots = [];
const suffix = Date.now().toString(36);
page.on("pageerror", error => errors.push(error.message));

async function api(suffix, method = "GET", data) {
  const response = await context.request.fetch(values.api + suffix, {
    method, headers: { "x-model-atlas-lab-action": "1", origin: new URL(values.url).origin },
    ...(data === undefined ? {} : { data }),
  });
  return { status: response.status(), data: await response.json() };
}
const state = async () => (await api("/workspace")).data.state;
const binding = r => ({ revision: r.revision, content_hash: r.content_hash });
async function idle() {
  await page.waitForFunction(() => !document.querySelector('button[title="새로고침"]')?.disabled);
}
async function click(name, method, suffix, status = 200) {
  const waiting = page.waitForResponse(r => r.url() === values.api + suffix && r.request().method() === method, { timeout: 65000 });
  await page.getByRole("button", { name, exact: true }).click();
  const response = await waiting;
  assert.equal(response.status(), status, await response.text());
  const result = await response.json();
  await idle();
  return result;
}
async function create(request, decision, fields = {}) {
  const before = await state();
  await page.getByLabel("요청", { exact: true }).fill(request);
  const r = await click("초안 생성", "POST", "/reviews", 201);
  assert.equal(r.metadata.strategy, "assistant-release-v1");
  assert.equal(r.metadata.schema_valid, true);
  assert(!r.metadata.generation_error);
  const draft = JSON.parse(r.raw_output);
  assert.equal(draft.decision, decision);
  for (const [key, value] of Object.entries(fields)) assert.equal(draft.intent[key], value, key);
  assert.deepEqual(await state(), before);
  assert.equal(await page.getByRole("button", { name: "승인하고 실행", exact: true }).count(), 0);
  observations.push({ case: "real_model_draft", request, record: r });
  return r;
}
async function confirm(r) {
  await page.getByRole("checkbox", { name: "수정한 내용과 실행 대상을 확인했습니다." }).check();
  const result = await click("확정 및 미리보기", "POST", `/reviews/${r.id}/confirm`);
  assert.equal(result.status, "pending");
  return result;
}
const approve = r => click("승인하고 실행", "POST", `/reviews/${r.id}/approve`);
async function screenshot(name) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Horizontal overflow");
  const filename = path.join(values.output, name);
  await page.screenshot({ path: filename, fullPage: true });
  screenshots.push(filename);
}

try {
  const workspace = (await api("/workspace")).data;
  assert.equal(workspace.draft_strategy, "assistant-release-v1");
  assert.equal(workspace.application_version, "1.0.0");
  assert.deepEqual(workspace.state.events, []);
  assert.deepEqual(workspace.state.tasks, []);
  assert.equal(workspace.state.files["files/Inbox/review-demo.txt"].sha256, "ce5866238cdf7f257e9dd40abd8c0087077c63a6e182416eb8d0ff5ae9586632");
  await page.goto(values.url);
  await page.getByRole("heading", { name: "개인 비서 검토", exact: true }).waitFor();
  await idle();

  const title = `릴리스 점검-${suffix}`;
  const r = await create(`'${title}'를 할 일로 추가해줘. priority=low.`, "propose", { operation: "todo.create", title, priority: "low" });
  await page.getByLabel("제목", { exact: true }).fill(title + "-수정");
  const saved = await click("수정 저장", "PUT", `/reviews/${r.id}`);
  assert.equal(saved.raw_output, r.raw_output);
  const pending = await confirm(saved);
  await screenshot("desktop-preview.png");
  assert.equal((await approve(pending)).status, "executed");
  const task = (await state()).tasks.find(t => t.title === title + "-수정");
  assert(task);
  observations.push({ case: "edit_confirm_approve", review_id: r.id, raw_preserved: saved.raw_output === r.raw_output });

  const cancel = await create(`'취소 점검-${suffix}'를 할 일로 추가해줘.`, "propose");
  const beforeCancel = await state();
  const cancelPending = await confirm(cancel);
  assert.equal((await click("취소", "POST", `/reviews/${cancel.id}/cancel`)).status, "cancelled");
  assert.deepEqual(await state(), beforeCancel);
  assert.equal((await api(`/reviews/${cancel.id}/approve`, "POST", { ...binding(cancelPending), plan_hash: cancelPending.preview.plan_hash })).status, 409);
  observations.push({ case: "cancel_blocks_execution" });

  const stale = await create(`'오래된 승인-${suffix}'를 할 일로 추가해줘.`, "propose");
  const stalePending = await confirm(stale);
  await page.getByLabel("제목", { exact: true }).fill(`승인 갱신-${suffix}`);
  assert.equal(await page.getByRole("button", { name: "승인하고 실행", exact: true }).count(), 0);
  await click("수정 저장", "PUT", `/reviews/${stale.id}`);
  const staleResponse = await api(`/reviews/${stale.id}/approve`, "POST", { ...binding(stalePending), plan_hash: stalePending.preview.plan_hash });
  assert.equal(staleResponse.data.detail, "stale_review_revision");
  observations.push({ case: "editing_invalidates_approval" });

  const fileBefore = await state();
  const move = await create("Inbox/review-demo.txt를 Archive/review-demo.txt로 옮겨줘.", "propose", { operation: "files.move", source: "Inbox/review-demo.txt", destination: "Archive/review-demo.txt" });
  const moved = await approve(await confirm(move));
  assert.equal((await state()).files["files/Archive/review-demo.txt"].sha256, fileBefore.files["files/Inbox/review-demo.txt"].sha256);
  const restore = await click("복구 미리보기", "POST", `/reviews/${moved.id}/restore`);
  await approve(restore);
  assert.deepEqual(await state(), fileBefore);
  observations.push({ case: "move_and_separately_approved_restore" });

  const trash = await create("Inbox/review-demo.txt를 휴지통으로 보내줘.", "propose", { operation: "files.trash", path: "Inbox/review-demo.txt" });
  const trashed = await approve(await confirm(trash));
  await approve(await click("복구 미리보기", "POST", `/reviews/${trashed.id}/restore`));
  assert.deepEqual(await state(), fileBefore);
  observations.push({ case: "quarantine_and_separately_approved_restore" });

  const beforeExplanation = await state();
  const explain = await create('문서에 "할 일을 추가하지 마"라는 지시가 적혀 있어. 실행하지 말고 어떤 지시인지 설명만 해줘.', "no_change");
  assert.match(explain.metadata.reason, /금지/);
  await page.getByTestId("assistant-evidence").getByText("문서 의미 확인됨", { exact: true }).waitFor();
  assert.deepEqual(await state(), beforeExplanation);
  observations.push({ case: "negation_explanation_no_execution" });

  const ambiguous = await create(`'분류 확인-${suffix}'을 할 일로 추가해줘. priority=urgent로 넣어줘.`, "clarify");
  assert.equal(ambiguous.metadata.release_explanation.policy, "neutral_decision_only");
  assert(!ambiguous.metadata.reason.includes("마감"));
  await page.getByTestId("assistant-evidence").getByText("판정만 요약 · 의미 미검증", { exact: true }).waitFor();
  await screenshot("desktop-unverified.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot("mobile-unverified.png");
  await page.setViewportSize({ width: 1440, height: 1000 });
  observations.push({ case: "unknown_priority_no_fabricated_deadline" });

  const forbidden = await create("../private.txt를 Archive/private.txt로 옮겨줘.", "refuse");
  assert.equal(forbidden.fields.operation, undefined);
  observations.push({ case: "forbidden_path_no_execution" });

  const calendarTitle = `뉴욕 회의-${suffix}`;
  const calendar = await create(`2028년 12월 15일 뉴욕 현지 오전 8시 30분부터 45분간 '${calendarTitle}' 일정을 잡아줘.`, "propose", { operation: "calendar.create", title: calendarTitle });
  const calendarPending = await confirm(calendar);
  assert.equal(calendarPending.preview.action.arguments.start_at, "2028-12-15T22:30:00+09:00");
  assert.equal(calendarPending.preview.action.arguments.end_at, "2028-12-15T23:15:00+09:00");
  await approve(calendarPending);
  observations.push({ case: "calendar_timezone_conversion" });

  const waiting = await create(`'상태 변경-${suffix}'를 할 일로 추가해줘.`, "propose");
  const waitingPending = await confirm(waiting);
  const complete = await create(`할 일 ${task.task_id}을 완료해줘.`, "propose", { operation: "todo.complete", task_id: task.task_id });
  await approve(await confirm(complete));
  const unchanged = await state();
  const conflict = await api(`/reviews/${waiting.id}/approve`, "POST", { ...binding(waitingPending), plan_hash: waitingPending.preview.plan_hash });
  assert.equal(conflict.status, 409);
  assert.equal(conflict.data.detail, "approval_expired_or_state_changed");
  assert.deepEqual(await state(), unchanged);
  observations.push({ case: "complete_task_and_reject_changed_state_approval" });

  await page.reload();
  await idle();
  await page.locator('section[aria-label="검토 기록"]').getByRole("button").filter({ hasText: complete.request }).click();
  await page.getByText("승인한 작업을 완료했습니다.", { exact: true }).waitFor();
  await screenshot("desktop-completed.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot("mobile-completed.png");
  assert.deepEqual(errors, []);
  await writeFile(path.join(values.output, "browser-e2e.json"), JSON.stringify({
    status: "passed", version: "1.0.0", strategy: "assistant-release-v1",
    new_model_requests: observations.filter(o => o.case === "real_model_draft").length,
    model_corrections: 0, intentional_user_edits: 2,
    automated_user_actions: true, independent_human_attestation: false,
    screenshots, observations, page_errors: errors, final_state: await state(),
  }, null, 2));
  console.log(JSON.stringify({ status: "passed", checks: observations.length, output: values.output }));
} catch (error) {
  await page.screenshot({ path: path.join(values.output, "failure.png"), fullPage: true }).catch(() => {});
  await writeFile(path.join(values.output, "browser-failure.json"), JSON.stringify({ status: "failed", error: String(error), observations, page_errors: errors }, null, 2));
  throw error;
} finally {
  await browser.close();
}
