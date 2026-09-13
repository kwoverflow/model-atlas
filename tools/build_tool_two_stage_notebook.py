"""Build and execute a compact, source-checked engineering experiment notebook."""

from pathlib import Path

import nbformat
from nbclient import NotebookClient

from audit_tool_two_stage import audit, sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "artifacts/reference-workload/tool-two-stage-diagnostic-v1.json"
DESTINATION = ROOT / "docs/reports/2026-09-09_tool_two_stage"


def main():
    result = audit(ROOT, ROOT / SOURCE)
    DESTINATION.mkdir(parents=True, exist_ok=True)
    source_hash = sha(ROOT / SOURCE)
    auditor_hash = sha(ROOT / "tools/audit_tool_two_stage.py")
    frozen = [row for row in result["summary"] if row["cohort"] == "frozen"]
    lines = [
        f"- {row['entry']}: historical {row['historical_exact']}/{row['n']}, "
        f"this run stage1 {row['stage1_exact']}/{row['n']}, "
        f"two-stage final {row['exact']}/{row['n']}."
        for row in frozen
    ]
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                "# Selected Tool Argument Generation\n\n## tl;dr\n\n"
                + "\n".join(lines)
                + "\n\nLocal diagnostic evidence only. Defaults and the official Gate are unchanged."
            ),
            nbformat.v4.new_markdown_cell(
                "## Context & Methods\n\n"
                "Question: does a second, selected-schema-only model call preserve explicit values? "
                "Stage1 retains the legacy full-call prompt, but its arguments are discarded. "
                "Stage2 returns an argument object; the final Tool envelope is assembled without value repair.\n\n"
                "### Key Assumptions\n\n"
                "Frozen cohort: 12 cases x 3 entries x 2 trials. Historical baseline was measured earlier. "
                "Challenge: 6 newly authored cases x 3 entries x 2 Tool orders x 2 variants, seed 42. "
                "AB/BA order alternates. These are not independently reviewed or statistically independent samples. "
                "Latency is local wall time, not an SLA; cache and host load are uncontrolled. "
                "Fault traces replay one output three times and use deterministic local fixtures."
            ),
            nbformat.v4.new_markdown_cell(
                "## Data\n\n### 1. Verify Sources\n\n"
                f"Source: `{SOURCE}`. SHA-256: `{source_hash}`. "
                "The audit reads only local files, makes no model calls and performs no application DB writes. "
                "Source hashes, journal equality, trial completeness, request parity, usage totals, "
                "unchanged arguments and raw-output exact matches are checked independently of the application scorer."
            ),
            nbformat.v4.new_code_cell(
                "import hashlib, json, sys\nfrom pathlib import Path\n"
                "root = Path.cwd()\n"
                "while not (root / 'reference_workload/runtime_matrix.json').exists():\n"
                "    assert root != root.parent, 'repository root not found'\n"
                "    root = root.parent\n"
                f"source = root / {SOURCE!r}\n"
                f"assert hashlib.sha256(source.read_bytes()).hexdigest() == {source_hash!r}\n"
                "auditor = root / 'tools/audit_tool_two_stage.py'\n"
                f"assert hashlib.sha256(auditor.read_bytes()).hexdigest() == {auditor_hash!r}\n"
                "sys.path.insert(0, str(root / 'tools'))\n"
                "from audit_tool_two_stage import audit\n"
                "result = audit(root, source)\n"
                "print({key: result[key] for key in ('assessment', 'observations', 'http_calls', 'trace_count')})"
            ),
            nbformat.v4.new_markdown_cell(
                "## Results\n\n### 2. Compare Exact Calls and Costs\n\n"
                "Exact means selected Tool and the entire argument object match explicitly requested values. "
                "All planned observations remain in the denominator. Token totals use complete HTTP usage only."
            ),
            nbformat.v4.new_code_cell(
                "from IPython.display import Markdown, display\n"
                "headers = ['entry', 'cohort', 'variant', 'n', 'stage1_exact', 'exact', "
                "'prompt_tokens', 'completion_tokens', 'median_latency_ms']\n"
                "table = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']\n"
                "for row in result['summary']:\n"
                "    table.append('| ' + ' | '.join(str(round(row[key], 1)) if isinstance(row[key], float) "
                "else str(row[key]) for key in headers) + ' |')\n"
                "display(Markdown('\\n'.join(table)))"
            ),
            nbformat.v4.new_markdown_cell(
                "### 3. Check Selection Drift and Regressions\n\n"
                "Within-candidate transitions compare that run's first response and final response. "
                "This avoids attributing repeated-run selection changes to stage2. "
                "Order-change counts have 18 case-entry pairs per variant."
            ),
            nbformat.v4.new_code_cell(
                "print(json.dumps({key: result[key] for key in (\n"
                "    'within_candidate_exact_transitions', 'frozen_stage1_selection_changed_vs_historical',\n"
                "    'challenge_pair_stage1_selection_changes', 'challenge_order_exact_changes',\n"
                "    'finish_reasons')}, indent=2))\n"
                "print('Non-exact observations:', len(result['failures']))"
            ),
            nbformat.v4.new_markdown_cell(
                "## Takeaways\n\n"
                "Retain this as an opt-in diagnostic candidate, not a default replacement. "
                "Use the per-entry results, regressions, and extra token cost together. "
                "Fresh independent requests, real Tool content/authorization validation and human review "
                "remain necessary before promotion. Native-output schema validity must not be conflated "
                "with the candidate's assembled-envelope validity."
            ),
            nbformat.v4.new_code_cell(
                "target = root / 'docs/reports/2026-09-09_tool_two_stage/audit.json'\n"
                "target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')\n"
                "print('Audit saved:', target.relative_to(root))"
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
    path = DESTINATION / "reproduce.ipynb"
    NotebookClient(
        notebook, timeout=120, resources={"metadata": {"path": str(ROOT)}}
    ).execute()
    nbformat.write(notebook, path)
    print(path)


if __name__ == "__main__":
    main()
