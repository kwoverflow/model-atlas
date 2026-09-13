"""Export the source alignment audit to the shared portable-report artifact format."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.reference_workload.manifest import stable_hash  # noqa: E402


def build_artifact(report):
    content = {k: v for k, v in report.items() if k != "content_sha256"}
    if stable_hash(content) != report["content_sha256"]:
        raise ValueError("alignment audit hash mismatch")
    summary = report["summary"]
    query = (
        "SELECT '기존 1.0.4' AS contract, SUM(json_extract(value, '$.old_reachable')) AS count "
        "FROM json_each(?, '$.cases') UNION ALL "
        "SELECT '제안 1.0.5', SUM(json_extract(value, '$.proposed_reachable')) "
        "FROM json_each(?, '$.cases')"
    )
    serialized = json.dumps(report, ensure_ascii=False)
    with closing(sqlite3.connect(":memory:")) as connection:
        chart_rows = [
            {"contract": label, "count": count}
            for label, count in connection.execute(query, (serialized, serialized))
        ]
    assert [row["count"] for row in chart_rows] == [
        summary["old_reachable"],
        summary["proposed_reachable"],
    ]
    chart_source = {
        "id": "reachability-query",
        "label": "Frozen source alignment audit: top-5 counts",
        "path": "source_alignment_audit.json",
        "query": {
            "engine": "SQLite JSON1",
            "sql": query,
            "description": "Both bound parameters contain the hash-verified audit JSON.",
        },
    }
    blocks = []

    def section(id, body):
        blocks.append({"id": id, "type": "markdown", "body": body, "sourceId": "audit"})

    section(
        "summary",
        "## 기술 요약\n\n"
        f"**핵심 사례 {summary['case_count']}건 중 {summary['proposed_change_count']}건의 "
        f"지정 근거를 바꾸는 검토안이며, {summary['retained_source_count']}건은 유지합니다.** "
        "기존 승인본 1.0.4는 수정하지 않았습니다. 1.0.5는 미승인 초안입니다.\n\n"
        f"기존 검색기로 필요한 근거를 찾는 사례는 {summary['old_reachable']}/5에서 "
        f"{summary['proposed_reachable']}/5가 됩니다. 이는 성능 개선이 아니라 더 직접적인 "
        "정답 근거를 지정했을 때 드러나는 검색 누락입니다. **Gate 통과나 운영 준비 완료를 "
        "의미하지 않습니다.**",
    )
    table = [
        "## 네 건의 근거 연결을 재검토해야 합니다",
        "",
        "| 사례 | 검토안 | 기존 근거 순위 | 제안 근거 순위 |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["cases"]:
        old = ", ".join(str(item["rank"]) for item in row["old_evidence"])
        new = ", ".join(str(item["rank"]) for item in row["proposed_evidence"])
        action = "변경 제안" if row["proposed_change"] else "기존 유지"
        table.append(f"| {row['external_case_id']} | {action} | {old} | {new} |")
    table.extend(
        [
            "",
            "검색 범위는 top-5이며, 제안 그룹 안의 문단은 모두 필요합니다. "
            "점수가 0인 문단의 순위는 동률 정렬 결과일 뿐 관련성의 증명이 아닙니다.",
        ]
    )
    section("findings", "\n".join(table))
    blocks.append({"id": "reachability-chart", "type": "chart", "chartId": "reachability"})
    section(
        "scope",
        "## 범위와 측정 기준\n\n"
        "분석 단위는 반복 실행 결과가 아니라 고유한 critical 일반 RAG 사례 5개입니다. "
        "승인된 1.0.4 사례 64개와 고정된 문서 14개·chunk 200개에서 선정했습니다. "
        "모델 추론이나 DB 기록 변경은 수행하지 않았습니다.\n\n"
        "근거 적합성 평가는 AI가 작성한 검토 의견입니다. 자동화한 것은 ID 존재 여부, "
        "인용문 정확 일치, 복수 문서 조건, 인용 개수 제한, 기존 계약 보존 및 검색 순위입니다. "
        "독립적인 사람 검토는 아직 없습니다.",
    )
    for row in report["cases"]:
        text = [
            f"## {row['external_case_id']}: "
            + ("기존 근거 유지" if not row["proposed_change"] else "직접 근거로 변경 제안"),
            "",
            f"**질문:** {row['question']}",
            "",
            row["reason"],
            "",
            "**변경하지 않은 필수 사실:** "
            + "; ".join(row["required_output_unchanged"]["required_facts"]),
            "",
            "**기존 지정 근거:**",
        ]
        for item in row["old_evidence"]:
            text.append(f"- {item['document_id']} / {item['title']} / 순위 {item['rank']}")
        text.extend(["", "### 질문의 세부 항목과 원문 연결", ""])
        sources = {item["chunk_id"]: item for item in row["proposed_evidence"]}
        for facet in row["facets"]:
            text.extend([f"**{facet['description']}**", ""])
            for support in facet["support"]:
                source = sources[support["chunk_id"]]
                text.extend(
                    [
                        f"출처: {source['document_id']} / {source['title']}",
                        "",
                        "```text",
                        support["quote"],
                        "```",
                        "",
                    ]
                )
        section(row["external_case_id"].lower(), "\n".join(text))
    section(
        "method",
        "## 검증 방법과 재현\n\n"
        f"질문의 세부 항목에 연결한 원문 {summary['exact_quote_checks']}개가 해당 문단에 "
        "정확히 존재하는지 검사했습니다. 문서의 의미가 옳다는 자동 판정은 아닙니다. "
        "복수 문서 사례는 최소 두 문서를 유지하며, 모든 필수 근거가 기본 최대 인용 수 "
        "3 안에 들어가는지 확인했습니다.\n\n"
        "질문, 검색 질문, top_k, 필수 사실, 금지 주장, 거절 요구, criticality, weight는 "
        "변경하지 않았습니다. 별도 검토 항목은 평가 모델의 입력이나 정답에 추가하지 않았습니다.\n\n"
        "재현 코드: backend/app/reference_workload/rag_contract_alignment.py\n\n"
        "계획 파일: reference_workload/diagnostics/rag-contract-alignment-v1.json\n\n"
        "고정 corpus SHA-256: `" + report["corpus"]["corpus_hash"] + "`",
    )
    section(
        "limits",
        "## 한계와 아직 답하지 못한 질문\n\n"
        "- 근거를 바꿔도 답변 모델과 검색기의 성능이 자동으로 좋아지지는 않습니다.\n"
        "- 기존 필수 사실은 짧고 의미 점수는 표현에 민감합니다. 이번에는 두 요소를 수정하지 "
        "않았으므로, 필수 사실 점수의 타당성은 별도로 검토해야 합니다.\n"
        "- 제안한 문단 조합이 질문에 충분한지, 다른 동등한 근거 조합도 필요한지는 사람이 "
        "확인해야 합니다. 현재 안은 완화된 OR 그룹이 아닌 AND 그룹입니다.\n"
        "- 고정된 한 버전의 검토이며 시간 추세나 독립 표본의 일반화 결과는 아닙니다.",
    )
    section(
        "next",
        "## 다음 단계\n\n"
        "1. revision_review.html에서 변경 제안 4건의 질문·원문·계약을 확인합니다. "
        "검토에 동의하지 않으면 거절로 남길 수 있습니다.\n"
        "2. 승인 기록이 있더라도 곧바로 배포하지 않습니다. 한국어 질문으로 영어 기술 문서를 "
        "찾는 검색 문제를 별도 후보에서 검증합니다.\n"
        "3. 근거에 도달한 뒤 답변의 사실 충족과 출처 관계를 새 관측으로 평가합니다. "
        "공식 Gate는 별도 재평가 전까지 유지합니다.",
    )
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Source Alignment Audit",
            "generatedAt": report["generated_at"],
            "blocks": blocks,
            "charts": [
                {
                    "id": "reachability",
                    "title": "계약별 top-5 근거 도달 사례 수 (전체 5개)",
                    "type": "bar",
                    "dataset": "reachability",
                    "sourceId": "reachability-query",
                    "source": chart_source,
                    "encodings": {
                        "x": {"field": "contract", "type": "nominal", "label": "계약"},
                        "y": {
                            "field": "count",
                            "type": "quantitative",
                            "label": "사례 수",
                            "format": "number",
                        },
                    },
                    "valueFormat": "number",
                    "yAxisTitle": "사례 수",
                    "layout": "full",
                }
            ],
            "sources": [
                {
                    "id": "audit",
                    "label": "1.0.5 source alignment audit (unreviewed)",
                    "path": "source_alignment_audit.json",
                },
                chart_source,
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": report["generated_at"],
            "status": "ready",
            "datasets": {"reachability": chart_rows},
        },
    }


def main():
    directory = ROOT / "reference_workload/revisions/1.0.5"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=directory / "source_alignment.artifact.json")
    args = parser.parse_args()
    artifact = build_artifact(
        json.loads((directory / "source_alignment_audit.json").read_text("utf-8"))
    )
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(artifact, target, ensure_ascii=False, indent=2)
    print(args.output)


if __name__ == "__main__":
    main()
