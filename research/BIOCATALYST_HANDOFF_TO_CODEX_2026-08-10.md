# BioCatalyst — current handoff, updated 2026-08-12

This supersedes the stale action list in the original 2026-08-10 handoff. The critical-path
engineering is shipped. The remaining launch gate is the real fourteen-day soak; no session may
compress or backfill it.

## Current verdict

| Area | Current state |
|---|---|
| Publication refusal | **Settled.** No freshness budget was widened. Current-only publication is live and verified |
| `BC-C2` Capital Structure PIT adapter | **Merged and eligible** at its narrow event-state boundary; unavailable cash/runway/dilution capabilities remain unavailable |
| Outcome-family forward clock | **Started by immutable activation receipts** at `2026-08-11T20:20:43.514252Z` |
| Change Tape surface | **Live.** Exact before/after values, source versions and correction lineage are rendered |
| Fixed cohort | **Installed, exact membership rotated, and live proof passed 4/4** |
| B1 launch-critical collector | **Active.** Fast, history and fixed-cohort timers were armed at the exact 02:00 UTC boundary; the first current and history opportunities passed |
| Launch-SLO window | `2026-08-12T02:00:00Z` through `2026-08-26T02:00:00Z` |
| Functional benchmark parity | **8/32.** The old 6/32 tally overstated its own row table by one; three newly live surfaces produce the corrected 8/32 |

## Production evidence

### Launch-critical current-record lane

The corrected hourly lane ran with the process environment
`BIOCATALYST_HISTORY_ENABLED=0` and completed inside the frozen fifteen-minute opportunity
window:

- run: `ctgov_run_20260811T232226512533Z_e679bb3d2518`
- four configured and four observed NCT records;
- publication state: `current_only`;
- R2 mirror receipt verified at `2026-08-11T23:22:27.023317Z`;
- 15 immutable mirrored objects, 517,157 total bytes;
- manifest SHA-256: `b69ea17419e00e9f3f5e1ccccc5e25d55887909ef5be9b92c692e9c583cf6b38`.

The earlier 900-second failure is preserved evidence of a deployment-boundary defect: systemd
`EnvironmentFile=` values override `Environment=` values regardless of textual order, so the
supposed fast lane inherited history=1. Merge `2f30530edeb359b6a99d29ec1336a5b2d4149b3b`
now prefixes each worker process with its lane-specific value. Production `/proc` inspection
proved hourly=0 and daily-history=1; neither freshness nor timeout was relaxed.

The dedicated history proof then completed as
`ctgov_run_20260811T232756727443Z_e679bb3d2518` under its 45-minute boundary. Its verified R2
receipt binds 381 objects / 10,796,970 bytes, including exactly 366 history objects; manifest
SHA-256 `b8efc41f1ec5b49b1522c45c6d0bc0a67dd1c9421bdc1dea08ee8e53ccbd70ed`.

### Exact soak activation

At `2026-08-12T02:00:00Z`, both root-owned transient activation services completed successfully.
The arm service enabled and started all three collector timers; production then reported each
timer `enabled` and `active`. The first launch-critical service began at exactly 02:00:00 UTC and
completed at 02:03:02 UTC, safely inside its 900-second opportunity:

- run: `ctgov_run_20260812T020019608850Z_e679bb3d2518`;
- 15 immutable R2 objects / 517,157 bytes;
- mirror receipt verified at `2026-08-12T02:00:20.178377Z`;
- manifest SHA-256: `7a45e2ee47ca3826f99fc02a5d698acd2200bf0f90a3452db750072873d91e90`.

The first scheduled history service began at 02:21:04 UTC and completed successfully at
02:36:56 UTC. Run `ctgov_run_20260812T022116101655Z_e679bb3d2518` binds 381 verified R2 objects /
10,796,970 bytes, exactly 366 history objects, with manifest SHA-256
`b0a6eb89f97c2f45ee639affb6c6baf74f3adba73178042b012dd36b1ec9f570`. These observations are
inside the frozen prospective denominator; neither a pre-window proof nor an excluded retry is
being substituted for them.

### Fixed-cohort transport

- active cohort: `ctgov_fixed_cohort_ec83219c405a1eec0ec86324`;
- manifest SHA-256: `c1d8bdd27607ea32333e8021131b61ca8bd0bca803ad5189aed04afc521d624f`;
- four members, stored only in root-owned immutable manifest files;
- rotation actor: `operator.chriswong`, known time `2026-08-11T23:09:22.403749Z`;
- successful live run: `ctgov_fixed_cohort_transport_run_c5958b366c8b7859a18cb95a`;
- result: `complete`, `exact_fixed_cohort_match`, 4 requested / 4 returned, two matching
  source-version probes, no error code.

The first run quarantined on `NEXT_PAGE_TOKEN_PRESENT`. ClinicalTrials.gov returned all four
records and `totalCount=4` but emitted a continuation token when `pageSize=4`; `pageSize=5`
returned the identical four records without a token. The fix requests one bounded sentinel
slot while retaining exact membership reconciliation and the continuation fail-closed fence.
It does not permit a fifth member or a second page.

### Forward clock

The operational store contains nine immutable `family_clock_activation` receipts: three open
and six closed. The open families, all with accrual start
`2026-08-11T20:20:43.514252Z`, are:

- `trial_progression_termination`;
- `timing_slip`;
- `enrollment_site_change`.

`endpoint_readout` remains closed on its separately declared blocker. No forecast, probability,
ranking, sizing or Prophet/Neural Web authority was created.

## Shipped merges and verification

- `BC-C2`: `c14f0390431`
- Change Tape surface: PR `#5387`, merge `812685f5d7361ddaa7a772a95ee0b4cb604127a1`
- B1S2c lane split and soak manifest: PR `#5399`, merge `2371f537a2532c65501394f30730693b7af5a84d`
- activation-boundary corrections: PR `#5404`, merge `2f30530edeb359b6a99d29ec1336a5b2d4149b3b`
- local full BioCatalyst suite: **1377 passed**, 68,969 deselected, five unrelated deprecation warnings
- post-merge integration baseline: **green**
- production product asset SHA-256:
  `e7200305da4863de5e9650022fd1d05ead5659ccb3f3c76764e1ff0b4cf6f607`

## What remains

1. Accrue all scheduled opportunities through `2026-08-26T02:00:00Z` without post-hoc
   exclusions. Record failures and upstream outages in the denominator.
2. At window close, build and verify the launch-SLO evidence artifact. Closed beta stays blocked
   on `closed_beta_source_denominator_not_met` until that verifier passes.
3. Continue the benchmark backlog only inside the ownership and rights boundaries recorded in
   `BIOCATALYST_PARITY_LEDGER_2026-08-06.md`.

## Authority fences that remain absolute

- BioCatalyst is facts/context only. It may not originate rankings, probabilities, signals,
  scores, sizing, escalation or candidate admission.
- `DNR:KILL-PHASE3-START-WEIGHT` remains live: Phase-3 START is display/context only.
- Sponsor-to-ticker identity remains post-selection context with operator-attested admission.
- The retrospective pre-2019 store remains look-ahead-selected and unusable for clean model
  evidence. Only forward accrual may support future pre-registered tests.
- No benchmark row moves to implemented merely because a backend exists. The user-reachable
  surface and an eligible source are both required.
