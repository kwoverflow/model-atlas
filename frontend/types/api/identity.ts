import type { UUID } from "./common";

import type { ReleaseDecisionPolicyEvaluation, ReleaseDecisionType } from "./release";



export type OperatorIdentity = {
  subject_id: string;
  display_name: string;
  role: string | null;
  identity_provider: string;
  auth_source: string;
  identity_verified: boolean;
  ticket_reference: string | null;
  release_permissions: {
    policy_version: string;
    decisions: Record<ReleaseDecisionType, ReleaseDecisionPolicyEvaluation>;
    [key: string]: unknown;
  };
  session_permissions: BrowserSessionPermissions;
};

export type BrowserSessionPermissions = {
  policy_version: string;
  can_audit: boolean;
  can_administer: boolean;
  auditor_roles: string[];
  administrator_roles: string[];
  identity_verified: boolean;
  signer_role: string | null;
};

export type BrowserOIDCStatus = {
  schema_version: string;
  enabled: boolean;
  authenticated: boolean;
  login_url: string | null;
  logout_url: string | null;
  session_cookie_name: string;
  identity_provider: string | null;
  logout_method: "POST";
  csrf_cookie_name: string;
  csrf_header_name: string;
  session_store: "database";
  session_id: UUID | null;
  session_fingerprint: string | null;
  session_expires_at: string | null;
};

export type BrowserSessionStatus = "active" | "expired" | "revoked";

export type BrowserSessionProviderTokenState = "retained" | "purged" | "not_available";

export type BrowserSessionRetentionPolicy = {
  retention_days: number;
  cleanup_enabled: boolean;
  cleanup_interval_seconds: number;
  cleanup_batch_size: number;
  provider_token_policy: string;
};

export type BrowserSessionOverview = {
  schema_version: string;
  generated_at: string;
  health: "healthy" | "attention";
  active_count: number;
  expired_count: number;
  revoked_count: number;
  retention_due_count: number;
  inactive_provider_token_count: number;
  audit_event_count: number;
  last_cleanup_job_id: UUID | null;
  last_cleanup_job_status: string | null;
  last_cleanup_completed_at: string | null;
  policy: BrowserSessionRetentionPolicy;
  permissions: BrowserSessionPermissions;
};

export type BrowserSession = {
  id: UUID;
  session_fingerprint: string;
  subject_id: string;
  display_name: string;
  role: string | null;
  identity_provider: string;
  provider_session_hash: string | null;
  client_fingerprint: string | null;
  authenticated_at: string;
  expires_at: string;
  last_seen_at: string;
  revoked_at: string | null;
  revocation_reason: string | null;
  provider_token_state: BrowserSessionProviderTokenState;
  provider_token_purged_at: string | null;
  status: BrowserSessionStatus;
  current_session: boolean;
};

export type BrowserSessionEvent = {
  id: UUID;
  session_id: UUID;
  session_fingerprint: string;
  subject_id: string;
  identity_provider: string;
  provider_session_hash: string | null;
  event_type: "issued" | "migrated" | "revoked" | "provider_token_purged" | "retention_deleted";
  reason: string | null;
  actor_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  metadata_json: Record<string, unknown>;
  previous_event_hash: string | null;
  event_hash: string;
  occurred_at: string;
  created_at: string;
};

export type BrowserSessionBulkAction = {
  action: "session" | "subject" | "provider_session";
  matched_count: number;
  revoked_count: number;
  already_inactive_count: number;
  current_session_preserved: boolean;
  event_ids: UUID[];
};
