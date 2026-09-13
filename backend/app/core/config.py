import json
import os
import socket
from functools import lru_cache


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    return float(raw_value) if raw_value is not None else default


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    return int(raw_value) if raw_value is not None else default


def _env_json_string_map(name: str) -> dict[str, str]:
    raw_value = os.getenv(name)
    if not raw_value:
        return {}
    parsed = json.loads(raw_value)
    if not isinstance(parsed, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in parsed.items()
    ):
        raise ValueError(f"{name} must be a JSON object with string values")
    return {key: value for key, value in parsed.items() if key and value}


def _env_csv(name: str, default: str) -> list[str]:
    raw_value = os.getenv(name) or default
    return [value.strip() for value in raw_value.split(",") if value.strip()]


class Settings:
    project_name: str = "Model Atlas"
    api_v1_prefix: str = "/api/v1"
    database_url: str
    cors_origins: list[str]
    trusted_operator_headers_enabled: bool
    trusted_proxy_networks: list[str]
    reject_untrusted_forwarded_headers: bool
    oidc_jwt_enabled: bool
    oidc_jwt_issuer: str | None
    oidc_jwt_audience: str | None
    oidc_jwt_algorithms: list[str]
    oidc_jwt_hs256_keys: dict[str, str]
    oidc_jwt_role_claim: str
    oidc_jwt_name_claim: str
    oidc_jwt_leeway_seconds: int
    oidc_discovery_url: str | None
    oidc_jwks_uri: str | None
    oidc_discovery_cache_ttl_seconds: int
    oidc_jwks_cache_ttl_seconds: int
    oidc_http_timeout_seconds: float
    oidc_allow_insecure_http: bool
    oidc_browser_login_enabled: bool
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_redirect_uri: str
    oidc_frontend_url: str
    oidc_authorization_endpoint: str | None
    oidc_token_endpoint: str | None
    oidc_end_session_endpoint: str | None
    oidc_scopes: list[str]
    oidc_session_secret: str | None
    oidc_session_cookie_name: str
    oidc_session_secure: bool
    oidc_session_ttl_seconds: int
    oidc_csrf_cookie_name: str
    oidc_csrf_header_name: str
    oidc_shared_cache_enabled: bool
    oidc_session_retention_days: int
    oidc_session_cleanup_enabled: bool
    oidc_session_cleanup_interval_seconds: int
    oidc_session_cleanup_batch_size: int
    instance_name: str
    agent_traffic_hmac_keys: dict[str, str]
    agent_traffic_allow_legacy_signatures: bool
    agent_traffic_max_clock_skew_seconds: int
    agent_traffic_source_stale_seconds: int
    agent_traffic_max_compressed_bytes: int
    agent_traffic_max_decompressed_bytes: int
    agent_worker_poll_seconds: float
    agent_job_lease_seconds: int
    agent_job_heartbeat_seconds: float
    agent_worker_offline_seconds: int
    agent_reconciliation_interval_seconds: int
    operational_snapshot_enabled: bool
    operational_snapshot_interval_seconds: int
    operational_snapshot_retention_days: int
    operational_slo_window_seconds: int
    operational_slo_short_window_seconds: int
    operational_slo_min_samples: int
    operational_identity_slo_target: float
    operational_worker_slo_target: float
    operational_slo_warning_burn_rate: float
    operational_slo_critical_burn_rate: float
    operational_incident_escalation_seconds: int
    operational_paging_enabled: bool
    operational_paging_webhook_url: str | None
    operational_paging_allowed_hosts: list[str]
    operational_paging_allow_insecure_http: bool
    operational_paging_hmac_secret: str | None
    operational_paging_hmac_keys: dict[str, str]
    operational_paging_hmac_keys_file: str | None
    operational_paging_active_key_id: str | None
    operational_paging_active_key_id_file: str | None
    operational_paging_ca_bundle_path: str | None
    operational_paging_provider: str
    operational_paging_require_receipt: bool
    operational_paging_receipt_max_age_seconds: int
    operational_paging_timeout_seconds: float
    operational_paging_max_response_bytes: int
    minimum_applied_judge_label_rate_for_local_demo: float
    minimum_critical_reviewed_count_for_local_demo: int
    minimum_production_captured_result_count: int
    minimum_applied_judge_label_rate_for_production: float
    minimum_critical_review_coverage_rate_for_production: float
    model_attestation_allowed_hosts: list[str]
    model_attestation_http_timeout_seconds: float
    model_publisher_jwks_path: str | None
    model_publisher_allowed_issuers: list[str]
    model_publisher_allowed_algorithms: list[str]
    production_evidence_jwks_path: str | None
    production_evidence_allowed_issuers: list[str]
    production_evidence_allowed_algorithms: list[str]
    signed_evidence_max_age_seconds: int
    trust_source_allowed_hosts: list[str]
    trust_source_allow_insecure_http: bool
    trust_source_http_timeout_seconds: float
    trust_source_max_jwks_bytes: int
    trust_source_scheduler_enabled: bool
    trust_source_scheduler_batch_size: int
    trust_source_schedule_lease_seconds: int

    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://model_atlas:model_atlas@localhost:5432/model_atlas",
        )
        raw_origins = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000")
        self.cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        self.trusted_operator_headers_enabled = _env_bool(
            "TRUSTED_OPERATOR_HEADERS_ENABLED",
            True,
        )
        raw_trusted_proxies = os.getenv(
            "TRUSTED_PROXY_NETWORKS",
            "127.0.0.1/32,::1/128,testclient",
        )
        self.trusted_proxy_networks = [
            source.strip() for source in raw_trusted_proxies.split(",") if source.strip()
        ]
        self.reject_untrusted_forwarded_headers = _env_bool(
            "REJECT_UNTRUSTED_FORWARDED_HEADERS",
            True,
        )
        self.oidc_jwt_enabled = _env_bool("OIDC_JWT_ENABLED", False)
        self.oidc_jwt_issuer = os.getenv("OIDC_JWT_ISSUER") or None
        self.oidc_jwt_audience = os.getenv("OIDC_JWT_AUDIENCE") or None
        self.oidc_jwt_hs256_keys = _env_json_string_map("OIDC_JWT_HS256_KEYS_JSON")
        legacy_jwt_secret = os.getenv("OIDC_JWT_HS256_SECRET")
        if legacy_jwt_secret and not self.oidc_jwt_hs256_keys:
            self.oidc_jwt_hs256_keys = {"default": legacy_jwt_secret}
        default_algorithms = "HS256" if self.oidc_jwt_hs256_keys else "RS256"
        self.oidc_jwt_algorithms = _env_csv(
            "OIDC_JWT_ALGORITHMS",
            default_algorithms,
        )
        self.oidc_jwt_role_claim = os.getenv("OIDC_JWT_ROLE_CLAIM", "role")
        self.oidc_jwt_name_claim = os.getenv("OIDC_JWT_NAME_CLAIM", "name")
        self.oidc_jwt_leeway_seconds = max(
            0,
            min(_env_int("OIDC_JWT_LEEWAY_SECONDS", 30), 300),
        )
        self.oidc_discovery_url = os.getenv("OIDC_DISCOVERY_URL") or None
        self.oidc_jwks_uri = os.getenv("OIDC_JWKS_URI") or None
        self.oidc_discovery_cache_ttl_seconds = max(
            30,
            min(_env_int("OIDC_DISCOVERY_CACHE_TTL_SECONDS", 3600), 86400),
        )
        self.oidc_jwks_cache_ttl_seconds = max(
            15,
            min(_env_int("OIDC_JWKS_CACHE_TTL_SECONDS", 300), 86400),
        )
        self.oidc_http_timeout_seconds = max(
            0.5,
            min(_env_float("OIDC_HTTP_TIMEOUT_SECONDS", 5.0), 30.0),
        )
        self.oidc_allow_insecure_http = _env_bool(
            "OIDC_ALLOW_INSECURE_HTTP",
            False,
        )
        self.oidc_browser_login_enabled = _env_bool(
            "OIDC_BROWSER_LOGIN_ENABLED",
            False,
        )
        self.oidc_client_id = os.getenv("OIDC_CLIENT_ID") or None
        self.oidc_client_secret = os.getenv("OIDC_CLIENT_SECRET") or None
        self.oidc_redirect_uri = os.getenv(
            "OIDC_REDIRECT_URI",
            "http://localhost:18000/api/v1/operator-identity/callback",
        )
        self.oidc_frontend_url = os.getenv(
            "OIDC_FRONTEND_URL",
            "http://localhost:3000",
        ).rstrip("/")
        self.oidc_authorization_endpoint = os.getenv("OIDC_AUTHORIZATION_ENDPOINT") or None
        self.oidc_token_endpoint = os.getenv("OIDC_TOKEN_ENDPOINT") or None
        self.oidc_end_session_endpoint = os.getenv("OIDC_END_SESSION_ENDPOINT") or None
        self.oidc_scopes = _env_csv("OIDC_SCOPES", "openid,profile,email")
        self.oidc_session_secret = os.getenv("OIDC_SESSION_SECRET") or None
        self.oidc_session_cookie_name = os.getenv(
            "OIDC_SESSION_COOKIE_NAME",
            "model_atlas_session",
        )
        self.oidc_session_secure = _env_bool("OIDC_SESSION_SECURE", True)
        self.oidc_session_ttl_seconds = max(
            300,
            min(_env_int("OIDC_SESSION_TTL_SECONDS", 3600), 43_200),
        )
        self.oidc_csrf_cookie_name = os.getenv(
            "OIDC_CSRF_COOKIE_NAME",
            "model_atlas_csrf",
        )
        self.oidc_csrf_header_name = os.getenv(
            "OIDC_CSRF_HEADER_NAME",
            "x-model-atlas-csrf",
        ).lower()
        self.oidc_shared_cache_enabled = _env_bool(
            "OIDC_SHARED_CACHE_ENABLED",
            True,
        )
        self.oidc_session_retention_days = max(
            1,
            min(_env_int("OIDC_SESSION_RETENTION_DAYS", 30), 3650),
        )
        self.oidc_session_cleanup_enabled = _env_bool(
            "OIDC_SESSION_CLEANUP_ENABLED",
            True,
        )
        self.oidc_session_cleanup_interval_seconds = max(
            60,
            min(_env_int("OIDC_SESSION_CLEANUP_INTERVAL_SECONDS", 3600), 86400),
        )
        self.oidc_session_cleanup_batch_size = max(
            1,
            min(_env_int("OIDC_SESSION_CLEANUP_BATCH_SIZE", 200), 1000),
        )
        self.instance_name = os.getenv("MODEL_ATLAS_INSTANCE_NAME", socket.gethostname())
        self.agent_traffic_hmac_keys = _env_json_string_map("AGENT_TRAFFIC_HMAC_KEYS_JSON")
        self.agent_traffic_allow_legacy_signatures = _env_bool(
            "AGENT_TRAFFIC_ALLOW_LEGACY_SIGNATURES",
            True,
        )
        self.agent_traffic_max_clock_skew_seconds = max(
            30,
            _env_int("AGENT_TRAFFIC_MAX_CLOCK_SKEW_SECONDS", 300),
        )
        self.agent_traffic_source_stale_seconds = max(
            30,
            _env_int("AGENT_TRAFFIC_SOURCE_STALE_SECONDS", 300),
        )
        self.agent_traffic_max_compressed_bytes = max(
            1024,
            _env_int("AGENT_TRAFFIC_MAX_COMPRESSED_BYTES", 1_048_576),
        )
        self.agent_traffic_max_decompressed_bytes = max(
            self.agent_traffic_max_compressed_bytes,
            _env_int("AGENT_TRAFFIC_MAX_DECOMPRESSED_BYTES", 10_485_760),
        )
        self.agent_worker_poll_seconds = max(
            0.1,
            _env_float("AGENT_WORKER_POLL_SECONDS", 1.0),
        )
        self.agent_job_lease_seconds = max(
            5,
            min(_env_int("AGENT_JOB_LEASE_SECONDS", 300), 900),
        )
        self.agent_job_heartbeat_seconds = max(
            1.0,
            min(
                _env_float("AGENT_JOB_HEARTBEAT_SECONDS", 30.0),
                max(1.0, self.agent_job_lease_seconds / 2),
            ),
        )
        self.agent_worker_offline_seconds = max(
            10,
            _env_int(
                "AGENT_WORKER_OFFLINE_SECONDS",
                max(60, int(self.agent_job_heartbeat_seconds * 3)),
            ),
        )
        self.agent_reconciliation_interval_seconds = max(
            10,
            _env_int("AGENT_RECONCILIATION_INTERVAL_SECONDS", 60),
        )
        self.operational_snapshot_enabled = _env_bool(
            "OPERATIONAL_SNAPSHOT_ENABLED",
            True,
        )
        self.operational_snapshot_interval_seconds = max(
            15,
            min(_env_int("OPERATIONAL_SNAPSHOT_INTERVAL_SECONDS", 60), 3600),
        )
        self.operational_snapshot_retention_days = max(
            1,
            min(_env_int("OPERATIONAL_SNAPSHOT_RETENTION_DAYS", 30), 3650),
        )
        self.operational_slo_window_seconds = max(
            300,
            min(_env_int("OPERATIONAL_SLO_WINDOW_SECONDS", 3600), 2_592_000),
        )
        self.operational_slo_short_window_seconds = max(
            self.operational_snapshot_interval_seconds,
            min(
                _env_int("OPERATIONAL_SLO_SHORT_WINDOW_SECONDS", 300),
                self.operational_slo_window_seconds,
            ),
        )
        self.operational_slo_min_samples = max(
            1,
            min(_env_int("OPERATIONAL_SLO_MIN_SAMPLES", 3), 10_000),
        )
        self.operational_identity_slo_target = max(
            0.5,
            min(_env_float("OPERATIONAL_IDENTITY_SLO_TARGET", 0.99), 1.0),
        )
        self.operational_worker_slo_target = max(
            0.5,
            min(_env_float("OPERATIONAL_WORKER_SLO_TARGET", 0.99), 1.0),
        )
        self.operational_slo_warning_burn_rate = max(
            1.0,
            min(_env_float("OPERATIONAL_SLO_WARNING_BURN_RATE", 6.0), 10_000.0),
        )
        self.operational_slo_critical_burn_rate = max(
            self.operational_slo_warning_burn_rate,
            min(
                _env_float("OPERATIONAL_SLO_CRITICAL_BURN_RATE", 14.4),
                10_000.0,
            ),
        )
        self.operational_incident_escalation_seconds = max(
            60,
            min(
                _env_int("OPERATIONAL_INCIDENT_ESCALATION_SECONDS", 900),
                604_800,
            ),
        )
        self.operational_paging_enabled = _env_bool(
            "OPERATIONAL_PAGING_ENABLED",
            False,
        )
        self.operational_paging_webhook_url = os.getenv("OPERATIONAL_PAGING_WEBHOOK_URL") or None
        self.operational_paging_allowed_hosts = _env_csv(
            "OPERATIONAL_PAGING_ALLOWED_HOSTS",
            "localhost,127.0.0.1,testserver",
        )
        self.operational_paging_allow_insecure_http = _env_bool(
            "OPERATIONAL_PAGING_ALLOW_INSECURE_HTTP",
            False,
        )
        self.operational_paging_hmac_secret = os.getenv("OPERATIONAL_PAGING_HMAC_SECRET") or None
        self.operational_paging_hmac_keys = _env_json_string_map(
            "OPERATIONAL_PAGING_HMAC_KEYS_JSON"
        )
        self.operational_paging_hmac_keys_file = (
            os.getenv("OPERATIONAL_PAGING_HMAC_KEYS_FILE") or None
        )
        self.operational_paging_active_key_id = (
            os.getenv("OPERATIONAL_PAGING_ACTIVE_KEY_ID") or None
        )
        self.operational_paging_active_key_id_file = (
            os.getenv("OPERATIONAL_PAGING_ACTIVE_KEY_ID_FILE") or None
        )
        self.operational_paging_ca_bundle_path = (
            os.getenv("OPERATIONAL_PAGING_CA_BUNDLE_PATH") or None
        )
        self.operational_paging_provider = os.getenv(
            "OPERATIONAL_PAGING_PROVIDER",
            "generic-webhook",
        ).strip()
        self.operational_paging_require_receipt = _env_bool(
            "OPERATIONAL_PAGING_REQUIRE_RECEIPT",
            False,
        )
        self.operational_paging_receipt_max_age_seconds = max(
            60,
            min(
                _env_int("OPERATIONAL_PAGING_RECEIPT_MAX_AGE_SECONDS", 86_400),
                2_592_000,
            ),
        )
        self.operational_paging_timeout_seconds = max(
            0.5,
            min(_env_float("OPERATIONAL_PAGING_TIMEOUT_SECONDS", 5.0), 30.0),
        )
        self.operational_paging_max_response_bytes = max(
            512,
            min(
                _env_int("OPERATIONAL_PAGING_MAX_RESPONSE_BYTES", 4096),
                65_536,
            ),
        )
        self.minimum_applied_judge_label_rate_for_local_demo = _env_float(
            "MIN_APPLIED_JUDGE_LABEL_RATE_FOR_LOCAL_DEMO",
            0.20,
        )
        self.minimum_critical_reviewed_count_for_local_demo = _env_int(
            "MIN_CRITICAL_REVIEWED_COUNT_FOR_LOCAL_DEMO",
            1,
        )
        self.minimum_production_captured_result_count = _env_int(
            "MIN_PRODUCTION_CAPTURED_RESULT_COUNT",
            20,
        )
        self.minimum_applied_judge_label_rate_for_production = _env_float(
            "MIN_APPLIED_JUDGE_LABEL_RATE_FOR_PRODUCTION",
            0.30,
        )
        self.minimum_critical_review_coverage_rate_for_production = _env_float(
            "MIN_CRITICAL_REVIEW_COVERAGE_RATE_FOR_PRODUCTION",
            0.80,
        )
        self.model_attestation_allowed_hosts = _env_csv(
            "MODEL_ATTESTATION_ALLOWED_HOSTS",
            "ollama,localhost,127.0.0.1,host.docker.internal,testserver",
        )
        self.model_attestation_http_timeout_seconds = max(
            0.5,
            min(_env_float("MODEL_ATTESTATION_HTTP_TIMEOUT_SECONDS", 5.0), 30.0),
        )
        self.model_publisher_jwks_path = os.getenv("MODEL_PUBLISHER_JWKS_PATH") or None
        self.model_publisher_allowed_issuers = _env_csv(
            "MODEL_PUBLISHER_ALLOWED_ISSUERS",
            "",
        )
        self.model_publisher_allowed_algorithms = _env_csv(
            "MODEL_PUBLISHER_ALLOWED_ALGORITHMS",
            "RS256",
        )
        self.production_evidence_jwks_path = os.getenv("PRODUCTION_EVIDENCE_JWKS_PATH") or None
        self.production_evidence_allowed_issuers = _env_csv(
            "PRODUCTION_EVIDENCE_ALLOWED_ISSUERS",
            "",
        )
        self.production_evidence_allowed_algorithms = _env_csv(
            "PRODUCTION_EVIDENCE_ALLOWED_ALGORITHMS",
            "RS256",
        )
        self.signed_evidence_max_age_seconds = max(
            60,
            min(
                _env_int("SIGNED_EVIDENCE_MAX_AGE_SECONDS", 2_592_000),
                31_536_000,
            ),
        )
        self.trust_source_allowed_hosts = _env_csv(
            "TRUST_SOURCE_ALLOWED_HOSTS",
            "localhost,127.0.0.1,testserver",
        )
        self.trust_source_allow_insecure_http = _env_bool(
            "TRUST_SOURCE_ALLOW_INSECURE_HTTP",
            False,
        )
        self.trust_source_http_timeout_seconds = max(
            0.5,
            min(_env_float("TRUST_SOURCE_HTTP_TIMEOUT_SECONDS", 5.0), 30.0),
        )
        self.trust_source_max_jwks_bytes = max(
            4096,
            min(_env_int("TRUST_SOURCE_MAX_JWKS_BYTES", 1_048_576), 4_194_304),
        )
        self.trust_source_scheduler_enabled = _env_bool(
            "TRUST_SOURCE_SCHEDULER_ENABLED",
            True,
        )
        self.trust_source_scheduler_batch_size = max(
            1,
            min(_env_int("TRUST_SOURCE_SCHEDULER_BATCH_SIZE", 20), 100),
        )
        self.trust_source_schedule_lease_seconds = max(
            30,
            min(_env_int("TRUST_SOURCE_SCHEDULE_LEASE_SECONDS", 900), 3600),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
