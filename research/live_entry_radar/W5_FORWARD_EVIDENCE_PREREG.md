# LIVE ENTRY RADAR — W5 / PR-5 FORWARD-EVIDENCE PREREGISTRATION

**Registered:** 2026-08-15 (W5 session, pre-outcome). **Status: REGISTERED — UNGRADED. Zero
Radar forward-outcome, replay-return, MFE/MAE, false-start, control-excess, or ranking rows
existed anywhere when this text froze, and none was read in choosing any mechanism below.**
**Program:** `research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` (the frozen PR-0 contract;
this document discharges every "pre-register in PR-5 before outcomes are read" clause of its
§10/§11 and the §18 A5.7 horizon stance). **Workstream:** `WS:LIVE-ENTRY-RADAR`, wave W5.
**Template precedent:** `research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md` (provenance →
frozen claims → evidence cells → inference → floors → consequence matrix → clock →
append-only grading log → dated amendments; including its pre-evidence red-team audit
discipline — see §19). **Look-ledger law:** contract §11 — the ledger IS
`engine/trial_ledger.py::TrialLedger`; §13 below declares the complete budget.

This document is the registry for W5's outcome reads. Post-freeze changes happen only as
numbered, dated, append-only amendments in §16 — never in-place edits — and any amendment
made after first replay results exist must state what results its author had seen.
Enforcement is mechanical where a mechanism exists and is named per-gate in §14 (what each
gate does and does not bound is stated there; nothing claims enforcement it does not have).
The replay/outcome runner refuses to execute unless the frozen-prefix hash of this
document, its merged-commit ancestry, the TrialLedger budget row, and the W3 detector spec
hashes all verify.

---

## §0 Provenance — what was and was not seen

**No-peek status.** Unlike the R4 precedent (which disclosed an in-sample sighting), no
Radar detector outcome sighting exists: W0–W3 were archaeology, contract, framework and
detector implementation with an explicit no-outcome law (`§18 A5.0`; W3 review dispositions
record "no forward outcome, replay return, MFE/MAE, false-start, or ranking result existed
or was consulted"). This registration is therefore a true pre-outcome freeze for every
Radar detector. What HAS been seen, and is disclosed as motivating context only:

- The champion's adverse prior (contract §3.1): Terminal's own record that acting on the
  raw early dot was *worse* entry quality than the confirmed buy, and the ±4.89d/12.7d
  lead-time duality. Neither number was derived under this document's ruler.
- The `DNR:KILL-WASHOUT-TURN` kill and its NC-2 proximity mechanism (contract §2) — the
  reason §9's kill arm exists. Confronted by name in §9 and in every primary read.
- **Data-property measurements taken 2026-08-15, pre-outcome, by this session** (fetch
  mechanics and unconditional price properties, not Radar outcomes): (a) vendor
  (Polygon/Massive) REST `v2/aggs` serves minute aggregates ≥ 2011 and daily OHLCV for
  arbitrary U.S. tickers with `adjusted=true`; (b) vendor `adjusted=true` is
  **split-only** — measured KO 2021-08-02 store/vendor close ratio 0.8625, JPM 0.8824,
  NVDA 0.9966, against the split+dividend total-return store `data/stocks/`
  (`collectors/_stock_ohlc.py` basis) — this measurement fixes §4's basis law; (c) vendor
  `v3/quotes` (NBBO) answered with real bid/ask for 2024 and 2012 probes under the estate
  key, contradicting the stale not-entitled note in `collectors/massive_flatfiles.py:11-15`
  — both facts recorded; §11's cost law works under either entitlement state;
  (d) confirmed-K<20 run frequency ≈ 11.8 runs/name/yr on the curated panel since 2020-07
  (exposure census over detector *inputs*, used only to size fetch budgets);
  (e) **unconditional 10-session forward-return dispersion** (no conditioning on any
  detector; a pure price property): cross-sectional median per-name SD ≈ **5.7pp**
  (IQR 4.7–7.1pp) on a seeded 60-name Panel-A sample, TEST era. This number sizes the §12
  floors honestly: at ~30 episodes / ~20 names per arm, a difference CI half-width of
  roughly 3–5pp is expected, so the §10 guardrail margins (−1.0pp, +5.0pp) are NOT
  powered at the floors — the guardrails therefore carry an explicit three-state verdict
  with INCONCLUSIVE the expected early state (§10), rather than a pass/fail pretense.

**Results seen: NONE.** No number in this document was tuned against any Radar forward
return, excursion, false-start, control excess, ranking, or cost realization.

---

## §1 Frozen identity — detectors, spec hashes, eras of record

**Detector arena (W3 lock, §18 A5; any firing-relevant change = new version = new
detector):**

| detector_id | spec_hash (frozen, published) |
|---|---|
| `G0_GREY_DOT@1` | `9be89a8acc8b905c` |
| `C1_1D_LIVE_WASHOUT@1` | `f0bbd6cf3a6e2339` |
| `C2_1D_TURN@1` | `d8ba60a25cfa7400` |
| `C3_1D_4H_RECOVERY@1` | `d54dc1e55c4261c8` |
| `C4_MTF_TURN@1` | `dce21ac680233ee2` (stratification-only; cannot fire; no outcome rows) |
| `C5_BOTTOM_WATCH@1` | `13dec66345a0376c` |
| `F1_FUSION` | NotYetSpecified — absent/refusing everywhere in W5 |

The runner recomputes each hash from `engine.entry_radar.detectors.DETECTORS` at execution
and refuses on any mismatch (§14). C4 acquires **no** directional claim, no qledger family,
and no outcome table of its own — it appears only as stratification columns on C2a
episodes (its stratified outcome read is a budgeted §13 cell, row 19). C2 means **C2a
(`c2a_kd_cross`)** in every confirmatory statistic (§18 A5.3 law); C2b–C2f are exploratory
and look-counted (§13 row 11).

**Era split (DT-R16, PSS §7 house standard):**

- **Replay era of record:** decision sessions in **2011-01-03 → 2026-02-13** (inclusive).
- **FIT:** 2011-01-03 → 2020-06-30. Descriptive/exploratory context only; nothing in W5 is
  fitted, and no confirmatory verdict may cite FIT-era rows.
- **TEST:** 2020-07-01 → 2026-02-13. The confirmatory family (§10) grades on TEST only.
  Full-sample-only effects are disqualified by construction.
- **HOLDOUT (§12):** every session strictly after **2026-02-13**, plus everything after the
  live-forward start (§8). Untouched in W5 — the runner refuses holdout decisions
  mechanically.

An episode belongs to an era by its **decision session** (`candidate_at` session). Episode
*anchors* in the holdout are never read. Outcome windows of boundary-adjacent TEST
episodes lawfully extend past 2026-02-13 by up to the horizon being read: **the seam is
10 sessions for every confirmatory primary (H=10), and up to 21 sessions for the
{15, 21}-session diagnostic cells** — the maximum declared horizon anywhere in §13. The
diagnostic cells carry that wider seam disclosed; no exclusion is applied (uniformity over
carve-outs), and no holdout-anchored episode enters any read.

---

## §2 Replay universes (panels), membership, and survivorship disclosure

Two pre-declared panels; every table names its panel.

- **Panel-A ("curated deep panel")** — the 240-name shared store `data/stocks/*.parquet`
  (split+dividend adjusted, H/L/C/V, 1999+). This is Layer-B core ("names under
  first-class single-stock coverage"). Detectors replayed on Panel-A: **C1, C2, C3**
  (minute-reconstruction detectors — §5), plus G0/C5/incumbent for the §13-row-16
  basis-fidelity check. Selection/survivorship disclosure: Panel-A is a curated,
  currently-covered, large-cap-tilted set; results generalize only with that caveat, said
  in every Panel-A table.
- **Panel-B ("broad panel")** — the current stock-library universe
  (`data/universe/membership.parquet` distinct tickers, ~2.9k names as materialized at
  run time and fingerprinted in the results package), price-served by the **vendor daily
  plane** (§4). Detectors replayed on Panel-B: **G0, C5, C4 features, incumbent gauge**.
  Survivorship disclosure (standards §3.1/§11.3): membership is **current-constituent** —
  names delisted before run date are absent, which flatters washout-buying results; this
  is stated in every Panel-B table, and §13 row 15 runs a pre-registered
  delisting-robustness arm: Q1 recomputed on the 2021-07-06 → 2026-02-13 sub-era with the
  name list taken from the delisting-inclusive `data/massive_stock_day` ticker census
  (~20k names incl. subsequently-delisted; the vendor plane serves their history), and
  the Q1 delta between the two lists is reported as the measured survivorship bias
  direction.
- **Controls** for a candidate are always drawn from the candidate's own panel (§7).
- PIT membership of the live Probe Set is **not reconstructable** for history (the Probe
  Set did not exist; Layer-C/D admissions are live-forward objects). Replay panels are
  therefore declared name lists with the survivorship disclosures above, not PIT probe
  sets; hotness enters matching as the §7 PIT proxy. This is the §0 R-1 disclosure form.

**Common-eligibility law (contract §11, Track F B8):** every cross-detector read uses only
(ticker, session) pairs where BOTH detectors were computable (warm-ups: G0 ≥ 90 3D bars;
C5 monthly dwell ≈ 28 months; C1/C2 ≈ 17 sessions + minute availability; C3 additionally
its 4H indicator warm-up). The eligibility gap is reported separately with every such
read. The IPO/young cohort (< 252 sessions of history) is C1/C2-only and no G0/C5
comparison is manufactured there.

---

## §3 Episode derivation per detector (replay)

Episode hygiene is contract §10 verbatim: one live episode per (ticker, detector_id);
episodes end only via INVALIDATED / EXPIRED / RESOLVED; never deleted; re-arm after an
episode ends requires confirmed K > 50 for 2 consecutive sessions or 15 elapsed sessions
(`engine.entry_radar.challengers.rearm_eligible`, the exported §10 primitive); ARMED /
TURNING without candidate-promotion expires after 15 sessions; CANDIDATE resolves at H.

- **G0**: population = the §3.1 mask computed by the **staged Terminal emitter** — the
  Terminal repo's own `signal_layer` at the A5.6-pinned commit
  `82cb8cbf799fc3a91c9bee0f11a4db718fde68eb`, exported via `git archive` into the run
  workspace and executed per name on the panel's close series (the W2 F6-probe precedent).
  No Terminal file is modified; no Macro reimplementation is introduced (the §3.2
  "seeded from origin/master only" law, satisfied by running the pinned original).
  Decision clock: `known_ts` (never `ts`), decision = the `known_ts` session's close;
  entry per §6. Fidelity pins: on the W2 fixture names (NVDA/NFLX/TSLA, census-vintage
  feed) the staged runner must reproduce the committed fixture dot dates and `known_ts`
  values exactly before any outcome attaches (§14 gate G-5 — whose scope limits are
  stated there). Panel-B events are `radar_derived` recomputations on the vendor basis
  (§4) and say so; their identity license is §13 row 16's measured agreement floor (§14).
- **C1 / C2**: the shipped W3 engine (`challengers.run_c1` / `run_c2`) over A5.1-lawful
  observation paths reconstructed from **episode-windowed minute aggregates** (§5).
  Candidate laws are the frozen A5.2/A5.3 ones (`candidate_at ≡ first_armed_at` for C1;
  first fire per episode×variant for C2). Multi-session episodes are evaluated
  session-by-session under the same engine with confirmed closes advancing per session;
  the §10 hygiene clocks stitch sessions into one episode (W3's single-episode-per-path
  design + `rearm_eligible`, exactly as its handoff assigns to PR-5).
- **C3**: the shipped `four_hour.run_c3` with a W5-supplied `IntradayReader`
  implementation (§5) building the A5.4 RTH 4H grid from vendor minute aggregates; arm =
  confirmed-daily K<20 knowable next session; candidate = first completed-4H histogram
  turn after arm; 15-session arm expiry (W3-2 law).
- **C4**: `c4_snapshot` stratification features attached to C2a episodes only; no
  episodes, no outcomes of its own; its stratified read is §13 row 19.
- **C5**: population = the A5.6 pinned formula family (`washed ∧ (early_dot ∨
  blocked_trigger)`) as emitted by the same staged Terminal emitter run (watch-event
  stream), decision clock = the event's `signal_known_ts`. Replay rows are research
  derivations; they never mutate or duplicate the production `mastermind.entry_event.v1`
  store; `pre_channel_reconstruction` honesty (A4.7) is inherited in the disclosure text.
- **Incumbent gauge (Q5 comparator, not an arena detector):** 2W anchor-A bars
  `close.resample("W-FRI").last().dropna().iloc[::2]`, `engine.canon.stoch_rsi_kd`, fire =
  `cross_up(K, D) & (K.shift(1) < 20)` — the PSS §7 ruler's own incumbent implementation
  (`scripts/research/ptt_w1_persistence_of_fit.py::bars_for/tool_dates`, family "S").
  Knowability = the fired 2W bucket's last actual session close; entry per §6
  confirmed-bar law.

Every replayed episode records: ticker, detector_id, detector_spec_hash, panel, era,
`first_armed_at`, `candidate_at` (decision timestamp), decision session, `P0`, `p0_basis`,
`A0`, `atr_basis`, feature snapshot at decision, cohort tag, regime tag, data-refusal
flags, and provenance of every input (source + vintage). Replay evidence rows are
**append-only research artifacts** under `research/live_entry_radar/w5_results/`
(fingerprinted in the results package); they are not the production forward ledger (§8)
and not `data/entry_radar/**`.

---

## §4 Price-basis law (frozen from the §0(b) measurement)

- **Vendor plane** (Polygon/Massive REST, `adjusted=true`, split-only): the ONE substrate
  for (i) all minute reconstruction, (ii) Panel-B daily history, (iii) all outcome legs
  (subject, SPY, sector ETF, controls) on both panels, and (iv) **A0 on BOTH panels** —
  P0, A0, MFE/MAE, and the false-start thresholds always resolve on one plane, so an
  ATR level is never compared against a price level from a different adjustment basis.
  A §15 battery row asserts per-episode plane consistency (`p0_basis` and `atr_basis`
  resolve on the same plane) or the episode refuses.
- **Curated plane** (`data/stocks`, split+dividend): the substrate for the §13-row-16
  fidelity check's exact-basis G0/C5 run only. Panel-A C1/C2/C3 **indicator history uses
  vendor daily closes** so that daily history and minute tape share one basis (the W3-1
  refusal law is honored, never worked around).
- Consequences, disclosed wherever relevant: outcome returns are **price returns**
  (dividends not reinvested) uniformly on every leg — internally consistent excess;
  ex-dividend gaps appear in subject and control paths alike; the false-start MAE
  threshold can absorb an ex-div gap (rare at H=10 scale; counted and disclosed via a
  per-episode in-window ex-div flag from vendor reference dividends, diagnostic only).
- The basis-fidelity check (§13 row 16) measures G0 event-set agreement (dates matched /
  extra / missing) between the curated-plane and vendor-plane runs on Panel-A ∩ Panel-B
  names, plus the Q1-metric delta on the intersection. **It is binding, not decorative
  (§14):** below its 90% date-agreement floor, every Panel-B G0 read (Q1, Q5) reports
  UNINFORMATIVE — identity not established at the graded population — rather than a
  verdict. It still cannot alter the §10 definitions themselves.

**No raw-basis tape is ever mixed with an adjusted daily series** — the W3-1 gate refuses
wholesale, and the runner treats any `daily_price_basis` disagreement as episode refusal,
never as a fallback.

---

## §5 PIT replay law (minute reconstruction, refusals)

Contract §5/§7.2 verbatim, operationalized:

- C1/C2 LIVE-state replay: per-episode-window fetch of vendor 1-minute aggregates
  (`/v2/aggs/ticker/<sym>/range/1/minute/<from>/<to>`, `adjusted=true`, ascending, one
  bounded window per episode; never a bulk crawl; no permanent minute store — the session
  cache lives outside the repo and its manifest+hashes are recorded in the results
  package). A5.1 sampling law exactly: RTH filter, session-open-anchored 5-minute
  intervals, last minute-agg close per interval, provisional close appended
  (append-not-replace), no EOD H/L/C beyond T, never raw one-minute lows.
- **Refusal law:** an episode/session whose minute window cannot be fetched or fails the
  A5.1/W3 validity gates (basis disagreement, stale continuity, empty RTH tape) is
  **REFUSED** — recorded in the refusal census with its reason, never approximated from
  EOD values. Detector×period combinations that refuse wholesale are live-forward-only,
  said so in the results.
- Superset screen (fetch-budget only, cannot create or destroy episodes): minute windows
  are fetched for sessions where the necessary condition `K(session-low provisional) < 20`
  holds on vendor daily bars, plus all sessions inside open episode windows. The screen is
  a pure necessary-condition filter (K is monotone ↑ in the provisional close, §7.1;
  sampled lows ≥ raw session low), so no lawful C1 arm can occur on a screened-out
  session; a mutation test proves the screen's necessity direction (§15 battery).
- C3's 4H history: same fetch mechanics with the warm-up window extended until canonical
  `rsi_macd` produces the 3-point predicate (A5.4's mathematical warm-up), bounded per
  episode.
- G0/C5/incumbent (confirmed-bar): replay from daily bars; no minute requirement except
  the §6 P0 reconstruction, which has its own lawful fallback.
- **Q4 lobe enlistment: LIVE-FORWARD ONLY.** No historical reconstruction of lobe
  nominations from today's lobe state, ever; the runner contains no code path that builds
  a historical enlistment flag, and the battery (§15.K) proves the refusal.

---

## §6 Reference units — P0, A0 (contract §10 frozen law, operationalized)

- **C1/C2 (LIVE):** `P0` = the 5-minute-sampled last trade observable at the decision
  timestamp T (the firing observation's sampled provisional close). `p0_basis =
  "sampled_last_trade_at_decision"`.
- **G0 / C3 / C5 / incumbent (confirmed-bar):** `P0` = the first trade after `known_at`,
  reconstructed as the opening print of the first RTH minute bar of the session following
  the knowability session (episode-windowed minute fetch); where that minute
  reconstruction is refused, `P0` = the **next session's close** (`p0_basis =
  "next_session_close"`), never the signal bar's own close, never a retroactively known
  open from a store that carries none.
- **A0** = ATR(14), Wilder, true-range on daily OHLC, as of the **prior confirmed close**
  before the decision (`engine.entry_radar.indicator_core.atr14_prior_confirmed` form),
  computed on the **vendor plane on both panels** (§4). `atr_basis =
  "true_range_daily_ohlc"`. Episodes where only a close-only ATR proxy is available are
  flagged and **excluded from the primary false-start read** (contract §10). No fourth
  ATR family is introduced.

---

## §7 Outcomes, false start, matched controls

**Outcome attachment (every resolved/censored episode):** forward return at H;
net-after-costs forward return; MFE; MAE; time-to-positive; time-to-MFE;
target-before-invalidation; gap-through-invalidation; `excess_vs_bench` (SPY);
`excess_vs_sector` (sector-matched ETF via the public
`engine.qledger.control_for_sector` / `sector_of_ticker` chain — the mapping's home
module is `engine.ai_desk`; a refactor there is a basis change and is treated as one);
termination/censoring status + `terminated_reason`; path granularity flag; costs +
provenance.

- **Horizons:** primary **H = 10 trading sessions**; secondary diagnostics {3, 5, 21}. All
  candidate-producing detectors share primary H=10 (A5.7: no per-detector horizons).
- **Windows (the contract's `(decision, decision+H]`, restored exactly):**
  - *Confirmed-bar detectors (G0/C3/C5/incumbent):* P0 sits at the next session's first
    trade (≈ open), so the primary window is that session and the following H−1 sessions
    of daily high/low bars — effectively `D+1 … D+H` with nothing material before P0.
  - *LIVE detectors (C1/C2):* the window opens at the intraday decision instant T. The
    **session-D remainder after T** is measured from the episode's own 5-minute sampled
    path (which every replayed LIVE episode has by construction, and the W4 live lane
    records going forward): its sampled last-trade prints after T contribute to MFE/MAE
    and to false-start threshold ordering as "session 0", followed by daily high/low bars
    for sessions `D+1 … D+H`. Sampled granularity understates raw intraday extremes
    (sampled lows ≥ raw lows — the A5.1 direction), which is disclosed; the treatment is
    identical for every LIVE episode regardless of minute coverage richness.
  - MFE = `max(0, max(path highs)/P0 − 1)`, MAE = `min(0, min(path lows)/P0 − 1)` over
    that window (signs per the `engine/grading.py`/`forward_dist.py` house convention);
    forward return = `close[D+H]/P0 − 1`.
  - Because C3 (confirmed-bar) and C2a (LIVE) windows both open at their own P0 instant
    and close at `D+H`, Q3's two arms are measured over comparable spans; a §15.G battery
    row proves the LIVE day-0 segment participates in false-start ordering and that
    confirmed-bar rows are unaffected.
- **Bench/sector legs:** close-to-close `D → D+H` on the vendor plane. Anchor-asymmetry
  disclosure, split by family: for LIVE subjects, P0 (an intraday print, conditionally
  near the session low because K is monotone ↑ in the provisional close) precedes the D
  close the legs anchor on — the subject captures the P0→close(D) segment the legs do
  not; for confirmed-bar subjects, P0 (next open) FOLLOWS the legs' D-close anchor — the
  legs capture the overnight D→D+1 gap the subject does not. The two directions are
  opposite; §13 row 21 budgets a bounding read re-anchoring subjects at their session
  close so the asymmetry's magnitude is measured, not assumed.
- **Risk geometry per candidate:** target = `P0 + 1.00×A0`; invalidation = `P0 −
  1.25×A0` (mirroring the frozen false-start thresholds); target-before-invalidation
  evaluated on the window with the same-session tie resolved **adverse-first**
  (conservative); gap-through-invalidation = vendor daily `open < invalidation` while the
  prior close ≥ invalidation. Both are reported inside §13 row 6's tables.
- **Censoring:** a name that stops trading inside H is censored at its last observable
  trade with `terminated_reason` recorded; never dropped, never extrapolated.
- **False start (frozen §10 definition, verbatim):** an episode that reached CANDIDATE is
  a false start iff, within H=10 sessions of `candidate_at`: (A) MAE reaches 1.25×A0
  **before** MFE reaches 1.00×A0 (first-touch ordering over the §7 window including the
  LIVE day-0 sampled segment; same-touch tie = adverse-first), OR (B) the 1D **confirmed**
  StochRSI re-enters K < 20 AND price makes a low below the episode's washout low.
  Episode washout low = min daily low from `first_armed_at` session through the decision
  session (episodes with an ARM state); for G0/C5/incumbent, the trailing-63-session
  minimum low ending at the decision session (the NC-2 proximity window, pre-declared
  here). Reported per detector: false-start rate; median MAE on false starts;
  time-to-failure.
- **27-cell sensitivity grid (diagnostic-only):** favorable {0.75, 1.00, 1.50}×A0 ×
  adverse {1.00, 1.25, 1.50}×A0 × horizon {5, 10, 15}, **run per detector** (consistent
  with the per-detector reporting law above) = 135 pre-counted cells (§13 row 4). It
  cannot overwrite the primary definition; no post-result threshold search.

**Matched controls (frozen):** for every candidate, controls come from the same panel's
names that (i) did NOT fire that detector within ±5 sessions of the decision session,
(ii) do NOT fire it anywhere in `(D, D+H]` (a day-+6 firer is excluded — its post-fire
path may not contribute), (iii) are not `suppressed_by_rearm` (inside the §10 re-arm
blackout at D), and (iv) satisfy the candidate's CEM cell: **same session, same sector,
same market-cap bucket (>$200B / $10–200B / $2–10B / <$2B), same 63-bar close-min
proximity decile**. Market cap at D (frozen PIT proxy, disclosed): current vendor
reference shares outstanding (split-consistent) × adjusted close at D — exact up to
buyback/issuance drift, the only PIT-computable form without a shares-history feed;
applied to candidates and controls alike so bucket-assignment error is symmetric. Sector
source: `data/universe/membership.parquet` (qledger's own `sector_of_ticker` source),
fallback `data/breadth/ticker_sectors.parquet`, recorded per name. **Missing-sector law:**
a candidate with no resolvable sector is `uninformative_no_control` (refused from the
primary, counted in the §13 row 14 census); an unmapped control name simply never enters
a cell; per-panel sector-mapping coverage is published with every table. Among cell
members, **k = 5 nearest controls** by L1 distance over four axes **each normalized to
[0, 1]** (decile/9; (quintile−1)/4; hot tier as 0/1): {dollar-volume decile,
trailing-60d-return quintile, realized-20d-vol quintile, hotness tier} — proximity/date/
sector/cap sit on the exact (CEM) side because they are the confound axes (NC-2, market
time, structure); the return/vol/liquidity axes are matched soft with a **maximum
admissible distance of 1.0** (of a possible 4.0) beyond which a would-be control is not
used. Equal-distance ties break by lexicographic ticker — fully deterministic. Fewer than
5 admissible → use all admissible (k ≥ 1; the k distribution is reported with every
table); **zero admissible → the candidate is recorded `uninformative_no_control`,
excluded from the primary mean, and counted** (missing-control law), and the primary is
additionally reported once with excluded candidates imputed at zero excess (the bounding
read; direction stated). All deciles/quintiles are **cross-sectional within (panel,
session)**; the dollar-volume decile uses the same trailing-60-session median dollar
volume as §11's cost tiers. Hotness tier (PIT proxy, frozen): `hot` iff rel-volume-20d
decile ≥ 9 or |5-session return| decile ≥ 9 on the decision session, else `cold` — a
declared replay proxy for the live Layer-C admission, disclosed as such. Control outcome
legs are close-to-close from D (controls have no fire and no P0); the subject leg is net
of §11 costs while controls are gross — conservative against the detector, disclosed.
**Primary comparison = candidate excess versus matched-control mean, aggregated per-name
first (never pooled-fire-first).**

**Cohorts (contract §12, declared before the read):** leader reset; partial/shallow
washout; full daily washout; deep multi-timeframe washout; gap/catalyst repair;
damaged-trend rebound; IPO/young (< 252 sessions); small-cap/high-vol momentum. Cohort
assignment is mechanical, frozen in the implementation PR before any outcome read
(`engine/entry_radar/replay/features.py` carries the exact first-match-wins law with
numbered constants; cohort cuts are look-counted, §13 row 8). Every episode also records
a market-regime tag (SPY 63-session drawdown ≤ −10% at D = "stressed", else "quiet" —
frozen here); **the regime-conditioned outcome read is budgeted** (§13 row 18), as is the
C4 recovery-count stratified read on C2a (§13 row 19) — recording an axis is not license
to read it, and both reads are declared here, before any outcome exists. Cohort reads
license no per-detector post-hoc calibration; C5 accrues without a sixth confirmatory
question.

**C32 decline-deceleration conditioner (frozen final form; sketch → pin per PSS §7):**
`C32(t) = TRUE` iff, on confirmed daily closes through the prior session: `close ≤
min(close over the trailing 60 sessions)` (fresh-low territory) AND `roc20 >
min(roc20 over the trailing 20 sessions)` (20-session rate-of-change off its own
20-session minimum — decline decelerating into the low), where `roc20 =
close/close.shift(20) − 1`. Graded WITH (episodes where C32 true at decision) and WITHOUT
(**all episodes within the same cohort** — the two arms share a denominator definition)
for Q1/Q2/Q3 on the gap/catalyst and deep-washout cohorts (§13 row 9) — never silently
only in the flattering version.

---

## §8 Live-forward ledger (prospective; no backfill; WAITING_FOR_LIVE_SOURCE)

- The **nightly reconciler** (`scripts/reconcile_entry_radar.py --nightly`, PR-5b) is the
  sole durable writer (`data/entry_radar/**`), hard-gated by
  `engine.ledger_lane.nightly_advance_enabled()` and running only in the US nightly lane.
  The W4 intraday lane never writes durable evidence (single-writer law).
- **Intake:** the reconciler consumes the W4 event spool
  (`live_flow/entry_radar_events/**`) exclusively. While no valid W4 live stream exists,
  the reconciler writes the ledger state `WAITING_FOR_LIVE_SOURCE` with a session stamp —
  it never manufactures observations, never synthesizes candidates from nightly
  artifacts, and never backfills.
- **Live-forward start clock (frozen rule, not a date):** live-forward eligibility begins
  at the first RTH session whose W4 spool events (a) carry `observed_at` at or after that
  session's open, (b) postdate this document's merged-commit timestamp, and (c) arrive
  through the spool-before-consume path. The first eligible session is recorded in the
  ledger as `live_forward_start` when it occurs. Observations seen before that recorded
  start can never be relabeled live-forward.
- **Prospective ordering is the decisive tier:** every candidate row is written before its
  outcome exists; outcomes attach only at later nightly passes. Episode/event history is
  append-only: states progress, prior states remain, false starts remain forever, no
  silent deletion.
- **Q4** (lobe-enlisted G0 vs G0-alone) accrues here and only here.

---

## §9 NC-2 proximity kill arm (mandatory, inherited from RUL-28)

- The **primary** comparison is proximity-MATCHED by construction (proximity decile sits
  in the §7 CEM cell) — that is the §11 design, not the kill arm.
- The **kill arm is a with/without contrast**, so it can actually fire: for each graded
  confirmatory question, the identical machinery is re-run with the proximity decile
  **dropped from the CEM cell** (all other mechanics unchanged — same k, same distance
  law, same exclusions). The pair (proximity-matched primary, proximity-unmatched
  companion) is read together: if the unmatched excess is favorable (CI excluding 0)
  while the matched excess is not, the result is a **PROXIMITY SHADOW** — apparent edge
  that dies when proximity-to-recent-low is controlled — and is reported as such, never
  as detector edge. If the matched primary survives on its own, the arm reports
  proximity-controlled edge. `DNR:KILL-WASHOUT-TURN` is confronted by name in every such
  report, and no W5 language may claim its territory has been cleared.
- For washout-arming detectors the operative counterfactual is **turn-vs-no-turn at
  equal proximity**: for Q2/Q3 the NC-2 read additionally restricts the comparison to
  C1-armed-but-unturned episodes in the same proximity band (fired-state equal, turn
  absent).
- **Overlap diagnostic + floor (frozen, redefined so it measures proximity support):**
  with every NC-2 read, publish the share of candidates whose proximity-UNMATCHED
  admissible control set contains ≥ 1 same-proximity-band member — i.e. whether common
  support exists ON the proximity dimension. **Floor = 0.50.** Below the floor the arm's
  verdict is **UNINFORMATIVE — never KILLED** (no common support is not a proximity
  shadow).

---

## §10 The confirmatory family (five questions, frozen; BH q = 0.10, m = 5)

FDR control: Benjamini–Hochberg at **q = 0.10** with the denominator **fixed at m = 5**
(the declared family size) regardless of how many questions grade — an ungraded question
contributes no rejection and never shrinks the denominator (the conservative reading of
the frozen family). One frozen primary metric per question; everything else exploratory
and labeled so. A question grades only when its §12 floors clear; an ungraded question
reports ACCRUING with counts, spends no confirmatory look, and the results state the
graded subset explicitly whenever it is smaller than five.

- **Q1 — G0 vs matched controls (Panel-B, TEST).** Does G0 outperform matched controls at
  H=10, net of §11 costs? Primary: per-name-first mean excess vs matched controls at
  H=10. Subject to §4's row-16 agreement floor: below 90% G0-date agreement on the
  Panel-A ∩ Panel-B intersection, Q1 reports UNINFORMATIVE (population identity not
  established).
- **Q2 — C2 vs C1-minus-C2 (Panel-A, TEST).** C2a is a strict subset of C1; the frozen
  contrast is C2a candidates vs C1 episodes that produced **no** C2a fire during the
  episode's nonterminal life (anchored at their respective decision clocks). Primary:
  difference in excess-vs-controls at H=10. **Bias disclosure (direction named):** the
  B arm conditions on the absence of a future in-window event (no cross during the
  episode's life, which ≈ the outcome window), and a C2a cross mechanically requires
  oscillator/price recovery — so the B arm is depleted of recovering episodes and the
  contrast is biased **anti-conservative (upward)** for Q2. Consequences, frozen: (a) a
  budgeted PIT-clean sensitivity arm (§13 row 17) re-reads the contrast as C2a candidates
  vs ALL C1 candidates (no future conditioning), both reported together; (b)
  interpretation ceiling — a favorable Q2 is partly mechanical and does not, on its own,
  evidence incremental information in the turn; the sensitivity arm and Q3 carry that
  weight.
- **Q3 — C3 vs C2 (Panel-A, TEST, common-eligibility rows only).** Does C3 reduce false
  starts without surrendering excess? Primary: false-start-rate difference (C3 − C2a,
  per-name-first). Guardrail (secondary, frozen): non-inferiority on excess with margin
  **−1.0pp** at H=10, read as three states — NON-INFERIOR (95% CI low of the C3−C2a
  excess difference > −1.0pp), ADVERSE (CI high < −1.0pp), else INCONCLUSIVE. Per §0(e)'s
  measured dispersion, INCONCLUSIVE is the expected state at the §12 floors; the
  guardrail becomes decision-bearing only at the accrual its own CI supports, and it
  never migrates into the primary after results are seen.
- **Q4 — lobe-enlisted G0 vs G0-alone. LIVE-FORWARD ONLY.** No historical enlistment
  reconstruction. Additionally matched on cap bucket / ADV tier / hotness tier. Primary:
  H=10 excess difference. Accrues until prospective observations exist; expected state in
  W5's package: ACCRUING with n=0 and `WAITING_FOR_LIVE_SOURCE`.
- **Q5 — G0 vs incumbent entry gauge (Panel-B, TEST).** Does G0 arrive earlier at
  equal-or-better false-start burden? Matching (frozen, two-sided so the question can
  fail): each G0 candidate joins the same ticker's **nearest** incumbent-gauge fire
  (§3 construction) within **±30 sessions** of the G0 decision; the pair's gap =
  incumbent knowability session − G0 decision session, **signed** (negative when the
  incumbent fired first). Primary aggregation (per-name-first, explicit): per name, the
  median signed gap over its matched pairs → cross-name mean of those per-name medians;
  the month-cluster bootstrap resamples decision months and recomputes the full two-step.
  PASS-shaped iff the 95% CI excludes 0 favorably AND the point estimate ≥ **+2
  sessions** (the pre-registered practically-meaningful minimum lead). Guardrail
  (frozen, three-state like Q3's): false-start-burden difference on the matched set
  (G0 rate − incumbent rate) with margin **+5.0pp** — EQUAL-OR-BETTER (CI high ≤ +5.0pp),
  WORSE (CI low > +5.0pp), else INCONCLUSIVE (expected at floors per §0(e)). Matched
  coverage (share of G0 candidates matched) and unmatched candidates are always
  reported; a sensitivity line treats unmatched G0 candidates as +30-session leads (the
  bounding read); no lead-time number without its matching rule and coverage.

**Verdict vocabulary** (contract + commission §23): HISTORICAL REPLAY / TEST /
WALK-FORWARD / ACCRUING / LIVE-FORWARD ACCRUING / NULL / PROXIMITY SHADOW /
UNINFORMATIVE / exploratory / descriptive. Never: validated, proven edge, winning
probability, production alpha, promoted detector, causal (absent a supporting design), or
any trade recommendation. A statistically favorable historical replay is not promotion;
live-forward is decisive for any later promotion claim.

---

## §11 Inference, costs, placebos

**Inference (PSS §7 ruler, reused with declared deltas):**

- Per-name-first aggregation everywhere (E1 errata law). Unit of the primary statistic:
  episode-level excess → per-name mean → cross-name mean (Q5's per-name statistic is the
  median gap, §10).
- **Month-cluster bootstrap**, cluster = calendar month of the decision session, **NB =
  1000**, months drawn with replacement **at the observed month count**; each replicate
  recomputes the full per-name-first aggregate (and, for difference metrics, the
  difference) on the episodes of the drawn months. Two-sided p = `min(1, 2·min(share(stat*
  ≤ 0), share(stat* ≥ 0)))` with the `(1+count)/(NB+1)` correction; 95% percentile CI
  printed with every estimate. Ticker-only clustering is forbidden (DT-R14). A
  cluster-robust t over monthly means is **printed alongside** every bootstrap p (the
  normal-approx-at-few-blocks trap disclosure); BH is keyed on the bootstrap p, both are
  shown.
- **Seeds (frozen rule):** `seed(family) = int(sha256("entry_radar_w5:" + family)[:8],
  16)`. Confirmatory seeds, computed and pinned (machine-derived 2026-08-15, not
  hand-typed): Q1 → `seed("Q1_g0_vs_controls")` = 3597397836; Q2 →
  `seed("Q2_c2_vs_c1minus")` = 2910048454; Q3 → `seed("Q3_c3_vs_c2")` = 2348434836; Q4 →
  `seed("Q4_lobe_enlisted")` = 3766887129; Q5 → `seed("Q5_g0_vs_incumbent")` =
  3329020363. A PR-5b test recomputes each from the rule and pins the printed values.
  Every other seeded read derives from the same rule with its §13 cell name; the results
  package prints each seed used.
- Nothing in W5 is fitted; if any future read fits anything, it is walk-forward or it is
  disqualified.

**Costs (contract §10 frozen; mechanics pinned here):** per-side cost = `max(measured
median half-spread at the signal timestamp when lawful NBBO exists, liquidity floor)`.
NBBO mechanics (frozen): vendor `v3/quotes` at the decision timestamp T — the last ≤ 50
quotes with `timestamp ≤ T` inside `[T − 15 minutes, T]` and inside T's session;
half-spread per quote = `(ask − bid) / 2 / midpoint` on valid quotes (bid > 0, ask > bid);
per-side measured cost = the median, in bps. Missing/invalid/unentitled NBBO → **the floor
binds** (missing NBBO is never zero cost). Liquidity floors on median trailing-60-session
dollar volume (vendor plane, close×volume): ≥ $50M → 5 bps/side; $5M–$50M → 15 bps/side;
< $5M → 40 bps/side. **Round-trip (2× per-side) applies to net outcome metrics.**
Confirmed-bar detectors' T = the P0 timestamp (first trade after known_at; opening-auction
spreads are the honest executable spread). Cost provenance (`measured` vs `floor`) rides
every episode.

**Placebos (matched-construction, frozen):** for Q1/Q2/Q3, a mechanism-stripped analog —
per candidate, **R = 5** pseudo-candidates on the same ticker at uniformly-drawn sessions
(seeded per §11's rule, cell names `placebo_q1/q2/q3`) on which **the same detector did
not fire**, drawn **within the candidate's own era** and same proximity decile, their
outcomes averaged per candidate, then graded through the identical control/aggregation
machinery. Published beside the real results, never suppressed. (The stratified
matched-control design is itself the richer §11 control; the placebo arm guards the
machinery, not the thesis.)

---

## §12 Floors (grading eligibility)

A confirmatory question grades only when **each arm** holds: (i) ≥ 30 episodes, (ii)
spanning ≥ 12 distinct decision months, and (iii) an **effective-N of distinct names ≥ 8**
(1/HHI over per-name episode shares — the contract §18 A2.5.6 instrument, so 30 episodes
from 2 names cannot grade) on TEST (for Q5: the same three floors over matched pairs; for
Q4: over live-forward rows). `n_names`, the HHI, and the month count print beside every
estimate. Below floors: ACCRUING, look unspent, no verdict vocabulary beyond
ACCRUING/UNINFORMATIVE. Floor honesty (per §0(e)'s measured dispersion): these are
sample-integrity minimums; at exactly these floors a ±3–5pp CI half-width is expected, so
small true effects will read INCONCLUSIVE rather than produce a verdict — stated here,
not discovered later. External reporting stays governed by the separate
**50-matured-observation floor** (`MASTERMIND_EVALUATION_STANDARDS.md` §4.7): below it,
accrual-status-only on any external surface. qledger's internal 25-distinct-date ACCRUING
boundary is a third, different threshold; the three are never conflated.

---

## §13 The complete TrialLedger look budget (declared before any outcome read)

Family: **`entry_radar`** (ONE flat pooled family; no sub-families, no second store, no
side ledgers — R1 registry precedent). Declared budget = **253 cells**, itemized:

| # | cell block | cells |
|---|---|---|
| 1 | Confirmatory primaries Q1–Q5 | 5 |
| 2 | Confirmatory guardrails (Q3 excess non-inferiority; Q5 false-start burden) | 2 |
| 3 | NC-2 kill arms (matched-vs-unmatched contrast + equal-proximity read, one per question) | 5 |
| 4 | False-start sensitivity grid, 27 threshold/horizon cells × 5 detectors (diagnostic-only) | 135 |
| 5 | Secondary horizons {3,5,21} × detectors {G0,C1,C2a,C3,C5} excess-vs-controls | 15 |
| 6 | Primary per-detector outcome tables (H=10 excess/MFE/MAE/false-start/costs/target-before-invalidation/gap-through-invalidation/ex-div flag counts) × 5 | 5 |
| 7 | FIT-era exploratory mirrors of row 6 (labeled HISTORICAL/FIT) | 5 |
| 8 | Cohort cuts: 8 cohorts × 5 detectors (descriptive, counted anyway) | 40 |
| 9 | C32 conditioner: Q1/Q2/Q3 × {with, without} × {gap-catalyst, deep-washout} | 12 |
| 10 | Matched-construction placebos (Q1/Q2/Q3) | 3 |
| 11 | C2 exploratory variants c2b–c2f vs c2a (H=10 excess, look-counted per A5.3) | 5 |
| 12 | Incumbent-gauge standalone table (Q5 context) | 1 |
| 13 | Common-eligibility gap diagnostic | 1 |
| 14 | Refusal / coverage census (incl. `uninformative_no_control` and sector-coverage shares) | 1 |
| 15 | Survivorship-robustness arm (Q1, delisting-inclusive 2021+ name list) | 1 |
| 16 | Basis-fidelity parity check (curated vs vendor plane, Panel-A ∩ B; carries the §4 90% agreement floor binding Q1/Q5) | 1 |
| 17 | Q2 PIT-clean sensitivity arm (C2a vs ALL C1, no future conditioning) | 1 |
| 18 | Regime-conditioned read: {stressed, quiet} × 5 detectors (H=10 excess) | 10 |
| 19 | C4 recovery-count strata on C2a (counts 1/2/3, H=10 excess) | 3 |
| 20 | Motivating-exemplar read (KRUS/MCK/NVDA/REGN/YELP, descriptive; §18 lead obligation) | 1 |
| 21 | Anchor-asymmetry bounding read (subjects re-anchored at session close, per family group) | 1 |
| **Σ** | | **253** |

Mechanics: the **execution site is this W5 session's full checkout** (data/ materialized;
`data/trial_ledger.jsonl` present with its pre-existing families — the runner asserts the
ledger file exists and already carries unrelated families before appending, refusing on
an empty or missing store; the sparse-worktree truncation hazard is thereby excluded).
After this document merges, the budget-declaration step runs
`TrialLedger.log_declared_budget(253, family="entry_radar", reason="w5_prereg=<merged
40-hex commit sha>; doc_sha256=<64-hex sha256 of this file's frozen prefix at that
commit>; itemized §13")` — the exact strings the §14 gate verifies. **The 253 cell NAMES
are enumerated in the code mirror** (`engine/entry_radar/replay/prereg.py::LOOK_CELLS`),
and the runner's look-logger **refuses any cell name outside that list** — the mechanism
behind §15.C's "undeclared look ⇒ caught". Every executed cell logs
`log_trial({cell:<name>, ...}, family="entry_radar", source="w5_replay",
info_cutoff=<data vintage>)` **before** its result is computed. Any look beyond these 253
requires a §16 amendment declaring it (and its addition to `LOOK_CELLS`) first. qledger's
own 5/21-session chassis grades are Evaluation OS machinery, not W5 looks; W5's ruler
never reads them as its verdict (§17/§20 separation).

---

## §14 Mechanical enforcement (the runner refuses; scope stated per gate)

The replay/outcome runner (`scripts/entry_radar_replay.py`) executes NOTHING until every
gate passes, in order, mirroring `engine/rule_experiments.py::verify_spec_hashes`
(refusal = a `PreregGateRefusal` naming the gate):

- **G-1 prereg frozen-prefix hash:** sha256 of this file's bytes **up to and including
  the §16 header line** equals the constant frozen into the runner at PR-5b (the hash of
  that prefix at the merged PR-5a commit). The prefix is immutable forever; §16
  amendments append strictly AFTER the marker, so a lawful amendment never changes the
  G-1 hash while any edit to the frozen body refuses. Tamper-vs-amendment is thereby
  mechanical (§15.C tests both directions).
- **G-2 merged ancestry:** the recorded prereg commit is an ancestor of the runner's HEAD
  (`git merge-base --is-ancestor`), i.e. the prereg is an earlier merged main commit, not
  a local file. Requires full git history (the run site's checkout is unshallowed; a
  shallow probe FAILS CLOSED with a message distinguishing "history unavailable" from
  "not an ancestor").
- **G-3 ledger admission:** `data/trial_ledger.jsonl` holds the §13 `declared_budget` row
  for family `entry_radar` with n=253 whose reason carries exactly the G-1/G-2
  identifiers — AND the ledger already carries pre-existing unrelated families (the §13
  anti-truncation assertion). Scope honesty: G-3 verifies the declaration exists; the
  per-look bound is enforced by the `LOOK_CELLS` refusal in the look-logger (§13), and
  the battery proves both.
- **G-4 spec hashes:** every §1 hash recomputed from `DETECTORS` matches; `F1_FUSION`
  still refuses (`NotYetSpecified`).
- **G-5 G0 staging fidelity:** the staged Terminal emitter reproduces the W2 fixture dot
  dates + `known_ts` values on the fixture names (curated census-vintage feed) before
  any outcome attaches. **Scope honesty: G-5 licenses the staged code path, not the
  Panel-B population** — the vendor-basis Panel-B G0 population is licensed only by §13
  row 16's measured ≥90% agreement floor, below which Q1/Q5 report UNINFORMATIVE (§4).
- **G-6 holdout fence:** the runner's era filter refuses any decision session >
  2026-02-13 (and any read of live-forward rows); the fence is mutation-tested (§15.D).

Every gate has a battery row (§15.C) proving a mutated input is refused.

---

## §15 Adversarial battery (ships as tests with PR-5b; commission §24 A–M)

A. outcome leakage (future-bar append + EOD mutation ⇒ pre-decision state bit-identical;
past-bar mutation ⇒ outcome row unchanged); B. reference price (signal-bar close refused
for confirmed-bar P0; C1/C2 use decision-time sampled price; per-episode plane
consistency: `p0_basis` and `atr_basis` on one plane or refuse — the §4 law); C. look
ledger (prereg frozen-prefix hash delete/alter ⇒ refuse; a lawful §16 append ⇒ G-1 still
passes; spec-hash mutation ⇒ refuse; a `log_trial` with a cell name outside `LOOK_CELLS`
⇒ refused); D. holdout (read attempt ⇒ refusal; boundary cannot slide post-results — the
boundary is inside the frozen prefix; the {15,21}-horizon seam is exactly as §1 states,
mutation-tested); E. controls (day-+6 firer excluded; `suppressed_by_rearm` excluded;
proximity mismatch rejected; distance cap enforced); F. common eligibility (removing one
detector's warm-up eligibility removes the pair; the gap is counted); G. MFE/MAE
(strictly-forward window; signs; the LIVE day-0 sampled segment participates in
false-start ordering; confirmed-bar rows unaffected by day-0 machinery; minute coverage
richness cannot change the primary beyond the declared day-0 segment); H. censoring
(truncated/delisted episode survives with `terminated_reason`); I. costs (missing NBBO ⇒
floor binds, never zero; floor binds when measured spread is lower); J. NC-2 (the
matched-vs-unmatched contrast produces PROXIMITY SHADOW semantics when unmatched-only is
favorable; inadequate overlap ⇒ UNINFORMATIVE, never KILLED); K. Q4 (historical lobe
reconstruction attempt ⇒ refusal); L. qledger (the reconciler registers `horizon_d=21`
`horizon_unit=trading_days` — a test fails if anyone sets 10; claims registered via
`register_batch` only; C4/F1 produce no claim); M. side-door law (permuting per-name
outcome histories changes no detector output, score, or routing input — ticker stays
memory only). Every test is non-vacuous: each carries a mutation control proving the
assertion can fail.

---

## §16 Amendments (append-only; none at freeze)

*(Amendments append strictly below this line — G-1 hashes everything above it. Any entry
after first replay results exist must state what results its author had seen.)*

---

## §17 qledger registration (Evaluation OS; separation law)

Registered by the **nightly reconciler only**, via `register_batch()` (never `register()`
in a loop, never from the intraday lane), for **live-forward episodes only** (historical
replay rows are never registered — no backfill):

`make_claim(desk="entry_radar", asof=<decision session ISO>,
claim_family="entry_radar_<detector_id>", scope_type="entity", scope_key=<ticker>,
direction=1, horizon_d=21, horizon_unit=HORIZON_UNIT_TRADING,
timestamp_quality="CRAWL_BOUNDED", bench="SPY", control=<sector ETF via
sector_of_ticker/control_for_sector>, sector=<GICS name>, falsifier=<the §10 question
family the detector answers + DNR:KILL-WASHOUT-TURN territory>, extra={authority:
all-false block, registration_note})`, where `registration_note` states substantively:
**"accruing forward meter; registration implies no directional performance claim; no
backfill; promotion requires clearing the §11 gauntlet and DNR:KILL-WASHOUT-TURN
falsifier territory."**

- `asof` = the decision session. qledger's own grader fills at the first close strictly
  after `asof` — i.e. the D+1 close — on **its own curated price plane**; that entry
  basis and plane differ from Radar's P0-anchored vendor-plane H=10 read **by design**,
  and a divergence between the two meters is expected, disclosed, and not a defect.
- `horizon_d=21`: on-rung (grades [5, 21], bracketing the program's H=10) and keeps the
  Evaluation OS ruler visibly distinct from Radar's own. (Measured 2026-08-15 against
  live code: post-P0b `in_scope_horizons(10) == [5, 10]` — the earlier "off-rung 10
  grades only at 5" rationale aged out; the commission's registration instruction stands
  and is followed, with the rationale corrected here. §15.L asserts the reconciler
  registers 21.)
- **Separation (contract §11 / commission §20):** Evaluation OS emits 5- and 21-session
  grades; Radar's own frozen ruler computes the H=10 primary read. No surface merges
  them; H=10 is never called an Evaluation OS verdict; qledger ACCRUING (< 25 distinct
  dates) and the external 50-observation floor are different thresholds and are never
  conflated.
- C4 registers nothing (cannot fire; no fabricated directional claim for symmetry). F1
  remains absent/refusing. Registration outcomes are recorded per claim from
  `register_batch`'s returned slots (basket_turn precedent), fail-closed.

## §18 Consequence matrix (what grading can and cannot change)

- Any Q grading PASS-shaped (CI excluding 0 in the favorable direction, BH-surviving at
  m=5): the result is reported as HISTORICAL REPLAY / TEST evidence with its NC-2 arm,
  placebo, coverage, and refusal census beside it. **It changes no authority**: no
  ranking, sizing, gating, Prophet input, or user-facing performance language. Promotion
  remains a future act requiring live-forward evidence, the §11 gauntlet, and the
  kill-territory confrontation.
- Any Q grading NULL / adverse / PROXIMITY SHADOW / UNINFORMATIVE: printed with the same
  prominence (nulls-printed law), and the detector keeps accruing display-tier — a null
  never blocks accrual.
- **Adjudication-coverage lead (standards §11.1–.2, frozen obligation):** every graded
  question's report LEADS with (a) the §13 row 20 motivating-exemplar read
  (KRUS/MCK/NVDA/REGN/YELP — the contract §18 A1.6 commissioning observations) and (b)
  the statement that TEST closes 2026-02-13, six-plus months before any W5 read, so **the
  current regime is out of sample by construction** — before any aggregate number is
  quoted.
- Every result carries its evidence tier: HISTORICAL / TEST / WALK-FORWARD /
  LIVE-FORWARD.
- Lapse: if the upstream detector specs change version, the affected cells lapse and
  require fresh registration under the new spec hashes.

## §19 Pre-merge red-team audit (2026-08-15, pre-evidence; results seen: NONE)

Per the R4 §9/§10 discipline, an independent fresh-context Opus reviewer attacked this
document before merge (no Radar outcome existed to see). Findings: 5 BLOCKER, 13 MAJOR,
11 MINOR — **all adjudicated and folded into the frozen text above in place** (lawful:
pre-merge, pre-evidence, the document was a draft until this commit). The blockers, for
the record: NC-2 arm was definitionally identical to the primary (fixed: §9
matched-vs-unmatched contrast + redefined overlap); Q5's primary could not fail (fixed:
§10 two-sided ±30 matching, signed gaps, +2-session minimum lead); both guardrails were
unpassable at the floors (fixed: §0(e) measured dispersion + three-state guardrail
verdicts); the first §16 amendment would have bricked the G-1 gate (fixed: frozen-prefix
hash law); Panel-A's A0 basis was ambiguous across planes (fixed: §4/§6 vendor plane on
both panels + battery row). Majors folded: seam restated at 21 sessions; BH denominator
pinned at m=5; distinct-name effective-N floor added; the LIVE-detector window restored
to the contract's `(decision, decision+H]` with the day-0 sampled segment; Q3/Q5 panels
named; k-NN normalization/cap/tie law; `asof` + fill + plane disclosure in §17; the
horizon-21 rationale corrected against measured `in_scope_horizons`; Q2's
conditioning-bias direction named + PIT-clean sensitivity arm budgeted; look-budget
enforcement mechanized via `LOOK_CELLS`; the grid counted per detector (135); dispersion
measured rather than declared unknowable; regime/C4 reads budgeted; G-5 scope honesty +
the row-16 agreement floor made binding; Q5 aggregation written out; missing-sector law;
ledger execution-site + anti-truncation assertion; exemplar/current-regime lead
obligation. Minors folded: month-draw count, p-value clamp, C32 WITHOUT denominator,
public-symbol citation, zero-control bounding read, k distribution reporting, G-2
shallow-history message, placebo pins (same detector / own era / R=5), row-6 outcome
naming, decile basis/window, anchor-asymmetry split disclosure + bounding read. The full
finding table with quotes lives in the W5 results package
(`research/live_entry_radar/w5_results/`, committed with PR-5c) as the audit receipt.

*Prepared pre-outcome by the W5 session. The §13 budget row and the §14 gates make this
document load-bearing: without the merged prereg, the machinery refuses to read a single
outcome.*
