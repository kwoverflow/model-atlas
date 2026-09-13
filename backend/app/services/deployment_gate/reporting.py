from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import GateEvaluation


def _text(value: object | None) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value: object | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_gate_report_markdown(gate: GateEvaluation) -> str:
    scorecard = gate.scorecard_json
    metrics: dict[str, dict[str, Any]] = scorecard.get("metrics", {})
    snapshot = gate.evidence_snapshot_json
    trust = scorecard.get("evidence_trust") or snapshot.get("evidence_trust") or {}
    explanation = scorecard.get("decision_explanation") or {}
    lines = [
        "# Model Atlas Deployment Gate Report",
        "",
        "## Status Summary",
        "",
        f"- Gate verdict: **{gate.verdict}**",
        f"- Evidence trust: **{_text(trust.get('trust_status'))}**",
        f"- Production readiness: **{_text(trust.get('production_readiness'))}**",
        "",
        gate.decision_summary,
        "",
        "## Why This Decision Was Made",
        "",
        _text(explanation.get("summary") or gate.decision_summary),
        "",
        "### Blocking Issues",
        "",
    ]
    blockers = explanation.get("blockers") or []
    lines.extend(
        [f"- **{_text(item.get('title'))}:** {_text(item.get('detail'))}" for item in blockers]
        or ["- none"]
    )
    lines.extend(["", "### Recommended Next Actions", ""])
    actions = explanation.get("next_actions") or []
    lines.extend(
        [f"- **{_text(item.get('title'))}:** {_text(item.get('description'))}" for item in actions]
        or [f"- {_text(action)}" for action in scorecard.get("next_actions", [])]
        or ["- none"]
    )
    lines.extend(
        [
            "",
            "## Evidence Trust",
            "",
            f"- Source distribution: `{_text(trust.get('source_distribution'))}`",
            f"- Score distribution: `{_text(trust.get('score_distribution'))}`",
            f"- Applied label coverage: {_number(trust.get('applied_judge_label_rate'))}",
            (
                "- Critical review coverage: "
                f"{_number(trust.get('critical_review_coverage_rate'))}"
            ),
            f"- Production-captured results: {_number(trust.get('production_captured_count'))}",
            "",
            "### Limitations",
            "",
            *([f"- {_text(item)}" for item in trust.get("limitations", [])] or ["- none"]),
            "",
            "## Critical Case Outcomes",
            "",
        ]
    )
    critical_cases = scorecard.get("critical_case_outcomes", [])
    if critical_cases:
        lines.extend(["| Case | Status | Quality | Error |", "| --- | --- | ---: | --- |"])
        for outcome in critical_cases:
            lines.append(
                f"| {_text(outcome.get('external_case_id'))} | {_text(outcome.get('status'))} | "
                f"{_number(outcome.get('quality_score'))} | {_text(outcome.get('error_type'))} |"
            )
    else:
        lines.append("No critical cases were evaluated.")
    lines.extend(
        [
            "",
            "## Policy Rule Results",
            "",
            "| Rule | Metric | Status | Severity | Value |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for result in scorecard.get("rule_results", []):
        lines.append(
            f"| {_text(result.get('rule_name'))} | {_text(result.get('metric_key'))} | "
            f"{_text(result.get('status'))} | {_text(result.get('severity'))} | "
            f"{_number(result.get('metric_value'))} |"
        )
    lines.extend(
        [
            "",
            "## Metric Scorecard",
            "",
            "| Metric | Value | Sample size |",
            "| --- | ---: | ---: |",
        ]
    )
    for key, metric in sorted(metrics.items()):
        lines.append(
            f"| {_text(key)} | {_number(metric.get('value'))} | "
            f"{_number(metric.get('sample_size'))} |"
        )
    lines.extend(["", "## Baseline Comparison", ""])
    baseline = scorecard.get("baseline_comparison", {})
    lines.extend(
        [
            f"- Baseline gate evaluation: `{_text(baseline.get('baseline_gate_evaluation_id'))}`",
            (
                "- Quality regression vs baseline: "
                f"{_number(baseline.get('quality_regression_vs_baseline'))}"
            ),
            (
                "- Latency regression vs baseline: "
                f"{_number(baseline.get('latency_regression_vs_baseline'))}"
            ),
        ]
    )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Snapshot schema: `{_text(snapshot.get('schema_version'))}`",
            f"- Evidence trust version: `{_text(snapshot.get('evidence_trust_version'))}`",
            f"- Policy engine version: `{_text(snapshot.get('policy_engine_version'))}`",
            f"- Metric calculation version: `{_text(snapshot.get('metric_calculation_version'))}`",
            f"- Adapter versions: `{_text(snapshot.get('adapter_versions'))}`",
            f"- Scorer versions: `{_text(snapshot.get('scorer_versions'))}`",
            f"- Deployment configuration ID: `{gate.deployment_configuration_id}`",
            f"- Configuration hash: `{_text(snapshot.get('configuration_hash'))}`",
            f"- Evaluation suite ID: `{gate.evaluation_suite_id}`",
            f"- Suite hash: `{_text(snapshot.get('suite_hash'))}`",
            f"- Acceptance policy ID: `{gate.acceptance_policy_id}`",
            f"- Policy hash: `{_text(snapshot.get('policy_hash'))}`",
            f"- Benchmark run IDs: `{', '.join(snapshot.get('benchmark_run_ids', []))}`",
            f"- Result count: {_number(snapshot.get('result_count'))}",
        ]
    )
    if scorecard.get("synthetic_data_warning"):
        lines.extend(["", "## Synthetic Data Warning", "", scorecard["synthetic_data_warning"]])
    lines.append("")
    return "\n".join(lines)


def _paragraph(value: object | None, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def _table(rows: list[list[object]]) -> Table:
    table = Table(rows, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def render_gate_report_pdf(gate: GateEvaluation) -> bytes:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "GateTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#202124"),
    )
    body_style = ParagraphStyle(
        "GateBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#202124"),
    )
    heading_style = ParagraphStyle(
        "GateHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=8,
        spaceAfter=5,
    )
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Model Atlas Deployment Gate Report",
    )
    scorecard = gate.scorecard_json
    trust = scorecard.get("evidence_trust") or gate.evidence_snapshot_json.get(
        "evidence_trust", {}
    )
    metrics: dict[str, dict[str, Any]] = scorecard.get("metrics", {})
    metric_rows = [["Metric", "Value", "Sample size"]]
    for key, metric in sorted(metrics.items()):
        metric_rows.append(
            [_text(key), _number(metric.get("value")), _number(metric.get("sample_size"))]
        )
    rule_rows = [["Rule", "Metric", "Status", "Severity", "Value"]]
    for result in scorecard.get("rule_results", []):
        rule_rows.append(
            [
                _text(result.get("rule_name")),
                _text(result.get("metric_key")),
                _text(result.get("status")),
                _text(result.get("severity")),
                _number(result.get("metric_value")),
            ]
        )
    story: list[object] = [
        _paragraph("Model Atlas Deployment Gate Report", title_style),
        _paragraph(f"Verdict: {gate.verdict}", heading_style),
        _paragraph(f"Evidence trust: {_text(trust.get('trust_status'))}", body_style),
        _paragraph(
            f"Production readiness: {_text(trust.get('production_readiness'))}",
            body_style,
        ),
        _paragraph(gate.decision_summary, body_style),
        Spacer(1, 6),
        _paragraph("Metric Scorecard", heading_style),
        _table(metric_rows),
        _paragraph("Rule Results", heading_style),
        _table(rule_rows),
        _paragraph("Next Actions", heading_style),
    ]
    for action in scorecard.get("next_actions", []):
        story.append(_paragraph(f"- {action}", body_style))
    if scorecard.get("synthetic_data_warning"):
        story.extend(
            [
                _paragraph("Synthetic Data Warning", heading_style),
                _paragraph(scorecard["synthetic_data_warning"], body_style),
            ]
        )
    doc.build(story)
    return buffer.getvalue()
