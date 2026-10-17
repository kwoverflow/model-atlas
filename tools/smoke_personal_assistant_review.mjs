// Browser regression against a real local model and a disposable workspace.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { parseArgs } from "node:util";
import path from "node:path";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://localhost:3000/personal-assistant" },
  api: { type: "string", default: "http://localhost:18000/api/v1/personal-assistant" },
  output: { type: "string" },
  "playwright-module": { type: "string", default: "playwright" },
} });
assert(values.output, "An artifact output directory is required");
const require = createRequire(import.meta.url);
const { chromium } = require(values["playwright-module"]);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(20000);
const observations = [];
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));
const suffix = Date.now().toString(36);
await mkdir(values.output, { recursive: true });

async function api(suffix, method = "GET", body) {
  const response = await context.request.fetch(values.api + suffix, {
    method, headers: { "x-model-atlas-lab-action": "1", origin: new URL(values.url).origin },
    ...(body === undefined ? {} : { data: body }),
  });
  return { status: response.status(), data: await response.json() };
}
async function state() { return (await api("/workspace")).data.state; }
function binding(record) { return { revision: record.revision, content_hash: record.content_hash }; }
async function clickRecord(name, method, suffix, expected = 200) {
  const responsePromise = page.waitForResponse((response) =>
    response.url() === values.api + suffix && response.request().method() === method,
    { timeout: 65000 });
  await page.getByRole("button", { name, exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), expected, await response.text());
  const record = await response.json();
  await page.getByRole("button", { name: "새로고침", exact: true }).waitFor({ state: "visible" });
  await page.waitForFunction(() => !document.querySelector('button[title="새로고침"]')?.disabled);
  return record;
}
async function create(request) {
  await page.getByLabel("요청", { exact: true }).fill(request);
  const record = await clickRecord("초안 생성", "POST", "/reviews", 201);
  assert.equal(record.metadata.model, "qwen3.5:9b");
  assert(record.metadata.schema_requested);
  assert(record.raw_output.length > 0);
  observations.push({ case: "real_model_draft", request, record });
  return record;
}
async function edit(record, fields) {
  const controls = {
    title: "제목", priority: "우선순위", source: "원본 파일", destination: "대상 파일",
    local_start: "현지 시작 시각", source_timezone: "시간대", duration_minutes: "길이(분)",
    task_id: "할 일 ID", path: "파일",
    local_due: "현지 마감 시각",
  };
  if (await page.getByLabel("작업", { exact: true }).inputValue() !== fields.operation) {
    await page.getByLabel("작업", { exact: true }).selectOption(fields.operation);
  }
  for (const [key, value] of Object.entries(fields).filter(([key]) => key !== "operation")) {
    const control = page.getByLabel(controls[key], { exact: true });
    const inputValue = value === null ? "" : String(value);
    if (["priority", "source_timezone"].includes(key)) await control.selectOption(inputValue);
    else await control.fill(inputValue);
  }
  if (!await page.getByRole("button", { name: "수정 저장", exact: true }).isEnabled()) return record;
  const saved = await clickRecord("수정 저장", "PUT", `/reviews/${record.id}`);
  observations.push({ case: "explicit_form_correction", review_id: record.id, before: record.fields, after: saved.fields });
  return saved;
}
async function confirm(record) {
  await page.getByRole("checkbox", { name: "수정한 내용과 실행 대상을 확인했습니다." }).check();
  return clickRecord("확정 및 미리보기", "POST", `/reviews/${record.id}/confirm`);
}
async function approve(record) {
  return clickRecord("승인하고 실행", "POST", `/reviews/${record.id}/approve`);
}
async function screenshot(name) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "Horizontal overflow");
  const createStyle = await page.getByRole("button", { name: "초안 생성", exact: true }).evaluate((button) => {
    const style = getComputedStyle(button);
    return { color: style.color, background: style.backgroundColor };
  });
  assert.notEqual(createStyle.color, createStyle.background, "Invisible primary button text");
  const approval = page.getByRole("button", { name: "승인하고 실행", exact: true });
  if (await approval.count()) {
    const styles = await approval.evaluate((button) => {
      const style = getComputedStyle(button);
      return { color: style.color, background: style.backgroundColor };
    });
    assert.notEqual(styles.color, styles.background, "Invisible approval text");
  }
  await page.screenshot({ path: path.join(values.output, name), fullPage: true });
}

try {
  await page.goto(values.url);
  await page.getByRole("heading", { name: "개인 비서 검토", exact: true }).waitFor();
  await page.waitForFunction(() => !document.querySelector('button[title="새로고침"]')?.disabled);
  const initial = await state();
  const request = `할 일 '초안 검토-${suffix}'을 추가해줘. 우선순위는 낮음으로 해줘.`;
  const draft = await create(request);
  assert.deepEqual(await state(), initial);
  assert.equal(await page.getByRole("button", { name: "승인하고 실행", exact: true }).count(), 0);
  const title = `사용자가 수정한 검토-${suffix}`;
  const saved = await edit(draft, { operation: "todo.create", title, priority: "low", local_due: null });
  assert.equal(saved.raw_output, draft.raw_output);
  assert.equal(saved.fields.title, title);
  const pending = await confirm(saved);
  assert.equal(pending.preview.action.arguments.title, title);
  assert.deepEqual(await state(), initial);
  await page.getByText("모델 원문 · 수정 내역", { exact: true }).click();
  await screenshot("desktop-preview.png");
  const executed = await approve(pending);
  assert.equal(executed.status, "executed");
  assert.equal((await state()).tasks.filter((task) => task.title === title).length, 1);
  await page.reload();
  await page.locator('section[aria-label="검토 기록"]').getByRole("button").filter({ hasText: request }).click();
  await page.getByText("승인한 작업을 완료했습니다.", { exact: true }).waitFor();
  observations.push({ case: "edited_confirmed_executed_persisted", review_id: draft.id, title });

  const cancelBefore = await state();
  const cancelRaw = await create(`할 일 '실행 취소-${suffix}'을 추가해줘.`);
  const cancel = await edit(cancelRaw, { operation: "todo.create", title: `실행 취소-${suffix}` });
  const cancelled = await clickRecord("취소", "POST", `/reviews/${(await confirm(cancel)).id}/cancel`);
  assert.equal(cancelled.status, "cancelled");
  assert.deepEqual(await state(), cancelBefore);
  observations.push({ case: "cancel_no_effect", review_id: cancel.id });

  const editingRaw = await create(`할 일 '승인 갱신-${suffix}'을 추가해줘.`);
  const editing = await edit(editingRaw, { operation: "todo.create", title: `승인 갱신-${suffix}` });
  const old = await confirm(editing);
  await page.getByLabel("제목", { exact: true }).fill(`수정 후 재검토-${suffix}`);
  assert.equal(await page.getByRole("button", { name: "승인하고 실행", exact: true }).count(), 0);
  await clickRecord("수정 저장", "PUT", `/reviews/${editing.id}`);
  const staleApproval = await api(`/reviews/${editing.id}/approve`, "POST", {
    ...binding(old), plan_hash: old.preview.plan_hash,
  });
  assert.equal(staleApproval.status, 409);
  assert.equal(staleApproval.data.detail, "stale_review_revision");
  observations.push({ case: "edit_invalidates_approval", review_id: editing.id });

  const beforeMove = await state();
  const moveRaw = await create("Inbox/review-demo.txt 파일을 Archive/review-demo.txt로 이동해줘.");
  const move = await edit(moveRaw, { operation: "files.move", source: "Inbox/review-demo.txt", destination: "Archive/review-demo.txt" });
  const movePending = await confirm(move);
  assert.equal(movePending.preview.action.tool, "files.move");
  assert.deepEqual(await state(), beforeMove);
  const moved = await approve(movePending);
  const afterMove = await state();
  assert(!afterMove.files["files/Inbox/review-demo.txt"]);
  assert.equal(afterMove.files["files/Archive/review-demo.txt"].sha256, beforeMove.files["files/Inbox/review-demo.txt"].sha256);
  const restore = await clickRecord("복구 미리보기", "POST", `/reviews/${moved.id}/restore`);
  assert.equal(restore.parent_id, moved.id);
  assert.deepEqual(await state(), afterMove);
  await approve(restore);
  assert.deepEqual(await state(), beforeMove);
  observations.push({ case: "file_move_and_separately_approved_restore", review_id: move.id });

  const beforeCalendar = await state();
  const calendarRaw = await create(`2026년 12월 15일 뉴욕 현지 오전 8시 30분에 '겨울 회의-${suffix}' 일정을 45분간 추가해줘.`);
  const calendar = await edit(calendarRaw, { operation: "calendar.create", title: `겨울 회의-${suffix}`, local_start: "2026-12-15T08:30:00", source_timezone: "America/New_York", duration_minutes: 45 });
  const calendarPending = await confirm(calendar);
  assert.equal(calendarPending.preview.action.arguments.start_at, "2026-12-15T22:30:00+09:00");
  assert.equal(calendarPending.preview.action.arguments.end_at, "2026-12-15T23:15:00+09:00");
  assert.deepEqual(await state(), beforeCalendar);
  await approve(calendarPending);
  observations.push({ case: "winter_timezone_conversion", review_id: calendar.id });

  const targetTask = (await state()).tasks.find((task) => task.title === title);
  const staleRaw = await create(`할 일 '상태 변경 차단-${suffix}'을 추가해줘.`);
  const staleDraft = await edit(staleRaw, { operation: "todo.create", title: `상태 변경 차단-${suffix}` });
  const stalePending = await confirm(staleDraft);
  const completeRaw = await create(`할 일 '${title}'을 완료해줘.`);
  const complete = await edit(completeRaw, { operation: "todo.complete", task_id: targetTask.task_id });
  await approve(await confirm(complete));
  assert.equal((await state()).tasks.find((task) => task.task_id === targetTask.task_id).status, "complete");
  const beforeRejected = await state();
  const rejected = await api(`/reviews/${stalePending.id}/approve`, "POST", {
    ...binding(stalePending), plan_hash: stalePending.preview.plan_hash,
  });
  assert.equal(rejected.status, 409);
  assert.equal(rejected.data.detail, "approval_expired_or_state_changed");
  assert.deepEqual(await state(), beforeRejected);
  observations.push({ case: "todo_complete_and_changed_state_approval_block", review_id: complete.id });

  const beforeTrash = await state();
  const trashRaw = await create("Inbox/review-demo.txt 파일을 보관함으로 보내줘. 영구 삭제는 하지 마.");
  const trash = await edit(trashRaw, { operation: "files.trash", path: "Inbox/review-demo.txt" });
  const trashed = await approve(await confirm(trash));
  assert(!(await state()).files["files/Inbox/review-demo.txt"]);
  const trashRestore = await clickRecord("복구 미리보기", "POST", `/reviews/${trashed.id}/restore`);
  await approve(trashRestore);
  assert.deepEqual(await state(), beforeTrash);
  observations.push({ case: "file_quarantine_and_separately_approved_restore", review_id: trash.id });
  await screenshot("desktop-executed.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot("mobile-executed.png");
  await page.getByRole("tab", { name: "파일", exact: true }).click();
  await screenshot("mobile-files.png");
  assert.deepEqual(pageErrors, []);
  await writeFile(path.join(values.output, "browser-e2e.json"), JSON.stringify({
    version: "personal-assistant-user-review-v1", status: "passed", created: new Date().toISOString(),
    automated_user_actions: true, independent_human_attestation: false,
    scope: "isolated synthetic local workspace", observations, page_errors: pageErrors,
    final_state: await state(),
  }, null, 2));
  console.log(JSON.stringify({ status: "passed", observations: observations.length, output: values.output }));
} catch (error) {
  await page.screenshot({ path: path.join(values.output, "failure.png"), fullPage: true }).catch(() => {});
  await writeFile(path.join(values.output, "browser-failure.json"), JSON.stringify({
    status: "failed", error: String(error), observations, page_errors: pageErrors,
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}
