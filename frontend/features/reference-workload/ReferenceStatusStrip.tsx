import { Database, Factory, ShieldCheck, TestTube2 } from "lucide-react";

import { StatusSummaryGrid } from "@/components/StatusSummaryGrid";
import type { ReferenceWorkloadOverview } from "@/types/api";

export function ReferenceStatusStrip({ data }: { data: ReferenceWorkloadOverview }) {
  return (
    <StatusSummaryGrid
      items={[
        {
          label: "Evaluation",
          value: data.evaluation_status,
          detail: `${data.actual_runtime_result_count} actual local-runtime results`,
          icon: TestTube2
        },
        {
          label: "Gate",
          value: data.gate_verdict,
          detail: `${data.gate_outcomes.filter((item) => item.gate_evaluation_id).length}/${data.configuration_matrix.filter((item) => item.status === "completed").length} configurations evaluated`,
          icon: ShieldCheck
        },
        {
          label: "Evidence Trust",
          value: data.evidence_trust.trust_status,
          detail: `${data.review_coverage.human_reviewed_count + data.review_coverage.applied_judge_label_count} reviewed model outputs`,
          icon: Database
        },
        {
          label: "Production Readiness",
          value: data.production_readiness,
          detail: `${data.production_captured_result_count} verified production-captured results`,
          icon: Factory
        }
      ]}
    />
  );
}
