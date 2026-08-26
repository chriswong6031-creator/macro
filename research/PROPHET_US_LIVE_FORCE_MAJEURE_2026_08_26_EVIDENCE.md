# US Prophet Live — Wave A incident evidence freeze (2026-08-26)

Read-only forensic bundle captured before any production modification by this session.
Commission: `PROPHET-US-LIVE-FORCE-MAJEURE-2026-08-26-FABLE-HANDOFF`.
Workstream: `WS:PROPHET-US-AVAILABILITY`. Shared boundary: `WS:BREATHING-PLATFORM`.

## 0. Headline correction to the commission's stated window

The commission (§3.2) records "observed user-facing last-good period: August 21, 2026"
and scopes the at-risk sessions to **Aug 24 + Aug 25**.

First-hand runtime evidence shows the outage is **27 days**, not 5:

> `live_flow/prophet_live.json` has not been written since **2026-07-30T17:20:56Z**.

The Aug-21 observation was not the freeze onset. Roughly **18 NYSE sessions**
(2026-07-31 → 2026-08-25) published no US Prophet Live artifact.

## 1. Runtime identity (captured 2026-08-26 ~07:46-08:10Z)

| Fact | Value |
|---|---|
| Host | `ubuntu-s-mastermindx` (146.190.142.17) |
| `/opt/macro` HEAD | `1db8306293fdb3514e9b50d9bb236962c6169c96` (== `origin/main`, not drifted) |
| `macro-live-prophet.timer` | `enabled` + `active` |
| Last trigger | 2026-08-25T21:58:02Z |
| Next elapse | 2026-08-26T13:03:03Z |
| `Persistent` | `no` — **correct, unchanged** (commission D11) |
| Service last result | `Result=success`, `ExecMainStatus=0` |
| Unit env wiring | `EnvironmentFile=-/etc/macro-live.env` — present and honoured |

**The timer was never dead.** The producer ran every 5 minutes throughout the outage
and exited 0 on every pass. This is the silent-freeze class, not a scheduler fault.

## 2. Initiating fault — credentials were never seeded at cutover

`/etc/macro-live.env` (mode 600 root:root) carries an in-file comment:

> `R2 credentials for the Prophet Live product lane — seeded 2026-08-26 from`
> `/etc/macro-api.env (same bucket, already provisioned). Cutover 2026-07-30 installed`
> `the unit but never seeded these, freezing live/prophet_live.json for 27 days.`

Corroborating timeline, independently established from runtime evidence:

| Timestamp (UTC) | Event |
|---|---|
| 2026-07-30T13:38:25Z | last `workflow_dispatch` of the GitHub backstop — success |
| 2026-07-30T17:20:08Z | **last GitHub backstop run that actually executed** (id `30565510113`) |
| 2026-07-30T17:20:56Z | last write of `live_flow/prophet_live.json` (`status=dark`, 355 B) |
| 2026-07-30T18:03:09Z | **first** `no R2 credentials` warning on the VPS lane (oldest journal entry) |
| 2026-07-30 → 2026-08-26 | every subsequent GitHub scheduled run `completed/skipped` |

The 2026-07-30 cutover made the VPS the primary writer (backstop self-disabled per
commission D6) and handed the lane to a producer that had **no credentials to publish
with**. `r2io.client()` returns `None` when `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` /
`R2_SECRET_ACCESS_KEY` are absent, and `r2_put_json` returns `False` rather than
raising (`engine/prophet_live/r2io.py:58`, `:111`, `:133`).

**Credential state at capture:** all four keys (`R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET`) present and non-empty; `PROPHET_LIVE_NO_PUBLISH`
absent; no `export` prefixes (systemd-parseable). Secret values never read or printed.

**Attribution honesty:** the seeding at `/etc/macro-live.env` mtime
`2026-08-26T07:43:28Z` happened ~3 minutes **before this session's first VPS
connection** (07:46:36Z). This session did **not** perform it. The SSH key
fingerprint and egress IP in `auth.log` match this operator machine, so the act
originated here (operator or sibling session), but it is **unattributed** and was
not recorded in any PR or Agent OS record at capture time.

## 3. Second, independent defect — armed-pack `as_of` mis-stamping

The evaluator darkens a session when the pack's `as_of` is not the last completed
NYSE session. Journal census of every `artifact dark (stale_pack)` reason:

| Session | pack `as_of` | expected | mis-stamp mode |
|---|---|---|---|
| 2026-08-03 | 2026-08-01 (Sat) | 2026-07-31 | weekend |
| 2026-08-04 | 2026-08-04 | 2026-08-03 | same-day |
| 2026-08-05 | 2026-08-05 | 2026-08-04 | same-day |
| 2026-08-06 | 2026-08-06 | 2026-08-05 | same-day |
| 2026-08-10 | 2026-08-09 (Sun) | 2026-08-07 | weekend |
| 2026-08-12 | 2026-08-10 | 2026-08-11 | one session behind |
| 2026-08-13 | 2026-08-13 | 2026-08-12 | same-day |
| 2026-08-17 | 2026-08-17 | 2026-08-14 | same-day |
| 2026-08-18 | 2026-08-18 | 2026-08-17 | same-day |
| 2026-08-19 | 2026-08-19 | 2026-08-18 | same-day |
| 2026-08-24 | 2026-08-22 (Sat) | 2026-08-21 | weekend |

Totals across the outage: **924** `stale_pack` dark passes, **29** `no_pack`.

Origin: `scripts/build_prophet_live_pack.py:167` derives `tip = AP.as_of_date(series.values())`
— the pack stamp is the **tip of the loaded close series**, so a same-day or weekend
row in the close store propagates straight into `as_of`. This is an upstream close-store
/ tip-selection defect, **not** a live-lane defect.

Consequence: on these 11 sessions the evaluator's `dark` verdict was **correct given the
pack it was handed**. Publication alone would not have produced signal.

## 4. Session classification (drives lawful backfill scope)

Journal coverage is **continuous** across 2026-07-30 → 2026-08-26 (no rotation gap;
3.2 G retained). Sessions split cleanly:

**Class R — genuine evaluation, publication lost (infrastructure loss):**
`2026-07-31, 08-07, 08-11, 08-14, 08-20, 08-21, 08-25` — **7 sessions**, each with a
full 84-pass in-window series carrying `pass=` lines (states, pack/quote clocks) and
per-name `EVENT` lines. Example (2026-08-25T20:23:07Z):
`pack_as_of=2026-08-24 quotes=2081@2026-08-25T20:22:30Z src=vps_local states={'dark':74,'unknown':30,'forming':28,'dormant':29,'near':7,'at_risk':9} events=65`

**Class D — correctly dark on a mis-stamped pack:**
`2026-08-03, 04, 05, 06, 10, 12, 13, 17, 18, 19, 24` — **11 sessions**. No genuine
transitions existed to lose.

**Partial:** 2026-07-30 tail after 17:20:56Z (≈13:21–16:15 ET) — lost mid-session.

## 5. Adjudication against the force-majeure DEC (commission §C0)

`DEC-FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT` authorizes reconstruction of
**infrastructure loss**, explicitly not data-correctness laundering.

- **Class R = infrastructure loss.** Correct pack, correct quote tape, correct state
  machine, correct verdicts — only the PUT was impossible. Backfill lawful.
- **Class D = data defect.** Recovering these requires minting a *differently stamped*
  pack that never existed in production and replaying a counterfactual. Commission §C2
  forbids exactly this ("refuse the backfill rather than minting a wider 'better'
  historical pack"). **Refuse**, and route the pack defect to its own repair.

This is a split verdict against stop-condition §24.1: it is triggered for Class D only.

## 6. Defect disposition (commission D1–D11)

| ID | Status at capture |
|---|---|
| D1 external dead-man does not grade US `prophet_live` | **CONFIRMED** — 27 days green while frozen |
| D2 `/api/status` omits `prophet_live` | **CONFIRMED** |
| D3 evaluator returns 0 on unexpected failure | **CONFIRMED** as amplifier |
| D4 missing R2 creds warning-only | **CONFIRMED — this was the initiating fault** |
| D5 live PUT failure warning-only | **CONFIRMED** (not exercised; creds absent earlier) |
| D6 GitHub backstop self-disables under VPS primary | **CONFIRMED** — correct design, fatal in combination |
| D7 armed-pack publication can fail quietly | **CONFIRMED + WORSE** — see §3, silent mis-stamp |
| D8 spool absence ≠ no passes | **CONFIRMED** — 0 spool objects, ~1,500 in-window passes |
| D9 two-writer CAS on `prophet_live.json` | intact; no third writer introduced |
| D10 reconciler sole `data/prophet_live/` writer | intact |
| D11 `Persistent=false` | intact (`Persistent=no`) |

New: **D12 — armed-pack `as_of` inherits a bad series tip** (§3).

## 7. Restoration precondition verified (read-only)

R2 write capability re-tested with the now-seeded credentials via a namespaced
diagnostic key (`live_flow/_diag/prophet_live_write_probe.json`): `PUT_OK` →
`READBACK_OK` (88 B) → `PROBE_CLEANED`. No product object touched.

Today's pack is correctly stamped — `live_flow/prophet_live_armed.json`
`as_of=2026-08-25`, `LastModified=2026-08-26T04:49:32Z` — which equals the last
completed session for a 2026-08-26 trade date, so today is **not** exposed to D12.

Natural first in-window pass expected ≈2026-08-26T13:28Z (09:28 ET). Production proof
per commission §9 requires two consecutive natural invocations and is **not yet held**.

## 8. What was lost

- **Product:** US Prophet Live strip served a `status=dark` document stamped
  `2026-07-30` for 27 days.
- **Evidence:** the prospective intraday transition record for the 7 Class-R sessions
  never reached R2, so `data/prophet_live/forward.parquet` never accrued them.
  The producer's own journal retains `EVENT` lines for those sessions — a
  contemporaneous first-hand record, materially stronger than PIT reconstruction.

## 9. Not done / open

- Production proof (§9) — pending the 13:28Z natural pass.
- Wave B permanent fail-closed + dead-man coverage — not yet built.
- Class-R recovery method (journal-derived vs PIT replay) — not yet adjudicated.
- D12 pack-stamp repair — owner not yet assigned.
- The unattributed 07:43Z credential seeding needs an operator acknowledgement.
