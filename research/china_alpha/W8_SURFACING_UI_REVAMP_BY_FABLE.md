# China Alpha W8 — Surfacing & UI Revamp — by Fable (2026-07-10)

*Wave 8 of the ACTIVE china_alpha program (extends CHINA_ALPHA_MASTERPLAN_BY_FABLE.md F1–F9).
Commissioned by operator 2026-07-10 ("sweeping radical reassessment of china_stocks.html").
Census: 11-reader fan-out 2026-07-10 (R1–R11, /tmp/china-revamp/census/).*

## Red-team disposition (three blockers folded into PR-A)

Three red-team blockers from the pre-build review were folded into the PR-A implementation:

**B1 — FALLING precedence veto (design):** Under the original OR-logic draft, 002709 (5d −24.4%,
MACD hist collapsing +0.315→−1.061) would have landed READY on its fresh 1W cross (bars_since=2).
The fix is a HARD PRECEDENCE cascade — FALLING is evaluated first and no cross evidence can
override it. Pinned as a fixture test: 002709→FALLING regardless of cross freshness.

**B2 — Article-2 display-tier framing (legality):** The RIPENING shelf lives inside
china_standouts (a registered board_ordering surface). Zones must be pure display regrouping —
not a rank-weight change. Enforced: (a) imminence (macd_bars_to_cross) REMAINS the primary
within-zone sort key; (b) zones carry no ordering/attention authority (not wired to alert_triage,
top_setups, or push floors); (c) zone artifact registered in synapse.yml at display/context tier
with may_rank=false; (d) PR adjudication note makes the display-only nature explicit.

**B3 — PRIME tooltip measurement-framing (copy law):** The W8-R4 PRIME label tooltip must be
comparative and measurement-framed ONLY — "historically filled at a lower median premium above
the 20d trough than CONFIRMED (measured, not a forward promise)". The "nearest the low" framing
is false (T4/T3 fill nearer the trough than T2; confirmed by measurement). This blocker applies
to W8-R4 / PR-C (tier vocabulary); PR-A carries no badge rename.

---

## 1. Adjudicated diagnosis

**D1 — The RIPENING shelf is upside-down.** Three verified mechanisms:
(a) *No direction guard*: Cond A (2W stoch ≤ 35) admits free-falling names — 000792 (5d −13.6%,
daily MACD hist collapsing +0.146→−0.253) and 002709 (5d −24.4%, +0.315→−1.061) sit at ripening
ranks #4/#6. (b) *Degenerate ordering*: sort key is MACD imminence, then stoch/10, then
alphabetical tiebreak among 200+ names at stoch=0.0 — DEEPEST washout sorts FIRST (knife-magnet
ordering), and readiness evidence (fresh 1W washout cross, daily MACD turn) is not in the key.
601933 — the freshest deep-washout cross in the universe (bars_since=1, d_at_cross=3.7) — ranked
#205/1166, surfacing only by tiebreak luck. (c) *Info-starved cards*: ~90px rip-cards show no
price, no spark, no MACD state, no washout-depth trend — a knife and a base-former render
identically (verified in screenshot: 000792/002709/601360/601933 all wear the same amber
"2W stoch washout (stoch=1.0)" chip).

**D2 — "Ready" names have no bridge to ENTRY.** A name whose daily/3D confluence is turning
(601360: MACD hist crossed positive, 1W cross from d=3.6) but whose gate verdict is ineligible
(stale cross / quality-block / T3 repaint) has no zone distinguishing it from a name 6 weeks from
turning. Meanwhile fresh T1 crosses that DO pass the gate can be buried by the rank blend
(600519: T1 fresh cross 07-07, ENTRY stage, at 3.0% of its 2-year range — ranked #89/110 because
conviction=11 drives 70% of the blend) while the card contradicts itself four ways (ENTRY badge +
READY 7 + "Extended — wait" + "UNCONFIRMED TURN") — the exact F6 violation class.

**D3 — The stocks-page act-now board is a different, older product.** Sector-ETF cycle-ladder
urgency bucketer (last meaningful logic #1530), no scoring, no themes, no subsectors; in a
washed-out tape it degenerates to TAKE PROFITS 3 / HOLD 1 / AVOID 12 — nothing actionable
(operator: "very boring and nothing to buy"). The baskets page runs the 7-leg theme_scoring
engine with clean-entry gating — a genuinely better product — but BOTH are trend-following:
at a bottom, both must say avoid.

**D4 — Bottom detection exists in-system but feeds no act-now surface.** cn_baijiu basket in
forward_log on 07-08: phase=Trough, osc_slope=+0.1 (turning) — invisible because the sector-turn
chip filter requires kind=='sector' (Food & Beverage L1 osc_slope −0.4 fails), theme_scoring
labels it deteriorating (score 31, trend-lagging by construction), and the US basket_turn_watch
organ explicitly excludes cn_ baskets. Three systems disagree about baijiu silently; the one
reading the turn is wired to nothing the operator was looking at.

**D5 — Tier vocabulary contradicts the ranking and the mental model.** Users read the badge
compounds as "Forming T1"/"Early T2"/"Buy T1". T2 outranks T1 by operator-ratified weight
(1.00 vs 0.90; T2 fills 7.7% above 20d trough vs T1 10.5%) yet the numbering implies T1 is
better. "forming" actually means T1-pending; "early✓" means CONFIRMED T2. Also the "T2 leads T1"
tooltip framing is misleading at universe scale (0.5% precursor rate — disjoint setups).

**D6 — Universe/cap:** all-cap admission is substantially true (30亿 floor is 46% placeholder,
correctly skipped). mktcap display would misclassify ~690 names; real caps exist in
tushare/valuation.parquet (5,596 names incl. circ_mv). No cap-bucket study exists; brainstorm
flags small-cap latent-factor risk without a verdict.

**D7 — Structural riders:** per-ticker chinastockdata JSONs 5 days stale (lookup shows
pre-collapse states for 000792/002709); baskets_china missing the #2010 lst-cap4 parity patch;
ripening/ran arrays silently dropped when cand empty; T3 tooltip cites pre-hardening repaint
figures (23.8%/15.1% vs measured 9.4%/0%); mobile nbgrid forces 155px cards; act-now 3-col
breaks at 390px.

## 2. Design rulings (W8-R*)

**W8-R1 — Ripening becomes a three-zone lifecycle (F1 refinement), display-tier, ledger-logged.**
Zone assignment is a HARD PRECEDENCE cascade (red-team blocker B1 — under OR-logic 002709
would land READY on its fresh 1W cross despite a −24.4%/5d collapse):
1. `FALLING` (evaluated FIRST, vetoes everything): 5d ret ≤ −8% OR (daily MACD hist negative
   AND falling). No fresh-cross evidence can override. Rendered as a collapsed, visually
   distinct "still falling — do not catch / 勿接飞刀" sink at the bottom. AVOID-direction
   annotation; always legal.
2. `READY`: directional evidence live AND daily tape not collapsing — (fresh 1W washout cross
   ≤3 weekly bars AND daily MACD hist ≥ 0 OR rising) OR daily MACD hist turned positive OR 2W
   MACD imminence ≤ threshold. Copy law: READY never uses BUY-family words (F1 stands); label
   "confluence forming — nearest to entry".
3. `BASING`: everything else with setup_live (washout present, decline arrested or drifting).
Fixture tests pinned on the four operator vectors: 000792→FALLING, 002709→FALLING (despite
fresh cross), 601360→READY, 601933→READY.
**Article-2 framing (red-team blocker B2):** the RIPENING shelf lives inside china_standouts
(a registered board_ordering surface). Therefore: (a) imminence (macd_bars_to_cross) REMAINS
the primary within-zone sort key — W8 only replaces the ARBITRARY stable-sort tiebreak among
equal-key names with a deterministic evidence tiebreak (cross bars_since asc); (b) zones are a
VISUAL display re-grouping carrying NO ordering/attention authority — not wired to alert_triage,
top_setups, or push floors; (c) the zone artifact is registered in synapse.yml at display/context
tier with may_rank=false; (d) the PR carries an explicit adjudication note (display-defect fix +
display regrouping, NOT a rank-weight change; CN-SYS-R7 lane respected).
Cap: 24→32 with zone quotas (READY up to 16, BASING fills remainder; FALLING sink capped 8,
collapsed) — update the build invariant `assert len(_ripening_rows) <= 24` → 32 or the build
crashes. Zone thresholds (−8%/5d, hist-slope, ≤3 weekly bars) are **v1 frozen descriptively,
amendment-logged, recalibrated at W6** (F3 discipline — not settled design). Every row logs
zone + evidence flags + sort_key to ripening.parquet as the PRECURSOR that enables the W6
RIPENING→ENTRY conversion grader (which does not exist yet and must be built in W6 — the
schema-union writer tolerates the new columns). Measure the added per-name compute (daily MACD
hist/slope/5d ret over ~1,530 names) against the render budget in PR-A.

**W8-R2 — Ripening cards become full scorecards.** Same chassis as nbcard: zone-colored identity
zone, price, spark, 2W-stoch + trend arrow, MACD glyph strip (D/2D/3D state), washout depth,
range position, days-in-washout, theme chip. Grid single-column <480px (applies to nbgrid too).

**W8-R3 — Act-Now v2 on the stock dashboard (unification, not fusion).** Replace the sector-ETF
bucketer panel with a four-lane board:
1. **Buy now** — theme_scoring act_now.buy (clean entry) + any sector whose ladder says
   BUY NOW/FRESH BUY; each row: name, reco pill, score, 20d rel, member count, link to basket.
2. **In favour — wait for pullback** — act_now.add_on_pullback + DON'T-CHASE sectors.
3. **Bottoming watch** *(new lane)* — baskets/sectors at phase=Trough with osc_slope>0 from the
   cycle forward_log (both kind=sector AND kind=basket rows), later upgraded by the CN basket
   turn organ (W8-R5). Hard copy law: "washout turning — NOT an entry signal"; never says buy.
4. **Reduce / avoid** — act_now.reduce + ladder DECLINE sectors, WITH honesty sub-labels: a
   sector that is simultaneously Trough-phase shows "avoid (trend) · washout turning (tape)"
   side-by-side — FT-R1 disagreement-display pattern, never auto-resolved.
Sectors and themes co-exist as typed rows (SECTOR/THEME chips). No new composite score; no
rank authority; rotation state and cycle state appear as separate chips, never fused
(DON'T-TEST kill honored). Baskets page gets the lst-cap4 parity patch; both pages cross-link.

**W8-R4 — Tier vocabulary v2 (display strings only; keys/ledgers/weights untouched).**
Headline badge renamed to stage-of-cross language, tier code retained as sub-chip:
T2 → **PRIME** — tooltip is comparative and measurement-framed ONLY (red-team blocker B3: T4/T3
fill nearer the trough than T2; "nearest the low" is false): "2D cross with 3D support —
historically filled at a lower median premium above the 20d trough than CONFIRMED (measured,
not a forward promise)"; T1 → **CONFIRMED** (master 3D confluence); T1-pending → **CONFIRMING**;
T3 → **APPROACHING** (projected, provisional); T4 → **FIRST SPARK** (earliest, above-200MA).
EN/ZH pairs; tooltips rewritten with post-hardening repaint figures (9.4% US / 0% CN); "T2 leads
T1" claim removed (disjoint-setups finding, 0.5% precursor rate) and no sequential-progression
implication reintroduced. Mockup adjudication: **Option A adopted** (stage-name badges, tier
code as sub-chip). No excess-edge implication anywhere (T2 CIs straddle zero).
Rename map documented in TIERED_CASCADE.md addendum. Site-wide (badge partial is shared) —
US/HK/CA inherit automatically.

**W8-R5 — CN basket turn-watch organ (the baijiu machine), display-tier, expected-NULL.**
Per-basket (22 curated + 237 THS) states from the EW series: FALLING / WASHED_OUT / BASING /
TURNING / CONFIRMED — same zone grammar as W8-R1 at basket level (washout depth vs own history,
decline arrest, MACD/stoch turn on basket series). Registered as expected-NULL forward meter
reproducing the FT-R9 disclosure-of-record VERBATIM pattern (sector-level standalone
washout→turn printed NULL — Oracle P8 P-W1/S-W3; this is a different construction, not a revival
claim); CN-SYS-R11 obligations (dag.yml asia-lane row, CN_LANE=asia gate, ≤2 min budget); ledger
appended nightly (asia lane); consumed by: Act-Now v2 bottoming lane, theme desk cards ("AVOID
(trend) · TURNING (tape)" dual chip), and per-stock theme chips via THS membership. Never
reorders theme_scoring recos (FT-R1). THS spine gap noted: reads
baskets_china_ths/membership.json directly.

**W8-R6 — Table view (flagship).** A dense row/table view toggle for the standouts board
(ENTRY + RAN/LATE + RIPENING + optionally full setup_live watch universe — the real fix for the
24-cap invisibility: the shelf stays curated, the table can show everything).
- Columns (default on): stage/zone badge, badge v2 (tier), ticker, name, price, Δ1d, sector,
  THS theme (+turn-state chip), conviction, mcap (real, Tushare-joined), off-high, range-pos,
  2W stoch, MACD D/2D/3D glyph strip, days-since-signal (board.parquet first-seen), imminence,
  washout/coiled flags. Column chooser: show/hide + drag-reorder + reset-to-default, persisted
  localStorage per-market key; view toggle (grid/table) persisted; every column sortable
  (user-initiated sort is a user action, not a system ranking claim — default order remains the
  locked system order); filter row: stage, zone, tier, sector, theme, cap bucket, fresh-only.
- Cap-bucket filter is a USER control; engine admission stays all-cap (D6: no evidence for a
  hard split; mcap bucket logged to board ledger for W6 to adjudicate). Board header prints
  cap-bucket composition honestly. Mcap join is NULL-SAFE: unjoined/placeholder names print
  "—", never 0 or the 30亿 sentinel (~690 names would misclassify otherwise).
- Fresh-pick surfacing: "NEW" dot + days-since-signal column (from ledger first-seen; ≤6d
  history today, grows nightly). No edge claim attaches to freshness (#1513 stands): sorting by
  it is available, default order unchanged.
- Ship CN first; port to US + HK next (Canada surface: verify existence before promising).

**W8-R7 — CN mtf_upturn port (per-stock MTF turn organ).** engine/mtf_upturn.py gains a CN path
(china_stocks_raw store + CN universe = board/ripening/theme-member cohort ~≤400 names for
budget); UPTURN_CONFIRMED/WATCH chips on cards + table column + turn-setups table on the
dashboard; forward ledger asia-lane gated. Display-tier, nulls printed; promotion question
belongs to the US TS clocks' CN analog (earliest 2027).

**W8-R8 — Honesty & staleness riders.** Per-ticker JSON cadence: chinastockdata/ is untracked
since 07-01 (R2-served, runner-local) and the 07-03 freeze overlaps the guard-echo beheading
window (fixed #2070) — VERIFY after the next asia-close before patching; the board-vs-lookup
contradiction (002709 FALLING on board while lookup says pre-collapse "extended") must resolve
coherently — if the lookup JSONs remain stale, the lookup as-of banner must be loud. Ripening
attach-outside-cand-guard fix; act-now mobile stacking; heading hierarchy pass; F6 contradiction
sweep on cards (one loud field: stage; conviction shown as context not verdict-competitor).
PERF GATE: every UI PR browser-verifies against prod-shaped data (full 110 buy + 32 ripening +
full table universe) — DOM weight and scroll perf judged in the browser, not by curl.
Path law: F-rulings cite research/china_alpha/CHINA_ALPHA_MASTERPLAN_BY_FABLE.md (subdirectory).

## 3. Legality map (rulings honored)

- Subsector/rotation state NEVER gates or ranks reversal entries (NW-U2, DO_NOT_REBUILD #791-era)
  — W8 uses it as chips/lanes only; no fused scores (CN-SYS-R13, WA-R1).
- BUY-family words only on ENTRY shelf (F1); bottoming lane + READY zone copy-law enforced.
- Board blend weights untouched until W6 ledger (~07-29) (CN-SYS-R7, F3).
- Limit-up/lianban data: AVOID direction only (CN-SYS-R3/CNPL-R7) — untouched.
- FRESH-BUY-as-edge refuted (#1513): freshness = UX metadata, never an edge claim.
- Rotation x cycle-position entry-confluence DON'T-TEST: displayed side-by-side, never combined.
- CN basket turn organ: expected-NULL registration + disclosure (FT-R9); never auto-resolves
  fast-vs-slow disagreement (FT-R1).
- "validated" word: not used in any new copy (CI).
- i18n: t()/td() pairs; data-tip-en/zh, no CJK in title= (CI); theme.js on any new page.
- Dual-mode template law: every china.html.j2 PR render-verifies BOTH outputs via the vm-snapshot
  fast-render harness.
- LLM-origination ban: no LLM anywhere in W8 signal paths.

## 4. Wave/PR plan (each: fresh branch off origin/main -> same-day squash-merge)

- **PR-A (W8a)**: Ripening zones engine + selection + ledger cols + full scorecards + knife sink
  + copy (build_china_library.py, setup_tier.py, china.html.j2, tests, both-mode render verify).
- **PR-B (W8b)**: Act-Now v2 board + baskets cap4 parity + cross-links + bottoming lane v0
  (forward_log-only).
- **PR-C (W8c)**: Tier vocabulary v2 (_sig_badge + tooltips + TIERED_CASCADE addendum + stale
  repaint figures).
- **PR-D (W8d)**: CN basket turn-watch organ + registration + theme-desk dual chips + bottoming
  lane v1.
- **PR-E (W8e)**: Table view flagship (+ mcap join + days-since-signal + theme column + filters
  + persistence).
- **PR-F (W8f)**: CN mtf_upturn port (organ + ledger + chips + turn table).
- **Phase 5**: table-view port to US, HK (+ Canada if surface exists).
Riders distributed: JSON cadence root-cause (PR-A or standalone), mobile fixes (PR-B/E).

Build protocol: mockups first (M1 act-now v2, M2 ripening zones, M3 table view + chooser,
M4 badge A/B) on REAL artifact data, screenshot-reviewed before build; builders receive mockup
PNGs; browser-verification with prod-shaped data at every gate; opus review per PR.
