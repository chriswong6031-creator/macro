# Postmortem 2026-08-03 — the Mag-7 earnings week Prophet never spoke about

Status: ADJUDICATED (Fable main loop, 2026-08-03). Operator complaint: "We're in a historic
Mag 7 rally with hyperscalers, beginning with earnings last week. But yet we did not detect
any of this through Prophet. Why did Prophet fail."

Companion fix charter: §6 below (built in the same PR). Prior art this postmortem stands on:
`POSTMORTEM_20260723_MAG7_FORCED_CALL_BY_FABLE.md` (the forced-call kill),
`research/DO_NOT_REBUILD.md` §2 Mag-7 row (what remains lawful),
`research/MAG7_WASHOUT_REENTRY_PREREG.md` (MWR, the lawful re-entry gate),
`research/MAG7_Q2_2026_EARNINGS_CAPEX_DILEMMA_AND_TAPE_SCENARIOS.md` (the 7/18 scenario memo).

## §0. The verdict in four sentences

The tape event was real and historic, but it was a **dispersion**, not a cohort rally:
MSFT +21.8% in 5 sessions (99.90th percentile of its own 40-year history — a top-10 week
in the stock's life), AMZN +17.0% (97.2th), GOOGL +11.4% (98.6th), ORCL +12.9% — while
AAPL −7.2%, META −6.5%, NVDA −2.9%, TSLA −0.6% over the same window (closes cache,
2026-07-24 → 2026-07-31). Prophet **did detect the single best expression of it, twice**:
the live board's buy lane held MSFT on 2026-07-20/21 (nine days before earnings) and a
MSFT BULL plan was cut the same day — entry $402.30, now +15.5% with MFE +1.04R. Then it
**lost the thread**: the fresh-cross tier expired after two sessions, and from 07-24
through 07-30 — the exact week of the explosion — the live board carried **no Mag-7 name
in any lane** (the `ran` "still riding" lane that would have kept MSFT visible shipped in
#4331 on 08-02, one day after the week ended). The plans surface ranked the MSFT plan
#43 of 71 (conviction 60 "neutral" — the composite already measured anti-predictive).
Every organ that watches the cohort was removed from display by the 2026-07-23 ruling
(leadership board, ignition strip, the `_mag7_panel` include), structurally out-of-band
(MWR's 2-week stochastic never armed on a shallow flush), or **aggregation-blind** (the
regime organ's cap-weighted headline read `rolling_over` for six straight sessions
through the rally because AAPL+NVDA's 41% weight diluted MSFT's move — while its own
subordinate `generals` block correctly printed `now=[MSFT], joining=[GOOGL, AMZN]`).
The failure is not missed detection; it is **detection without narration**: the system
held the facts in five different dark or buried artifacts and had no lawful surface
wired to speak them.

## §1. The event, measured from our own stores

5-session returns to 2026-07-31 (`data/breadth/_closes_cache.parquet`), own-history
percentile from the deep parquets (`data/stocks/<SYM>.parquet`):

| Name | 5d | own-history percentile of that 5d window | history |
|---|---:|---:|---|
| MSFT | +21.75% | **99.90** (z +4.8; ~top-10 of 10,169 windows) | 1986→ |
| AMZN | +17.00% | 97.19 (z +2.1) | 1997→ |
| GOOGL | +11.38% | 98.57 (z +2.5) | 2004→ |
| ORCL | +12.94% | — (hyperscaler-adjacent) | |
| AAPL | −7.24% | 7.46 | 1980→ |
| META | −6.47% | 7.07 | 2012→ |
| NVDA | −2.94% | 27.31 | 1999→ |
| TSLA | −0.58% | — | |

The cap-weighted Mag-7 composite gained only ~+5.0% on the week (`mag7_regime` `cw.r5`
0.0503) — the aggregate a cohort lens sees — because the two largest weights (NVDA
21.4%, AAPL 19.9%) sat flat-to-down. Adjacent context: the AI-hardware cohort was
simultaneously BROKEN (`leadership_crack` state `BROKEN` since 2026-07-07, carnage share
0.83, CRWV/SNDK −48%) — the week was a violent rotation *into* hyperscaler platforms,
*out of* AI hardware. The 2026-07-18 scenario memo called this split season nearly
name-for-name (MSFT cleanest reaction; AAPL sell-the-news; dispersion, not cohort move)
— and lives in `research/`, read by no surface.

## §2. What each organ did during the week (receipts)

| Organ | What it did | Why |
|---|---|---|
| Live board buy lane (`data/us_board_ledger/snapshots.jsonl` — the real "Prophet Stock Signals" board; the `_v2` file is the isolated Buy Board 2.0 shadow) | **Caught it**: MSFT `watch` 07-14 → `buy` 07-20/21; AMZN `watch` 07-20/21 → `buy` 07-31 | PEAD/insider/revisions confluence + fresh cross admitted MSFT pre-earnings |
| Same board, 07-24 → 07-30 | **No Mag-7 name in any lane for the five sessions of the event** | Fresh-cross tiers expire in ~2 sessions; pre-#4331 the board had no lane for "detected, still running" (the `ran` lane shipped 08-02); AMZN's 07-31 re-entry rendered as "Wait — leader, poor entry" with verb `TRIM ONLY` (extended/capped_by_entry), zone $243.90 vs spot $271.58 |
| Prophet plans (`site/prophet/index.json`) | **Caught it**: MSFT-BULL-20260720, entry 402.30, trigger 405.80, T1 492.38; `triggered_pre_t1`, +15.5%, MFE +1.04R | Same 07-20 detection, plan form |
| Same surface, ranking | Buried it: #43/71, `_conviction_score` 60 "neutral"; thesis carried "Narrative basket (Technology (Equal-Weight)) is deteriorating — risk gate: trim / size down" | Sorted by the conviction composite already measured anti-predictive (P@1 0.20 vs 0.60, us_prophet_v1 charter); Terminal default sort is recency, so by 7/29 it sat below 8 newer plans |
| Theme layer | `mag7` theme spotlight read `EMERGING` / reco `ENTER` on 07-31 | Rendered only as a sub-object inside the AMZN card's conviction block — no page-level statement |
| Full-universe scan (`data/name_score/us_calls.parquet`, 2,989 names daily) | All 14 Mag-7/hyperscaler tickers scanned every day — never unscanned; META `setting_up` 52-61 through 07-30 then score 0 on 07-31; AMD peaked `setting_up` 62 on 07-31; ORCL flat score-0 for 32 consecutive days (separate observation, chipped) | Scan coverage was never the problem; admission gates were doing their designed job |
| Global admission bar | `gate_go: false` (macro-caution) across us_standouts, prophet index, and the MSFT plan all window | Systemic name-agnostic tightening on top of per-name gates |
| Pick Lab (`data/pick_lab/`, experimental sandbox) | AAPL rank-1 07-28 (pre-earnings), AMZN rank-1 breakout 07-31, MSFT onset 07-31 | Lab lane saw it; lab is explicitly non-authoritative and not the product surface |
| Showcase (`site/prophet/showcase.json`) | Featured 7/15's delayed graded winners | By design backward-looking (`kind: delayed_winners`) — cannot speak about a live event |
| `mag7_regime` headline | `rolling_over` 07-24→07-30 (six sessions), `cooling` on 07-31; never `turning_up`/`running_*` | `_compute_trend_state` requires cap-weighted `r10 ≥ +2%`; AAPL+NVDA dilution kept `cw.r10` ≈ +1.0% at peak week |
| `mag7_regime` generals block | **Caught it**: `now=[MSFT], joining=[GOOGL, AMZN], coverage 0.605`; MSFT `contrib10` 0.6052 | The per-member attribution lens sees dispersion — but it is a subordinate field of an artifact no template renders |
| `_mag7_panel.html.j2` | Dark — computed + published nightly (`site/stockdata/mag7_regime.json`), included by no template | Include stripped 2026-07-23 with the leadership board (the panel itself was not killed by the ruling — it fell with the page section) |
| MWR (`data/mag7_washout/`) | `idle` throughout; 0 triggers ever; basket 2W K 55.7, 0/7 members washed | Per-spec: its S1/S3 constructions arm on 2-week-deep washouts (April-2026-class capitulations). The verified flush — −7.1% EW peak-to-trough 07-21→07-29, worst single day −4.95% (14th of 1,255 sessions since 2021-08), then +4.3% reversal 07-29→31 — is outside its band **by construction** (MWR prereg §8 records this as idle-by-band) |
| `index_momentum` MAG7 carrier | All grids MACD-below-signal through 07-31 | MACD lag on an equal-weight carrier; 1D `hist_vel3` +1.59 was the only early hint |
| `index_leadership` | Stale — snapshots pinned at 2026-06-30 (`n_days: 1`) | Separate defect, display-only lane |
| Notifications (`scripts/notify_turn_events.py`) | Nothing | Its only Mag-7 source is MWR triggers (source f), which never fired |

## §3. Root causes (ranked)

1. **No lawful narration channel existed.** The 2026-07-23 ruling removed the leadership
   board/ignition strip and left "plain data display / display-tier watch item" as the
   lawful forms — but nothing was rebuilt in those forms. Every cohort-aware artifact
   became compute-without-surface. The ruling explicitly permits what was missing; the
   gap is wiring, not law.
2. **Aggregation blindness in the one cohort organ still computing.** Cap-weighted
   composite + threshold vocabulary (`turning_up` needs cw r10 ≥ +2%) is structurally
   unable to see a 3-of-7 dispersion event led by mid-weight members. The lens that sees
   it (per-member contribution / generals) exists but is subordinate and has no
   event-tier vocabulary ("this member's week is a 1-in-2,000 window of its own history").
3. **Detection continuity had a two-session memory.** The board admitted MSFT on the
   fresh cross (07-20/21) and then had no representation for "detected, still running" —
   the name simply vanished from the product during the five sessions it mattered most.
   #4331's `ran` lane closed exactly this hole on 08-02, one day after the window; this
   postmortem records the cost of the gap, no further code change needed for it.
4. **Pick-engine anti-chase is by design and by ruling, not a bug — and the dominant
   mechanical excluder is the fresh-cross cascade, not the alpha leg.** On 07-31,
   12 of 13 Mag-7/hyperscaler names read `signal_gate` `eligible: False` with crosses
   4–40 ticks stale (`FRESH_TICKS=2`, `engine/confluence_tiers.py:44`; gate applied at
   `scripts/build_stock_library.py:839-848`) — including MU (+2.83 residual alpha, the
   strongest reading in the set), AMD (+1.91), VRT (+1.46) and GOOGL (+1.30), whose
   alpha was fine. Residual-alpha erasure (`engine/residual_alpha.py` strips market +
   sector beta, then sector-demeans — "a theme rally is mostly beta",
   `engine/us_board_rank.py:838-852`) explains the negative readings of MSFT/AMZN/NVDA/
   META/ORCL/AVGO/TSLA/ANET but is only the secondary mechanism. The library
   self-documents the visibility consequence: "APP visible 1 day, PLTR 1 day, MSFT
   3 days, each never seen again" (`scripts/build_stock_library.py:4096-4103`). The one
   fresh cross of the week (AMZN, T2 ticks=0 on 07-31) was then independently vetoed by
   `entry_signal` `bounce_wait`, `alignment.overextended`, and `conviction.band == "low"`
   at `engine/prophet_bridge.py:249` — the anti-chase law working as ruled (the 7/11
   forced call proved where overriding it ends). The defect is that nothing else was
   authorized to speak about the tape fact.
5. **The one correct pick was ranked by a measured-anti-predictive score.** us_prophet_v1
   (#4331) removed conviction's authority on the board but the plans surface's emitted
   order still uses it; the Terminal's own default sort (recency) buried it by earnings
   week regardless. Burial is a symptom; narration is the cure (a cohort event strip
   names the plan's ticker even when the plan list is long).
6. **MWR idle was correct but illegible.** Nothing recorded "idle-by-band, not
   idle-broken," so the natural next-session question ("why didn't MWR fire?") had no
   pre-written answer. Band-gap now documented (§6 F4).

## §4. What does NOT change (fences honored)

- No directional Mag-7 call returns to any surface. The strip built in §6 carries
  realized moves + own-history percentile receipts + a watch stance — no direction, no
  forecast, no rank. (DNR §2: "Mag-7 as plain data display … stays lawful"; "operator
  conviction may seed a display-tier watch item".)
- Board/plan **membership** is untouched (DNR:KILL-PROPHET-POP-MERGE byte-identical fence; no
  Top-setups data-lane merge into the graded board).
- MWR S1/S3 constructions are NOT tuned to July (that would be fitting the miss —
  exactly the §0 chart-memory trap MWR itself documents). A shallow-flush arm, if ever
  wanted, enters as a NEW phase-1 candidate with multiplicity accounting.
- The residual-alpha pick engine is not "fixed" into chasing mega-caps.
- `trend_state` vocabulary/thresholds unchanged (ledger continuity); the event lens is
  additive fields.

## §5. Non-invented-here check

`docs/ACTIVE_BUILD_MAP.md` + `research/DO_NOT_REBUILD.md` reviewed 2026-08-03: no open
lane owns Mag-7 event detection; the killed constructions (leadership board, ignition
strip, forced calls) are not what §6 builds; `_mag7_panel` revival as-was is NOT
attempted (its content mixes trend calls into glance tier — §6's strip is a narrower,
event-gated, plain-facts form). Governance walls that stay standing: the theme layer's
`mag7` read carries `ZERO_SCORE_AUTHORITY` (`engine/us_board_rank.py:149-162`);
MLC-R2/R3/R4/R5 (`research/MEGACAP_LEADERSHIP_COHERENCE_MASTERPLAN_BY_FABLE.md`) forbid
any cohort read gaining rank/size/gate authority outside its prereg; the one promotion
path, `research/S_MLC_1_LEADERSHIP_CONTINUATION_PREREG.md`, needs ≥8 non-overlapping
episodes (earliest verdict ~2028). §6's event lens claims **no continuation and no
forward anything** — it states realized moves against the member's own history, which
is outside S-MLC-1's domain and cannot preempt it. The 07-14 rotation-miss postmortem
§4.4 ("megacap-narrowness blindness") already documented the same aggregation-blindness
class in the theme scorer — this postmortem extends that finding to the regime organ's
headline state and closes it at display tier only.

## §6. The fix (this PR)

- **F1 — event lens in `engine/mag7_regime.py`**: per-member 5d/21d return percentile vs
  the member's own full deep history (`data/stocks/<SYM>.parquet`, fallback
  `data/baskets/ohlcv` with disclosed span), tiers `historic` (≥99.5 or ≤0.5, ≥15y
  history) / `extreme` (≥98 or ≤2), receipts (`n_windows`, `hist_years`,
  `last_larger_date`), cohort split state (`split` / `broad_up` / `broad_down` / null)
  + the existing generals promoted into the event block. New optional fields on
  `mag7_regime.v1` (`events` block) in `latest.json`, `site/stockdata/mag7_regime.json`,
  and the ledger row. Deterministic, descriptive, no forecast — plain data.
- **F2 — "Mega-cap tape" strip on us_stocks** (`templates/_mag7_tape_strip.html.j2`,
  included at the removed board's anchor, dashboard.html.j2 mode=='stocks'):
  event-gated (renders ONLY when F1 fires a tier; silent otherwise — honest-null like
  the Forming-today strip), bilingual, glance tier = plain words ("MSFT +21.8% this week
  — a top-10 five-day gain in its 40-year history"), Tier-2 hover = percentile/window
  receipts, stance line = watch-don't-chase + names any open plan ticker overlap as
  fact ("a MSFT plan from Jul 20 is open" — presentation-tier linkage only). No
  direction words, no internal names, banned-vocab test like `test_mag7_panel.py`.
- **F3 — notification source (g)** in `scripts/notify_turn_events.py`: fresh `historic`
  tier events (dedup `(sym, window, date)`), so the operator is TOLD next time, not
  asked to look.
- **F4 — MWR prereg addendum**: 2026-07 band-gap documented (idle-by-band); shallow-flush
  arm = new candidate path only.
- **F5 — this postmortem** committed.

Out of scope, chipped as follow-ups: Terminal ProphetView cohort context chip
(cross-repo; reads the already-published `site/stockdata/mag7_regime.json`),
`index_leadership` staleness (separate defect).
