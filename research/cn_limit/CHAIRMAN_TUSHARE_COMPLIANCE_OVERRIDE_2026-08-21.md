# Chairman Override — TuShare Compliance Boundary

**Date:** 2026-08-21  
**Authority:** Chairman/operator — final company authority  
**Decision:** `DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE`  
**Status:** binding immediately; runtime/masterplan implementation commissioned

## Ruling

TuShare licensing/compliance has been verified internally and privately and is satisfied.
The controlling agreement and supporting compliance evidence are confidential. They are not
repository artifacts and cannot be disclosed to coding sessions, AI agents, contractors, or
third parties because of NDA/confidentiality and privacy constraints.

The prior CEO/Codex-generated construction requiring a separately uploaded written commercial
or institutional grant, `cn_tushare_written_authorization.v1`, grant-document SHA-256,
`authorization_trust_allowlist`, or code-reviewed licensing-document trust-root is **overruled,
null, and superseded**.

No current or future coding session may turn the private agreement into a runtime, CI,
research, launch, backfill, model, or product prerequisite. Public-web research or absence of
license bytes in the repository cannot reopen the compliance question. Only a later explicit
Chairman/compliance-owner decision can change this status.

## Engineering boundary after the override

Remove private-license proof machinery. Retain independently justified engineering controls:

- token/secret hygiene;
- endpoint access and entitlement/quota observations;
- rate/governor controls;
- request/response schema binding;
- exact clocks and point-in-time semantics;
- source-row accounting and quarantine;
- resumability and immutable receipts for **data provenance**, not license proof;
- licensed-data wording must be removed where it implies coding sessions verify the license;
- bounded live canary for technical correctness/throughput;
- range-campaign correctness;
- completeness and correction receipts;
- `BULK_HISTORICAL_BACKFILL_READY` only if retained as a pure technical readiness gate.

This override does not alter `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, Prophet authority,
identity ownership, PIT rules, correction law, no-rebuild boundaries, or scientific promotion
gates.

## Required repo result

After the commissioned implementation PR, a cold coding session searching the current tree
must not find an **active** TuShare requirement to:

- obtain or send a vendor letter;
- upload or inspect a license/grant;
- construct an authorization receipt;
- hash a grant document;
- maintain a license trust allowlist;
- add a license-document SHA to a code constant;
- block TuShare collection/backfill because private license evidence is not in the repo.

Historical git may of course show the superseded construction. Current-tree tombstones may
name it only to state that it is null and must not be revived.

The exact implementation commission is:
`agentos/handoffs/CN-LIMIT-ALPHA-2026-08-21-CHAIRMAN-TUSHARE-OVERRIDE.md`.
