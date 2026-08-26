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

---

# 10. Wave C feasibility — what the journal can and cannot do

## 10.1 The commission's mandatory control cannot be run as written

§13 requires replay output to be compared "against the real R2 event spool" for a
known-good session. **Zero spool objects exist for any session in the outage** —
the evaluator only spools when it can publish, and it could never publish
(commission D8 in its strongest form: absence of spool proves nothing, and here it
also removes the specified control substrate).

## 10.2 The producer's journal substitutes for that control

The systemd journal retains, continuously from 2026-07-30, one `pass=` line per
in-window pass plus one `EVENT` line per transition. Measured against §13's own
minimum acceptance list, the journal supplies:

| §13 acceptance requirement | Journal supplies |
|---|---|
| exact genuine event identity set `(ticker, kind)` | yes — 598 distinct keys over 7 sessions |
| no spurious extra transition keys | yes — the set is exhaustive per pass |
| internal vs public transition kinds agree | yes — `crossing_unconfirmed` / `at_risk_unconfirmed` are logged distinctly from `forming` / `at_risk` / `confirming_into_close` |
| first transition in the same pass bucket | yes — journal timestamps are the real pass times |
| pack / session / quote clocks agree | yes — `pack_as_of`, `session_et`, `quote_asof` per pass |
| price-basis audit decisions agree | yes — `basis levels=… checked=N unchecked=N mismatched=N` per pass |

Recoverable volume, by session (distinct `(date, ticker, kind)` — the reconciler's
exact merge key):

| Session | keys | Session | keys |
|---|---|---|---|
| 2026-07-31 | 90 | 2026-08-20 | 71 |
| 2026-08-07 | 15 | 2026-08-21 | 31 |
| 2026-08-11 | 162 | 2026-08-25 | 86 |
| 2026-08-14 | 143 | **total** | **598** |

Kind distribution across the outage: `forming` 16,634, `at_risk` 5,872,
`confirming_into_close` 2,140, `crossing_unconfirmed` 1,016,
`at_risk_unconfirmed` 296 (line counts, not distinct keys).

## 10.3 …but the journal is a CONTROL, never a ledger SOURCE

An earlier reading of this evidence treated the journal as stronger than replay
because it is first-hand. That is true as *evidence of what happened* and false as
*ledger input*. The logged line is a lossy projection of the event row:

```
prophet-live EVENT {kind} {ticker} px={price} from={from} passes={passes} age={quote_age_min}m
```

`live_states.transitions()` builds rows carrying `ticker, ts, session_phase,
price, quote_age_min, passes, from, entered, kind` and optionally `via`. Two
load-bearing fields are **absent from the log**:

- **`entered`** — the field that separates a genuine intraday CROSS from a board
  member's first-pass reading. Its own source comment records the P0 receipt as
  "~108 board rows to 2 crosses", i.e. without it the headline population is
  silently the non-crosses.
- **`via`** — the fall-back-vs-overrun axis, and for the internal markers the
  suppressed-pass side that the public row deliberately omits.

`ts` and `session_phase` are recoverable (both are pure functions of the pass
clock). `entered` and `via` are not; they are state-machine outputs.

**Conclusion:** journal-derived rows cannot be written to the forward ledger.
The journal's correct role is the §13 known-good control that the missing spool
can no longer provide — which is exactly what unblocks a replay-based Wave C.

## 10.4 Historical armed packs do not exist — the live §24.2 risk

For session D the evaluator needs the pack armed at D-1's close. Retention probe
against the production bucket:

- `get_bucket_versioning` → **not enabled**
- `list_object_versions` → `NotImplemented` on this R2 bucket
- `live_flow/prophet*` holds exactly **3** objects: the frozen live doc, ONE
  current `prophet_live_armed.json` (`as_of=2026-08-25`), and `prophet_marks.json`

So no historical pack bytes are retained anywhere in R2. Every Class-R session
would need its pack reconstructed from the exact prior-session Git/data vintage.
§C2 warns precisely against assuming that reproduces: the production builder is
wall-clock budgeted (`max_seconds` in `config.yml`) and can withhold names on
deadline, so an unhurried later machine may mint a WIDER cohort than production
actually armed — and a wider pack manufactures transitions that never existed.

**This is stop condition §24.2 in a live state, not a hypothetical.**

## 10.5 The fidelity test that would settle it

The journal makes the refusal decidable rather than a judgement call. Each
in-window pass records the realised cohort:

```
prophet-live basis … checked=105 unchecked=72 mismatched=1
states={'dark':109,'dormant':25,'near':10,'unknown':10,'forming':23}
```

`checked + unchecked` is the armed cohort size and the `states` map sums to it, so
a reconstructed pack can be tested against the size production actually armed,
per session, before any replay runs. Gate:

1. reconstruct pack at D-1 vintage;
2. **reject** unless cohort size matches the journal for that session;
3. replay the real `engine.prophet_live.live_states` over a delay-respecting
   historical quote view;
4. **reject** unless the produced `(ticker, kind)` set equals the journal's set
   exactly — no spurious keys, no missing keys;
5. only then are that session's rows lawful input for the existing reconciler.

Any session failing 2 or 4 is **refused**, not widened.

# 11. Recommended disposition (for Sol)

| Wave | State |
|---|---|
| A — forensics + restore | **done**; production proof pending today's 13:25Z window |
| B — silent-freeze elimination | **built**, PR #6464, mutation-proven; merge + deploy + live proof outstanding |
| C — PIT replay | **feasible but gated**: control substrate solved (§10.2), pack fidelity unproven (§10.4) |
| D — backfill | **blocked on C**; lawful scope is the 7 Class-R sessions / 598 keys ONLY |
| E — acceptance + records | in progress |

Class-D's 11 sessions are **refused** on the force-majeure DEC's own terms: their
`dark` verdicts were correct for the pack handed to them, so "recovering" them
means minting a pack production never armed. That is data manufacture, not
infrastructure reconstruction.

# 12. Two items needing an operator/Sol act

1. **Unattributed credential seeding.** `/etc/macro-live.env` gained the four R2
   keys at mtime `2026-08-26T07:43:28Z`, ~3 minutes before this session's first
   VPS connection. This session did not do it. It needs acknowledgement and an
   Agent OS record, because it is currently the single most load-bearing
   production change in this incident and it has no carrier.
2. **D12 ownership.** The pack `as_of` mis-stamp is an upstream close-store /
   tip-selection defect. It darkened 11 sessions and will recur. PR #6464 makes it
   VISIBLE (`pack_ok`, graded by the dead-man) but deliberately does not repair it.

---

# 13. D12 refined — mechanism confirmed, trigger not reproducible today

`engine/prophet_live/armed_pack.py:855 as_of_date()` takes the **MAX last-bar date
across the whole universe**, deliberately ("the pack must say what it is actually
armed on"). The consequence is a single-point fragility: **one** contaminated
series sets the stamp for all ~3,000 names, and the evaluator then darkens the
entire next session because that stamp is not the last completed session.

Journal evidence of contamination is unambiguous — tips landed on **Saturdays**
(2026-08-01, 08-09, 08-22) and on the build's own calendar day (08-04/05/06/13/
17/18/19). A Saturday bar in a US close store is not a defensible reading.

**But it is episodic, and today's pack is clean.** Probe of the live
`prophet_live_armed.json` (`as_of=2026-08-25`, `built_at=2026-08-26T04:49:31Z`):

| `bar_date` | names |
|---|---|
| 2026-08-25 | 3,034 |
| 2026-08-24 | 4 |
| older (08-10, 06-26, 05-07, 05-13) | 1 each |
| **ahead of `as_of`** | **0** |

So the mechanism is proven and the *source* of the ahead-dated bars is not
identifiable from a clean pack. Naming a culprit today would be a guess.

**Proposed repair (NOT built — needs an owner and a ruling).** `as_of_date`
should refuse a tip that is not a completed NYSE session rather than propagate one
series' MAX, using the calendar already imported by
`live_states.last_completed_session`. This preserves the docstring's intent (a
stale store still reports honestly stale) while making an impossible date
unrepresentable. It is pinnable without a live reproduction:

> feed `as_of_date` a series set in which one series' last bar is a Saturday and
> assert the returned tip is the last **session**, not the Saturday.

Deliberately not done in this program: it edits the nightly pack path, this
session could not reproduce the trigger, and PR #6464 has already told Sol the
defect needs an owner. PR #6464 makes it *visible* (`pack_ok` on `/api/status`,
graded by the dead-man) so the next occurrence pages instead of silently darkening
a session.

---

# 14. Production proof — 2026-08-26 NYSE session (commission §9)

The lane published for the **first time since 2026-07-30T17:20:56Z**. Captured
13:37Z from first-hand host state, not from CI.

| § | Requirement | Observed |
|---|---|---|
| 1 | timer enabled + active | `enabled` / `active` |
| 2 | two consecutive natural invocations | `13:28:05Z`, `13:33:05Z` (no manual dispatch) |
| 3 | `pass_ts` advances on cadence | 13:28:05 → 13:33:05 |
| 4 | `session_et` = current session | `2026-08-26` |
| 5 | `pack_as_of` = last completed session | `2026-08-25` = `expected_session` |
| 6 | quote clock within budget | `quote_asof` 13:32:22Z, age 5.3m |
| 7 | payload semantically non-vacuous | `evaluated_n=180`, states `{at_risk:19, forming:13, unknown:27, dormant:21, near:12, dark:88}` |
| 8 | R2 live object advances | `LastModified=2026-08-26T13:33:11Z`, `status=live` |
| 9 | served object advances | `/var/lib/macro-live/public/live/prophet_live.json` 21,247 B @13:33 — **had not existed at all** |
| — | `no R2 credentials` warnings in-window | **0** (was every pass for 27 days) |
| — | `/api/status` projection | `expected_now=True status=live pack_ok=True pass_age_min=4.6 quote_age_min=5.3` |

Events resumed accruing immediately: `events=25` on the 13:28Z pass and `events=15`
on 13:33Z — prospective intraday evidence is flowing into the spool again.

## 14.1 What the proof caught that CI could not

The external dead-man went **red** on the same capture:

```
VPS LIVE UNHEALTHY:
- prophet_live: missing producer (unowned lane)
```

PR #6464 graded ownership identity — which the commission requires (§B2) and the
breadth lane already carries — but nothing on the producing side ever wrote the
field, so the check could never go green. That is the same always-red-therefore-
unread failure #6464 had to heal in the public-live inventory guard, reintroduced
one layer over. Repaired in PR #6482 by stamping `meta.producer` after the single
`LS.evaluate` call, so globally dark artifacts are owned too.

**This is the entire argument for §24.10.** Every check in #6464 was green, the
mutation matrix passed against pristine code, and the defect was still there. Only
a real session against real production surfaced it.

## 14.2 Closure — heartbeat green in a live session

`meta.producer` shipped in PR #6482 (`e01895f5fcc4`) and deployed mid-session.
Re-verified at 15:23:00Z, inside RTH, with the lane actively publishing:

| Surface | Observed |
|---|---|
| served artifact | `status=live`, `pass_ts=2026-08-26T15:23:00Z`, `producer=scripts/prophet_live_evaluator.py` |
| `/api/status` | `expected_now=True status=live pack_ok=True pass_age_min=2.5 quote_age_min=3.2 n_names=180` |
| external dead-man | **`VPS live plane healthy`** (exit 0) |

Both halves of the contract are now demonstrated on the same lane, in production:
the dead-man **red**s a non-publishing lane (13:37Z capture) and **green**s a
publishing one (15:23Z) — which is what makes it an instrument rather than a
decoration.

Note on verification method: `git merge-base --is-ancestor` against `/opt/macro`
answers "not deployed" for a merge SHA it has not fetched — the box is a partial
clone and main moves faster than the 3-minute pull, so the box holds a
*descendant*, never the exact SHA. Deployment must be confirmed from the deployed
FILE and the artifact it produces, never from ancestry alone.
