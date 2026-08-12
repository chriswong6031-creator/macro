# BioCatalyst — production/account transfer state, updated 2026-08-12

This is the operational companion to `BIOCATALYST_HANDOFF_TO_CODEX_2026-08-10.md`. It records
paths and non-secret state only. Never copy credential values into a handoff.

## Production host and runtime

| Item | Value |
|---|---|
| Host | `root@146.190.142.17` |
| Repository | `/opt/macro` |
| Primary runtime | `/opt/macro-biocatalyst/current` |
| Primary state | `/var/lib/macro-biocatalyst` |
| Fixed-cohort runtime | `/opt/macro-biocatalyst-fixed-cohort/current` |
| Fixed-cohort state | `/var/lib/macro-biocatalyst-fixed-cohort` |
| Fixed-cohort membership root | `/etc/macro-biocatalyst-fixed-cohort` |

Production health and the VPS checkout were verified at a descendant of BioCatalyst merge
`2f30530edeb359b6a99d29ec1336a5b2d4149b3b`. The public product asset exactly matched the
committed SHA-256
`e7200305da4863de5e9650022fd1d05ead5659ccb3f3c76764e1ff0b4cf6f607`.

## Root-owned environment state

`/etc/macro-biocatalyst.env` is root-owned, mode `0600`. Credential values are present and
verified but deliberately omitted here.

| Key | Current non-secret state |
|---|---|
| `BIOCATALYST_ENABLED` | `1` |
| `BIOCATALYST_HISTORY_ENABLED` | `1` in the shared file; service process prefixes enforce hourly=0 and daily-history=1 |
| `BIOCATALYST_PROSPECTIVE_ENABLED` | `0` |
| `BIOCATALYST_CANARY_NCTS` | Four sorted, explicit NCT identifiers |
| `BIOCATALYST_USER_AGENT` | `MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)` |
| R2 endpoint/bucket/access keys | Present; live conditional-create and read-back receipts verified |

`biocatalyst@mastermind-x.com` was confirmed by the operator as a routed address.

`/etc/macro-biocatalyst-fixed-cohort.env` is root-owned, mode `0600`:

| Key | Current state |
|---|---|
| `BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED` | `1` |
| `BIOCATALYST_FIXED_COHORT_USER_AGENT` | `MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)` |

Membership is forbidden in that environment file. It exists only in immutable root-owned
manifests. Active cohort:

- ID `ctgov_fixed_cohort_ec83219c405a1eec0ec86324`;
- four exact NCT members;
- file SHA-256 `c1d8bdd27607ea32333e8021131b61ca8bd0bca803ad5189aed04afc521d624f`;
- rotation receipt under
  `/var/lib/macro-biocatalyst-fixed-cohort/receipts/rotations/2026/08/`.

## Installed units

| Unit | Role | Boundary |
|---|---|---|
| `macro-biocatalyst.service` | hourly current-record publication | process-forced history=0, timeout 900s |
| `macro-biocatalyst.timer` | hourly opportunity scheduler | operator-armed only |
| `macro-biocatalyst-history.service` | daily history refresh | process-forced history=1, timeout 2700s |
| `macro-biocatalyst-history.timer` | daily history scheduler | 02:20 UTC plus bounded jitter, operator-armed only |
| `macro-biocatalyst-fixed-cohort.service` | private exact-cohort source proof | no R2/publication credentials, timeout 600s |
| `macro-biocatalyst-fixed-cohort.timer` | daily fixed-cohort scheduler | operator-armed only |
| `macro-biocatalyst-activation-heartbeat.timer` | prospective R2 activation heartbeat | disabled while prospective collection remains off |

The process prefix is load-bearing. systemd `EnvironmentFile=` values override `Environment=`
settings even when the latter appears later in the unit. The correct `ExecStart` boundaries are:

```text
/usr/bin/env BIOCATALYST_HISTORY_ENABLED=0 /opt/macro-biocatalyst/current/bin/python ...
/usr/bin/env BIOCATALYST_HISTORY_ENABLED=1 /opt/macro-biocatalyst/current/bin/python ...
```

Production `/proc/<pid>/environ` inspection proved both values. Do not replace these with
`Environment=BIOCATALYST_HISTORY_ENABLED=...`.

## Live proof receipts

### Current-record/R2 publication

- run `ctgov_run_20260811T232226512533Z_e679bb3d2518`;
- 4 configured / 4 observed;
- 15 mirrored objects, 517,157 bytes;
- verified at `2026-08-11T23:22:27.023317Z`;
- committed generation and `current.json` pointer present.

### Fixed cohort

- run `ctgov_fixed_cohort_transport_run_c5958b366c8b7859a18cb95a`;
- `complete`, `exact_fixed_cohort_match`;
- 4 requested / 4 returned;
- source API version `2.0.5`, matching before/after dataset timestamps;
- no error code and no public projection.

### Outcome-family activation

The primary operational store has nine immutable family-clock activation receipts. Three are
open from `2026-08-11T20:20:43.514252Z`:

- `trial_progression_termination`;
- `timing_slip`;
- `enrollment_site_change`.

The other six remain closed on their declared blockers. Re-running the same activation is
idempotent and must not fabricate a new accrual start.

## Soak state

The immutable launch-SLO manifest is
`biocatalyst_launch_slo_6424cdec9e0568bac6486b91`, content SHA-256
`6424cdec9e0568bac6486b9106e98bb75a610529d8fbb203ea381baf8754a86c`.
Its scheduled window is:

```text
2026-08-12T02:00:00Z through 2026-08-26T02:00:00Z
```

All three pre-window proofs are green. The dedicated history run
`ctgov_run_20260811T232756727443Z_e679bb3d2518` committed 381 verified R2 objects / 10,796,970
bytes, exactly 366 of them history objects, under the 45-minute boundary.

Two transient root-owned timers held the exact activation act:

- `macro-biocatalyst-soak-arm.timer` → at `2026-08-12T02:00:00Z`, enable and start the hourly,
  daily-history and fixed-cohort timers;
- `macro-biocatalyst-soak-first-opportunity.timer` → at the same microsecond-accuracy boundary,
  start the first launch-critical hourly opportunity.

Both fired successfully at `2026-08-12T02:00:00Z`. The hourly, daily-history and fixed-cohort
timers are now `enabled` and `active`. The first hourly service ran from 02:00:00 through 02:03:02
UTC as `ctgov_run_20260812T020019608850Z_e679bb3d2518`, publishing 15 verified R2 objects /
517,157 bytes. Its mirror receipt was verified at `2026-08-12T02:00:20.178377Z`, manifest
SHA-256 `7a45e2ee47ca3826f99fc02a5d698acd2200bf0f90a3452db750072873d91e90`.

The first scheduled history opportunity ran from 02:21:04 through 02:36:56 UTC as
`ctgov_run_20260812T022116101655Z_e679bb3d2518`. It committed 381 verified R2 objects /
10,796,970 bytes, exactly 366 history objects, manifest SHA-256
`b0a6eb89f97c2f45ee639affb6c6baf74f3adba73178042b012dd36b1ec9f570`. These are the first
prospective launch-window observations. At window close, no closed-beta claim is valid until the
launch-SLO evidence verifier consumes the full scheduled denominator and passes.

## Verification baseline

- `pytest -q tests/ -k biocatalyst`: **1377 passed**, 68,969 deselected;
- focused activation-boundary suites: **258 passed**;
- CI manifest: 180 legacy jobs validated;
- unrun audit: zero strictly dark suites;
- post-merge integration baseline: green.

## Non-negotiable traps

1. User agents require a routable contact containing `@`.
2. Main canary identifiers must remain sorted and explicit.
3. Fixed-cohort membership may never enter an environment variable or command-line membership
   option.
4. A systemd success caused by worker-lock overlap is not a history proof; verify a committed
   history generation.
5. Do not widen the fifteen-minute opportunity or the 7200-second freshness SLO to convert a
   runtime defect into green telemetry.
6. The fixed-cohort lane has no public/R2 authority; the launch-critical lane has no scoring,
   Prophet or Neural Web authority.
