import type { PriorityChoice } from "@/types/structuredRequests";

export type ScenarioTask = {
  id: string;
  request: string;
  pack_version: string;
  pack_hash: string;
};
export type ScenarioCatalog = {
  version: string;
  hash: string;
  count: number;
  tasks: ScenarioTask[];
};
export type ScenarioOutcome =
  "passed" | "known_limitation" | "regression" | "error";
export type ScenarioResult = {
  id: string;
  title: string;
  outcome: ScenarioOutcome;
  expected?: {
    status: number;
    reason: string | null;
    handler_invocations: number;
  };
  observed?: {
    status: number;
    reasons: string[];
    handler_invocations: number;
    replayed: boolean;
    confirmation_status: number;
  };
  expectations?: Record<string, boolean>;
  error_type?: string;
  fixture: { draft: { original_request: string }; proposal: string };
};
export type ScenarioRun = {
  id: string;
  created_at: string;
  report: {
    version: string;
    pack_hash: string;
    status: string;
    duration_ms: number;
    counts: Record<ScenarioOutcome, number>;
    rows: ScenarioResult[];
    implementation_hashes: Record<string, string>;
    model_calls: number;
    human_review: false;
    gate_evidence: false;
  };
};
export type StudyAnswer = {
  decision: "confirm" | "clarify";
  query: string;
  priority: PriorityChoice;
};
export type StudyAttempt = {
  id: string;
  source: "automated_qa" | "participant_self_report";
  revision: number;
  task: ScenarioTask;
  answer: StudyAnswer | null;
  answer_hash: string | null;
  correction_count: number;
  started_at: string;
  submitted_at: string | null;
  human_review_verified: false;
  gate_evidence: false;
  actor: { display_name: string; identity_verified: boolean };
  result: null | {
    matches_scenario_key: boolean;
    mismatches: string[];
    expected: StudyAnswer;
    elapsed_seconds: number;
    correction_count: number;
    human_review_verified: false;
    gate_evidence: false;
  };
};
