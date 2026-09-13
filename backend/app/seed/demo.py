from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    BenchmarkExecutionLog,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    GateEvaluation,
    GateRuleResult,
    HardwareProfile,
    InferenceMetric,
    MetricDefinition,
    Model,
    ModelArtifact,
    PromptVersion,
    WorkloadProfile,
)
from app.schemas import GateEvaluationCreate
from app.services.deployment_gate.evaluator import create_gate_evaluation
from app.services.deployment_gate.evidence import deployment_configuration_hash, stable_hash

DATA_SOURCE = "synthetic_demo"
CAPTURED_DEMO_SOURCE = "captured_demo"
HARDWARE_NAME = "RTX 4080 Super Local Workstation"
MODEL_NAMES = ["llama-3.1-8b-instruct", "qwen2.5-7b-instruct", "gemma-2-9b-it"]
ARTIFACT_NAMES = [
    "llama-3.1-8b-instruct-fp16",
    "llama-3.1-8b-instruct-q4_k_m",
    "qwen2.5-7b-instruct-bf16",
    "qwen2.5-7b-instruct-int4",
    "gemma-2-9b-it-fp16",
]
TASK_NAMES = [
    "Korean document QA",
    "Structured JSON generation",
    "Tool calling",
    "Latency smoke test",
]
WORKLOAD_SLUG = "korean-document-assistant"
SUITE_NAME = "Korean Operations Assistant Acceptance Suite"
TOOL_SUITE_NAME = "Executable Tool Calling Evaluation Suite"
TOOL_POLICY_NAME = "Executable Tool Calling Policy"
RAG_SUITE_NAME = "RAG Grounded Answer Evaluation Suite"
RAG_POLICY_NAME = "RAG Grounded Answer Policy"
RAG_DEPLOYMENT_NAME = "Qwen2.5 7B Local RAG Assistant"
RELIABILITY_SUITE_NAME = "Runtime Reliability Evaluation Suite"
RELIABILITY_POLICY_NAME = "Runtime Reliability Policy"
RELIABILITY_DEPLOYMENT_NAMES = [
    "Qwen2.5 7B Reliability Runtime A",
    "Qwen2.5 7B Reliability Runtime B",
]
AGENT_SUITE_NAME = "Bounded Agent Operations Evaluation Suite"
AGENT_POLICY_NAME = "Bounded Agent Operations Policy"
AGENT_DEPLOYMENT_NAME = "Qwen2.5 7B Bounded Operations Agent"
ADAPTIVE_AGENT_SUITE_NAME = "Adaptive Agent Operations Evaluation Suite"
ADAPTIVE_AGENT_POLICY_NAME = "Adaptive Agent Operations Policy"
ADAPTIVE_AGENT_DEPLOYMENT_NAME = "Qwen2.5 7B Adaptive Operations Agent"
POLICY_NAMES = [
    "Strict Local Release Policy",
    "Demo Policy",
    TOOL_POLICY_NAME,
    RAG_POLICY_NAME,
    RELIABILITY_POLICY_NAME,
    AGENT_POLICY_NAME,
    ADAPTIVE_AGENT_POLICY_NAME,
]
DEPLOYMENT_NAMES = [
    "Qwen2.5 7B Local Document Assistant",
    RAG_DEPLOYMENT_NAME,
    *RELIABILITY_DEPLOYMENT_NAMES,
    AGENT_DEPLOYMENT_NAME,
    ADAPTIVE_AGENT_DEPLOYMENT_NAME,
]
EXTENSION_SUITE_NAMES = [
    TOOL_SUITE_NAME,
    RAG_SUITE_NAME,
    RELIABILITY_SUITE_NAME,
    AGENT_SUITE_NAME,
    ADAPTIVE_AGENT_SUITE_NAME,
]
METRIC_KEYS = [
    "mean_quality_score",
    "json_validity_rate",
    "tool_call_validity_rate",
    "tool_selection_accuracy",
    "tool_argument_validity_rate",
    "tool_execution_success_rate",
    "tool_sequence_success_rate",
    "tool_retry_recovery_rate",
    "rag_retrieval_recall",
    "rag_citation_precision",
    "rag_citation_recall",
    "rag_groundedness_score",
    "rag_unsupported_claim_rate",
    "reliability_success_rate",
    "reliability_timeout_rate",
    "reliability_oom_rate",
    "p99_end_to_end_latency_ms",
    "latency_variation_coefficient",
    "trial_coverage_rate",
    "context_stress_success_rate",
    "agent_task_success_rate",
    "agent_plan_validity_rate",
    "agent_step_success_rate",
    "agent_action_sequence_accuracy",
    "agent_policy_violation_rate",
    "agent_final_response_rate",
    "agent_memory_provenance_rate",
    "agent_tool_retry_recovery_rate",
    "agent_replan_success_rate",
    "agent_recovery_step_success_rate",
    "agent_approval_compliance_rate",
    "agent_approval_provenance_rate",
    "agent_pending_approval_rate",
    "agent_observation_coverage_rate",
    "agent_unrecovered_failure_rate",
    "groundedness_score",
    "faithfulness_score",
    "critical_case_failure_rate",
    "p50_end_to_end_latency_ms",
    "p95_end_to_end_latency_ms",
    "p95_ttft_ms",
    "mean_tokens_per_second",
    "p95_gpu_vram_used_mb",
    "oom_rate",
    "real_case_count",
    "critical_case_count",
    "quality_regression_vs_baseline",
    "latency_regression_vs_baseline",
]


@dataclass(frozen=True)
class SeedSummary:
    hardware_profiles: int
    models: int
    model_artifacts: int
    benchmark_tasks: int
    prompt_versions: int
    benchmark_runs: int
    benchmark_results: int
    inference_metrics: int
    workload_profiles: int = 0
    evaluation_suites: int = 0
    evaluation_cases: int = 0
    metric_definitions: int = 0
    acceptance_policies: int = 0
    deployment_configurations: int = 0
    gate_evaluations: int = 0


def _hash_prompt(system_prompt: str, user_template: str) -> str:
    payload = f"{system_prompt}\n---\n{user_template}".encode()
    return hashlib.sha256(payload).hexdigest()


def reset_synthetic_data(db: Session) -> None:
    demo_deployment_ids = select(DeploymentConfiguration.id).where(
        DeploymentConfiguration.name.in_(DEPLOYMENT_NAMES)
    )
    demo_run_ids = select(BenchmarkRun.id).where(
        (BenchmarkRun.data_source == DATA_SOURCE)
        | (BenchmarkRun.deployment_configuration_id.in_(demo_deployment_ids))
    )
    db.execute(delete(GateRuleResult))
    db.execute(delete(GateEvaluation))
    db.execute(delete(BenchmarkExecutionLog).where(BenchmarkExecutionLog.benchmark_run_id.in_(demo_run_ids)))
    db.execute(delete(InferenceMetric).where(InferenceMetric.benchmark_run_id.in_(demo_run_ids)))
    db.execute(delete(BenchmarkResult).where(BenchmarkResult.benchmark_run_id.in_(demo_run_ids)))
    db.execute(delete(BenchmarkRun).where(BenchmarkRun.id.in_(demo_run_ids)))
    db.execute(delete(AcceptancePolicyRule))
    db.execute(delete(AcceptancePolicy).where(AcceptancePolicy.name.in_(POLICY_NAMES)))
    db.execute(delete(MetricDefinition).where(MetricDefinition.key.in_(METRIC_KEYS)))
    db.execute(
        delete(DeploymentConfiguration).where(
            DeploymentConfiguration.name.in_(DEPLOYMENT_NAMES)
        )
    )
    db.execute(delete(EvaluationCase).where(EvaluationCase.data_source == DATA_SOURCE))
    extension_suite_ids = select(EvaluationSuite.id).where(
        EvaluationSuite.name.in_(EXTENSION_SUITE_NAMES)
    )
    db.execute(
        delete(EvaluationCase).where(
            EvaluationCase.evaluation_suite_id.in_(extension_suite_ids)
        )
    )
    db.execute(
        delete(EvaluationSuite).where(EvaluationSuite.name.in_(EXTENSION_SUITE_NAMES))
    )
    db.execute(delete(EvaluationSuite).where(EvaluationSuite.name == SUITE_NAME))
    db.execute(delete(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    db.execute(delete(PromptVersion).where(PromptVersion.version_label == "synthetic-demo-v1"))
    db.execute(delete(BenchmarkTask).where(BenchmarkTask.name.in_(TASK_NAMES)))
    db.execute(delete(ModelArtifact).where(ModelArtifact.artifact_name.in_(ARTIFACT_NAMES)))
    db.execute(delete(Model).where(Model.name.in_(MODEL_NAMES)))
    db.execute(delete(HardwareProfile).where(HardwareProfile.name == HARDWARE_NAME))
    db.commit()


def seed_demo_data(db: Session) -> SeedSummary:
    reset_synthetic_data(db)

    hardware = HardwareProfile(
        name=HARDWARE_NAME,
        cpu_name="Intel Core i9-13900K",
        cpu_cores=24,
        ram_gb=64,
        gpu_name="RTX 4080 Super",
        gpu_vram_gb=16,
        gpu_count=1,
        os_name="Windows 11 / WSL2 compatible",
        cuda_version="12.4",
        driver_version="synthetic-local-driver",
        notes="Primary local workstation profile from the Sprint 1 prompt.",
    )
    db.add(hardware)

    model_records = [
        Model(
            provider="Meta",
            family="Llama",
            name="llama-3.1-8b-instruct",
            display_name="Llama 3.1 8B Instruct",
            parameter_count_b=8.0,
            architecture_type="decoder-only transformer",
            supports_text=True,
            supports_vision=False,
            supports_tool_calling=True,
            supports_structured_output=True,
            context_length=128000,
            license_name="Llama 3.1 Community License",
            commercial_use_allowed=True,
            primary_languages=["en", "ko"],
            source_url="https://huggingface.co/meta-llama",
            notes="Synthetic benchmark metadata for local portfolio demonstration.",
        ),
        Model(
            provider="Alibaba",
            family="Qwen",
            name="qwen2.5-7b-instruct",
            display_name="Qwen2.5 7B Instruct",
            parameter_count_b=7.0,
            architecture_type="decoder-only transformer",
            supports_text=True,
            supports_vision=False,
            supports_tool_calling=True,
            supports_structured_output=True,
            context_length=131072,
            license_name="Apache-2.0",
            commercial_use_allowed=True,
            primary_languages=["en", "ko", "zh"],
            source_url="https://huggingface.co/Qwen",
            notes="Synthetic benchmark metadata for local portfolio demonstration.",
        ),
        Model(
            provider="Google",
            family="Gemma",
            name="gemma-2-9b-it",
            display_name="Gemma 2 9B IT",
            parameter_count_b=9.0,
            architecture_type="decoder-only transformer",
            supports_text=True,
            supports_vision=False,
            supports_tool_calling=False,
            supports_structured_output=True,
            context_length=8192,
            license_name="Gemma Terms of Use",
            commercial_use_allowed=True,
            primary_languages=["en", "ko"],
            source_url="https://huggingface.co/google",
            notes="Synthetic benchmark metadata for local portfolio demonstration.",
        ),
    ]
    db.add_all(model_records)
    db.flush()
    models_by_name = {model.name: model for model in model_records}

    artifact_records = [
        ModelArtifact(
            model_id=models_by_name["llama-3.1-8b-instruct"].id,
            artifact_name="llama-3.1-8b-instruct-fp16",
            format="safetensors",
            quantization=None,
            precision="fp16",
            file_size_gb=16.1,
            minimum_vram_gb=15.5,
            recommended_vram_gb=16,
            context_limit=32768,
            runtime_compatibility=["transformers", "vllm-future"],
            checksum="synthetic-checksum-llama-fp16",
            is_active=True,
            notes="Synthetic demonstration artifact; no real weights are included.",
        ),
        ModelArtifact(
            model_id=models_by_name["llama-3.1-8b-instruct"].id,
            artifact_name="llama-3.1-8b-instruct-q4_k_m",
            format="gguf",
            quantization="Q4_K_M",
            precision="int4",
            file_size_gb=4.9,
            minimum_vram_gb=6,
            recommended_vram_gb=8,
            context_limit=32768,
            runtime_compatibility=["llama.cpp", "ollama-future"],
            checksum="synthetic-checksum-llama-q4",
            is_active=True,
            notes="Synthetic demonstration artifact; no real weights are included.",
        ),
        ModelArtifact(
            model_id=models_by_name["qwen2.5-7b-instruct"].id,
            artifact_name="qwen2.5-7b-instruct-bf16",
            format="safetensors",
            quantization=None,
            precision="bf16",
            file_size_gb=14.2,
            minimum_vram_gb=14,
            recommended_vram_gb=16,
            context_limit=32768,
            runtime_compatibility=["transformers", "vllm-future"],
            checksum="synthetic-checksum-qwen-bf16",
            is_active=True,
            notes="Synthetic demonstration artifact; no real weights are included.",
        ),
        ModelArtifact(
            model_id=models_by_name["qwen2.5-7b-instruct"].id,
            artifact_name="qwen2.5-7b-instruct-int4",
            format="awq",
            quantization="AWQ",
            precision="int4",
            file_size_gb=4.6,
            minimum_vram_gb=6,
            recommended_vram_gb=8,
            context_limit=32768,
            runtime_compatibility=["transformers", "exllama-future"],
            checksum="synthetic-checksum-qwen-int4",
            is_active=True,
            notes="Synthetic demonstration artifact; no real weights are included.",
        ),
        ModelArtifact(
            model_id=models_by_name["gemma-2-9b-it"].id,
            artifact_name="gemma-2-9b-it-fp16",
            format="safetensors",
            quantization=None,
            precision="fp16",
            file_size_gb=18.0,
            minimum_vram_gb=15,
            recommended_vram_gb=16,
            context_limit=8192,
            runtime_compatibility=["transformers"],
            checksum="synthetic-checksum-gemma-fp16",
            is_active=True,
            notes="Synthetic demonstration artifact; no real weights are included.",
        ),
    ]
    db.add_all(artifact_records)
    db.flush()
    artifacts_by_name = {artifact.artifact_name: artifact for artifact in artifact_records}

    task_records = [
        BenchmarkTask(
            name="Korean document QA",
            category="quality",
            description="Answer Korean document questions with faithful, concise responses.",
            task_type="qa",
            language="ko",
            input_format="document_plus_question",
            expected_output_format="short_answer",
            scoring_method="synthetic rubric score",
            dataset_version="synthetic-ko-docqa-v1",
            is_active=True,
        ),
        BenchmarkTask(
            name="Structured JSON generation",
            category="format_following",
            description="Generate valid JSON matching a requested schema.",
            task_type="json_generation",
            language="en",
            input_format="instruction",
            expected_output_format="json_object",
            scoring_method="json validity plus rubric score",
            dataset_version="synthetic-json-v1",
            is_active=True,
        ),
        BenchmarkTask(
            name="Tool calling",
            category="tool_use",
            description="Select a tool and return structured arguments.",
            task_type="tool_call",
            language="en",
            input_format="instruction_with_tool_spec",
            expected_output_format="tool_call_json",
            scoring_method="tool-call validity plus rubric score",
            dataset_version="synthetic-tool-v1",
            is_active=True,
        ),
        BenchmarkTask(
            name="Latency smoke test",
            category="performance",
            description="Short prompt response used to compare local latency metrics.",
            task_type="latency",
            language="en",
            input_format="short_prompt",
            expected_output_format="plain_text",
            scoring_method="completion success",
            dataset_version="synthetic-latency-v1",
            is_active=True,
        ),
    ]
    db.add_all(task_records)
    db.flush()
    tasks_by_name = {task.name: task for task in task_records}

    prompt_records: list[PromptVersion] = []
    for task in task_records:
        system_prompt = (
            f"You are evaluating {task.name}. Return synthetic demonstration output only."
        )
        user_template = f"Task input for {task.name}: {{input}}"
        output_schema: dict[str, Any] | None = None
        if task.name == "Structured JSON generation":
            output_schema = {"type": "object", "required": ["answer", "confidence"]}
        if task.name == "Tool calling":
            output_schema = {"type": "object", "required": ["tool_name", "arguments"]}
        prompt_records.append(
            PromptVersion(
                name=f"{task.name} prompt",
                benchmark_task_id=task.id,
                system_prompt=system_prompt,
                user_template=user_template,
                output_schema=output_schema,
                prompt_hash=_hash_prompt(system_prompt, user_template),
                version_label="synthetic-demo-v1",
                is_active=True,
                notes="Synthetic prompt version for Sprint 1 local dashboard data.",
            )
        )
    db.add_all(prompt_records)
    db.flush()
    prompts_by_task_id = {prompt.benchmark_task_id: prompt for prompt in prompt_records}

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    run_specs = [
        ("llama-3.1-8b-instruct-q4_k_m", "Korean document QA", "llama.cpp", 91, 0.83),
        ("llama-3.1-8b-instruct-q4_k_m", "Structured JSON generation", "llama.cpp", 92, 0.88),
        ("qwen2.5-7b-instruct-int4", "Tool calling", "transformers", 93, 0.9),
        ("gemma-2-9b-it-fp16", "Latency smoke test", "transformers", 94, 0.78),
        ("qwen2.5-7b-instruct-bf16", "Korean document QA", "transformers", 95, 0.86),
        ("llama-3.1-8b-instruct-fp16", "Structured JSON generation", "transformers", 96, 0.91),
    ]

    run_records: list[BenchmarkRun] = []
    for index, (
        artifact_name,
        task_name,
        runtime_name,
        seed,
        _quality_base,
    ) in enumerate(run_specs):
        task = tasks_by_name[task_name]
        started_at = now - dt.timedelta(hours=6 - index)
        run_records.append(
            BenchmarkRun(
                hardware_profile_id=hardware.id,
                model_artifact_id=artifacts_by_name[artifact_name].id,
                benchmark_task_id=task.id,
                prompt_version_id=prompts_by_task_id[task.id].id,
                runtime_name=runtime_name,
                runtime_version="synthetic-demo-0.1",
                runtime_config_json={
                    "temperature": 0,
                    "max_tokens": 512,
                    "batch_size": 1,
                    "synthetic": True,
                },
                dataset_version=task.dataset_version,
                seed=seed,
                started_at=started_at,
                completed_at=started_at + dt.timedelta(minutes=7),
                status="completed",
                failure_reason=None,
                data_source=DATA_SOURCE,
            )
        )
    db.add_all(run_records)
    db.flush()

    metric_profiles = {
        "llama-3.1-8b-instruct-q4_k_m": (190, 1180, 48, 7800),
        "qwen2.5-7b-instruct-int4": (210, 1320, 44, 8200),
        "gemma-2-9b-it-fp16": (285, 1680, 31, 15400),
        "qwen2.5-7b-instruct-bf16": (250, 1510, 35, 15050),
        "llama-3.1-8b-instruct-fp16": (245, 1440, 38, 15100),
    }
    artifacts_by_id = {artifact.id: artifact for artifact in artifact_records}

    result_records: list[BenchmarkResult] = []
    metric_records: list[InferenceMetric] = []
    for run_index, run in enumerate(run_records):
        task = tasks_by_name[run_specs[run_index][1]]
        artifact = artifacts_by_id[run.model_artifact_id]
        quality_base = run_specs[run_index][4]
        ttft_base, latency_base, tps_base, vram_base = metric_profiles[artifact.artifact_name]
        for sample_index in range(1, 6):
            sample_id = f"{task.dataset_version}-sample-{sample_index:02d}"
            quality = max(0, min(1, quality_base + (sample_index - 3) * 0.015))
            json_valid = task.name in ("Structured JSON generation", "Tool calling")
            tool_call_valid = task.name == "Tool calling"
            if tool_call_valid:
                normalized_output = json.dumps(
                    {
                        "tool_name": "lookup_benchmark_case",
                        "arguments": {"sample_id": sample_id},
                        "synthetic": True,
                    }
                )
            elif json_valid:
                normalized_output = json.dumps(
                    {
                        "answer": f"synthetic structured answer {sample_index}",
                        "confidence": round(quality, 2),
                    }
                )
            else:
                normalized_output = f"synthetic answer {sample_index}"

            result_records.append(
                BenchmarkResult(
                    benchmark_run_id=run.id,
                    sample_id=sample_id,
                    quality_score=round(quality, 3),
                    exact_match=quality >= 0.85,
                    json_valid=json_valid,
                    tool_call_valid=tool_call_valid,
                    groundedness_score=round(max(0, quality - 0.03), 3),
                    faithfulness_score=round(max(0, quality - 0.02), 3),
                    human_label="synthetic-pass" if quality >= 0.8 else "synthetic-review",
                    error_type=None,
                    raw_output=normalized_output,
                    normalized_output=normalized_output,
                    metadata_json={
                        "synthetic": True,
                        "rubric_version": "demo-rubric-v1",
                        "data_source": DATA_SOURCE,
                    },
                    data_source=DATA_SOURCE,
                )
            )
            metric_records.append(
                InferenceMetric(
                    benchmark_run_id=run.id,
                    sample_id=sample_id,
                    ttft_ms=ttft_base + sample_index * 7,
                    end_to_end_latency_ms=latency_base + sample_index * 41,
                    prompt_tokens=240 + sample_index * 9,
                    completion_tokens=96 + sample_index * 6,
                    tokens_per_second=tps_base - sample_index * 0.7,
                    gpu_vram_used_mb=vram_base + sample_index * 38,
                    gpu_utilization_pct=64 + sample_index * 2,
                    cpu_utilization_pct=21 + sample_index,
                    peak_memory_mb=22000 + sample_index * 75,
                    oom_occurred=False,
                    retry_count=0,
                    data_source=DATA_SOURCE,
                )
            )

    db.add_all(result_records)
    db.add_all(metric_records)
    db.flush()

    workload = WorkloadProfile(
        name="Korean Internal Document Assistant",
        slug=WORKLOAD_SLUG,
        description=(
            "Local-only Korean internal document assistant requiring grounded answers, "
            "JSON output, and valid tool-call selection."
        ),
        domain="internal_operations",
        primary_language="ko",
        local_only_required=True,
        data_classification="internal",
        expected_output_modes_json=["grounded_answer", "json_object", "tool_call"],
        risk_notes="Synthetic demo workload; do not treat seeded evidence as real readiness.",
        is_active=True,
    )
    db.add(workload)
    db.flush()

    suite_payload = {
        "workload_profile_id": workload.id,
        "name": SUITE_NAME,
        "version_label": "v1",
        "description": "Synthetic Sprint 3A acceptance suite for a Korean operations assistant.",
        "status": "active",
        "dataset_source": DATA_SOURCE,
        "is_synthetic": True,
    }
    suite = EvaluationSuite(
        **suite_payload,
        suite_hash=stable_hash(suite_payload),
    )
    db.add(suite)
    db.flush()

    metric_specs = [
        ("mean_quality_score", "Mean quality score", "quality", "mean", "higher_is_better", None),
        (
            "json_validity_rate",
            "JSON validity rate",
            "reliability",
            "rate",
            "higher_is_better",
            None,
        ),
        (
            "tool_call_validity_rate",
            "Tool-call validity rate",
            "reliability",
            "rate",
            "higher_is_better",
            None,
        ),
        ("groundedness_score", "Groundedness score", "quality", "mean", "higher_is_better", None),
        ("faithfulness_score", "Faithfulness score", "quality", "mean", "higher_is_better", None),
        (
            "critical_case_failure_rate",
            "Critical case failure rate",
            "reliability",
            "rate",
            "lower_is_better",
            None,
        ),
        (
            "p50_end_to_end_latency_ms",
            "P50 end-to-end latency",
            "performance",
            "p50",
            "lower_is_better",
            "ms",
        ),
        (
            "p95_end_to_end_latency_ms",
            "P95 end-to-end latency",
            "performance",
            "p95",
            "lower_is_better",
            "ms",
        ),
        ("p95_ttft_ms", "P95 TTFT", "performance", "p95", "lower_is_better", "ms"),
        (
            "mean_tokens_per_second",
            "Mean tokens per second",
            "performance",
            "mean",
            "higher_is_better",
            "tokens/sec",
        ),
        (
            "p95_gpu_vram_used_mb",
            "P95 GPU VRAM used",
            "resource",
            "p95",
            "lower_is_better",
            "MB",
        ),
        ("oom_rate", "OOM rate", "resource", "rate", "lower_is_better", None),
        ("real_case_count", "Real case count", "evidence", "count", "higher_is_better", "cases"),
        (
            "critical_case_count",
            "Critical case count",
            "evidence",
            "count",
            "higher_is_better",
            "cases",
        ),
        (
            "quality_regression_vs_baseline",
            "Quality regression vs baseline",
            "quality",
            "mean",
            "higher_is_better",
            "delta",
        ),
        (
            "latency_regression_vs_baseline",
            "Latency regression vs baseline",
            "performance",
            "mean",
            "lower_is_better",
            "ms",
        ),
    ]
    metric_records_new = [
        MetricDefinition(
            key=key,
            display_name=display_name,
            domain=domain,
            aggregation=aggregation,
            direction=direction,
            unit=unit,
            description=f"{display_name} calculated by the Sprint 3A Deployment Gate.",
            calculation_version="deployment-gate-sprint-3a-v1",
            is_active=True,
        )
        for key, display_name, domain, aggregation, direction, unit in metric_specs
    ]
    db.add_all(metric_records_new)
    db.flush()
    metric_by_key = {metric.key: metric for metric in metric_records_new}

    case_records: list[EvaluationCase] = []
    case_specs: list[tuple[str, str, int]] = [
        ("json_extraction", "JSON extraction", 12),
        ("tool_selection", "Tool selection", 10),
        ("grounded_answer", "Grounded answer", 10),
        ("long_context_latency", "Long-context latency", 8),
    ]
    case_counter = 1
    for category, title_prefix, count in case_specs:
        for index in range(1, count + 1):
            criticality = "critical" if case_counter <= 10 else "standard"
            external_case_id = f"koda-{case_counter:03d}"
            case_records.append(
                EvaluationCase(
                    evaluation_suite_id=suite.id,
                    external_case_id=external_case_id,
                    category=category,
                    title=f"{title_prefix} case {index:02d}",
                    input_payload_json={
                        "language": "ko",
                        "prompt": f"synthetic Korean operations prompt {case_counter}",
                    },
                    expected_output_json={
                        "type": "object",
                        "required": ["answer", "evidence"],
                    }
                    if category in {"json_extraction", "grounded_answer"}
                    else None,
                    reference_context_json={
                        "document_id": f"synthetic-doc-{case_counter:03d}",
                        "facts": ["demo fact A", "demo fact B"],
                    },
                    expected_tool_schema_json={
                        "tool_name": "lookup_internal_document",
                        "required_arguments": ["document_id"],
                    }
                    if category == "tool_selection"
                    else None,
                    tags_json=[category, criticality, DATA_SOURCE],
                    criticality=criticality,
                    weight=1.5 if criticality == "critical" else 1.0,
                    is_active=True,
                    data_source=DATA_SOURCE,
                )
            )
            case_counter += 1
    db.add_all(case_records)
    db.flush()

    strict_policy_payload = {
        "workload_profile_id": workload.id,
        "name": "Strict Local Release Policy",
        "version_label": "v1",
        "description": "Strict local-only release policy for production deployment decisions.",
        "allow_conditional": True,
        "is_active": True,
    }
    demo_policy_payload = {
        "workload_profile_id": workload.id,
        "name": "Demo Policy",
        "version_label": "v1-demo",
        "description": "Dashboard demo policy that still cannot approve synthetic-only evidence.",
        "allow_conditional": True,
        "is_active": True,
    }
    strict_policy = AcceptancePolicy(
        **strict_policy_payload,
        policy_hash=stable_hash(strict_policy_payload),
    )
    demo_policy = AcceptancePolicy(
        **demo_policy_payload,
        policy_hash=stable_hash(demo_policy_payload),
    )
    db.add_all([strict_policy, demo_policy])
    db.flush()

    strict_rules = [
        ("json_validity_rate", "JSON validity must be at least 99%", "gte", 0.99, "blocker", 12),
        (
            "tool_call_validity_rate",
            "Tool-call validity must be at least 95%",
            "gte",
            0.95,
            "blocker",
            10,
        ),
        (
            "critical_case_failure_rate",
            "Critical cases must not fail",
            "eq",
            0.0,
            "blocker",
            10,
        ),
        ("p95_end_to_end_latency_ms", "P95 latency exceeds target", "lte", 5000, "warning", 8),
        ("oom_rate", "OOM must not occur", "eq", 0.0, "blocker", 40),
        ("p95_gpu_vram_used_mb", "VRAM headroom is too low", "lte", 14600, "warning", 40),
        ("real_case_count", "At least 30 real cases are required", "gte", 30, "blocker", None),
        (
            "critical_case_count",
            "At least 10 critical cases are required",
            "gte",
            10,
            "blocker",
            None,
        ),
    ]
    demo_rules = [
        ("json_validity_rate", "JSON validity should be at least 90%", "gte", 0.9, "blocker", 12),
        (
            "critical_case_failure_rate",
            "Critical cases must not fail",
            "eq",
            0.0,
            "blocker",
            10,
        ),
        ("p95_end_to_end_latency_ms", "Demo latency warning threshold", "lte", 1600, "warning", 8),
        (
            "real_case_count",
            "Synthetic-only evidence cannot approve deployment",
            "gte",
            30,
            "blocker",
            None,
        ),
    ]
    policy_rule_records: list[AcceptancePolicyRule] = []
    for policy, rule_specs in [(strict_policy, strict_rules), (demo_policy, demo_rules)]:
        for metric_key, rule_name, operator, threshold, severity, sample_size in rule_specs:
            policy_rule_records.append(
                AcceptancePolicyRule(
                    acceptance_policy_id=policy.id,
                    metric_definition_id=metric_by_key[metric_key].id,
                    rule_name=rule_name,
                    operator=operator,
                    threshold_value=threshold,
                    severity=severity,
                    minimum_sample_size=sample_size,
                    required=True,
                    enabled=True,
                    message_on_fail=rule_name,
                )
            )
    db.add_all(policy_rule_records)
    db.flush()

    deployment_payload = {
        "name": "Qwen2.5 7B Local Document Assistant",
        "workload_profile_id": workload.id,
        "hardware_profile_id": hardware.id,
        "model_artifact_id": artifacts_by_name["qwen2.5-7b-instruct-int4"].id,
        "runtime_name": "transformers",
        "runtime_version": "synthetic-demo-0.1",
        "runtime_config_json": {"device": "cuda", "local_only": True, "quantization": "int4"},
        "context_length": 32768,
        "generation_config_json": {"temperature": 0.1, "top_p": 0.9, "max_new_tokens": 1024},
        "prompt_bundle_json": {"bundle": "korean-document-assistant", "version": "v1"},
        "output_schema_version": "koda-output-v1",
        "tool_schema_version": "koda-tools-v1",
        "retrieval_config_json": {"mode": "not_implemented_sprint_3a"},
        "concurrency_target": 2,
        "status": "ready",
        "notes": "Synthetic Sprint 3A deployment configuration.",
    }
    deployment_config = DeploymentConfiguration(
        **deployment_payload,
        configuration_hash=deployment_configuration_hash(deployment_payload),
    )
    db.add(deployment_config)
    db.flush()

    gate_task = tasks_by_name["Korean document QA"]
    gate_run = BenchmarkRun(
        hardware_profile_id=hardware.id,
        model_artifact_id=artifacts_by_name["qwen2.5-7b-instruct-int4"].id,
        benchmark_task_id=gate_task.id,
        prompt_version_id=prompts_by_task_id[gate_task.id].id,
        deployment_configuration_id=deployment_config.id,
        evaluation_suite_id=suite.id,
        runtime_name="transformers",
        runtime_version="synthetic-demo-0.1",
        runtime_config_json=deployment_payload["runtime_config_json"],
        dataset_version="synthetic-koda-acceptance-v1",
        seed=301,
        started_at=now + dt.timedelta(minutes=10),
        completed_at=now + dt.timedelta(minutes=18),
        status="completed",
        failure_reason=None,
        data_source=DATA_SOURCE,
    )
    db.add(gate_run)
    db.flush()

    gate_results: list[BenchmarkResult] = []
    gate_metrics: list[InferenceMetric] = []
    for index, case in enumerate(case_records, start=1):
        sample_id = case.external_case_id
        is_tool = case.category == "tool_selection"
        is_json = case.category in {"json_extraction", "grounded_answer"}
        critical_failure = index in {3, 8}
        json_valid = is_json and not critical_failure
        tool_call_valid = is_tool and index != 14
        quality = 0.62 if critical_failure else 0.88 + (index % 5) * 0.01
        if is_tool:
            normalized_output = json.dumps(
                {
                    "tool_name": "lookup_internal_document",
                    "arguments": {"document_id": f"synthetic-doc-{index:03d}"},
                }
            )
        elif is_json:
            normalized_output = json.dumps(
                {
                    "answer": f"synthetic Korean answer {index}",
                    "evidence": [f"synthetic-doc-{index:03d}"],
                }
            )
        else:
            normalized_output = f"synthetic long-context answer {index}"
        gate_results.append(
            BenchmarkResult(
                benchmark_run_id=gate_run.id,
                evaluation_case_id=case.id,
                sample_id=sample_id,
                quality_score=round(quality, 3),
                exact_match=not critical_failure,
                json_valid=json_valid,
                tool_call_valid=tool_call_valid,
                groundedness_score=0.62 if critical_failure else 0.87,
                faithfulness_score=0.64 if critical_failure else 0.89,
                human_label="synthetic-fail" if critical_failure else "synthetic-pass",
                error_type="critical_grounding_failure" if critical_failure else None,
                raw_output=normalized_output,
                normalized_output=normalized_output,
                metadata_json={"synthetic": True, "gate_demo": True},
                data_source=DATA_SOURCE,
            )
        )
        gate_metrics.append(
            InferenceMetric(
                benchmark_run_id=gate_run.id,
                sample_id=sample_id,
                ttft_ms=180 + index * 3,
                end_to_end_latency_ms=980 + index * 55,
                prompt_tokens=600 + index * 12,
                completion_tokens=160 + index * 4,
                tokens_per_second=39 - (index % 4) * 0.8,
                gpu_vram_used_mb=9000 + index * 85,
                gpu_utilization_pct=70,
                cpu_utilization_pct=24,
                peak_memory_mb=24000 + index * 80,
                oom_occurred=False,
                retry_count=0,
                data_source=DATA_SOURCE,
            )
        )
    db.add_all(gate_results)
    db.add_all(gate_metrics)
    db.commit()

    create_gate_evaluation(
        db,
        GateEvaluationCreate(
            deployment_configuration_id=deployment_config.id,
            evaluation_suite_id=suite.id,
            acceptance_policy_id=strict_policy.id,
        ),
    )

    return SeedSummary(
        hardware_profiles=1,
        models=len(model_records),
        model_artifacts=len(artifact_records),
        benchmark_tasks=len(task_records),
        prompt_versions=len(prompt_records),
        benchmark_runs=len(run_records) + 1,
        benchmark_results=len(result_records) + len(gate_results),
        inference_metrics=len(metric_records) + len(gate_metrics),
        workload_profiles=1,
        evaluation_suites=1,
        evaluation_cases=len(case_records),
        metric_definitions=len(metric_records_new),
        acceptance_policies=2,
        deployment_configurations=1,
        gate_evaluations=1,
    )


def main() -> None:
    with SessionLocal() as db:
        summary = seed_demo_data(db)
    print(json.dumps(summary.__dict__, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
