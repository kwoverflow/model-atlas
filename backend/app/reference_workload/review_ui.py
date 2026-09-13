# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_json_for_script(payload: dict[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_review_assistance_html(report: dict[str, Any]) -> str:
    report_json = _safe_json_for_script(report)
    return _HTML.replace("__EMBEDDED_REPORT__", report_json)


def write_review_assistance_html(path: Path, *, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(render_review_assistance_html(report), encoding="utf-8")
    temporary.replace(path)


_HTML = r'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Model Atlas 사례 검토</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #18201f;
      --muted: #65706e;
      --line: #d8dfdd;
      --surface: #ffffff;
      --surface-soft: #f4f7f6;
      --brand: #146c63;
      --brand-dark: #0e514b;
      --brand-soft: #e6f3f0;
      --warning: #9a6300;
      --warning-soft: #fff4d6;
      --danger: #a23a32;
      --danger-soft: #fbe9e7;
      --focus: #0a6fd6;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--surface-soft); color: var(--ink); }
    body { font: 14px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: 0; }
    button, input, select, textarea { font: inherit; letter-spacing: 0; }
    button, select, input, textarea { border: 1px solid var(--line); }
    button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {
      outline: 3px solid color-mix(in srgb, var(--focus) 28%, transparent);
      outline-offset: 1px;
    }
    button { cursor: pointer; background: var(--surface); color: var(--ink); }
    button:disabled { cursor: not-allowed; opacity: .48; }
    .app { min-height: 100vh; display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; }
    .topbar { background: #132a27; color: #fff; padding: 14px 22px; display: flex; align-items: center; gap: 14px; }
    .brand-mark { width: 36px; height: 36px; display: grid; place-items: center; border: 1px solid #6ea59f; font-weight: 800; }
    .topbar h1 { margin: 0; font-size: 18px; line-height: 1.2; }
    .topbar p { margin: 3px 0 0; color: #b8cbc8; font-size: 12px; overflow-wrap: anywhere; }
    .topbar .spacer { flex: 1; }
    .hash { font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; color: #c8d8d5; }
    .status-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); background: var(--surface); border-bottom: 1px solid var(--line); }
    .status-cell { padding: 12px 18px; border-right: 1px solid var(--line); min-width: 0; }
    .status-cell:last-child { border-right: 0; }
    .status-label { display: block; color: var(--muted); font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .status-value { display: block; margin-top: 2px; font-size: 18px; font-weight: 750; overflow-wrap: anywhere; }
    .status-value.small { font-size: 13px; color: var(--danger); padding-top: 4px; }
    .workspace { min-height: 0; display: grid; grid-template-columns: 340px minmax(0, 1fr); }
    .case-panel { min-height: 0; display: grid; grid-template-rows: auto auto minmax(0, 1fr); border-right: 1px solid var(--line); background: var(--surface); }
    .filters { padding: 14px; display: grid; gap: 9px; border-bottom: 1px solid var(--line); }
    .filters-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .filters input, .filters select { width: 100%; min-height: 38px; padding: 7px 9px; background: var(--surface); border-radius: 4px; }
    .progress-wrap { padding: 11px 14px; background: var(--surface-soft); border-bottom: 1px solid var(--line); }
    .progress-label { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; font-weight: 700; }
    .progress-track { height: 7px; margin-top: 7px; background: #dde5e3; overflow: hidden; }
    .progress-bar { height: 100%; width: 0; background: var(--brand); transition: width .18s ease; }
    .case-list { overflow: auto; min-height: 0; }
    .case-row { width: 100%; min-height: 76px; padding: 11px 13px; border: 0; border-bottom: 1px solid var(--line); text-align: left; display: grid; gap: 4px; border-radius: 0; }
    .case-row:hover { background: #f1f7f5; }
    .case-row.active { background: var(--brand-soft); box-shadow: inset 4px 0 var(--brand); }
    .case-row.reviewed .case-id::after { content: "  확인됨"; color: var(--brand); font-weight: 750; }
    .case-meta { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 11px; min-width: 0; }
    .case-id { font: 700 11px ui-monospace, SFMono-Regular, Consolas, monospace; color: var(--ink); }
    .case-title { font-weight: 700; overflow-wrap: anywhere; }
    .badge { display: inline-flex; align-items: center; min-height: 20px; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 800; }
    .badge.required { color: var(--warning); background: var(--warning-soft); }
    .badge.bulk { color: var(--brand-dark); background: var(--brand-soft); }
    .badge.repair { color: var(--danger); background: var(--danger-soft); }
    .detail { min-width: 0; overflow: auto; padding: 22px clamp(18px, 3vw, 42px) 96px; background: var(--surface-soft); }
    .detail-inner { max-width: 1040px; margin: 0 auto; }
    .detail-header { padding-bottom: 16px; border-bottom: 2px solid var(--ink); }
    .detail-kicker { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; color: var(--muted); font-size: 12px; }
    .detail h2 { margin: 8px 0 5px; font-size: 23px; line-height: 1.28; overflow-wrap: anywhere; }
    .question { margin: 0; font-size: 16px; color: #293331; overflow-wrap: anywhere; }
    .review-toggle { margin-top: 15px; display: flex; gap: 10px; align-items: flex-start; padding: 12px; background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--warning); }
    .review-toggle.done { border-left-color: var(--brand); background: #f4fbf9; }
    .review-toggle input { width: 19px; height: 19px; margin: 1px 0 0; accent-color: var(--brand); }
    .section { margin-top: 24px; }
    .section h3 { margin: 0 0 10px; font-size: 14px; }
    .contract-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .contract-block, .evidence, .check { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
    .contract-block { padding: 12px; min-width: 0; }
    .contract-block h4 { margin: 0 0 7px; color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .contract-block ul { margin: 0; padding-left: 19px; }
    .contract-block li + li { margin-top: 4px; }
    .empty { color: var(--muted); }
    .evidence-list, .checks { display: grid; gap: 9px; }
    .evidence summary { cursor: pointer; padding: 11px 13px; font-weight: 700; overflow-wrap: anywhere; }
    .evidence-body { padding: 0 13px 13px; }
    .evidence-path { font: 11px ui-monospace, SFMono-Regular, Consolas, monospace; color: var(--brand-dark); overflow-wrap: anywhere; }
    .excerpt { margin: 9px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
    .check { padding: 10px 12px; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 8px; }
    .check-icon { width: 20px; height: 20px; display: grid; place-items: center; border-radius: 50%; font-weight: 900; }
    .check.pass .check-icon { background: var(--brand-soft); color: var(--brand); }
    .check.fail .check-icon { background: var(--warning-soft); color: var(--warning); }
    .check-title { font: 700 12px ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
    .check-detail { margin-top: 2px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .risk-list { display: flex; flex-wrap: wrap; gap: 6px; }
    .risk-item { padding: 4px 7px; background: var(--warning-soft); color: #6f4900; border-radius: 3px; font-size: 11px; }
    .actionbar { position: fixed; z-index: 10; bottom: 0; left: 340px; right: 0; min-height: 66px; padding: 10px 20px; display: flex; align-items: center; gap: 9px; background: rgba(255,255,255,.96); border-top: 1px solid var(--line); backdrop-filter: blur(8px); }
    .actionbar .spacer { flex: 1; }
    .btn { min-height: 40px; padding: 8px 13px; border-radius: 4px; font-weight: 700; }
    .btn:hover:not(:disabled) { border-color: #9aaba7; background: var(--surface-soft); }
    .btn.primary { color: #fff; background: var(--brand); border-color: var(--brand); }
    .btn.primary:hover:not(:disabled) { background: var(--brand-dark); border-color: var(--brand-dark); }
    .btn.compact { min-width: 42px; padding: 7px 10px; }
    dialog { width: min(620px, calc(100vw - 30px)); border: 1px solid var(--line); border-radius: 6px; padding: 0; box-shadow: 0 18px 60px rgba(16,38,34,.24); }
    dialog::backdrop { background: rgba(12,27,24,.48); }
    .dialog-head { padding: 17px 20px; border-bottom: 1px solid var(--line); }
    .dialog-head h2 { margin: 0; font-size: 19px; }
    .dialog-body { padding: 18px 20px; display: grid; gap: 14px; }
    .field { display: grid; gap: 6px; }
    .field label { font-weight: 700; font-size: 12px; }
    .field input, .field textarea { width: 100%; padding: 9px; border-radius: 4px; }
    .field textarea { min-height: 96px; resize: vertical; }
    .consent { display: flex; gap: 9px; align-items: flex-start; padding: 11px; background: var(--warning-soft); }
    .consent input { width: 18px; height: 18px; margin-top: 1px; accent-color: var(--brand); }
    .dialog-actions { padding: 13px 20px; display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--line); }
    .notice { padding: 10px 12px; border-left: 4px solid var(--brand); background: var(--brand-soft); }
    .hidden { display: none !important; }
    @media (max-width: 820px) {
      .topbar { padding: 12px 14px; }
      .topbar .hash { display: none; }
      .status-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .status-cell:nth-child(2) { border-right: 0; }
      .status-cell:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .workspace { grid-template-columns: 1fr; grid-template-rows: minmax(260px, 38vh) minmax(0, 1fr); }
      .case-panel { border-right: 0; border-bottom: 1px solid var(--line); }
      .detail { padding: 18px 14px 90px; }
      .contract-grid { grid-template-columns: 1fr; }
      .actionbar { left: 0; padding: 9px 12px; }
      .action-label { display: none; }
    }
  </style>
</head>
<body>
  <main class="app">
    <header class="topbar">
      <div class="brand-mark" aria-hidden="true">MA</div>
      <div>
        <h1>참조 워크로드 사례 검토</h1>
        <p>Model Atlas Korean Operator Assistant</p>
      </div>
      <div class="spacer"></div>
      <div class="hash" id="reportHash"></div>
    </header>

    <section class="status-strip" aria-label="검토 상태">
      <div class="status-cell"><span class="status-label">전체 사례</span><span class="status-value" id="totalCount"></span></div>
      <div class="status-cell"><span class="status-label">자동 일괄검토</span><span class="status-value" id="bulkCount"></span></div>
      <div class="status-cell"><span class="status-label">직접 확인</span><span class="status-value" id="spotCount"></span></div>
      <div class="status-cell"><span class="status-label">Production readiness</span><span class="status-value small">NOT_PRODUCTION_READY</span></div>
    </section>

    <div class="workspace">
      <aside class="case-panel" aria-label="사례 목록">
        <div class="filters">
          <input id="searchInput" type="search" placeholder="ID, 제목, 질문 검색" aria-label="사례 검색">
          <div class="filters-row">
            <select id="statusFilter" aria-label="검토 유형 필터">
              <option value="required">직접 확인 26건</option>
              <option value="all">전체 64건</option>
              <option value="bulk">자동 일괄검토</option>
              <option value="repair">수정 필요</option>
            </select>
            <select id="categoryFilter" aria-label="카테고리 필터"><option value="all">모든 카테고리</option></select>
          </div>
        </div>
        <div class="progress-wrap">
          <div class="progress-label"><span>필수 검토 진행률</span><span id="progressText">0 / 26</span></div>
          <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
        </div>
        <div class="case-list" id="caseList"></div>
      </aside>

      <section class="detail" id="detailPane" aria-live="polite">
        <div class="detail-inner" id="detailContent"></div>
      </section>
    </div>

    <nav class="actionbar" aria-label="검토 이동 및 완료">
      <button class="btn compact" id="prevButton" type="button" title="이전 필수 사례">←</button>
      <button class="btn compact" id="nextButton" type="button" title="다음 필수 사례">→</button>
      <span class="action-label" id="positionLabel"></span>
      <div class="spacer"></div>
      <button class="btn primary" id="finishButton" type="button" disabled>검토 결과 만들기</button>
    </nav>
  </main>

  <dialog id="finishDialog">
    <form method="dialog" id="finishForm">
      <div class="dialog-head"><h2>검토 결과 생성</h2></div>
      <div class="dialog-body">
        <div class="notice" id="completionNotice"></div>
        <div class="field">
          <label for="reviewerInput">Reviewer ID</label>
          <input id="reviewerInput" autocomplete="name" maxlength="160" required placeholder="실제 검토자 식별자">
        </div>
        <div class="field">
          <label for="notesInput">검토 메모</label>
          <textarea id="notesInput" maxlength="1200" required placeholder="검토 범위와 판단 근거를 간단히 기록하세요."></textarea>
        </div>
        <label class="consent">
          <input id="bulkConsent" type="checkbox" required>
          <span>필수 사례를 직접 확인했고, 자동 검사를 통과한 나머지 사례의 일괄 승인을 수락합니다.</span>
        </label>
      </div>
      <div class="dialog-actions">
        <button class="btn" id="cancelDialog" type="button">취소</button>
        <button class="btn primary" id="downloadButton" type="submit">승인 JSON 다운로드</button>
      </div>
    </form>
  </dialog>

  <script>
    "use strict";
    const report = __EMBEDDED_REPORT__;
    const requiredIds = report.summary.required_human_case_ids;
    const requiredSet = new Set(requiredIds);
    const storageKey = `model-atlas-review:${report.report_sha256}`;
    const itemMap = new Map(report.items.map((item) => [item.external_case_id, item]));
    function loadSaved() {
      try { return JSON.parse(localStorage.getItem(storageKey) || "{}"); }
      catch (_error) { return {}; }
    }
    const saved = loadSaved();
    const confirmed = new Set((saved.confirmed || []).filter((id) => requiredSet.has(id)));
    let currentId = saved.currentId && itemMap.has(saved.currentId) ? saved.currentId : requiredIds[0];

    const byId = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    const labelFor = (recommendation) => ({
      spot_check_required: "직접 확인",
      eligible_for_bulk_review: "일괄검토",
      repair_required: "수정 필요"
    })[recommendation] || recommendation;
    const badgeClass = (recommendation) => ({
      spot_check_required: "required",
      eligible_for_bulk_review: "bulk",
      repair_required: "repair"
    })[recommendation] || "bulk";

    function persist() {
      try {
        localStorage.setItem(storageKey, JSON.stringify({currentId, confirmed: [...confirmed]}));
      } catch (_error) {
        // Some browsers isolate local file storage; the in-memory review remains usable.
      }
    }

    function filteredItems() {
      const status = byId("statusFilter").value;
      const category = byId("categoryFilter").value;
      const query = byId("searchInput").value.trim().toLocaleLowerCase("ko");
      return report.items.filter((item) => {
        const statusMatch = status === "all"
          || (status === "required" && requiredSet.has(item.external_case_id))
          || (status === "bulk" && item.machine_recommendation === "eligible_for_bulk_review")
          || (status === "repair" && item.machine_recommendation === "repair_required");
        const categoryMatch = category === "all" || item.category === category;
        const haystack = `${item.external_case_id} ${item.title} ${item.query_or_request}`.toLocaleLowerCase("ko");
        return statusMatch && categoryMatch && (!query || haystack.includes(query));
      });
    }

    function renderList() {
      const items = filteredItems();
      byId("caseList").innerHTML = items.length ? items.map((item) => `
        <button type="button" class="case-row ${item.external_case_id === currentId ? "active" : ""} ${confirmed.has(item.external_case_id) ? "reviewed" : ""}" data-case-id="${escapeHtml(item.external_case_id)}">
          <div class="case-meta"><span class="case-id">${escapeHtml(item.external_case_id)}</span><span class="badge ${badgeClass(item.machine_recommendation)}">${labelFor(item.machine_recommendation)}</span></div>
          <div class="case-title">${escapeHtml(item.title)}</div>
          <div class="case-meta">${escapeHtml(item.category)} · ${escapeHtml(item.criticality)}</div>
        </button>`).join("") : '<div class="empty" style="padding:18px">조건에 맞는 사례가 없습니다.</div>';
      byId("caseList").querySelectorAll("[data-case-id]").forEach((button) => {
        button.addEventListener("click", () => selectCase(button.dataset.caseId));
      });
    }

    function listBlock(title, values, emptyText) {
      const list = Array.isArray(values) ? values : [];
      return `<div class="contract-block"><h4>${escapeHtml(title)}</h4>${list.length
        ? `<ul>${list.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>`
        : `<span class="empty">${escapeHtml(emptyText)}</span>`}</div>`;
    }

    function renderContract(item) {
      const contract = item.expected_contract || {};
      const output = contract.expected_output || {};
      const tool = contract.expected_tool_schema || null;
      const agent = contract.agent || null;
      const toolValues = tool ? [
        `Tool: ${tool.tool_name}`,
        `최대 시도: ${tool.max_attempts}`,
        `필수 인자: ${(tool.arguments?.required || []).join(", ") || "없음"}`
      ] : [];
      const agentValues = agent ? [
        `허용 action: ${(agent.allowed_actions || []).join(" → ")}`,
        `최대 step: ${agent.max_steps}`,
        `Tool 호출 / 검색: ${agent.max_tool_calls} / ${agent.max_retrievals}`,
        `메모리 쓰기: ${agent.allow_memory_write ? "허용" : "차단"}`
      ] : [];
      return `<div class="contract-grid">
        ${listBlock("필수 사실", output.required_facts, "Agent step 계약에서 확인")}
        ${listBlock("금지 주장", output.forbidden_claims, "명시된 금지 주장 없음")}
        ${listBlock("Tool 계약", toolValues, "Tool 호출 없음")}
        ${listBlock("Agent 실행 한도", agentValues, "Agent 실행 없음")}
      </div>`;
    }

    function renderEvidence(item) {
      if (!item.source_evidence.length) return '<div class="empty">직접 RAG 근거가 없는 계약 중심 사례입니다.</div>';
      return `<div class="evidence-list">${item.source_evidence.map((evidence, index) => `
        <details class="evidence" ${index === 0 ? "open" : ""}>
          <summary>${escapeHtml(evidence.source_path)} · ${escapeHtml((evidence.heading_path || []).join(" › "))}</summary>
          <div class="evidence-body">
            <div class="evidence-path">chunk ${escapeHtml(evidence.chunk_id)} · ${escapeHtml(String(evidence.chunk_sha256 || "").slice(0, 16))}</div>
            <p class="excerpt">${escapeHtml(evidence.excerpt)}</p>
          </div>
        </details>`).join("")}</div>`;
    }

    function renderChecks(item) {
      return `<div class="checks">${item.checks.map((check) => `
        <div class="check ${check.passed ? "pass" : "fail"}">
          <div class="check-icon" aria-hidden="true">${check.passed ? "✓" : "!"}</div>
          <div><div class="check-title">${escapeHtml(check.check_id)}</div><div class="check-detail">${escapeHtml(check.detail)}</div></div>
        </div>`).join("")}</div>`;
    }

    function renderDetail() {
      const item = itemMap.get(currentId);
      if (!item) return;
      const isRequired = requiredSet.has(item.external_case_id);
      const isDone = confirmed.has(item.external_case_id);
      byId("detailContent").innerHTML = `
        <header class="detail-header">
          <div class="detail-kicker"><span class="case-id">${escapeHtml(item.external_case_id)}</span><span class="badge ${badgeClass(item.machine_recommendation)}">${labelFor(item.machine_recommendation)}</span><span>${escapeHtml(item.category)} · ${escapeHtml(item.criticality)}</span></div>
          <h2>${escapeHtml(item.title)}</h2>
          <p class="question">${escapeHtml(item.query_or_request)}</p>
          ${isRequired ? `<label class="review-toggle ${isDone ? "done" : ""}"><input id="caseConfirmation" type="checkbox" ${isDone ? "checked" : ""}><span><strong>이 사례의 질문, 기대 계약, 근거를 확인했습니다.</strong><br><span class="empty">체크하면 이 브라우저에 진행 상황이 저장됩니다.</span></span></label>` : '<div class="notice" style="margin-top:15px">자동 구조 검사를 통과한 일괄검토 대상입니다. 필요하면 내용을 추가로 확인할 수 있습니다.</div>'}
        </header>
        <section class="section"><h3>기대 계약</h3>${renderContract(item)}</section>
        <section class="section"><h3>선택된 근거</h3>${renderEvidence(item)}</section>
        <section class="section"><h3>자동 검사</h3>${renderChecks(item)}</section>
        <section class="section"><h3>검토 위험 신호</h3><div class="risk-list">${item.risk_reasons.length ? item.risk_reasons.map((reason) => `<span class="risk-item">${escapeHtml(reason)}</span>`).join("") : '<span class="empty">추가 위험 신호 없음</span>'}</div></section>`;
      const checkbox = byId("caseConfirmation");
      if (checkbox) checkbox.addEventListener("change", () => {
        checkbox.checked ? confirmed.add(currentId) : confirmed.delete(currentId);
        persist(); renderAll();
      });
    }

    function renderProgress() {
      const completed = requiredIds.filter((id) => confirmed.has(id)).length;
      const percentage = requiredIds.length ? completed / requiredIds.length * 100 : 100;
      byId("progressText").textContent = `${completed} / ${requiredIds.length}`;
      byId("progressBar").style.width = `${percentage}%`;
      byId("finishButton").disabled = completed !== requiredIds.length || report.summary.repair_required > 0;
      const position = Math.max(0, requiredIds.indexOf(currentId));
      byId("positionLabel").textContent = requiredSet.has(currentId) ? `필수 사례 ${position + 1} / ${requiredIds.length}` : "추가 사례";
      byId("prevButton").disabled = position <= 0 && requiredSet.has(currentId);
      byId("nextButton").disabled = position >= requiredIds.length - 1 && requiredSet.has(currentId);
    }

    function selectCase(id) {
      if (!itemMap.has(id)) return;
      currentId = id; persist(); renderAll();
      byId("detailPane").scrollTop = 0;
    }

    function moveRequired(offset) {
      let index = requiredIds.indexOf(currentId);
      if (index < 0) index = offset > 0 ? -1 : requiredIds.length;
      const next = requiredIds[Math.max(0, Math.min(requiredIds.length - 1, index + offset))];
      selectCase(next);
    }

    function renderAll() { renderList(); renderDetail(); renderProgress(); }

    function openFinish() {
      const completed = requiredIds.filter((id) => confirmed.has(id)).length;
      byId("completionNotice").textContent = `필수 사례 ${completed}건과 자동 일괄검토 ${report.summary.eligible_for_bulk_review}건을 하나의 보고서 해시에 결합합니다.`;
      byId("finishDialog").showModal();
    }

    function downloadAttestation(event) {
      event.preventDefault();
      const reviewer = byId("reviewerInput").value.trim();
      const notes = byId("notesInput").value.trim();
      if (reviewer.length < 2 || !notes || !byId("bulkConsent").checked) {
        byId("finishForm").reportValidity(); return;
      }
      const payload = {
        schema_version: "model-atlas-review-attestation-v1",
        review_report_sha256: report.report_sha256,
        reviewer,
        attestation: "I personally reviewed the automated report and every required spot-check case.",
        approve_automated_passes: true,
        required_case_ids: requiredIds,
        confirmed_case_ids: requiredIds.filter((id) => confirmed.has(id)),
        notes
      };
      const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {type: "application/json"});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "review_attestation.json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      byId("finishDialog").close();
    }

    [...new Set(report.items.map((item) => item.category))].sort().forEach((category) => {
      const option = document.createElement("option"); option.value = category; option.textContent = category;
      byId("categoryFilter").appendChild(option);
    });
    byId("reportHash").textContent = `report ${report.report_sha256.slice(0, 16)}`;
    byId("totalCount").textContent = report.summary.case_count;
    byId("bulkCount").textContent = report.summary.eligible_for_bulk_review;
    byId("spotCount").textContent = report.summary.spot_check_required;
    ["searchInput", "statusFilter", "categoryFilter"].forEach((id) => byId(id).addEventListener("input", renderList));
    byId("prevButton").addEventListener("click", () => moveRequired(-1));
    byId("nextButton").addEventListener("click", () => moveRequired(1));
    byId("finishButton").addEventListener("click", openFinish);
    byId("cancelDialog").addEventListener("click", () => byId("finishDialog").close());
    byId("finishForm").addEventListener("submit", downloadAttestation);
    document.addEventListener("keydown", (event) => {
      if (event.target.matches("input, textarea, select") || byId("finishDialog").open) return;
      if (event.key === "ArrowLeft") moveRequired(-1);
      if (event.key === "ArrowRight") moveRequired(1);
    });
    renderAll();
  </script>
</body>
</html>
'''
