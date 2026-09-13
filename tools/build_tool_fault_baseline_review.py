"""Reconcile a completed paired baseline and build its notebook and canonical report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]

LOAD = """import hashlib, json, sqlite3
from pathlib import Path
root = Path.cwd()
while not (root / "reference_workload/runtime_matrix.json").exists():
    assert root != root.parent, "repository root not found"
    root = root.parent
source = root / SOURCE_PATH
assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
report = json.loads(source.read_text(encoding="utf-8"))
assert report["status"] == "complete"
assert report["human_reviewed"] is False and report["gate_evidence"] is False
assert report["database_writes_performed"] is False
rows = [{"entry": entry["name"], **row} for entry in report["entries"] for row in entry["rows"]]
assert len(rows) == report["protocol"]["expected_observations"]
assert len({(r["entry"], r["id"], r["trial"]) for r in rows}) == len(rows)
assert not any("error" in row for row in rows)
for name, expected in report["source_sha256"].items():
    assert hashlib.sha256((root / "backend/app" / name).read_bytes()).hexdigest() == expected, name
journal = source.with_suffix(".observations.jsonl")
assert hashlib.sha256(journal.read_bytes()).hexdigest() == report["journal_sha256"]
assert [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()] == rows
for filename, key in [("runtime_matrix.json", "matrix_sha256"),
                      ("diagnostics/tool-fault-baseline-v1.json", "case_pack_sha256"),
                      ("revisions/1.0.4/manifest.json", "manifest_sha256")]:
    assert hashlib.sha256((root / "reference_workload" / filename).read_bytes()).hexdigest() == report[key]
print({"observations": len(rows), "journal_and_source_hashes": "verified"})"""

CHECK = """def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()
cases = {c["id"]: c for c in report["case_pack"]["cases"]}
flat = []
faults = []
for entry in report["entries"]:
    expected_keys = {(case_id, trial) for case_id in cases
                     for trial in range(1, entry["matrix_entry"]["trials"] + 1)}
    assert {(r["id"], r["trial"]) for r in entry["rows"]} == expected_keys
    assert entry["generation_config"] == entry["matrix_entry"]["generation"]
for row in rows:
    body = row["request_body"]
    assert row["request_hash"] == digest(body)
    assert body["seed"] == row["seed"] == 41 + row["trial"]
    public = json.loads(body["messages"][1]["content"])
    assert public["input"]["query"] == cases[row["id"]]["request"]
    assert "expected_tool_schema_json" not in public
    assert "tool_fault_scenario" not in public["input"]
    assert "simulate_failure" not in json.dumps(public["input"]["available_tools"])
    normalized = json.loads(row["normalized_output"])
    tool, arguments = normalized["tool_name"], normalized["arguments"]
    selected = tool == cases[row["id"]]["expected_tool"]
    exact = arguments == cases[row["id"]]["expected_arguments"]
    assert selected == row["selection_correct"]
    assert exact == row["arguments_exact"]
    assert (selected and exact) == row["selection_and_arguments_exact"]
    guard = row["metadata"]["tool_call_contract"]
    assert digest(arguments) == guard["normalized_arguments_hash"]
    assert guard["raw_arguments_hash"] == guard["normalized_arguments_hash"]
    assert row["raw_schema_valid"] == row["raw_guard"]["schema_valid"]
    assert row["normalized_schema_valid"] == guard["schema_valid"]
    assert row["guard_eligible"] == (not guard["schema_errors"] and not guard["boundary_errors"])
    for mode, trace in row["traces"].items():
        assert trace["steps"][0]["arguments"] == arguments
        attempts = trace["steps"][0]["attempts"]
        scenario = trace["fault_scenario"]
        assert scenario["gate_evidence"] is False
        assert scenario["handler_invocation_count"] == sum(a["handler_invoked"] for a in attempts)
        assert scenario["injected_failure_count"] == sum(a["fault_injected"] for a in attempts)
        if not guard["execution_allowed"] or not selected:
            assert attempts == [] and scenario["status"] == "not_exercised"
        if mode == "permanent":
            assert trace["successful"] is False
        faults.append((row["entry"], mode, int(trace["successful"]), int(scenario["passed"]),
                       int(scenario["status"] == "not_exercised"),
                       scenario["handler_invocation_count"], scenario["injected_failure_count"]))
    flat.append((row["entry"], row["id"], row["trial"], int(selected),
                 int(row["raw_schema_valid"]), int(row["guard_eligible"]), int(exact),
                 int(selected and exact), int(row["traces"]["normal"]["successful"])))
connection = sqlite3.connect(":memory:")
connection.row_factory = sqlite3.Row
connection.execute("CREATE TABLE observations (entry, case_id, trial, selected, schema_valid, eligible, exact_arguments, exact_call, tool_success)")
connection.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)", flat)
connection.execute("CREATE TABLE faults (entry, mode, success, passed, not_exercised, handlers, injected)")
connection.executemany("INSERT INTO faults VALUES (?,?,?,?,?,?,?)", faults)
print({"paired_traces": len(faults), "independent_row_checks": "passed"})"""

SQL = """SELECT entry, COUNT(*) AS total, SUM(selected) AS selected,
SUM(schema_valid) AS schema_valid, SUM(eligible) AS eligible,
SUM(exact_call) AS exact_call, SUM(tool_success) AS tool_success,
SUM(tool_success = 1 AND exact_call = 0) AS success_with_wrong_values
FROM observations GROUP BY entry ORDER BY entry"""

RESULTS = """summary = [dict(r) for r in connection.execute(SQL)]
for item in summary:
    original = next(e["summary"] for e in report["entries"] if e["name"] == item["entry"])
    for independent, stored in [("total", "observation_count"), ("selected", "selection_correct"),
                               ("schema_valid", "raw_schema_valid"), ("eligible", "guard_eligible"),
                               ("exact_call", "selection_and_arguments_exact"),
                               ("tool_success", "normal_tool_success")]:
        assert item[independent] == original[stored]
print(json.dumps(summary, ensure_ascii=False, indent=2))
mode_summary = [dict(r) for r in connection.execute(
    "SELECT mode, COUNT(*) AS total, SUM(success) AS successes, SUM(passed) AS fixture_passed, "
    "SUM(not_exercised) AS not_exercised, SUM(handlers) AS handlers, SUM(injected) AS injected "
    "FROM faults GROUP BY mode ORDER BY mode")]
print(json.dumps(mode_summary, indent=2))
output = {"source_sha256": SOURCE_SHA256, "summary": summary, "mode_summary": mode_summary,
          "checks": "passed", "observation_count": len(rows), "paired_trace_count": len(faults)}
(root / AUDIT_PATH).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    notebook_path = args.output_dir / "reproduce.ipynb"
    artifact_path = args.output_dir / "artifact.json"
    if notebook_path.exists() or artifact_path.exists():
        parser.error("review artifacts already exist")
    source_path = args.input.resolve().relative_to(ROOT).as_posix()
    source_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    audit_path = (args.output_dir / "audit.json").resolve().relative_to(ROOT).as_posix()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    total = report["summary"]["observation_count"]
    exact = report["summary"]["selection_and_arguments_exact"]
    success = report["summary"]["normal_tool_success"]
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                f"# Model Atlas Tool Fault Baseline\n\n## tl;dr\n\nExact Tool and arguments: {exact}/{total}; normal fixture success: {success}/{total}. This is a new narrow baseline, not a historical improvement claim."
            ),
            nbformat.v4.new_markdown_cell(
                "## Context & Methods\n\nOne actual model output per entry/case/trial is replayed in three modes. Private labels are excluded from the captured requests.\n\n### Key Assumptions\n\nLocal, unreviewed exact-literal requests; deterministic handlers; executor retries; two zero-temperature trials are not independent estimates of broad accuracy. No live inference or database writes in this notebook."
            ),
            nbformat.v4.new_markdown_cell(
                "## Data\n\nVerify artifact identity, full trial coverage, source hashes and the observation journal."
            ),
            nbformat.v4.new_code_cell(
                f"SOURCE_PATH = {source_path!r}\nSOURCE_SHA256 = {source_hash!r}\nAUDIT_PATH = {audit_path!r}\n"
                + LOAD
            ),
            nbformat.v4.new_markdown_cell(
                "### Independently Check Requests And Traces\n\nRecompute exact calls from captured JSON and private labels, and verify pairing and handler counts."
            ),
            nbformat.v4.new_code_cell(CHECK),
            nbformat.v4.new_markdown_cell(
                "## Results\n\nSQLite aggregates the independently reconstructed rows, then reconciles the runner summaries."
            ),
            nbformat.v4.new_code_cell(f"SQL = {SQL!r}\n" + RESULTS),
            nbformat.v4.new_markdown_cell(
                "## Takeaways\n\nUse this as a frozen diagnostic baseline. Execution success does not prove requested-value correctness. Permanent expected failure is never Tool success. Review explicit value failures before changing the generation strategy; retain this baseline and do not promote it to Gate evidence."
            ),
        ],
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            }
        },
    )
    nbformat.validate(notebook)
    nbformat.write(notebook, notebook_path)
    NotebookClient(
        notebook, timeout=120, resources={"metadata": {"path": str(ROOT)}}
    ).execute()
    nbformat.write(notebook, notebook_path)
    audit = json.loads((ROOT / audit_path).read_text(encoding="utf-8"))
    summary = audit["summary"]
    titles = {
        "small-baseline": "0.5B / v1",
        "medium-candidate": "1.5B / v1",
        "prompt-variant": "1.5B / v2",
    }
    for row in summary:
        row["configuration"] = titles[row["entry"]]
        row["exact_rate"] = row["exact_call"] / row["total"]
    mismatch = sum(row["success_with_wrong_values"] for row in summary)
    sources = [
        {
            "id": "baseline",
            "label": "Actual local model baseline",
            "path": source_path,
            "query": {
                "description": "Fresh model calls; paired environment replays. Source SHA-256: "
                + source_hash,
                "tables_used": ["observations"],
                "engine": "SQLite (in-memory)",
                "language": "sql",
                "sql": SQL,
                "metric_definitions": {
                    "exact_call": "Selected Tool and all explicit argument values equal the private expected contract; all generation trials remain in the denominator."
                },
            },
        },
        {
            "id": "audit",
            "label": "Executed independent reconciliation",
            "path": audit_path,
            "query": {
                "engine": "SQLite (in-memory)",
                "language": "sql",
                "tables_used": ["faults"],
                "description": "Mode totals from independently checked paired traces.",
                "sql": (
                    "SELECT mode, COUNT(*) AS total, SUM(success) AS successes, "
                    "SUM(passed) AS fixture_passed, SUM(not_exercised) AS not_exercised, "
                    "SUM(handlers) AS handlers, SUM(injected) AS injected "
                    "FROM faults GROUP BY mode ORDER BY mode"
                ),
            },
        },
        {
            "id": "cases",
            "label": "Local diagnostic case pack",
            "path": "reference_workload/diagnostics/tool-fault-baseline-v1.json",
        },
    ]
    blocks = []

    def prose(id, heading, body, source=None):
        block = {"id": id, "type": "markdown", "body": heading + "\n\n" + body}
        if source:
            block["sourceId"] = source
        blocks.append(block)

    title = "Model Atlas Tool Fault Baseline"
    prose("title", "# " + title, "")
    prose(
        "summary",
        "## 실행 성공과 요청값 정확도는 다릅니다",
        f"실제 모델 추론 {total}건에서 Tool과 요청 인자가 모두 정확한 응답은 **{exact}/{total}건**입니다. 정상 모의 Tool 실행 성공은 {success}/{total}건이며, 그중 {mismatch}건은 요청값 정확도 조건을 만족하지 않았습니다. 이번 결과는 새 진단 기준선이며 기존 실험 대비 향상률이 아닙니다.",
        "baseline",
    )
    prose(
        "scope",
        "## 명시한 값을 보존하는 좁은 과제를 측정했습니다",
        "한국어 업무 요청 12개에 대해 Tool 6종을 각각 2개 사례로 다뤘습니다. 기존 3개 구성에서 2회씩 실행해 구성별 분모는 24건입니다. 선택 정확도는 기대 Tool 일치, 스키마 유효는 공개 인자 형식 충족, 실행 허용은 검증기 통과, 값 정확도는 요청에 명시된 인자 사전의 완전 일치입니다. 값의 의미적 동등성을 채점한 것이 아닙니다.",
        "baseline",
    )
    prose(
        "findings",
        "## 모델·프롬프트별 기준선을 고정했습니다",
        "아래 막대는 Tool과 요청값이 모두 맞은 비율입니다. 0.5B/v1은 13/24, 1.5B/v1은 16/24, 1.5B/v2는 14/24건입니다. 1.5B/v1은 Tool 선택은 모두 맞았지만 실행 성공 중 8건에서 요청값을 잘못 전달했습니다. 0.5B/v1과 1.5B/v2에는 각각 9건과 4건의 선택 오류도 있습니다. 표의 단계별 지표를 함께 봐야 합니다. 표본이 작고 케이스가 독립 검토되지 않았으므로 모델의 일반적 우열로 해석하지 않습니다.",
        "baseline",
    )
    blocks.append(
        {"id": "exact_chart_block", "type": "chart", "chartId": "exact_chart"}
    )
    blocks.append(
        {"id": "entry_table_block", "type": "table", "tableId": "entry_table"}
    )
    prose(
        "faults",
        "## 장애 환경은 동일한 응답을 재사용했습니다",
        "모델을 환경별로 다시 호출하지 않고 한 응답을 세 환경에서 재생했습니다. 따라서 실행 추적 216건은 독립 모델 응답 216건이 아닙니다. 영구 실패에서 검사를 통과했다는 것은 재시도 없이 중단했다는 뜻이며, Tool 실행 성공이 아닙니다. 재시도는 모델이 아니라 실행기가 결정합니다.",
        "baseline",
    )
    blocks.append({"id": "mode_table_block", "type": "table", "tableId": "mode_table"})
    prose(
        "method",
        "## 정답과 장애 설정은 모델 입력에서 분리했습니다",
        "기존 v21 어댑터, 기본 Tool 프롬프트, temperature 0, max_tokens 256을 사용했습니다. 시행 seed는 42와 43입니다. 공개 요청·Tool 스키마·고정 문서 목록만 모델에 전달하고 실제 HTTP 요청 본문을 저장했습니다. 정답은 생성 후 평가에만 사용했습니다. 모드별로 동일한 인자를 유지했으며, 잘못된 호출은 장애 주입 전 차단했습니다. 문서 ID 목록은 승인된 1.0.4 corpus에서 구성했습니다.",
        "baseline",
    )
    prose(
        "validation",
        "## 저장 원본에서 독립적으로 재집계했습니다",
        "실행 노트북에서 관측 중복·누락, 요청 및 구현 해시, 기록 파일 일치, 인자 동일성, handler 호출 수를 확인했습니다. SQLite로 원본 응답의 선택·값 정확도를 다시 계산해 실행기 요약과 대조했습니다. 결과 파일은 진단용이며 데이터베이스와 공식 Gate를 변경하지 않았습니다.",
        "audit",
    )
    prose(
        "limits",
        "## 실제 업무 성공과 일반화는 아직 검증하지 않았습니다",
        "직접 작성한 명시적 값 전달 요청이므로 자연스러운 자유 질의보다 좁은 과제입니다. Tool은 로컬 모의 구현이며 실제 문서 내용·접근 권한·외부 서비스의 부분 성공을 검증하지 않습니다. 두 번의 temperature 0 시행은 통계적으로 독립적인 충분한 표본이 아닙니다. 문서·스키마·케이스가 다른 과거 성공률과 비교할 수 없습니다. matrix의 context_length는 선언값으로, 실제 요청에서 강제한 설정이 아닙니다. 사람의 소스 검토나 실제 출력 검토를 대체하지 않습니다.",
    )
    prose(
        "next",
        "## 다음 후보는 명시한 인자값 보존에 집중해야 합니다",
        "1. 이 기준선과 실패 원문을 보존합니다.\n2. Tool 선택 이후 선택된 스키마만으로 인자를 생성하는 별도 후보를 시험합니다. 값을 자동 채우거나 정답으로 보정하지 않습니다.\n3. 같은 케이스의 전후 결과뿐 아니라 새로운 요청과 목록 순서 변화에서도 회귀를 검사합니다.\n4. 독립 검토와 실제 서비스 검증 전에는 공식 Gate로 승격하지 않습니다.",
    )
    prose(
        "questions",
        "## 더 확인할 질문",
        "- 자유로운 한국어 요청에서도 정확한 Tool과 인자를 생성하는가?\n- 인자 생성 단계를 분리할 때 추가 지연과 토큰 비용은 어느 정도인가?\n- 실제 문서 내용과 접근 권한을 연결해도 같은 결과가 유지되는가?",
    )

    def table(id, title, dataset, fields, sort):
        return {
            "id": id,
            "title": title,
            "dataset": dataset,
            "sourceId": "baseline" if dataset == "summary" else "audit",
            "density": "spacious",
            "defaultSort": {"field": sort, "direction": "asc"},
            "columns": [
                {
                    "field": field,
                    "label": label,
                    **({"type": "text"} if field == sort else {"format": "number"}),
                }
                for field, label in fields
            ],
        }

    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "generatedAt": report["completed_at"],
            "sources": sources,
            "blocks": blocks,
            "charts": [
                {
                    "id": "exact_chart",
                    "title": "Tool 및 명시적 인자 정확도",
                    "type": "bar",
                    "dataset": "summary",
                    "sourceId": "baseline",
                    "valueFormat": "percent",
                    "encodings": {
                        "x": {
                            "field": "configuration",
                            "type": "nominal",
                            "label": "구성",
                        },
                        "y": {
                            "field": "exact_rate",
                            "type": "quantitative",
                            "label": "정확도",
                        },
                    },
                }
            ],
            "tables": [
                table(
                    "entry_table",
                    "구성별 검증 단계",
                    "summary",
                    [
                        ("configuration", "구성"),
                        ("total", "전체"),
                        ("selected", "선택"),
                        ("schema_valid", "스키마"),
                        ("eligible", "허용"),
                        ("tool_success", "실행"),
                        ("exact_call", "선택+값"),
                    ],
                    "configuration",
                ),
                table(
                    "mode_table",
                    "환경별 동일 응답 재생",
                    "modes",
                    [
                        ("mode", "환경"),
                        ("total", "전체"),
                        ("successes", "Tool 성공"),
                        ("fixture_passed", "환경 검사 통과"),
                        ("not_exercised", "미실행"),
                        ("handlers", "Handler 호출"),
                    ],
                    "mode",
                ),
            ],
        },
        "snapshot": {
            "version": 1,
            "status": "ready",
            "generatedAt": report["completed_at"],
            "datasets": {"summary": summary, "modes": audit["mode_summary"]},
        },
        "sources": sources,
    }
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "notebook": str(notebook_path),
                "artifact": str(artifact_path),
                "audit": audit,
            }
        )
    )


if __name__ == "__main__":
    main()
