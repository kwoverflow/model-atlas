import type { RequestContract } from "@/types/structuredRequests";

export type WorkflowTask = {
  id: string;
  request: string;
  pack_version: string;
  pack_hash: string;
};
export type WorkflowSource = "participant_self_report" | "automated_qa";
export type WorkflowFeedback = {
  assistance: "none_reported" | "received" | "not_reported" | "not_applicable";
  difficulty: number | null;
  note: string;
};
export type WorkflowAttempt = {
  evidence: {
    canonical_json: string;
    sha256: string;
    verified: boolean;
  } | null;
  id: string;
  revision: number;
  source: WorkflowSource;
  task: WorkflowTask;
  request_id: string | null;
  request_state_hash: string | null;
  request: RequestContract | null;
  help_count: number;
  started_at: string;
  ended_at: string | null;
  result: {
    expected: { query: string | null };
    assessment: "matches_task" | "does_not_match_task" | "abandoned";
    disposition: "finished" | "clarification_requested" | "abandoned";
    mismatches: string[];
    evidence_hash: string;
    feedback: WorkflowFeedback;
    request_snapshot: RequestContract | null;
    metrics: {
      elapsed_seconds: number;
      saved_revision_count_after_first: number;
      help_request_count: number;
      proposal_count: number;
      model_proposal_count: number;
      manual_proposal_count: number;
      blocked_proposal_count: number;
      execution_count: number;
    };
  } | null;
};
export type WorkflowSummary = {
  groups: {
    pack_hash: string;
    source: WorkflowSource;
    assistance: string;
    total: number;
    open: number;
    matches_task: number;
    does_not_match_task: number;
    abandoned: number;
  }[];
};
