import {
  BookOpenCheck,
  ClipboardCheck,
  Database,
  Download,
  FileJson,
  Layers3,
  ListChecks
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { ConfigurationCharts } from "@/features/reference-workload/ConfigurationCharts";
import { ConfigurationComparison } from "@/features/reference-workload/ConfigurationComparison";
import { FailureReviewQueue } from "@/features/reference-workload/FailureReviewQueue";
import { GateEvidenceSummary } from "@/features/reference-workload/GateEvidenceSummary";
import { ReferenceStatusStrip } from "@/features/reference-workload/ReferenceStatusStrip";
import { ReproductionPanel } from "@/features/reference-workload/ReproductionPanel";
import { api } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";

export const dynamic = "force-dynamic";

export default async function ReferenceWorkloadPage() {
  const data = await api.referenceWorkloadOverview();

  return (
    <>
      <header className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-4xl">
            <div className="flex items-center gap-2 text-sm font-medium text-teal">
              <BookOpenCheck size={17} aria-hidden="true" />
              Reference Workload
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-ink">{data.workload.name}</h1>
            <p className="mt-2 text-sm leading-6 text-neutral-600">{data.workload.description}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">v{data.workload.version}</Badge>
            <Badge tone={data.portfolio_completion.status === "ready" ? "teal" : "amber"}>
              Portfolio {data.portfolio_completion.status}
            </Badge>
            <a
              href={`${API_BASE_URL}/reference-workload/report`}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium text-ink hover:bg-neutral-50"
              title="Download the reference workload report as JSON"
            >
              <FileJson size={16} aria-hidden="true" /> JSON
            </a>
            <a
              href={`${API_BASE_URL}/reference-workload/report.md`}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white hover:bg-neutral-800"
              title="Download the reference workload report as Markdown"
            >
              <Download size={16} aria-hidden="true" /> Report
            </a>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-neutral-500">
          <span>Domain: {data.workload.domain}</span>
          <span>Language: {data.workload.primary_language.toUpperCase()}</span>
          <span>Local only: {data.workload.local_only_required ? "Required" : "Optional"}</span>
          <span>Generated: {new Date(data.generated_at).toLocaleString()}</span>
        </div>
      </header>

      <ReferenceStatusStrip data={data} />

      <section className="border-t border-line pt-6" aria-labelledby="workload-coverage">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="workload-coverage" className="text-base font-semibold text-ink">Workload and source coverage</h2>
            <p className="mt-1 text-sm text-neutral-600">Approved source cases remain separate from model-output review evidence.</p>
          </div>
          <div className="text-xs text-neutral-500">Corpus {data.corpus.corpus_version} · {data.corpus.chunk_count} chunks · {data.manifest.file_count} source files</div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryCard label="Approved source cases" value={data.case_coverage.approved_case_count} detail={`${(data.case_coverage.source_review_coverage_rate * 100).toFixed(0)}% source review coverage`} tone="teal" />
          <SummaryCard label="Approved critical cases" value={data.case_coverage.approved_critical_case_count} detail={`${data.case_coverage.critical_category_counts ? Object.keys(data.case_coverage.critical_category_counts).length : 0} critical categories`} tone="rose" />
          <SummaryCard label="Actual runtime results" value={data.actual_runtime_result_count} detail={`${data.configuration_matrix.filter((item) => item.status === "completed").length} completed configurations`} tone="violet" />
          <SummaryCard label="Reviewed model outputs" value={data.review_coverage.human_reviewed_count + data.review_coverage.applied_judge_label_count} detail={`${data.review_coverage.remaining_to_target} remaining to target`} tone="amber" />
        </div>
      </section>

      <section className="border-t border-line pt-6" aria-labelledby="runtime-comparison">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="runtime-comparison" className="text-base font-semibold text-ink">Actual execution comparison</h2>
            <p className="mt-1 text-sm text-neutral-600">Metrics are computed only from the latest stored actual-runtime run for each matrix entry.</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-neutral-500"><Layers3 size={16} aria-hidden="true" /> {data.metric_comparison.length} comparable configurations</div>
        </div>
        <ConfigurationCharts rows={data.metric_comparison} />
        <div className="mt-6"><ConfigurationComparison rows={data.configuration_matrix} /></div>
      </section>

      <section className="border-t border-line pt-6" aria-labelledby="critical-failures">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="critical-failures" className="text-base font-semibold text-ink">Critical failures and review</h2>
            <p className="mt-1 text-sm text-neutral-600">Failure-first queue with direct paths to the run, Judge review, and Gate evidence.</p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/reference-workload/review-plan" className="inline-flex items-center gap-2 text-sm font-medium text-teal hover:underline"><ListChecks size={16} aria-hidden="true" /> Open prioritized plan</Link>
            <Link href="/judge-labels" className="inline-flex items-center gap-2 text-sm font-medium text-teal hover:underline"><ClipboardCheck size={16} aria-hidden="true" /> Open full review queue</Link>
          </div>
        </div>
        <FailureReviewQueue failures={data.critical_failures} />
        {data.critical_failure_count > 12 ? <p className="mt-3 text-xs text-neutral-500">Showing 12 of {data.critical_failure_count} critical failures.</p> : null}
      </section>

      <section className="border-t border-line pt-6" aria-labelledby="gate-evidence">
        <div className="mb-4">
          <h2 id="gate-evidence" className="text-base font-semibold text-ink">Gate, evidence trust, and production readiness</h2>
          <p className="mt-1 text-sm text-neutral-600">Policy verdict, evidence provenance, and production authorization are reported as separate states.</p>
        </div>
        <GateEvidenceSummary data={data} />
      </section>

      <section className="border-t border-line pt-6" aria-labelledby="reproduce">
        <div className="mb-4 flex items-center gap-2">
          <Database size={18} className="text-neutral-500" aria-hidden="true" />
          <h2 id="reproduce" className="text-base font-semibold text-ink">Reproduce and continue</h2>
        </div>
        <ReproductionPanel data={data} />
      </section>

      <details className="border-y border-line py-4">
        <summary className="cursor-pointer text-sm font-semibold text-ink">Advanced details and limitations</summary>
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold uppercase text-neutral-500">Limitations</h3>
            <ul className="mt-3 grid gap-2 text-sm leading-6 text-neutral-600">
              {data.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase text-neutral-500">Source paths</h3>
            <ul className="mt-3 grid gap-2 font-mono text-xs leading-5 text-neutral-600">
              {data.manifest.source_paths.map((path) => <li key={path} className="break-all">{path}</li>)}
            </ul>
          </div>
        </div>
      </details>
    </>
  );
}
