# VEND-0 Commission — Institutional Estimates Vendor Bake-Off

## ROUTE

`research` — one evidence/decision PR, then stop. No procurement or adapter.

## Mission

Run the common-sample, rights-aware bake-off in
`../VENDOR_BAKEOFF_PROTOCOL.md` for LSEG I/B/E/S, FactSet Estimates and S&P
Capital IQ/Visible Alpha, with API-first alternatives recorded where they can
be evidenced. Determine the best long-run PIT substrate or honestly return
`SAMPLE_REQUIRED` / `NO_QUALIFIED_VENDOR`.

## Bootstrap and collision gate

Re-pin current Skillpack, Macro `main`, Linear `MAS-118`/`MAS-119`, open vendor,
procurement, estimates and Market Belief work, and any existing licensed data
contracts. Never expose credentials, confidential pricing, sample payloads or
contract terms in chat, Git, screenshots or ordinary logs.

## In scope

- Primary-source product/schema/rights reconnaissance.
- Identical sample request for every candidate.
- Real sample/API/export inspection when access is lawfully available.
- Field, clock, PIT, revision, population, coverage, identity, correction,
  operational and rights receipts.
- Predeclared hard-gate/weighted comparison.
- A redacted decision packet and evidence manifest suitable for repository use.

## Out of scope

- Signing a contract, starting a paid trial with persistent obligations, sending
  confidential company data, provisioning production credentials, building an
  adapter or choosing a vendor from marketing claims.
- Replacing MAS-119 federation, current free collection or owner source truth.

## Acceptance

- Same request/sample definition demonstrably used for all candidates.
- Each factual product claim cites current primary vendor evidence.
- Shortlisted candidates have real payload/schema evidence or are explicitly
  `SAMPLE_NOT_OBTAINED`.
- Rights matrix covers storage, redistribution, derived data, model training,
  audit, cancellation and retention.
- Costs and terms are redacted/classified if confidential.
- Decision is one of the protocol's four honest states; failed hard gates are
  visible independently.
- One records-only PR lands with no adapter/runtime/data-plane mutation.

## Stop and return

Stop after the decision packet. If a sample or commercial action needs Chairman
authority, return the exact request rather than selecting around it:

```text
STATUS
RESULT STATE
CANDIDATES CONTACTED/VERIFIED
SAMPLE/PAYLOAD RECEIPTS
RIGHTS RECEIPTS
COMPARISON
CONFIDENTIAL EVIDENCE LOCATION
EXACT PR/MERGE
GAPS
DEVIATIONS
AUTHORITY NEEDED (if any)
```
