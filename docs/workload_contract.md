# Workload Contract

A workload contract defines what a local AI configuration must do before deployment approval is possible.

## Workload Profile

`WorkloadProfile` defines the operational scope:

- intended workload name and slug;
- domain;
- primary language;
- local-only requirement;
- data classification;
- expected output modes;
- risk notes;
- active status.

Example: `Korean Internal Document Assistant`.

## Evaluation Suite

`EvaluationSuite` is a versioned set of cases for one workload.

Important fields:

- `version_label`;
- `suite_hash`;
- `status`;
- `dataset_source`;
- `is_synthetic`.

Changing the suite version or case set should create a new suite version instead of silently changing past decisions.

## Evaluation Case

`EvaluationCase` defines a reproducible test case.

Important fields:

- external case ID;
- category;
- input payload;
- expected output;
- reference context;
- expected tool schema;
- tags;
- criticality;
- weight;
- active status;
- data source.

Criticality values are:

- `critical`
- `standard`
- `exploratory`

Critical cases are zero-tolerance for approval when they fail.

## Metric Definition

`MetricDefinition` gives policy rules a stable metric key and meaning.

Metric domains include:

- quality;
- reliability;
- performance;
- resource;
- governance;
- evidence.

The calculation version is stored so future metric changes can be audited.

## Acceptance Policy

`AcceptancePolicy` is a versioned business rule set for one workload. It stores a policy hash and `allow_conditional`.

`AcceptancePolicyRule` defines:

- metric key;
- operator;
- threshold;
- severity;
- minimum sample size;
- required flag;
- failure message.

Severity values are:

- `blocker`
- `warning`

## Deployment Configuration

`DeploymentConfiguration` is the immutable candidate being evaluated.

It includes:

- workload;
- hardware profile;
- model artifact;
- runtime and runtime version;
- runtime config;
- context length;
- generation config;
- prompt bundle;
- output schema version;
- tool schema version;
- retrieval config;
- concurrency target;
- configuration hash.

The hash is generated from canonical JSON over semantic configuration fields. Changing relevant fields changes the hash.

## Decision Record

`GateEvaluation` is the decision record. It links the deployment configuration, suite, policy, optional baseline, evidence snapshot, scorecard, verdict, summary, and decision hash.

`GateRuleResult` stores the auditable outcome of each policy rule.

`DeploymentBaseline` records which approved gate evaluation is the active comparison point for a
deployment configuration, suite, and policy scope. Promoting a new baseline supersedes the previous
active baseline in that scope.

This structure lets a reviewer answer:

```text
What was evaluated?
Against which workload and policy?
Which benchmark runs were used?
Which rules passed, failed, or lacked evidence?
Why was the candidate not approved?
```
