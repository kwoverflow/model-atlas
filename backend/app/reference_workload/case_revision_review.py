# ruff: noqa: E501
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.reference_workload.case_revision import (
    CASE_REVISION_REPORT_VERSION,
    EVIDENCE_CASE_REVISION_REPORT_VERSION,
    LEGACY_CASE_REVISION_REPORT_VERSION,
    CasePackRevisionError,
)
from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.contracts import (
    REFERENCE_REVIEW_SCHEMA_VERSION,
    CaseReviewDecisionContract,
)
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import canonical_json, file_sha256, stable_hash

LEGACY_CASE_REVISION_ATTESTATION_VERSION = (
    "model-atlas-reference-case-pack-revision-attestation-v1"
)
CASE_REVISION_ATTESTATION_VERSION = "model-atlas-reference-case-pack-revision-attestation-v2"
CASE_REVISION_FINALIZATION_VERSION = "model-atlas-reference-case-pack-revision-finalization-v1"
LEGACY_CASE_REVISION_ATTESTATION_STATEMENT = (
    "I personally reviewed every changed case, its source evidence, and its retrieval contract."
)
CASE_REVISION_ATTESTATION_STATEMENT = (
    "I personally reviewed every changed case, its source evidence, retrieval contract, and "
    "semantic contract."
)
_MACHINE_REVIEWER_PATTERN = re.compile(
    r"(^|[-_ ])(codex|openai|automated|automation|machine|llm|ai[-_ ]?reviewer|test)([-_ ]|$)",
    re.IGNORECASE,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseRevisionDecision(_StrictModel):
    external_case_id: str = Field(pattern=r"^KO-[A-Z0-9-]+-\d{3}$")
    revised_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approved", "rejected"]
    notes: str = Field(min_length=1, max_length=2000)


class CaseRevisionAttestation(_StrictModel):
    schema_version: str
    revision_id: str
    revision_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    statement: str
    reviewer: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    decisions: list[CaseRevisionDecision] = Field(min_length=1, max_length=20)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value not in {
            LEGACY_CASE_REVISION_ATTESTATION_VERSION,
            CASE_REVISION_ATTESTATION_VERSION,
        }:
            raise ValueError(f"unsupported revision attestation version: {value}")
        return value

    @model_validator(mode="after")
    def validate_statement(self) -> CaseRevisionAttestation:
        expected = (
            CASE_REVISION_ATTESTATION_STATEMENT
            if self.schema_version == CASE_REVISION_ATTESTATION_VERSION
            else LEGACY_CASE_REVISION_ATTESTATION_STATEMENT
        )
        if self.statement != expected:
            raise ValueError("revision attestation statement does not match")
        return self

    @field_validator("reviewer")
    @classmethod
    def validate_human_reviewer(cls, value: str) -> str:
        normalized = value.strip()
        if _MACHINE_REVIEWER_PATTERN.search(normalized):
            raise ValueError("revision reviewer must identify a human reviewer")
        return normalized

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @field_validator("decisions")
    @classmethod
    def validate_unique_decisions(
        cls,
        value: list[CaseRevisionDecision],
    ) -> list[CaseRevisionDecision]:
        identifiers = [decision.external_case_id for decision in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("revision decisions must be unique")
        return value


def _load_revision_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CasePackRevisionError(f"revision report is invalid: {exc}") from exc
    if report.get("schema_version") not in {
        LEGACY_CASE_REVISION_REPORT_VERSION,
        EVIDENCE_CASE_REVISION_REPORT_VERSION,
        CASE_REVISION_REPORT_VERSION,
    }:
        raise CasePackRevisionError("revision report schema is unsupported")
    observed_hash = stable_hash(
        {
            key: value
            for key, value in report.items()
            if key not in {"generated_at", "report_sha256"}
        }
    )
    if report.get("report_sha256") != observed_hash:
        raise CasePackRevisionError("revision report hash does not match its content")
    return report


def _contract_evidence(contract: dict[str, Any]) -> str:
    evidence_by_id = {
        str(item.get("chunk_id")): item
        for item in contract.get("evidence", [])
        if isinstance(item, dict) and item.get("chunk_id")
    }
    groups = contract.get("acceptable_evidence_groups")
    if not isinstance(groups, list) or not groups:
        groups = [contract.get("relevant_chunk_ids", [])]
    ranks = contract.get("expected_chunk_ranks", {})
    rendered_groups: list[str] = []
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, list):
            continue
        items: list[str] = []
        for chunk_id in group:
            evidence = evidence_by_id.get(str(chunk_id), {})
            items.append(
                f"""
                <div class="evidence-item">
                  <p class="source">{html.escape(str(evidence.get("source_path") or ""))} · {html.escape(str(evidence.get("heading") or ""))}</p>
                  <p class="rank">{html.escape(str(chunk_id))} · 기대 순위 {html.escape(str(ranks.get(str(chunk_id))))}</p>
                  <p>{html.escape(str(evidence.get("excerpt") or ""))}</p>
                </div>
                """
            )
        rendered_groups.append(
            f"""
            <div class="evidence-group">
              <h4>허용 그룹 {index} <span>그룹 내부 근거는 모두 필요</span></h4>
              {''.join(items)}
            </div>
            """
        )
    return "".join(rendered_groups)


def _semantic_contract(contract: dict[str, Any] | None) -> str:
    contract = contract if isinstance(contract, dict) else {}
    groups = contract.get("acceptable_required_fact_groups")
    if not isinstance(groups, list) or not groups:
        primary = contract.get("required_facts")
        groups = [primary] if isinstance(primary, list) and primary else []
    rendered_groups = []
    for index, group in enumerate(groups, start=1):
        facts = group if isinstance(group, list) else []
        rendered_groups.append(
            f"""
            <div class="fact-group">
              <h4>허용 의미 그룹 {index} <span>그룹 내부 사실은 모두 필요</span></h4>
              <ul>{''.join(f'<li>{html.escape(str(fact))}</li>' for fact in facts)}</ul>
            </div>
            """
        )
    forbidden = contract.get("forbidden_claims")
    forbidden = forbidden if isinstance(forbidden, list) else []
    return f"""
      <p class="contract">{html.escape(str(contract.get("semantic_contract_version") or "rag-semantic-contract-v1"))}</p>
      <p>거부 요구: {html.escape(str(contract.get("must_refuse")))}</p>
      {''.join(rendered_groups)}
      <h4>금지 주장</h4>
      <ul>{''.join(f'<li>{html.escape(str(claim))}</li>' for claim in forbidden) or '<li>없음</li>'}</ul>
    """


def _case_section(change: dict[str, Any], *, revision_id: str) -> str:
    old = change["old_contract"]
    revised = change["revised_contract"]
    old_semantic = change.get("old_semantic_contract") or change.get("semantic_contract")
    revised_semantic = change.get("revised_semantic_contract") or change.get(
        "semantic_contract"
    )
    external_case_id = html.escape(str(change["external_case_id"]))
    return f"""
    <section class="case" data-case-id="{external_case_id}"
      data-case-sha="{html.escape(str(change["revised_case_sha256"]))}">
      <div class="case-head">
        <div><span class="critical">CRITICAL</span><h2>{external_case_id}</h2></div>
        <p>{html.escape(str(change["title"]))}</p>
      </div>
      <dl class="request"><dt>사용자 요청</dt><dd>{html.escape(str(change.get("request") or ""))}</dd></dl>
      <div class="comparison">
        <article>
          <h3>기존 계약</h3>
          <p class="contract">{html.escape(str(old.get("evidence_contract_version") or "rag-evidence-contract-v1"))}</p>
          {_contract_evidence(old)}
        </article>
        <article class="revised">
          <h3>{html.escape(revision_id)} 후보</h3>
          <p class="contract pass">{html.escape(str(revised.get("evidence_contract_version") or "rag-evidence-contract-v1"))} · best-group recall {html.escape(str(revised.get("retrieval_recall")))}</p>
          {_contract_evidence(revised)}
        </article>
      </div>
      <dl><dt>검색 query</dt><dd><code>{html.escape(str(revised["query"]))}</code></dd></dl>
      <div class="comparison semantic-comparison">
        <article>
          <h3>기존 의미 계약</h3>
          {_semantic_contract(old_semantic)}
        </article>
        <article class="revised">
          <h3>{html.escape(revision_id)} 의미 계약</h3>
          {_semantic_contract(revised_semantic)}
        </article>
      </div>
      <dl><dt>변경 이유</dt><dd>{html.escape(str(change["rationale"]))}</dd></dl>
      <fieldset>
        <legend>검토 결정</legend>
        <label><input type="radio" name="decision-{external_case_id}" value="approved"> 승인</label>
        <label><input type="radio" name="decision-{external_case_id}" value="rejected"> 거절</label>
        <label class="notes">검토 메모<input type="text" data-notes placeholder="근거, query, 의미 계약이 요청에 부합하는지 기록" maxlength="2000"></label>
      </fieldset>
    </section>
    """


def write_case_revision_review_html(report_path: Path, output_path: Path) -> None:
    report = _load_revision_report(report_path)
    sections = "".join(
        _case_section(change, revision_id=str(report["revision_id"]))
        for change in report["changes"]
    )
    revision_id = html.escape(str(report["revision_id"]))
    report_hash = html.escape(str(report["report_sha256"]))
    change_count = len(report["changes"])
    retained_count = int(report.get("summary", {}).get("retained_approval_count") or 0)
    source_version = html.escape(str(report.get("source_workload_version") or "canonical"))
    semantic_revision = report.get("schema_version") == CASE_REVISION_REPORT_VERSION
    attestation_version = (
        CASE_REVISION_ATTESTATION_VERSION
        if semantic_revision
        else LEGACY_CASE_REVISION_ATTESTATION_VERSION
    )
    attestation_statement = (
        CASE_REVISION_ATTESTATION_STATEMENT
        if semantic_revision
        else LEGACY_CASE_REVISION_ATTESTATION_STATEMENT
    )
    document = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Model Atlas {revision_id} 계약 검토</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, "Segoe UI", sans-serif; color: #172126; background: #f4f6f5; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; }}
    header, main, footer {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; }}
    header {{ padding: 32px 0 22px; border-bottom: 1px solid #aeb9b5; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    h2, h3 {{ letter-spacing: 0; }}
    .summary {{ color: #42534f; margin: 0; }}
    .hash {{ margin-top: 14px; font: 12px ui-monospace, monospace; overflow-wrap: anywhere; color: #53635f; }}
    .case {{ padding: 28px 0; border-bottom: 1px solid #aeb9b5; }}
    .case-head {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; }}
    .case-head h2 {{ display: inline; margin: 0 0 0 10px; font-size: 20px; }}
    .case-head p {{ margin: 0; font-weight: 600; }}
    .critical {{ color: #9b2c2c; font-size: 12px; font-weight: 800; }}
    dl {{ display: grid; grid-template-columns: 130px 1fr; gap: 12px; margin: 18px 0; }}
    dt {{ font-weight: 700; color: #344440; }}
    dd {{ margin: 0; line-height: 1.55; }}
    code {{ overflow-wrap: anywhere; }}
    .comparison {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: #aeb9b5; border: 1px solid #aeb9b5; }}
    article {{ background: #fff; padding: 18px; min-width: 0; }}
    article.revised {{ background: #f0f8f4; }}
    article h3 {{ margin: 0 0 10px; font-size: 16px; }}
    article h4 {{ margin: 0 0 8px; font-size: 14px; }}
    article h4 span {{ color: #53635f; font-size: 12px; font-weight: 500; }}
    article p {{ line-height: 1.5; }}
    .contract {{ font: 12px ui-monospace, monospace; color: #53635f; }}
    .evidence-group + .evidence-group {{ margin-top: 18px; padding-top: 16px; border-top: 1px solid #c8d1ce; }}
    .semantic-comparison {{ margin-top: 18px; }}
    .fact-group + .fact-group {{ margin-top: 14px; padding-top: 12px; border-top: 1px solid #c8d1ce; }}
    .fact-group ul {{ margin: 8px 0 0; padding-left: 20px; }}
    .evidence-item + .evidence-item {{ margin-top: 12px; }}
    .source {{ font-weight: 700; color: #273834; }}
    .rank {{ color: #8d3232; }}
    .rank.pass {{ color: #17633f; }}
    fieldset {{ display: flex; flex-wrap: wrap; align-items: center; gap: 18px; border: 1px solid #879691; padding: 16px; }}
    legend {{ font-weight: 700; }}
    label {{ font-weight: 600; }}
    .notes {{ flex: 1 1 420px; display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 10px; }}
    input[type="text"], #reviewer {{ width: 100%; min-height: 38px; border: 1px solid #73827d; background: #fff; padding: 8px 10px; font: inherit; }}
    footer {{ padding: 28px 0 48px; }}
    .attest {{ display: grid; gap: 14px; max-width: 780px; }}
    button {{ width: fit-content; border: 0; background: #155f46; color: white; padding: 11px 16px; font: inherit; font-weight: 700; cursor: pointer; }}
    button:hover {{ background: #0f4936; }}
    #status {{ min-height: 24px; color: #9b2c2c; font-weight: 700; }}
    @media (max-width: 720px) {{
      .comparison {{ grid-template-columns: 1fr; }}
      .case-head {{ align-items: start; flex-direction: column; }}
      dl {{ grid-template-columns: 1fr; gap: 4px; }}
      .notes {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Model Atlas case-pack {revision_id} 검토</h1>
    <p class="summary">변경된 critical case {change_count}건만 검토합니다. {source_version}의 기존 승인 {retained_count}건과 canonical case-pack은 변경되지 않습니다.</p>
    <p class="hash">revision report SHA-256: {report_hash}</p>
  </header>
  <main>{sections}</main>
  <footer>
    <div class="attest">
      <label>검토자 이름<input id="reviewer" type="text" maxlength="160" autocomplete="name"></label>
      <label><input id="statement" type="checkbox"> 모든 변경 case의 원문 근거, query, 허용 근거 그룹과 의미 계약을 직접 검토했습니다.</label>
      <button id="download" type="button">검토 증명 다운로드</button>
      <p id="status" role="status"></p>
    </div>
  </footer>
  <script>
    const schemaVersion = {json.dumps(attestation_version)};
    const statementText = {json.dumps(attestation_statement)};
    const revisionId = {json.dumps(str(report["revision_id"]))};
    const reportHash = {json.dumps(str(report["report_sha256"]))};
    document.getElementById("download").addEventListener("click", () => {{
      const reviewer = document.getElementById("reviewer").value.trim();
      const accepted = document.getElementById("statement").checked;
      const status = document.getElementById("status");
      const decisions = [];
      for (const section of document.querySelectorAll(".case")) {{
        const caseId = section.dataset.caseId;
        const selected = section.querySelector(`input[name="decision-${{caseId}}"]:checked`);
        const notes = section.querySelector("[data-notes]").value.trim();
        if (!selected || !notes) {{
          status.textContent = `${{caseId}}의 결정과 검토 메모를 입력해 주세요.`;
          return;
        }}
        decisions.push({{
          external_case_id: caseId,
          revised_case_sha256: section.dataset.caseSha,
          decision: selected.value,
          notes,
        }});
      }}
      if (!reviewer || !accepted) {{
        status.textContent = "검토자 이름과 직접 검토 확인이 필요합니다.";
        return;
      }}
      const payload = {{
        schema_version: schemaVersion,
        revision_id: revisionId,
        revision_report_sha256: reportHash,
        statement: statementText,
        reviewer,
        reviewed_at: new Date().toISOString(),
        decisions,
      }};
      const blob = new Blob([JSON.stringify(payload, null, 2)], {{type: "application/json"}});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `model-atlas-case-revision-${{revisionId}}-attestation.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      status.textContent = "검토 증명을 생성했습니다.";
      status.style.color = "#17633f";
    }});
  </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(output_path)


def finalize_case_pack_revision(
    *,
    repository_root: Path,
    output_directory: Path,
    attestation_path: Path,
) -> dict[str, Any]:
    root = repository_root.resolve()
    output = output_directory.resolve()
    canonical_directory = (root / "reference_workload").resolve()
    if output == canonical_directory or not output.is_relative_to(canonical_directory):
        raise CasePackRevisionError(
            "revision finalization must remain in an isolated reference_workload revision"
        )
    report_path = output / "revision_report.json"
    report = _load_revision_report(report_path)
    artifact_identity = report["artifact_identity"]
    expected_files = {
        "manifest_sha256": output / "manifest.json",
        "cases_sha256": output / "cases.jsonl",
        "reviews_sha256": output / "review_manifest.jsonl",
    }
    for key, path in expected_files.items():
        if file_sha256(path) != artifact_identity[key]:
            raise CasePackRevisionError(
                f"revision artifact changed after review packet generation: {path.name}"
            )
    try:
        attestation = CaseRevisionAttestation.model_validate_json(
            attestation_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise CasePackRevisionError(f"revision attestation is invalid: {exc}") from exc
    expected_attestation_version = (
        CASE_REVISION_ATTESTATION_VERSION
        if report.get("schema_version") == CASE_REVISION_REPORT_VERSION
        else LEGACY_CASE_REVISION_ATTESTATION_VERSION
    )
    if attestation.schema_version != expected_attestation_version:
        raise CasePackRevisionError(
            "revision attestation schema does not cover the report contract"
        )
    if attestation.revision_id != report["revision_id"]:
        raise CasePackRevisionError("revision attestation targets another revision")
    if attestation.revision_report_sha256 != report["report_sha256"]:
        raise CasePackRevisionError("revision attestation report hash does not match")
    expected_changes = {change["external_case_id"]: change for change in report["changes"]}
    decisions = {decision.external_case_id: decision for decision in attestation.decisions}
    if set(decisions) != set(expected_changes):
        raise CasePackRevisionError(
            "revision attestation must decide every changed case exactly once"
        )
    for external_case_id, decision in decisions.items():
        if (
            decision.revised_case_sha256
            != expected_changes[external_case_id]["revised_case_sha256"]
        ):
            raise CasePackRevisionError(f"revision decision hash mismatch for {external_case_id}")

    reviews_path = output / "review_manifest.jsonl"
    retained_lines = reviews_path.read_text(encoding="utf-8").splitlines()
    new_reviews = [
        CaseReviewDecisionContract(
            schema_version=REFERENCE_REVIEW_SCHEMA_VERSION,
            external_case_id=decision.external_case_id,
            case_sha256=decision.revised_case_sha256,
            decision=decision.decision,
            reviewer=attestation.reviewer,
            reviewed_at=attestation.reviewed_at,
            notes=(
                f"Revision {attestation.revision_id} review bound to report "
                f"{attestation.revision_report_sha256}. {decision.notes}"
            ),
        )
        for decision in attestation.decisions
    ]
    merged_lines = [
        *retained_lines,
        *(canonical_json(review.model_dump(mode="json")) for review in new_reviews),
    ]
    temporary = reviews_path.with_suffix(reviews_path.suffix + ".tmp")
    temporary.write_text("\n".join(merged_lines) + "\n", encoding="utf-8")

    bundle = build_reference_corpus(
        output / "manifest.json",
        repository_root=root,
    )
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=output / "cases.jsonl",
        review_manifest_path=temporary,
    )
    temporary.replace(reviews_path)
    finalization: dict[str, Any] = {
        "schema_version": CASE_REVISION_FINALIZATION_VERSION,
        "revision_id": report["revision_id"],
        "revision_report_sha256": report["report_sha256"],
        "reviewer": attestation.reviewer,
        "reviewed_at": attestation.reviewed_at.isoformat(),
        "approved_case_ids": sorted(
            decision.external_case_id
            for decision in attestation.decisions
            if decision.decision == "approved"
        ),
        "rejected_case_ids": sorted(
            decision.external_case_id
            for decision in attestation.decisions
            if decision.decision == "rejected"
        ),
        "case_pack": pack.summary(),
        "review_manifest_sha256": file_sha256(reviews_path),
        "evidence_boundary": {
            "canonical_case_pack_mutated": False,
            "historical_results_mutated": False,
            "bootstrap_allowed": pack.portfolio_ready,
            "authoritative_portfolio_evidence": False,
            "production_readiness": "not_production_ready",
        },
    }
    finalization["report_sha256"] = stable_hash(finalization)
    finalization_path = output / "finalization_report.json"
    temporary = finalization_path.with_suffix(finalization_path.suffix + ".tmp")
    temporary.write_text(
        f"{canonical_json(finalization)}\n",
        encoding="utf-8",
    )
    temporary.replace(finalization_path)
    return {**finalization, "output_path": str(finalization_path)}
