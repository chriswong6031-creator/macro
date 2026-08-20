# Fable COO Handoff — Dislocation P0 Source Program

## Observable mission

Deliver and audit the first independently useful Dislocation Intelligence vertical:

> A frozen SEC query cell produces 20 deterministic, price-blind source packets with exact clocks, document receipts, typed failures, evidence-backed Grok proposals and independent audit.

## Why it matters

Mastermind already detects statistical shocks. It does not yet know whether an adverse event represents temporary damage, structural impairment or unresolved evidence. This source vertical creates the lawful evidence organ required by OpportunityCase and later P0 testing.

## Authority and document precedence

1. Chairman intent.
2. Turn 4 P0 preregistration.
3. Turn 5 source architecture freeze.
4. Existing broad SEC source plane, SEC document spine, Company Intelligence identity, AgentOS and DNR.
5. This handoff.
6. Operator convenience last.

## Verified current state and recent PRs

- #6057: canonical EXK execution; closed unmerged.
- #6060: Turn 4 architecture/P0 records.
- #6061: source-estate census; passed and closed unmerged.
- #6062: SEC FTS capacity census; passed and closed unmerged.
- Local material 8-K store: 50,936 rows / 664 tickers, but date-only and basket-scoped.
- Item-2.02 store: 98,975 rows / 1,314 tickers with exact clocks, but committed accession schema is stale.
- SEC FTS: ample candidate capacity, but form amendments and 10,000-result ceilings require client normalization.
- SEDAR+ public automation is rights-blocked.

## Exact scope and repositories

Primary repo: `macro`.

### P0-S0 PR

Build a research-only source packet compiler that:

- consumes frozen query cells;
- recursively shards and fully paginates SEC FTS;
- exact-filters 8-K/6-K and preserves amendments;
- deduplicates and hash-ranks candidates;
- consumes broad SEC source bytes and `sec_document_spine` rather than rebuilding them;
- emits exactly 20 deterministic source packets and a refusal ledger;
- includes a real machine-readable audit consumer;
- mounts no market-data path.

### P0-S1 operator wave

Send the 20 packets to Grok under `GROK_P0_S1_BLIND_SOURCE_EXTRACTION_2026-08-20.md`, then commission a separate Opus/Fable auditor.

## Explicit non-goals

No full 336-row extraction; no price join; no P0 outcome result; no score; no Prophet/Radar/Fusion/Entry Availability change; no product page; no new EDGAR store; no SEDAR scraping; no model probability; no trade recommendation.

## Complete user and machine journey

```text
frozen query cell
→ complete SEC result enumeration
→ exact filing/document receipts
→ deterministic 20-candidate packet set
→ machine-readable refusal/audit surface
→ Grok evidence proposals
→ independent Fable/Opus audit
→ Sol K-packet
```

The useful capability is not “a script exists.” It is that an analyst or machine can open an adverse-event source packet and see exact source identity, public clock, evidence capacity, corrections and typed uncertainty without any price leakage.

## Data, contract, time, null and correction behavior

Use the Turn 5 source architecture freeze exactly.

- Call canonical SEC source owners rather than reproducing filing/document logic.
- Preserve `accepted_at`, `filed_on`, retrieval and recorded clocks independently.
- Every null and refusal is typed.
- Preserve original/amendment and origin/mitigation/resolution relationships.
- Frozen packets are content-addressed.
- Do not infer Item-2.02 accession from ticker/date.
- A capped query cell is incomplete, not a complete large pool.

## Deterministic vs statistical vs model-generated responsibilities

### Codex or mechanical builder

- query/shard/page/filter/dedup/rank;
- source joins and hashes;
- schema validation;
- packet/refusal rendering;
- deterministic tests and proof receipts.

### Grok

- source-only semantic proposals with exact evidence spans.

### Fable/Opus

- audit, repair/reject, consistency review and acceptance ruling.

No statistical market method is in P0-S0/S1.

## Failure states

- SEC FTS cell remains capped or incomplete;
- response correction changes pool hash;
- historical Submissions shard unavailable;
- accepted-at missing;
- document receipt missing or hash mismatch;
- `/A` treated as origin;
- Item-2.02 accession join cannot be proven;
- market path present;
- candidate order differs on rerun;
- model field lacks evidence;
- auditor disagreement unresolved;
- 20-case family/control coverage not achieved.

Any one blocks P0-S2.

## Ordered implementation sequence

1. Review architecture against canonical source owners.
2. Implement query receipt and recursive sharding.
3. Implement exact form/amendment normalization.
4. Implement accession/document-spine join.
5. Freeze the 20-candidate pool with hash ordering.
6. Emit packets/refusals and the audit consumer.
7. Run twice for byte identity.
8. Dispatch Grok proposals.
9. Run independent audit.
10. Produce P0-S0/S1 K-packet for Sol.

## Acceptance tests and real production-path proof

The PR is accepted only when a real SEC query flows through the real canonical source path to 20 visible packet artifacts, all exact receipts replay, the price firewall is demonstrated, and the audited proposal bundle is independently useful to a machine consumer.

Required proof:

- market-data directories physically absent;
- network allowlist restricted to official SEC hosts;
- every query leaf below cap and fully paginated;
- exact client-side base-form filtering;
- exact CIK/accession/accepted-at for every accepted packet;
- document content hashes and archive receipts;
- typed refusals visible to the consumer;
- byte-identical packet manifest on rerun;
- 20 Grok proposals/refusals with evidence spans;
- independent audit and disagreement matrix;
- all authority flags false.

Green CI without the 20 real packets is not completion.

## Stop condition

Stop at the audited 20-case pilot. Do not begin full extraction until Sol reviews the K-packet and freezes any corrections.

## Required K-packet

- exact PRs and SHAs;
- input query lexicon and candidate-pool hashes;
- 20 packet IDs and source hashes;
- family/form/era/refusal coverage;
- Grok proposal SHA;
- auditor verdict and disagreement matrix;
- firewall proof;
- schema/clock/rights/correction failures;
- capability now unlocked;
- decisions required;
- exact next action.