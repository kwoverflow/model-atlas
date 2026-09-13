import { CheckCircle2, CircleX, FileText, Quote } from "lucide-react";

import { Badge } from "@/components/Badge";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type { RagEvaluationTraceRecord } from "@/types/api";

type RagEvaluationTracePanelProps = {
  traces: RagEvaluationTraceRecord[];
};

export function RagEvaluationTracePanel({ traces }: RagEvaluationTracePanelProps) {
  return (
    <div className="divide-y divide-line">
      {traces.map((record) => {
        const trace = record.trace;
        const retrieval = trace.retrieval;
        const selection = retrieval.evidence_selection;
        const acceptableGroups = retrieval.acceptable_evidence_groups?.length
          ? retrieval.acceptable_evidence_groups
          : [retrieval.expected_relevant_chunk_ids];
        const relevantIds = new Set(acceptableGroups.flat());
        const selectedIds = new Set(selection?.selected_chunk_ids ?? []);
        const matchedAlternative = (retrieval.satisfied_selection_group_index ?? 0) > 0;
        return (
          <section key={record.benchmark_result_id} className="px-5 py-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-semibold uppercase text-neutral-500">
                  {record.sample_id} {record.criticality ? `/ ${record.criticality}` : ""}
                </div>
                <h3 className="mt-1 text-base font-semibold text-ink">
                  {record.case_title ?? retrieval.query}
                </h3>
                <p className="mt-2 max-w-4xl text-sm text-neutral-600">{retrieval.query}</p>
              </div>
              <Badge tone={statusTone(trace.status)}>{statusLabel(trace.status)}</Badge>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <Metric label="Retrieval recall" value={trace.retrieval.retrieval_recall} />
              <Metric label="Citation precision" value={trace.citation_precision} />
              <Metric label="Citation recall" value={trace.citation_recall} />
              <Metric label="Groundedness" value={trace.groundedness_score} />
              <Metric label="Unsupported claims" value={trace.unsupported_claim_rate} inverse />
            </div>

            {trace.output_error || retrieval.errors.length ? (
              <div className="mt-4 border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm text-neutral-700">
                {[trace.output_error, ...retrieval.errors].filter(Boolean).join(" ")}
              </div>
            ) : null}

            {trace.semantic_contract_declared ? (
              <div className="mt-4 border-l-4 border-line px-4 py-3">
                <div className="flex flex-wrap items-center gap-2 text-sm text-neutral-700">
                  <Badge tone={trace.semantic_contract_satisfied ? "teal" : "rose"}>
                    Semantic contract {trace.semantic_contract_satisfied ? "passed" : "failed"}
                  </Badge>
                  <span>{trace.semantic_contract_version ?? "rag-semantic-contract-v1"}</span>
                  <span>
                    Refusal {trace.must_refuse ? "required" : "not required"}: {trace.refusal_detected ? "detected" : "not detected"}
                  </span>
                  <span>Required facts: {percent(trace.required_fact_coverage)}</span>
                  <span>Forbidden violations: {trace.forbidden_claim_violation_count}</span>
                  {(trace.satisfied_required_fact_group_index ?? 0) > 0 ? (
                    <Badge tone="teal">Alternative fact group matched</Badge>
                  ) : null}
                  {trace.answer_contract_applied ? (
                    <Badge tone={trace.answer_contract_satisfied ? "teal" : "rose"}>
                      Bounded answer {trace.answer_contract_satisfied ? "matched" : "mismatched"}
                    </Badge>
                  ) : null}
                </div>
                {trace.required_fact_results.some((result) => !result.matched) ? (
                  <p className="mt-2 text-sm text-rose">
                    Missing: {trace.required_fact_results.filter((result) => !result.matched).map((result) => result.expectation).join(", ")}
                  </p>
                ) : null}
              </div>
            ) : null}

            {selection?.selected_count ? (
              <div className="mt-4 border-l-4 border-teal px-4 py-3 text-sm text-neutral-700">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    tone={selection.abstain_recommended ? "amber" : "teal"}
                  >
                    Evidence {selection.confidence}
                  </Badge>
                  <span>{selection.selector_version}</span>
                  <span>Selection recall: {percent(retrieval.evidence_selection_recall)}</span>
                  <span>
                    Evidence contract: {retrieval.evidence_contract_version ?? "rag-evidence-contract-v1"}
                  </span>
                  {matchedAlternative ? <Badge tone="teal">Alternative group matched</Badge> : null}
                </div>
                <p className="mt-2 leading-6">
                  {selection.selections[0]?.claim}
                </p>
              </div>
            ) : null}

            <div className="mt-5 overflow-x-auto rounded-md border border-line">
              <table className="w-full min-w-[780px] text-left text-sm">
                <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
                  <tr>
                    <th className="px-4 py-3">Rank</th>
                    <th className="px-4 py-3">Chunk</th>
                    <th className="px-4 py-3">Document</th>
                    <th className="px-4 py-3">Score</th>
                    <th className="px-4 py-3">Selected</th>
                    <th className="px-4 py-3">Accepted</th>
                    <th className="px-4 py-3">Cited</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {retrieval.retrieved_chunks.map((chunk) => (
                    <tr key={chunk.chunk_id}>
                      <td className="px-4 py-3 font-medium text-ink">{chunk.rank}</td>
                      <td className="px-4 py-3">
                        <div className="font-mono text-xs text-ink">{chunk.chunk_id}</div>
                        <div className="mt-1 max-w-md text-xs text-neutral-500">{chunk.title}</div>
                      </td>
                      <td className="px-4 py-3 text-neutral-700">{chunk.document_id}</td>
                      <td className="px-4 py-3 text-neutral-700">{chunk.score.toFixed(3)}</td>
                      <td className="px-4 py-3">
                        <BooleanState value={selectedIds.has(chunk.chunk_id)} />
                      </td>
                      <td className="px-4 py-3">
                        <BooleanState value={relevantIds.has(chunk.chunk_id)} />
                      </td>
                      <td className="px-4 py-3">
                        <BooleanState value={trace.citations.includes(chunk.chunk_id)} />
                      </td>
                    </tr>
                  ))}
                  {!retrieval.retrieved_chunks.length ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-5 text-neutral-500">
                        No chunks were retrieved.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              <div>
                <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase text-neutral-500">
                  <FileText size={15} aria-hidden="true" />
                  Answer
                </div>
                <p className="mt-2 text-sm leading-6 text-neutral-700">
                  {trace.answer || "No answer was produced."}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {trace.citations.map((citation) => (
                    <Badge
                      key={citation}
                      tone={trace.invalid_citation_ids.includes(citation) ? "rose" : "teal"}
                    >
                      {citation}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase text-neutral-500">
                  <Quote size={15} aria-hidden="true" />
                  Claim support
                </div>
                <div className="mt-2 divide-y divide-line">
                  {trace.claims.map((claim, index) => {
                    const support = trace.claim_support_scores[index] ?? 0;
                    return (
                      <div key={`${record.sample_id}-claim-${index}`} className="py-2 text-sm">
                        <div className="flex items-start justify-between gap-3">
                          <span className="leading-6 text-neutral-700">{claim}</span>
                          <Badge tone={support >= 0.6 ? "teal" : "rose"}>
                            {percent(support)}
                          </Badge>
                        </div>
                      </div>
                    );
                  })}
                  {!trace.claims.length ? (
                    <div className="py-3 text-sm text-neutral-500">No claims were produced.</div>
                  ) : null}
                </div>
              </div>
            </div>

            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-sm font-medium text-neutral-700">
                Retrieved chunk text and raw trace
              </summary>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <div className="divide-y divide-line">
                  {retrieval.retrieved_chunks.map((chunk) => (
                    <div key={`${chunk.chunk_id}-text`} className="py-3">
                      <div className="font-mono text-xs text-neutral-500">{chunk.chunk_id}</div>
                      <p className="mt-1 text-sm leading-6 text-neutral-700">{chunk.text}</p>
                    </div>
                  ))}
                </div>
                <pre className="max-h-[420px] overflow-auto bg-neutral-950 p-3 text-xs leading-5 text-neutral-100">
                  {JSON.stringify(trace, null, 2)}
                </pre>
              </div>
            </details>
          </section>
        );
      })}
      {!traces.length ? (
        <div className="px-5 py-8 text-sm text-neutral-600">No RAG traces are stored.</div>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  inverse = false
}: {
  label: string;
  value: number;
  inverse?: boolean;
}) {
  const healthy = inverse ? value === 0 : value >= 0.8;
  return (
    <div className="border-b border-line pb-3">
      <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
      <div className={`mt-2 text-lg font-semibold ${healthy ? "text-teal" : "text-rose"}`}>
        {percent(value)}
      </div>
    </div>
  );
}

function BooleanState({ value }: { value: boolean }) {
  return value ? (
    <span className="inline-flex items-center gap-1.5 text-teal">
      <CheckCircle2 size={15} aria-hidden="true" /> Yes
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-neutral-500">
      <CircleX size={15} aria-hidden="true" /> No
    </span>
  );
}
