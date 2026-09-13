.PHONY: up down migrate seed seed-tool-calling seed-rag seed-reliability seed-agent seed-agent-adaptive test lint backend-test frontend-lint pull-local-model validate-local-model idp-up observability-up operational-staging-verify operational-failure-drill paging-key-rotate isolation-test supply-chain-demo trust-registry-demo trust-source-up reference-lock reference-draft reference-review-worksheet reference-review-assist reference-finalize-review reference-validate reference-bootstrap reference-case-revision reference-case-revision-review reference-finalize-case-revision reference-retrieval-audit reference-smoke reference-run reference-compare reference-gate reference-report

REFERENCE_CASE_REVISION ?= 1.0.2

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose run --rm backend alembic upgrade head

seed:
	docker compose run --rm backend python -m app.seed.demo

seed-tool-calling:
	docker compose run --rm backend python -m app.seed.tool_calling

seed-rag:
	docker compose run --rm backend python -m app.seed.rag_evaluation

seed-reliability:
	docker compose run --rm backend python -m app.seed.runtime_reliability

seed-agent:
	docker compose run --rm backend python -m app.seed.agent_operations

seed-agent-adaptive:
	docker compose run --rm backend python -m app.seed.adaptive_agent_operations

test:
	docker compose run --rm backend pytest

lint:
	docker compose run --rm backend ruff check .
	docker compose run --rm frontend npm run lint

backend-test:
	docker compose run --rm backend pytest

frontend-lint:
	docker compose run --rm frontend npm run lint

pull-local-model:
	docker compose --profile runtime up -d ollama
	docker compose exec ollama ollama pull $(or $(OLLAMA_MODEL),qwen2.5:0.5b)

validate-local-model:
	docker compose run --rm agent-worker python -m app.validation.local_model_validation \
		--deployment-configuration-id $(DEPLOYMENT_CONFIGURATION_ID) \
		--evaluation-suite-id $(EVALUATION_SUITE_ID) \
		--benchmark-task-id $(BENCHMARK_TASK_ID) \
		--prompt-version-id $(PROMPT_VERSION_ID) \
		--base-url $(or $(OPENAI_COMPATIBLE_BASE_URL),http://ollama:11434) \
		--model $(or $(OLLAMA_MODEL),qwen2.5:0.5b) \
		--output-dir /artifacts/model-validation

idp-up:
	docker compose --env-file deploy/idp/.env.keycloak.example --profile idp up -d keycloak backend frontend

observability-up:
	docker compose --env-file deploy/observability/.env.observability.example \
		--profile observability --profile trust-source up -d --build \
		--scale agent-worker=2 \
		backend agent-worker frontend prometheus alertmanager alert-sink \
		paging-tls-init paging-secrets-init paging-sink trust-source-fixture

operational-staging-verify:
	python tools/verify_operational_staging.py

operational-failure-drill:
	powershell -ExecutionPolicy Bypass -File tools/run_operational_failure_drill.ps1

paging-key-rotate:
	docker compose --profile observability run --rm paging-secrets-init \
		python -m app.operations.paging_secrets rotate \
		--directory /paging-secrets --new-key-id $(KEY_ID) --retain 2

isolation-test:
	docker compose -f deploy/isolation/docker-compose.isolation.yml run --rm tool-evaluator
	docker compose -f deploy/isolation/docker-compose.isolation.yml run --rm rag-evaluator

supply-chain-demo:
	docker compose exec backend python -m app.validation.supply_chain_bundle publisher \
		--output-dir /artifacts/supply-chain \
		--runtime-attestation-id $(RUNTIME_ATTESTATION_ID) \
		--runtime-model-name $(RUNTIME_MODEL_NAME) \
		--artifact-digest $(ARTIFACT_DIGEST) \
		--artifact-attestation-hash $(ARTIFACT_ATTESTATION_HASH) \
		--runtime-manifest-hash $(RUNTIME_MANIFEST_HASH)

trust-registry-demo:
	docker compose exec backend python -m app.validation.trust_registry_bundle \
		--output-dir /artifacts/supply-chain \
		--private-key /artifacts/supply-chain/demo-publisher-private.pem \
		--jwks /artifacts/supply-chain/publisher-jwks.json \
		--supply-chain-attestation-id $(SUPPLY_CHAIN_ATTESTATION_ID) \
		--supply-chain-attestation-hash $(SUPPLY_CHAIN_ATTESTATION_HASH) \
		--statement-id $(SUPPLY_CHAIN_STATEMENT_ID) \
		--subject-digest $(ARTIFACT_DIGEST)

trust-source-up:
	docker compose --profile trust-source up -d trust-source-fixture backend frontend

reference-lock:
	docker compose run --rm backend python -m app.reference_workload.cli lock-manifest

reference-draft:
	docker compose run --rm backend python -m app.reference_workload.cli draft-cases --force

reference-review-worksheet:
	docker compose run --rm backend python -m app.reference_workload.cli review-worksheet

reference-review-assist:
	docker compose run --rm backend python -m app.reference_workload.cli review-assist

reference-finalize-review:
	docker compose run --rm backend python -m app.reference_workload.cli finalize-assisted-review

reference-validate:
	docker compose run --rm backend python -m app.reference_workload.cli validate

reference-bootstrap:
	docker compose run --rm backend python -m app.reference_workload.cli bootstrap

reference-case-revision:
	docker compose run --rm backend python -m app.reference_workload.cli \
		create-case-revision \
		--spec /workspace/reference_workload/revisions/$(REFERENCE_CASE_REVISION)/revision_spec.json \
		--output-directory /workspace/reference_workload/revisions/$(REFERENCE_CASE_REVISION)

reference-case-revision-review:
	docker compose run --rm backend python -m app.reference_workload.cli \
		case-revision-review \
		--report /workspace/reference_workload/revisions/$(REFERENCE_CASE_REVISION)/revision_report.json \
		--output /workspace/reference_workload/revisions/$(REFERENCE_CASE_REVISION)/revision_review.html

reference-finalize-case-revision:
	docker compose run --rm backend python -m app.reference_workload.cli \
		finalize-case-revision \
		--output-directory /workspace/reference_workload/revisions/$(REFERENCE_CASE_REVISION) \
		--attestation /workspace/reference_workload/revisions/$(REFERENCE_CASE_REVISION)/review_attestation.json

reference-retrieval-audit:
	docker compose run --rm backend python -m app.reference_workload.cli \
		audit-retrieval-contracts \
		--output /artifacts/reference-workload/retrieval-contract-audit.json

reference-smoke:
	docker compose run --rm \
		-e REFERENCE_RUNTIME_BASE_URL=$(or $(REFERENCE_RUNTIME_BASE_URL),http://ollama:11434) \
		-e REFERENCE_MODEL_SMALL=$(REFERENCE_MODEL_SMALL) \
		-e REFERENCE_MODEL_MEDIUM=$(REFERENCE_MODEL_MEDIUM) \
		backend python -m app.reference_workload.cli run \
		--mode smoke \
		--matrix /workspace/reference_workload/runtime_matrix.json \
		--output /artifacts/reference-workload/runtime-matrix-smoke.json

reference-run:
	docker compose run --rm \
		-e REFERENCE_RUNTIME_BASE_URL=$(or $(REFERENCE_RUNTIME_BASE_URL),http://ollama:11434) \
		-e REFERENCE_MODEL_SMALL=$(REFERENCE_MODEL_SMALL) \
		-e REFERENCE_MODEL_MEDIUM=$(REFERENCE_MODEL_MEDIUM) \
		backend python -m app.reference_workload.cli run \
		--mode portfolio \
		--matrix /workspace/reference_workload/runtime_matrix.json \
		--output /artifacts/reference-workload/runtime-matrix-portfolio.json

reference-compare:
	docker compose run --rm backend python -m app.reference_workload.cli compare-runtime \
		--input /artifacts/reference-workload/runtime-matrix-portfolio.json

reference-gate:
	docker compose run --rm backend python -m app.reference_workload.cli gate

reference-report:
	docker compose run --rm backend python -m app.reference_workload.cli report \
		--output-directory /artifacts/reference-workload
