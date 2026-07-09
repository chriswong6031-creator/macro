# HK Pick Lab — candidate books on forward entry ledgers (masterplan by Fable)

Date: 2026-07-09 · Status: ADJUDICATED — build authorized (display-tier)
Program id: `hk_pick_lab` · Siblings: `research/PICK_LAB_MASTERPLAN_BY_FABLE.md` (US),
`research/CHINA_PICK_LAB_MASTERPLAN_BY_FABLE.md` (CN)
Operator directive: 2026-07-09 session — "HK and China both move fast… everything is
washed out and calm and suddenly BAM… the 1D confluence should be way better at
identifying alpha and leaders than 2D and 3D laggards who crossed over, based around,
but did not blast off right away, meaning something might be wrong."

---

## §1 Problem statement and diagnosis

HK is the market where the operator's 1D-velocity hypothesis has the strongest
first-principles case: **no daily price limits** (nothing truncates the washout→ignition
move), thin liquid universe (~160 names) dominated by a handful of China-beta
bellwethers, and regime whiplash driven by offshore flows (ADR overnight lead,
southbound, VHSI). A name that prints a 1D confluence and *immediately* runs is showing
real demand; a name that crossed on 2D/3D, based, and did NOT blast off is — per the
operator's hypothesis — showing *absence* of the buyer that the setup promised. The lab
formalizes both sides: the fast cohort as buy-books, the stale-cross cohort as a
diagnostic.

The July-2026 HK overhaul already built most of the lab's raw material (the operator:
"already basically a lab"): the WASHOUT WATCH state ladder + forward ledger (#1959),
the 8-force command panel + combustibility verdict (#1965), ADR bridge / CBBC leverage
map / filing bus / narrative / catalyst organs with their own ledgers, A/H value at
near-GO (H3, DSR 0.879), per-name global-beta roles. **The HK lab integrates these
organs as book inputs; it does not duplicate them.** Existing organ ledgers keep their
own rulers (washout-watch grades asymmetric ignition-capture); the lab adds the
*comparable cross-book ruler* (21-session HSI-excess) so 20 differently-shaped books
can be ranked on one scoreboard.

Standing kills that bound the design: HK residual/selection momentum KILL (DSR/IC),
southbound holding-Δ as ranker NO-GO (lag eats it), southbound flow-vs-price divergence
FALSIFIED, COILED do-not-port to HK, Connect-inclusion events NO-GO.

## §2 Rulings (HKPL-R1..R10)

- **HKPL-R1 (tier).** Display-tier; ranks/gates nothing in production; organ ledgers and
  their rulers untouched. Promotion = gauntlet + time-preserving placebo, per house law.
- **HKPL-R2 (frozen configs).** PL-R2 verbatim (config_hash; v2 on any change).
- **HKPL-R3 (ruler).** Primary: **21-session excess vs `^HSI`** for all entry books
  (5/10/63 descriptive ladder; MFE/MAE over 25 sessions). Washout-family books
  additionally print MFE-capture/MAE-pain descriptively (kinship with the organ's
  asymmetric ruler) — the excess column is the verdict column. Inverse books graded as
  avoid-accuracy (expected negative).
- **HKPL-R4 (execution + halt law).** Exec = next HK session, fill at close
  (`fill_basis="close"`; no price limits, no T+1 buy constraint; board lots ignored at
  ledger tier — noted, not modeled). **Halts:** if the exec session has no print, fill
  at the first traded session within 5 sessions, else the fire is voided
  (`halt_voided` counter). A name halted >5 consecutive sessions inside a grade window
  grades to last trade with `halted=true` — never silent ffill.
- **HKPL-R5 (controls).** `hklab_random_ctrl` + buy-anytime base rate mandatory; all
  headline numbers are lifts.
- **HKPL-R6 (episodes/n).** Refire lockout 21 sessions (satisfies DT-R14 episode
  collapsing at book grain); effective-N = distinct fire dates; ACCRUING floor n≥25 /
  ≥3 months / ≥6 dates. The HK universe is small (~160) — books cap at **8 picks/day**
  and low-n books print honest n rather than being dropped.
- **HKPL-R7 (organ inputs are PIT).** Books may consume same-night organ artifacts
  (washout_watch states, ADR bridge, CBBC, filing bus, narrative, catalyst calendar,
  beta roles, SFC shorts) — all are nightly-committed PIT surfaces with
  `asof_freshness` stamps; a book input staler than 2 HK sessions disables that book
  for the night (fail-closed, mirrors the organ freshness law).
- **HKPL-R8 (lane).** Asia-close lane, after `build_hk` completes; ≤2 min; `CN_LANE=asia`
  required for ledger appends; artifacts under the asia job's commit globs.
- **HKPL-R9 (no HK long-hold grids).** Same reasoning as CN (CNPL-R10) plus the H3/H2a
  edges are already accruing under their own programs. Deferred with its own prereg.
- **HKPL-R10 (headline hypotheses).** (a) 1D-velocity family vs the stale-cross
  diagnostic: does immediate blast-off after a 1D cross out-perform the based-but-
  didn't-run 2D/3D cohort? (b) organ-confluence books (washout×1D, washout×buyback)
  vs the organ states alone. First operator read **2026-08-20**.

## §3 Candidate registry (20 books)

Defaults: max 8 picks/day; refire lockout 21 sessions; universe = HK search universe
(~160 names); liquidity floor 63d ADV ≥ HK$20M (null ⇒ `liq_unknown`); books drop
names with no print in the last 2 sessions (suspension guard).

### Family A — 1D velocity (flagship-2 family; ruler: 21d HSI-excess)

| # | engine_id | Construction (frozen v1) | Rank by |
|---|---|---|---|
| 1 | `hklab_1d_pure` | 1D RSI-MACD cross-up ≤2 sessions AND 1D StochRSI k×d cross ≤8 AND 1D from_os AND rsi14 < 70 | edge_z |
| 2 | `hklab_1d_ignition` | 1D MACD cross ≤3 AND washout_watch state ∈ {ignition_watch, pullback_entry_watch} (organ × 1D trigger) | confluence_count |
| 3 | `hklab_1d_adr` | 1D MACD cross ≤2 AND ADR-bridge implied_open_gap_pct ≥ +0.5 (overnight US confirmation of the HK cross) | gap size |
| 4 | `hklab_1d_blastoff` | 1D MACD cross ≤3 AND 3D MACD not yet crossed AND above 200dma (the fast cohort the 2D/3D gate misses) | 5d return |
| 5 | `hklab_1d_regime` | 1D MACD cross ≤3 AND risk_state = Risk-on AND peg not weak-side pressure | edge_z |

### Family B — washout/ignition (organ-integrated)

| 6 | `hklab_washout_ignite` | washout_watch state = ignition_watch (the organ's strongest state, graded at the lab's comparable ruler — the organ ledger keeps its own asymmetric ruler) | confluence_count |
| 7 | `hklab_washout_sb` | state ∈ {washout_watch, ignition_watch} AND `SB_ACCUM` in confluence_signals (southbound LEVEL-turn as organ signal; Δ-ranker NO-GO cited §8) | accum_z |
| 8 | `hklab_washout_buyback` | any washout state AND `BUYBACK` in confluence_signals (company bid under a washout) | confluence_count |
| 9 | `hklab_pullback_entry` | state = pullback_entry_watch (ignited, now re-testing — the second-chance entry) | rsi reclaim depth |
| 10 | `hklab_knife_avoid` | **INVERSE (avoid):** knife_risk = true names — expected NEGATIVE excess (prices the knife chip) | dd depth |

### Family C — HK-unique structure

| 11 | `hklab_cbbc_fuel` | CBBC leverage_state ∈ {bear_skew, bear_skew_froth} on the name/underlying AND price > 20dma (dense bear call-cluster ABOVE spot = forced-buy fuel on rallies; leverage-mechanics, not price-derived) | bear skew ratio |
| 12 | `hklab_ah_value` | Top A/H-discount own-history percentile names (H-leg cheap vs A twin; the H3 near-GO edge as a book) | discount percentile |
| 13 | `hklab_short_squeeze` | SFC short-pressure top quartile AND RSI reclaim through 30–50 band (crowded short + price turn; H2a ACCRUE leg) | short pressure |
| 14 | `hklab_catalyst_narrative` | Catalyst within 5 sessions AND attention_shock_z ≥ 1.5 AND tone ≥ 55 AND rsi14 < 70 (attended catalyst, not yet extended) | shock z |

### Family D — beta/regime

| 15 | `hklab_beta_amplifier` | risk_state = Risk-on AND beta role = amplifier AND above 200dma (formalizes the measured +0.41%/21d risk-on amplifier read) | beta |
| 16 | `hklab_beta_cushion` | risk_state = Risk-off AND role = cushion (defensive book for the off state) | inverse beta |
| 17 | `hklab_hibor_easy` | liquidity_regime = EASY (peg strong-side, aggregate balance high) AND washout_2w (liquidity-cushioned rebound thesis) | washout depth |

### Family E — ablations + controls

| 18 | `hklab_flagship_nogate` | Top-8 by edge_z IGNORING the signal_gate entry-open/setting-up grouping (gate ablation on the HK board's own edge blend) | edge_z |
| 19 | `hklab_chase_avoid` | **INVERSE (avoid):** washout_watch state = chase_risk (RSI ≥ 70 gapped names) — expected NEGATIVE excess | rsi desc |
| 20 | `hklab_random_ctrl` | 8 deterministic-random liquid names, seed sha256(engine_id+asof) | random |

**Diagnostic (not a book): the stale-cross cohort.** Nightly, the snapshot tags names
whose 2D/3D cross is ≥5 sessions old with |return since cross| < 3% ("based but didn't
blast off"). The lab page prints this cohort's forward 21d excess next to
`hklab_1d_blastoff`'s — the operator's "something might be wrong" hypothesis as a
side-by-side chart. No ledger authority; pure display comparison from the same grades
machinery.

## §4 Flagship-2 — the 1D Velocity Desk (surface UI, hk_stocks.html)

Computed inside `build_hk_library` (close panel + organs in scope; O(seconds)):

- **Membership:** union of books 1–5 conditions (any 1D-family fire).
- **Rank:** confluence count (how many of: from_os, washout state, ADR gap, Risk-on,
  above-200) then edge_z.
- **Chips:** which 1D conditions fired, washout state, ADR gap, CBBC skew, knife/chase
  warnings, beta role.
- Emitted as `site/factordata/hk_1d_velocity_desk.json` + vm key; rendered as a featured
  lane on `hk_stocks.html` beside the existing board (flagship-1 untouched);
  `🧪 Lab` button → `hk_stocks_lab.html`.
- Mirrored to the ledger as `hklab_flagship2_mirror` (not counted in the 20) so both
  flagships ride the same ruler.

## §5 Measurement — shared machinery, HK parameters

```
market="HK": benchmark=^HSI (store.read("hk", ...)),
sessions: price-panel index; freshness via lib/hk_calendar.expected_last_session,
fires: data/hk_pick_lab/fires.jsonl (+ grades.jsonl),
fill: next-session close (HKPL-R4 halt law; fill_basis="close"),
extra fire stamps: risk_state, peg_state, washout_state, adr_gap, beta_role,
                   vhsi_pctile, halted/halt_voided flags
```

Floors/dedup/effective-N/ACCRUING: PL-R4/R5 verbatim. Scoreboard adds `halt_voided`
and per-book `disabled_stale_nights` counters (HKPL-R7 fail-closed honesty).

**Snapshot:** producer block at the end of `compute_hk_standouts()` in
`scripts/build_hk_library.py` (close panel, edge legs, gate, washout list, beta roles
all in scope; never-fatal). Enrichment join (runner): organ artifacts
(`site/factordata/hk_adr_bridge.json`, `hk_cbbc.json`, `hk_filing_bus.json`,
`hk_narrative.json`, `hk_catalyst_calendar.json`), `data/hk_regime/latest.json`,
liquidity/peg state. Persisted `data/hk_pick_lab/snapshots/<YYYY-MM>.parquet`.

## §6 Architecture and wiring

```
engine/pick_lab/hk.py + registry_hk.py       # HK profile + 20 books
scripts/build_hk_pick_lab.py                 # asia-lane runner (≤2 min, CN_LANE=asia, exit 0)
data/hk_pick_lab/{snapshots/,fires.jsonl,grades.jsonl}
site/labdata/hk_pick_lab.json                # horizon_role: entry
site/hk_stocks_lab.html                      # standalone lab page
site/factordata/hk_1d_velocity_desk.json     # flagship-2 (build_hk_library)
```

Runner after `build_hk` in the asia lane; asia commit globs must cover the new paths;
synapse registrations (snapshot infra + lab entry + desk entry) with count-pin updates.
Template edits to `templates/hk.html.j2` follow CN-SYS-R10 page laws (theme.js, t(),
no translated title=).

## §7 UI

- `hk_stocks.html`: flagship-1 board untouched; **1D Velocity Desk** featured lane +
  `🧪 Lab` button.
- `hk_stocks_lab.html`: tabs Scoreboard / 1D Velocity / All Books / Method (+ the
  stale-cross diagnostic chart on the 1D tab). EN/ZH, ACCRUING badges, avoid-books
  clearly NOT-buys, freshness-disabled books visibly flagged. No Long-Hold tab
  (HKPL-R9).

## §8 Kill-registry adjacency (cited at registration)

| Book | Standing kill nearby | Why distinct |
|---|---|---|
| 15,18 | HK residual/selection momentum KILL (DSR/IC) | rank keys are beta-role and the board's fused edge_z (A/H + context legs), not momentum factors |
| 7 | Southbound Δ-ranker NO-GO (H1, lag); SB divergence FALSIFIED | consumes the organ's SB_ACCUM level-turn confluence signal inside a washout state — not a Δ-ranking of the board |
| — | COILED-HK KILLED (do not force-port) | no COILED book exists for HK |
| — | Connect-inclusion (H-INCL/H-INCL2) NO-GO, retired | no inclusion-event book |
| 6,9,19 | (none — organ states are new, display-tier) | organ's own promotion clock unaffected; lab adds a comparable ruler only |
| 11 | (new construction) | leverage-mechanics (CBBC call clusters), not price-derived momentum |

## §9 V1 ship notes (accepted gaps, printed not hidden)

- **Velocity Desk predicates are mirrored, not shared** with `hk.py`'s five 1D book
  implementations (a coordinated refactor was out of v1 scope). Drift risk is real;
  follow-up: extract shared predicate functions and add a contract test.
- **SFC-shorts freshness rides the `sb` organ tag** (conservative fail-closed proxy);
  `hklab_ah_value` has no organ freshness stamp of its own (the A/H store is the
  program's own nightly artifact). Plumb dedicated stamps when those organs get them.
- **`hklab_1d_blastoff` ranks by return-since-cross** as the 5d-return proxy until the
  producer emits a dedicated ret_5d column.
- The stale-cross diagnostic counts **sessions** (bar-count/session-count mixing was
  caught in review and fixed); its forward grades populate only once the runner has
  live benchmark data — empty state until then.

## §10 Clocks

- **2026-08-20** — first operator read with US/CN labs; 1D-vs-stale-cross diagnostic
  first look; prune degenerate books.
- **2026-10-09** — floor-eligible verdict window for high-frequency books.
- **2027-01** — H3 come-back clock (A/H panel deepens) — book 12 re-baselines if the
  H3 program promotes/changes construction.
