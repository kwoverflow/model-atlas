"use client";

import { LoaderCircle, PlayCircle, SearchCheck } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { GatePreflightPanel } from "@/components/GatePreflightPanel";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  AcceptancePolicy,
  DeploymentConfiguration,
  EvaluationSuite,
  GateEvaluation,
  GatePreflightResponse
} from "@/types/api";

type GateEvaluationFormProps = {
  configurations: DeploymentConfiguration[];
  suites: EvaluationSuite[];
  policies: AcceptancePolicy[];
  baselines: GateEvaluation[];
  initialConfigurationId?: string;
  initialSuiteId?: string;
  initialPolicyId?: string;
};

type FlowState =
  | "idle"
  | "loading_preflight"
  | "preflight_success"
  | "preflight_warning"
  | "preflight_blocked"
  | "evaluation_running"
  | "api_error";

export function GateEvaluationForm({
  configurations,
  suites,
  policies,
  baselines,
  initialConfigurationId,
  initialSuiteId,
  initialPolicyId
}: GateEvaluationFormProps) {
  const router = useRouter();
  const [configurationId, setConfigurationId] = useState(
    initialValue(configurations, initialConfigurationId)
  );
  const [suiteId, setSuiteId] = useState(initialValue(suites, initialSuiteId));
  const [policyId, setPolicyId] = useState(initialValue(policies, initialPolicyId));
  const [baselineId, setBaselineId] = useState("");
  const [flowState, setFlowState] = useState<FlowState>("idle");
  const [preflight, setPreflight] = useState<GatePreflightResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const matchingBaselines = baselines.filter(
    (gate) =>
      gate.deployment_configuration_id === configurationId &&
      gate.evaluation_suite_id === suiteId &&
      gate.acceptance_policy_id === policyId
  );
  const selectionComplete = Boolean(configurationId && suiteId && policyId);

  function invalidatePreflight() {
    setPreflight(null);
    setFlowState("idle");
    setMessage(null);
  }

  async function reviewEvidence() {
    if (!selectionComplete) return;
    setFlowState("loading_preflight");
    setMessage("Reviewing selected evidence");
    try {
      const response = await browserApiFetch(`${API_BASE_URL}/deployment-gates/preflight`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(requestBody())
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(detail?.detail ?? "Preflight request failed");
      }
      const result = (await response.json()) as GatePreflightResponse;
      setPreflight(result);
      if (!result.can_evaluate) {
        setFlowState("preflight_blocked");
        setMessage("Preflight found blocking preconditions");
      } else if (result.warnings.length || result.expected_outcome_constraints.length) {
        setFlowState("preflight_warning");
        setMessage("Preflight completed with evidence limitations");
      } else {
        setFlowState("preflight_success");
        setMessage("Preflight completed");
      }
    } catch (error) {
      setPreflight(null);
      setFlowState("api_error");
      setMessage(error instanceof Error ? error.message : "Preflight request failed");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preflight?.can_evaluate) return;
    setFlowState("evaluation_running");
    setMessage("Evaluating gate");
    try {
      const response = await browserApiFetch(`${API_BASE_URL}/deployment-gates/evaluations`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(requestBody())
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(detail?.detail ?? "Gate evaluation failed");
      }
      const gate = (await response.json()) as GateEvaluation;
      router.push(`/deployment-gates/${gate.id}`);
    } catch (error) {
      setFlowState("api_error");
      setMessage(error instanceof Error ? error.message : "Gate evaluation failed");
    }
  }

  function requestBody() {
    return {
      deployment_configuration_id: configurationId,
      evaluation_suite_id: suiteId,
      acceptance_policy_id: policyId,
      baseline_gate_evaluation_id: baselineId || null
    };
  }

  return (
    <>
      <form onSubmit={submit} className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="grid grid-cols-3 border-b border-line text-xs font-medium text-neutral-500">
          <Step number="1" label="Select scope" active />
          <Step number="2" label="Review evidence" active={preflight !== null} />
          <Step
            number="3"
            label="Evaluate gate"
            active={flowState === "evaluation_running"}
          />
        </div>
        <div className="grid gap-4 p-5 lg:grid-cols-2">
          <SelectField
            label="Deployment configuration"
            value={configurationId}
            onChange={(value) => {
              setConfigurationId(value);
              setBaselineId("");
              invalidatePreflight();
            }}
            options={configurations.map((configuration) => ({
              value: configuration.id,
              label: configuration.name
            }))}
          />
          <SelectField
            label="Evaluation suite"
            value={suiteId}
            onChange={(value) => {
              setSuiteId(value);
              setBaselineId("");
              invalidatePreflight();
            }}
            options={suites.map((suite) => ({
              value: suite.id,
              label: `${suite.name} ${suite.version_label}`
            }))}
          />
          <SelectField
            label="Acceptance policy"
            value={policyId}
            onChange={(value) => {
              setPolicyId(value);
              setBaselineId("");
              invalidatePreflight();
            }}
            options={policies.map((policy) => ({
              value: policy.id,
              label: `${policy.name} ${policy.version_label}`
            }))}
          />
          <SelectField
            label="Baseline gate"
            value={baselineId}
            onChange={(value) => {
              setBaselineId(value);
              invalidatePreflight();
            }}
            optionalLabel="Use active baseline automatically"
            options={matchingBaselines.map((gate) => ({
              value: gate.id,
              label: `${gate.verdict} ${gate.id.slice(0, 8)}`
            }))}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-4">
          <button
            type="button"
            onClick={reviewEvidence}
            className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-4 text-sm font-medium text-ink disabled:opacity-50"
            disabled={
              !selectionComplete ||
              flowState === "loading_preflight" ||
              flowState === "evaluation_running"
            }
          >
            {flowState === "loading_preflight" ? (
              <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
            ) : (
              <SearchCheck size={16} aria-hidden="true" />
            )}
            Review Evidence
          </button>
          <button
            type="submit"
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:opacity-40"
            disabled={!preflight?.can_evaluate || flowState === "evaluation_running"}
          >
            {flowState === "evaluation_running" ? (
              <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
            ) : (
              <PlayCircle size={16} aria-hidden="true" />
            )}
            Evaluate Gate
          </button>
          <span aria-live="polite" className="text-sm text-neutral-600">
            {message}
          </span>
        </div>
      </form>
      {preflight ? <GatePreflightPanel preflight={preflight} /> : null}
    </>
  );
}

function initialValue(items: Array<{ id: string }>, requested?: string): string {
  return items.some((item) => item.id === requested) ? requested ?? "" : items[0]?.id ?? "";
}

function Step({ number, label, active }: { number: string; label: string; active: boolean }) {
  return (
    <div className={`flex min-h-12 items-center gap-2 px-4 ${active ? "text-ink" : "text-neutral-400"}`}>
      <span className={`grid h-6 w-6 place-items-center rounded-full border ${active ? "border-ink bg-ink text-white" : "border-neutral-300"}`}>
        {number}
      </span>
      <span>{label}</span>
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
  optionalLabel
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  optionalLabel?: string;
}) {
  return (
    <label className="grid gap-2 text-sm font-medium text-neutral-700">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-md border border-line bg-white px-3 text-sm"
        required={!optionalLabel}
      >
        {optionalLabel ? <option value="">{optionalLabel}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
