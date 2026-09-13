# Report Source And QA Notes

- Audience: technical. The main purpose is measurement design and validation, not model ranking.
- Delivery: canonical MCP report; no parallel HTML/Sites publication. The artifact passed the
  source-aware validator and was submitted to the report renderer. Visual inspection of the
  in-app MCP surface is not available through the local browser tools; no pixel QA is claimed.
- Structure: title, technical summary, definitions before the chart, findings and exact table,
  paired-fault experiment, method, independent validation, limitations, next steps, questions.
  Definitions precede findings so that execution and exact-value accuracy cannot be confused.
- Chart contract: one native vertical bar chart of exact-call rate by three configurations.
  Fractional rates; a single series; no redundant grouping or legend. Dataset also retains all
  numerators, denominators, selection, eligibility, execution, and mismatch counts for audit.
- Tables: three configuration rows for exact stage counts and three environment rows for paired
  execution counts. Explicit initial sort; no movement colors. Counts are not independent samples.
- No time trend, causal estimate, confidence interval, or latency ranking is shown. There is one
  narrow local run with two zero-temperature trials; those visuals would suggest unsupported scope.
- Required source: captured local runtime artifact and its observation journal. No external
  business data, connected account, or web source is needed. Existing documentation supplies
  protocol history only; old repaired/legacy recovery totals are not comparison observations.
- Independent checks: executed `reproduce.ipynb` reconciles source hashes, request hashes, journal
  rows, coverage/uniqueness, exact arguments, paired traces, and handler/fault counts using SQLite.
- Caveats remain visible: local unreviewed cases, explicit-value copying, deterministic handlers,
  no ACL/content validation, declared context lengths, and executor-controlled retries.
- Official Gate state is reported in the technical guide from a separate read-only overview check;
  it is not mixed into the chart's diagnostic source or its denominators.
