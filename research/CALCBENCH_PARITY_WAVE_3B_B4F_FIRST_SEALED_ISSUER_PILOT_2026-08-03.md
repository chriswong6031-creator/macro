# Calcbench Parity — Wave 3B B4F First Sealed Issuer Pilot

**Canonical B4F build and activation docket**

## Status and nonclaims

This is a bounded, clean-room, SEC-only pilot for one issuer: Apple Inc.
(`AAPL`, CIK `0000320193`). It is **not yet a sealed issuer receipt**. The code
lane has passed a real-source hermetic local run and remains unpublished until
its PR is merged and the protected live run is separately reviewed.
The protected `attested-history-seed` environment exists with one required
reviewer and a custom `main`-only deployment policy, but no live R2 seed,
review-only artifact review, or canonical issuer packet has occurred.

The dedicated-bucket read-only repository-secret names have been verified:

- `R2_RESEARCH_READONLY_ENDPOINT`
- `R2_RESEARCH_READONLY_ACCESS_KEY_ID`
- `R2_RESEARCH_READONLY_SECRET_ACCESS_KEY`
- `R2_RESEARCH_READONLY_BUCKET`

That verifies secret presence only. It does not prove the role's permissions,
any R2 operation, an issuer packet, or data coverage. The writer secrets remain
unprovisioned at the protected-environment boundary:
`R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID` and
`R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY`.

There is no cron, public/user-facing Calcbench replacement, Excel integration,
Neural Web or Prophet authority, score, trading action, alert, broad issuer
coverage, or full-parity claim. The output is evidence infrastructure, not a
financial recommendation.

## Clean-room boundary

The pilot may use only public SEC source material acquired by the project:

- SEC submissions history, including every historical submissions shard declared
  by the current submissions response;
- the selected AAPL 10-K filing index and explicitly retained primary iXBRL
  document; and
- SEC Company Facts for the same CIK.

It retains source bytes, deterministic manifests, exact source paths, hashes,
clocks, archive-member states, parser/extraction policy identities, and the
B3 correspondence needed to explain a selected fact. It does not ingest or
derive from Calcbench code, data exports, proprietary taxonomies, customer data,
account content, screenshots, UI assets, or internal implementation details.
Observed competitor jobs-to-be-done may guide a clean-room product decision;
they are not a data source or implementation specification.

## What the first controlled run does

`scripts/seed_fundamental_forensics_attested_history.py` is constrained to a
single manual AAPL bootstrap. It captures current submissions, all declared
older submissions, Company Facts, and exactly one latest eligible AAPL 10-K.
The filing archive records the full document-index inventory; it retains the
primary iXBRL member and marks every other member explicitly as not requested.

Before contacting the SEC, the runner executes a storage-control probe using
two distinct clients against the same dedicated bucket:

1. prove the control object is absent;
2. create it with strict create-only semantics;
3. prove a conflicting absent-create is rejected;
4. advance it with exact-version CAS and reject a stale CAS; and
5. read the final exact bytes through the separately issued read-only client.

The Cloudflare parent tokens may carry the dashboard's broader Object Read or
Object Read & Write permission sets, including List. They are never handed to
boto. The runner locally mints at-most-30-minute children scoped to the single
`fundamental_forensics/` prefix: the writer child has exactly Get/Head/Put and
the reader child exactly Get/Head; neither has List or Delete. Probe failure
stops the run before source acquisition and no fallback to broad Research Vault
credentials is allowed.

After acquisition, the runner materializes a bounded filing package, parses and
replays the selected iXBRL fact, binds it to an exact SEC Company Facts
occurrence, and prepares a v1 base candidate through the governed query kernel.
The dimensions-unknown bridge is evidence-only: confidence D, review required,
formula-free, and isolated from core metrics. It cannot enter a Neural Web or
Prophet authority path.

## Publication and receipt boundary

The seed may write only the bounded source objects and an immutable v1 base
receipt needed for later review. It may not publish a v2 attested-history
overlay, update a public/latest pointer, create a canonical publication, or
change a user-facing surface. Because this is a public repository, its Actions
artifacts are review-only rather than confidential. The bundle contains exactly:

- `attested_history_operator_packet.json`
- `attested_history_preflight_receipt.json`
- `attested_history_seed_receipt.json`
- `attested_history_seed_bundle_receipt.json`

The bundle receipt binds the other three files by exact byte length and SHA-256,
and binds the run to its repository, commit, ref, run/attempt IDs, protected
environment, workflow, and the exact hash-locked dependency set.

The read-only preflight is deliberately a separate action using the separately
issued reader. A successful `prepared` receipt proves a bounded in-memory
reconstruction under that reader; it does not by itself prove that the v1 base
is appropriate for public serving or that the issuer has complete disclosure
coverage.

## Real-source local validation evidence

On 2026-08-03 the exact macOS arm64 CPython 3.12 dependency lock completed one
fresh end-to-end AAPL run against the public SEC endpoints and a local strict
conditional-write store. This was not an R2 write or a GitHub Actions run.

- The source snapshot was
  `ffsecsrc_560cab6991e4b7d9f2f9c5e979eb2a9bedab0bf4712744d8b91f92ecb586c70a`;
  its source clock was `2026-08-03T13:38:09.176490Z`.
- The selected filing was AAPL accession `0000320193-25-000079`, primary
  document `aapl-20250927.htm`. The archive index exposed 93 members: exactly
  one was stored and 92 were explicitly `not_requested`. One older submissions
  shard declared by the current SEC response was retained.
- The complete Company Facts conversion ledger contained 25,135 immutable
  occurrence events. Candidate-scoped filing metadata prevented unrelated
  historical filed-date anomalies from poisoning selection; the complete
  ledger still remained the query and sealing input.
- The prepared base was
  `ffqs_e6e459c1de1397ae2422ed3f1e60c8492f5bb3568819a9b58c6a1367f44150aa`.
  Its one evidence-only cell selected B3 match
  `ffatt_match_0b27a3c7175e6244aea847f24986ebb700a754a909ff3031ffbd8bad565cb795`
  and raw occurrence
  `rawfact_eea363787a412717da70c41716bef927c11229d16c2b05b321b6516383e59478`:
  `us-gaap:OperatingLeaseRightOfUseAsset`, instant `2025-09-27`, as-reported
  value `11205000000` USD, confidence D, review required.
- The zero-write preflight returned `prepared`, one binding, zero rejected
  leaves, and zero storage-write attempts. Every storage-control outcome was
  true. Neither the SEC-source nor query-snapshot `latest.json` pointer existed
  after the run.
- The bundle's exact byte counts and SHA-256 bindings were independently
  recomputed for its packet, preflight, and seed receipts. The four local
  artifact hashes were packet
  `79a6176a938a1c0e534b8cda7067217cce46379f09b8a8231a9cfbd4b42d5cc1`,
  preflight
  `f1874488027ce81a3fd469f734819a617a60d459526ffa870ed44d07e7b41254`,
  seed
  `e0bef07136cd70bb8c38fd8c5f72a5168abc23141fce85ad280f84e289c95e58`,
  and bundle
  `4e84ba1b10d9b7a8a6f1def6b7cabd1743f1d91a29a5a4a9cf246f0fc879f0ff`.

This evidence proves the bounded local construction path and its fail-closed
controls. It does not satisfy the protected-environment, live-R2, independent
artifact-review, or canonical-packet completion requirements below.

## CI and activation sequence

The B4F runner, manual workflow, and three focused suites are wired into the
Fundamental Forensics CI path:

- `tests/test_fundamental_forensics_attested_history_pilot.py`
- `tests/test_fundamental_forensics_attested_history_seed.py`
- `tests/test_fundamental_forensics_attested_occurrence_governance.py`

Activation must occur in this order:

1. Merge the B4F code lane and CI wiring to `main` after its normal tests.
2. Confirm the existing protected `attested-history-seed` GitHub environment
   still has its required reviewer and exact `main` branch policy. Add only the
   two writer secrets there; do not put them at repository scope or expose them
   to branch dispatches.
3. Dispatch `attested-history-aapl-seed.yml` manually on `main` with its boolean
   enable input. There is intentionally no `schedule:` trigger.
4. Review the four review-only artifacts, including storage-control outcomes,
   exact run/lock hashes, and the zero-write read-only preflight receipt. Do not
   infer success from logs or treat the public Actions artifact as confidential.
5. Review the candidate packet and commit it separately as the canonical
   operator packet. Then dispatch the existing read-only operator manually on
   `main` against that committed packet.
6. Any future scheduler, public API/UI, multi-issuer expansion, normalized
   analytics, or authority promotion requires a separately designed and tested
   lane.

## Completion evidence for this pilot

Do not call B4F complete until all of the following exist and agree:

- merged CI-tested code on `main`;
- an approved protected-environment run on `main`;
- review-only seed, preflight, packet, and bundle artifacts with exact IDs,
  provenance, and hashes;
- verified separate read-only replay against the same bucket; and
- a separately reviewed, committed canonical issuer packet.

Until then, this docket is an activation plan—not proof of a completed issuer
seed or Calcbench parity.
