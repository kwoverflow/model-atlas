# Executable Tool Calling Evaluation

Sprint 4B evaluates whether a model can select, parameterize, and sequence tools whose behavior is
actually executed inside a bounded local registry. It extends benchmark evidence; it does not grant
an agent permission to operate production systems.

## Evaluation Flow

```mermaid
flowchart LR
    A["Versioned Tool Case"] --> B["Inference Adapter"]
    B --> C["JSON Call Parser"]
    C --> D["Selection Validation"]
    D --> E["Argument Validation"]
    E --> F["Local Tool Handler"]
    F --> G["Attempt and Retry Trace"]
    G --> H["Executable Tool Scorer"]
    H --> I["Tool Metrics"]
    I --> J["Deployment Gate"]
    J --> K["Release and Audit Flow"]
```

The inference adapter proposes calls. The benchmark service owns execution. The Gate consumes only
the stored result, trace, and metrics.

## Registry Boundary

The `local-tool-registry-v1` registry contains:

| Tool | Behavior | Side effect |
| --- | --- | --- |
| `lookup_internal_document` | Returns an in-memory document fixture | none |
| `lookup_policy` | Returns a local release policy fixture | none |
| `search_incidents` | Searches deterministic incident records | none |
| `create_ticket` | Returns a deterministic simulated ticket ID | simulated |
| `lookup_customer` | Returns a customer contract fixture | none |
| `summarize_thread` | Summarizes supplied local text and prior-step count | none |

Handlers cannot access the network, filesystem, subprocesses, credentials, or production services.
An unknown or unexpected tool is skipped before invocation.

## Case Contract

Single-step example:

```json
{
  "tool_name": "search_incidents",
  "arguments": {
    "type": "object",
    "required": ["query"],
    "properties": {
      "query": {"type": "string"},
      "simulate_failure": {
        "type": "string",
        "enum": ["transient_once", "permanent"]
      }
    },
    "additionalProperties": false
  },
  "example_arguments": {
    "query": "Find retry-related incidents",
    "simulate_failure": "transient_once"
  },
  "max_attempts": 2
}
```

Multi-step example:

```json
{
  "expected_sequence": [
    {"tool_name": "lookup_customer", "arguments": {"type": "object"}},
    {"tool_name": "lookup_policy", "arguments": {"type": "object"}},
    {"tool_name": "summarize_thread", "arguments": {"type": "object"}}
  ]
}
```

The mock adapter uses `example_arguments` to make the deterministic integration path reproducible.
Real model outputs are evaluated from their emitted arguments.

## Accepted Output Shapes

Single call:

```json
{"tool_name": "lookup_policy", "arguments": {"query": "release"}}
```

Multiple calls:

```json
{
  "tool_calls": [
    {"tool_name": "lookup_customer", "arguments": {"query": "C-001"}},
    {"tool_name": "summarize_thread", "arguments": {"query": "status"}}
  ]
}
```

OpenAI-native response-shaped calls with `function.name` and JSON-string `function.arguments` are
normalized to the same internal representation.

## Execution Rules

1. A case can emit at most eight tool calls.
2. A step can attempt execution at most three times.
3. The expected tool and registered tool must match.
4. Arguments must satisfy both registry and case schemas.
5. Invalid selection or arguments cause a skipped step, not an invocation.
6. Only retryable errors can consume another attempt.
7. Output must satisfy the tool descriptor output schema.
8. Prior successful outputs are available to later in-process handlers as context.

`transient_once` and `permanent` are deterministic fixture failure modes. They are not model-facing
production controls.

## Stored Trace

`BenchmarkResult.metadata_json.tool_execution` stores:

- `tool-execution-trace-v1` and registry version;
- parse, call, and sequence validity;
- expected and actual tool sequences;
- selection, argument, execution, and retry-recovery rates;
- each call's arguments, attempts, output, failure type, and duration;
- final success, partial-failure, failure, or invalid-call status.

Execution logs receive one summary event per tool step and one completion event per tool case.
Snapshot provenance aggregates the registry and trace versions.

## Gate Metrics

| Metric | Meaning |
| --- | --- |
| `tool_selection_accuracy` | Expected selection match across calls |
| `tool_argument_validity_rate` | Registry and case argument validation rate |
| `tool_execution_success_rate` | Successfully executed and output-valid calls |
| `tool_sequence_success_rate` | Exact expected-order match across tool cases |
| `tool_retry_recovery_rate` | Recovered calls among calls that retried |

The seeded **Executable Tool Calling Policy** requires perfect selection, argument, and sequence
evidence, at least 95% execution success, and successful recovery for the seeded retry case.
Critical tool failure also participates in the existing critical-case blocker.

## APIs

- `GET /api/v1/benchmark-executions/tool-registry`
- `POST /api/v1/benchmark-executions`
- `GET /api/v1/benchmark-executions/{benchmark_run_id}`
- `GET /api/v1/benchmark-executions/{benchmark_run_id}/logs`
- `POST /api/v1/deployment-gates/preflight`
- `POST /api/v1/deployment-gates/evaluations`

## Reproducible Run

```bash
make seed
make seed-tool-calling
```

In Benchmark Execution choose:

- suite: `Executable Tool Calling Evaluation Suite`;
- task: `Tool calling`;
- adapter: `mock` for deterministic verification or `openai_compatible` for a local model;
- data source: `local_authored`.

After execution, open **Inspect Tool Trace**. In Deployment Gates, select the same suite and the
`Executable Tool Calling Policy`, review Preflight, and evaluate the Gate.

## Limitations

- The schema validator intentionally supports the object, array, primitive type, required,
  properties, enum, string-length, items, and additional-properties subset used by current tools.
- Retry execution is synchronous; there is no background queue or distributed worker.
- Durations measure in-process fixture execution, not remote service latency.
- The pack does not continue a model conversation after receiving tool output.
- Production-connected tools require a separate security and authorization design.
