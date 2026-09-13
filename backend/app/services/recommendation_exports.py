from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.recommendations import RecommendationCandidate, RecommendationReport


def _text(value: object | None) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _candidate_table(candidates: list[RecommendationCandidate]) -> list[str]:
    lines = [
        (
            "| Rank | Artifact | Final score | Raw score | Confidence | Quality | "
            "Latency ms | Tokens/sec | VRAM MB | Coverage | Pareto |"
        ),
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for candidate in candidates:
        lines.append(
            "| "
            f"{candidate.rank} | "
            f"{_text(candidate.artifact_name)} | "
            f"{_number(candidate.recommendation_score)} | "
            f"{_number(candidate.raw_recommendation_score)} | "
            f"{_percent(candidate.evidence_confidence)} | "
            f"{_number(candidate.average_quality_score)} | "
            f"{_number(candidate.average_end_to_end_latency_ms, 0)} | "
            f"{_number(candidate.average_tokens_per_second, 1)} | "
            f"{_number(candidate.average_vram_usage_mb, 0)} | "
            f"{candidate.benchmark_coverage_count} | "
            f"{_yes_no(candidate.pareto_optimal)} |"
        )
    if not candidates:
        lines.append(
            "| n/a | No eligible candidates | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | n/a |"
        )
    return lines


def _excluded_table(report: RecommendationReport) -> list[str]:
    lines = [
        "| Artifact | Reason | Message |",
        "| --- | --- | --- |",
    ]
    for issue in report.excluded:
        lines.append(
            f"| {_text(issue.artifact_name)} | {_text(issue.reason_code)} | "
            f"{_text(issue.message)} |"
        )
    if not report.excluded:
        lines.append("| n/a | n/a | No artifacts were excluded. |")
    return lines


def render_recommendation_report_markdown(
    report: RecommendationReport,
    *,
    title: str = "Model Atlas Recommendation Report",
) -> str:
    request = report.request
    weights = request.weights
    recommended = report.recommended_candidate
    lines = [
        f"# {_text(title)}",
        "",
        "## Decision Summary",
        "",
        report.decision_summary,
        "",
        "## Request",
        "",
        f"- Hardware: {_text(report.hardware_profile_name)}",
        f"- Benchmark task: {_text(report.benchmark_task_name or 'All benchmark evidence')}",
        f"- Top K: {request.top_k}",
        f"- Min context length: {_text(request.min_context_length)}",
        f"- Require tool calling: {_yes_no(request.require_tool_calling)}",
        f"- Require structured output: {_yes_no(request.require_structured_output)}",
        f"- Commercial use required: {_yes_no(request.commercial_use_required)}",
        "",
        "## Scoring Weights",
        "",
        "| Quality | Latency | Throughput | VRAM efficiency |",
        "| ---: | ---: | ---: | ---: |",
        (
            f"| {_number(weights.quality)} | {_number(weights.latency)} | "
            f"{_number(weights.throughput)} | {_number(weights.vram_efficiency)} |"
        ),
        "",
        "## Recommended Candidate",
        "",
    ]

    if recommended is None:
        lines.append("No eligible model artifact matched the selected filters.")
    else:
        lines.extend(
            [
                f"- Artifact: {_text(recommended.artifact_name)}",
                f"- Model: {_text(recommended.model_name)}",
                f"- Provider / family: {_text(recommended.provider)} / {_text(recommended.family)}",
                f"- Final score: {_number(recommended.recommendation_score)}",
                f"- Raw score: {_number(recommended.raw_recommendation_score)}",
                f"- Evidence confidence: {_percent(recommended.evidence_confidence)}",
                f"- Benchmark coverage: {recommended.benchmark_coverage_count} run(s)",
                f"- Pareto optimal: {_yes_no(recommended.pareto_optimal)}",
            ]
        )

    lines.extend(
        [
            "",
            "## Ranked Candidates",
            "",
            *_candidate_table(report.candidates),
            "",
            "## Pareto Frontier",
            "",
            *_candidate_table(report.pareto_frontier),
            "",
            "## Excluded Artifacts",
            "",
            *_excluded_table(report),
            "",
            "## Method Notes",
            "",
            "- Scores are deterministic projections over stored benchmark evidence.",
            "- Final score equals raw weighted score multiplied by evidence confidence.",
            "- Evidence confidence is based on benchmark run coverage for the selected scope.",
            (
                "- Seeded benchmark values are synthetic demonstration data unless replaced "
                "with real runs."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _pdf_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ModelAtlasTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            spaceAfter=8,
            textColor=colors.HexColor("#202124"),
        ),
        "heading": ParagraphStyle(
            "ModelAtlasHeading",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor("#202124"),
        ),
        "body": ParagraphStyle(
            "ModelAtlasBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#202124"),
        ),
        "small": ParagraphStyle(
            "ModelAtlasSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#4b5563"),
        ),
        "right": ParagraphStyle(
            "ModelAtlasRight",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#4b5563"),
        ),
    }


def _paragraph(value: object | None, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def _pdf_table(
    rows: list[list[object]],
    *,
    col_widths: list[float] | None = None,
    repeat_rows: int = 1,
) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#202124")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _candidate_pdf_table(
    candidates: list[RecommendationCandidate],
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows: list[list[object]] = [
        [
            "Rank",
            "Artifact",
            "Final",
            "Raw",
            "Conf.",
            "Quality",
            "Latency",
            "Tok/s",
            "VRAM",
            "Runs",
            "Pareto",
        ]
    ]
    for candidate in candidates:
        rows.append(
            [
                str(candidate.rank),
                _paragraph(candidate.artifact_name, styles["small"]),
                _number(candidate.recommendation_score),
                _number(candidate.raw_recommendation_score),
                _percent(candidate.evidence_confidence),
                _number(candidate.average_quality_score),
                _number(candidate.average_end_to_end_latency_ms, 0),
                _number(candidate.average_tokens_per_second, 1),
                _number(candidate.average_vram_usage_mb, 0),
                str(candidate.benchmark_coverage_count),
                _yes_no(candidate.pareto_optimal),
            ]
        )
    if not candidates:
        rows.append(
            [
                "n/a",
                "No eligible candidates",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "0",
                "n/a",
            ]
        )
    return _pdf_table(
        rows,
        col_widths=[
            12 * mm,
            60 * mm,
            17 * mm,
            17 * mm,
            17 * mm,
            18 * mm,
            18 * mm,
            18 * mm,
            18 * mm,
            13 * mm,
            17 * mm,
        ],
    )


def _footer(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(15 * mm, 10 * mm, "Model Atlas")
    canvas.drawRightString(282 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def render_recommendation_report_pdf(
    report: RecommendationReport,
    *,
    title: str = "Model Atlas Recommendation Report",
) -> bytes:
    buffer = BytesIO()
    styles = _pdf_styles()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=title,
    )
    request = report.request
    weights = request.weights
    recommended = report.recommended_candidate
    story: list[object] = [
        _paragraph(title, styles["title"]),
        _paragraph(report.decision_summary, styles["body"]),
        Spacer(1, 6),
        _paragraph("Request", styles["heading"]),
        _pdf_table(
            [
                ["Hardware", _text(report.hardware_profile_name)],
                ["Benchmark task", _text(report.benchmark_task_name or "All benchmark evidence")],
                ["Top K", str(request.top_k)],
                ["Min context length", _text(request.min_context_length)],
                ["Require tool calling", _yes_no(request.require_tool_calling)],
                ["Require structured output", _yes_no(request.require_structured_output)],
                ["Commercial use required", _yes_no(request.commercial_use_required)],
            ],
            col_widths=[42 * mm, 140 * mm],
            repeat_rows=0,
        ),
        _paragraph("Scoring Weights", styles["heading"]),
        _pdf_table(
            [
                ["Quality", "Latency", "Throughput", "VRAM efficiency"],
                [
                    _number(weights.quality),
                    _number(weights.latency),
                    _number(weights.throughput),
                    _number(weights.vram_efficiency),
                ],
            ],
            col_widths=[35 * mm, 35 * mm, 35 * mm, 35 * mm],
        ),
        _paragraph("Recommended Candidate", styles["heading"]),
    ]

    if recommended is None:
        story.append(
            _paragraph("No eligible model artifact matched the selected filters.", styles["body"])
        )
    else:
        story.append(
            _pdf_table(
                [
                    ["Artifact", _text(recommended.artifact_name)],
                    ["Model", _text(recommended.model_name)],
                    [
                        "Provider / family",
                        f"{_text(recommended.provider)} / {_text(recommended.family)}",
                    ],
                    ["Final score", _number(recommended.recommendation_score)],
                    ["Raw score", _number(recommended.raw_recommendation_score)],
                    ["Evidence confidence", _percent(recommended.evidence_confidence)],
                    ["Benchmark coverage", f"{recommended.benchmark_coverage_count} run(s)"],
                    ["Pareto optimal", _yes_no(recommended.pareto_optimal)],
                ],
                col_widths=[42 * mm, 140 * mm],
                repeat_rows=0,
            )
        )

    story.extend(
        [
            KeepTogether(
                [
                    _paragraph("Ranked Candidates", styles["heading"]),
                    _candidate_pdf_table(report.candidates, styles),
                ]
            ),
            KeepTogether(
                [
                    _paragraph("Pareto Frontier", styles["heading"]),
                    _candidate_pdf_table(report.pareto_frontier, styles),
                ]
            ),
            _paragraph("Excluded Artifacts", styles["heading"]),
        ]
    )
    excluded_rows: list[list[object]] = [["Artifact", "Reason", "Message"]]
    for issue in report.excluded:
        excluded_rows.append(
            [
                _paragraph(issue.artifact_name, styles["small"]),
                _text(issue.reason_code),
                _paragraph(issue.message, styles["small"]),
            ]
        )
    if not report.excluded:
        excluded_rows.append(["n/a", "n/a", "No artifacts were excluded."])
    story.extend(
        [
            _pdf_table(excluded_rows, col_widths=[60 * mm, 38 * mm, 140 * mm]),
            _paragraph("Method Notes", styles["heading"]),
            _paragraph(
                "Scores are deterministic projections over stored benchmark evidence. "
                "Final score equals raw weighted score multiplied by evidence confidence. "
                "Seeded benchmark values are synthetic demonstration data unless replaced "
                "with real runs.",
                styles["body"],
            ),
        ]
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
