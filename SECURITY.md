# Security Boundaries

Model Atlas is a local evaluation MVP. It has not received a production security audit.
Do not expose the review Compose stack to the Internet. Its fixed development credentials
and trusted operator headers exist for localhost mock demonstrations, not production identity.

Do not put credentials, private signing keys, user data, model weights, database exports, or
raw production logs in issues, pull requests, or review ZIPs. Use synthetic/redacted reproductions.
If a real secret is exposed, revoke it; removing a file from the latest commit is not sufficient.

The publication scanner detects selected token/private-key patterns and prohibited paths.
A successful scan does not prove the absence of secrets, personal data, or vulnerabilities.
Frontend dependency auditing is also not a complete application security assessment.

Use GitHub's private vulnerability reporting when enabled for this repository. Otherwise,
open a minimal issue requesting a private reporting route without publishing exploit details
or sensitive data. No response-time or production support commitment is provided.
