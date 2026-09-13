export type PriorityChoice =
  | { mode: "set"; value: "low" | "normal" | "high" }
  | { mode: "omit" | "unresolved" };
export type TicketDraft = {
  original_request: string;
  query: string;
  priority: PriorityChoice;
};
export type ContractVerdict = {
  allowed: boolean;
  reasons: string[];
  actual_arguments: Record<string, unknown> | null;
  requested_arguments: Record<string, unknown>;
  normalized_proposal: string;
};
export type ProposalRecord = {
  id: string;
  revision: number;
  contract_hash: string;
  proposal: string;
  source: string;
  verdict: ContractVerdict;
  created_at: string;
  generation: { model: string; latency_ms: number } | null;
  execution: {
    executed_at: string;
    side_effect_mode: string;
    trace: { successful: boolean; steps: { output: unknown }[] };
  } | null;
};
export type RequestContract = {
  id: string;
  revision: number;
  status: "draft" | "confirmed" | "revoked";
  draft: TicketDraft;
  contract_hash: string;
  expires_at: string | null;
  expired: boolean;
  executed_check_id: string | null;
  confirmation: {
    authority: string;
    actor: { display_name: string; identity_verified: boolean };
    confirmed_at: string;
  } | null;
  checks: ProposalRecord[];
  events: {
    event: string;
    at: string;
    revision: number;
    actor: { display_name: string };
  }[];
};
