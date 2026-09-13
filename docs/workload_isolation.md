# Tool And RAG Workload Isolation

Updated: 2026-07-20, Sprint 5F

## Purpose

Tool and RAG evaluation must not inherit unrestricted network, credential, filesystem, or process
access. Sprint 5F adds a versioned policy registry and a fail-closed execution preflight, plus a
Docker enforcement example for the host boundary.

## Policies

| Policy | Workload | Network | Credentials | Filesystem |
| --- | --- | --- | --- | --- |
| `tool-offline-strict` | Tool | none | none | ephemeral write only under `/tmp/model-atlas` |
| `rag-readonly-internal` | RAG | `ollama`, `vllm` only | none | read-only app/data plus bounded tmpfs |
| `tool-rag-internal-authenticated` | Tool/RAG | `ollama`, `vllm` only | `OPENAI_COMPATIBLE_API_KEY` reference only | read-only app/data plus bounded tmpfs |

Every policy also fixes allowed tools, subprocess permission, maximum execution time, and maximum
output bytes. All bundled policies block subprocess execution.

## Enforcement Flow

`BenchmarkExecutionCreate` accepts an optional `isolation_policy_id`. Before a Tool or RAG case is
executed, the benchmark service derives requested tools, runtime host, secret environment
references, read/write paths, and subprocess intent. `execution_isolation_preflights()` evaluates
each workload kind and raises a domain error before adapter or handler execution when any boundary
is violated. The accepted normalized preflight is persisted in run configuration for audit.

APIs:

- `GET /api/v1/isolation/policies`;
- `POST /api/v1/isolation/preflight`.

The UI at `/isolation` exposes the effective policy registry.

## Docker Enforcement Example

`deploy/isolation/docker-compose.isolation.yml` demonstrates a second enforcement layer:

- read-only root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- no network for Tool evaluation;
- an internal-only runtime network for RAG;
- read-only RAG data mount;
- bounded `noexec,nosuid` tmpfs.

Validate and run with:

```bash
make isolation-test
```

The application policy is a deterministic admission control and the Docker file is a deployable
example. The main Compose stack does not launch every benchmark in a fresh sandbox container.
Production hardening should add per-job orchestration, seccomp/AppArmor or Kubernetes policies,
egress DNS/IP enforcement, short-lived workload identity, resource quotas, and audit collection
from the operating-system boundary.

