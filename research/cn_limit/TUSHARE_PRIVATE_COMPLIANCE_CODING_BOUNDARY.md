# TuShare private-compliance coding boundary

This file exists to prevent a recurring architecture failure: coding agents must not turn
private licensing evidence into repository/runtime configuration.

Current company state: **TuShare compliance is Chairman-verified, private, and satisfied.**

The controlling agreement is deliberately unavailable to coding sessions because of
confidentiality/NDA and privacy constraints. Its absence from the repository is expected and
must never be diagnosed as missing compliance.

Allowed coding questions:

- Does the token authenticate?
- Is the endpoint available to the account at request time?
- What rate/quota behavior is observed?
- Does the response match the documented schema/request?
- Is the collection PIT-safe, complete, resumable, correction-safe and provenance-bound?
- Has the technical live canary passed?
- Is bulk historical collection technically ready?

Forbidden coding questions/actions:

- Upload/show me the license.
- Hash the private agreement so code can trust it.
- Give CI an allowlist of grant documents.
- Ask a model to decide whether the company's private license is sufficient from public terms.
- Block collection because no license file is visible to the agent.
- Recreate the superseded vendor-letter requirement under a different label.

Authority: `DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE`.
