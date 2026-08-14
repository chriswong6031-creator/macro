# STOCK IDENTITY — W2 / PR-2 REGISTRATION: EXPERT REPLAY + PROVENANCE PINNING

**Wave:** W2 (masterplan §14 PR-2 row), authorized by the CEO/operator §16.9 return of 2026-08-14 ("W1 ACCEPTED, W2 AUTHORIZED") after #5612 merged (2026-08-14T12:22Z, merge `7b51d82bb5c6`).
**Binding contract:** the frozen masterplan (§5 expert library, §7.3 attribution clause, §9.4 leakage, §14 PR-2 row) + the six W1-return rulings, restated in §0 below. W1's sealed objects (SI-SEALED-CAL-P1, blind arm, `si_constants_v1.json`, fingerprint spec `0e3457b1…`) are **frozen inputs — nothing in W2 redraws, recalibrates, or re-hashes them.**

## §0. The W1-return rulings, applied (all six binding)

1. **Descriptive/research-only.** W2 reconstructs and preserves expert events + provenance. No per-name expert selection, no best-expert anything, no routing authority, no Prophet change, no score/gate/size authority, no disguised outcome audition. **W2 publishes NO ruler metric** — not even lead/lag: §7.3 metrics are PR-3's object. W2's only aggregates are inventory counts (events per family × name × era) and join coverage counts.
2. **Survivor-only stands; no close-only plane.** The **Dead Instrument Control Set** (≥5 identity-resolved terminated US instruments, full historical adjusted OHLCV, fingerprint-machinery-compatible plane) is a **separately registered future act that BLOCKS PR-5/Q1** — recorded here and in the WS record as a standing obligation; W2 does not build it.
3. **GOLD/Barrick identity (pilot addendum, §6 below).** NYSE `GOLD` = Gold.com, Inc. (fka A-Mark; AMRK→GOLD 2025-12-02; store tape = A-Mark's spinoff listing 2014-03-17→, zero Barrick rows — #5613 forensics). GOLD is preserved **only as that instrument**; its W1 "miner neighborhood probe" role is void. **Barrick Mining, NYSE `B`** (GOLD→B rename 2025-05-09; lineage ABX→GOLD→B is one continuous NYSE listing) is added as the intended miner pilot. Sealed partitions untouched; roster/config repair belongs to the sibling lane (#5613 + the separate curated basket act) and is not duplicated here.
4. **N=42 is descriptive-only** (missed its 80% stability floor); it earns no Channel-A predictive role without a later preregistered reliability step. W2 uses it only as the frozen episode-segmentation constant it already is.
5. **The degenerate universe-wide v0 cluster component is never inferential effective-N.** Frozen artifact preserved; PR-3 owns the refinement. W2 quotes no cluster count as N.
6. Mixed SVG/PNG dossiers accepted; no conversion work.

## §1. R1 rail: evaluate-first verdict (masterplan §12.1 — written justification)

R1 (`research/rule_replay/R1_CHARTER.md`) is the **fire-tape × exit-policy-grid** rail: entry events come from the production fire tape (`data/replay/replay_boarded.parquet`, 2021-07+ cohort), and its parameter space is cohort filter × fill delay × **exit policy** × per-fire weight. W2's object is disjoint on every axis: (i) W2 *produces* event histories per family by era-pinned recomputation/ledger extraction over full per-name depth (decades), rather than consuming the boarded fire tape; (ii) W2 evaluates **no exit policy and no outcome** — its terminal artifact is events + attribution edges; (iii) W2's histories predate R1's tape by up to five decades. Extending R1 would mean grafting a family-recomputation front-end onto a rail whose registry, policy vocabulary, and outputs all assume exit-policy grids — a scope violation of R1's own charter, not a reuse. **Verdict: parallel extraction under `engine/stock_identity/replay/`, ADOPTING from R1:** the vintage-stamp schema on every artifact (`price_plane_id, adjustment_mode, universe_as_of, survivorship_biased, coverage_frac, dead_name_coverage_pct, era_law_cohort`), single-writer committed artifacts, close-of-completed-bar conservatism, and the no-adhoc discipline (extraction runs from a committed spec, not interactive flags). G-7 note: W2 performs **no parameter sweep** — extraction runs at shipped/frozen parameters only, so no TrialLedger grid registration arises; if any diagnostic grid is ever added it registers first.

## §2. Import-firewall amendment (scoped, test-enforced)

W1's firewall (no G-8 module imports anywhere in `engine/stock_identity/**`) remains **total for the identity layer** (`plane/partition/fingerprint/state/episodes/hygiene/census/dossier` — the episode catalog stays expert-free, G-3). The new subpackage `engine/stock_identity/replay/**` holds the ONLY exemption: it may import, **read-only**, exactly these producers for recomputation-by-the-engine's-own-function (re-implementation = the silent-fork hazard, archaeology §4.2):
`engine.signal_quality` (signal_frame, analyze/buy-filter surfaces), `engine.confluence_tiers` (tier_stream), `engine.washout_turn` (organ recompute), `engine.canon` (oscillator core), `engine.us_early_turn` (union_admission signature; not G-8-protected but listed for completeness).
Never imported anywhere: `engine.signal_gate` (authority, not event math), `engine.prophet_*`, `engine.entry_radar.*`, `engine.stock_personality`, `engine.oracle.*`, Terminal internals. The G-8 clean-diff proof still covers every protected path (imports mutate nothing). The firewall test is amended to encode exactly this scoped allowlist.

## §3. Family registry v0 (keys minted from producer receipts — never invented)

`data/stock_identity/expert_events/family_registry.json`: one entry per family with `family_key, producer (module:function), family, subtype(s), stage, era pin(s), family_first_available, provenance_class ∈ {R, B, P, C}, spec_hash (sha256 over the producer's formula constants as extracted), replay_notes, parity_notes`. Authority all-false. Classes per masterplan §5 + archaeology §4:

- **Class R (replayed in W2):** `grey_dot_macro` (signal_frame.early recompute, 3D grid; **as-recorded AND as-restated dual series** — each fire flagged `in_washout_context` per the 2026-08-11 amber carve-out rule so both readings ship together, F13b); `confirmed_buy` / `rebuy` (ledger `data/signal_archive/track_record.parquet` rows stamped `ledger_recorded` ∪ deeper recompute stamped `replay_recomputed` with `spec_postdates_history: true` on pre-ledger rows); `reclaim_waiver` (re-derived ONLY over the committed nightly state artifact's own era — `family_first_available` honesty; zero synthesized context); `weekly_washout_turn` (ledger `data/washout_turn/ledger.jsonl` ∪ earlier organ recompute on completed W-FRI bars); `sea_event_classes` (join of `data/stock_events/events_backfill.parquet` + `live/`, keep-FIRST honored); naive comparators `rsi30_cross`, `low20d_bounce`, `stoch2w_cross` (frozen specs in §5 below — reference constructions, not production engines).
- **Class B (locked-spec backcast, stamped `spec_postdates_history: true` on every row):** `tier_cascade_t1..t4` (tier_stream() under `ANCHOR_ERA="abs-session-2026-08-06"`); `grey_dot_terminal` (Macro-side locked-spec port: same formula, `resample("2B")` bucketing per the Terminal twin — measured as a SEPARATE era-pinned expert; **parity vs `grey_dot_macro` measured on the pilot and REPORTED as counts of agreeing/disagreeing fire dates** — archaeology §4.5 item 2 — never collapsed in W2); `bottom_watch_terminal` (locked-spec C5 port per Radar contract §3.4; declared parity fixture).
- **Class C → resolution required this wave (masterplan §14 PR-2):** the STARTER trio. W2 investigates PIT reconstructability of the licensing context (historical basket/leader state from committed artifacts). Consequence matrix, binding: context PIT-reconstructable → `starter_pending/failed/converted` replay as Class R over the reconstructable era; NOT reconstructable → **the trio reclassifies to Class P** (no synthetic context, no backfill) AND the admission **signature** alone ships as its own honestly-named family `starter_signature` (union_admission legs, replayable, era `union-admission-v1-2026-08-11` noted as spec era). Never merged, never partially faked.
- **Class P (enumerated with zero rows — test-enforced):** `amber_early` (born Terminal `935389d4` 2026-08-11), `door_r_rearm` (charter forbids backfill), `turn_watch_deck`, `gc_v2_scores`, Radar `C1/C2` live detectors. Present in the registry for structural-absence honesty; the events table contains **no row** for any of them.

## §4. Event store v0 — `mastermind.entry_event.v1`-compatible (program-owned)

`data/stock_identity/expert_events/pilot_events_v0.parquet` — one row per reconstructed/extracted event, adopting the Radar A1 field vocabulary verbatim where it applies: `event_id` (deterministic `sha256(family_key|ticker|signal_ts|subtype)[:16]`), `producer, detector_id (null), family, subtype, stage, quality, context, signal_ts, signal_known_ts, source_identity{source_hash, signal_era, detector_spec_hash}, scored_authority (recorded fact, never a grant), family_first_available, family_era, field_origin` — with the enum **extended** for historical provenance: `field_origin ∈ {emitter_verbatim, radar_derived, ledger_recorded, replay_recomputed}` (extension documented; schema field names/types otherwise identical so PR-7's prospective Radar ingestion unions cleanly). Typed edges live in `event_edges_v0.parquet` (`relation ∈ {promoted_by, dedup_suppressed_by}`, source/target event_id) — the grey-dot as-restated view is expressed as edges, not row deletion. **This store is program-owned under `data/stock_identity/**`; the Radar store is never written, never pre-empted** (Radar PR-0 merged = contract only; its store lands at Radar PR-2 and remains Radar's).
**known_ts law (G-4/§9.4):** every replayed event's `signal_known_ts` = the completion timestamp of the bar that fires it (daily close for 1D; the completing session's close for 2D/3D buckets; W-FRI close for weekly organs) — completed bars only, provisional-bar readings prohibited (Radar §5 spirit); `known_basis` recorded per row.
**Attribution join:** `attribution_v0.parquet` — event → identity episode where `signal_known_ts ∈ [leg_start − P_pre, resolution]` under W1's frozen `P_pre = 5`; unresolved/censored episodes attribute normally (they simply have no anchor yet); events outside any episode carry a null edge and are RETAINED (the §7.3 unconditional block needs them at PR-3). Join coverage counts (events joined / total, per family × name) are the ONLY published aggregate.

## §5. Naive comparator frozen specs (reference constructions)

- `rsi30_cross`: canon RSI(14) daily crosses up through 30 (prior close <30, this close ≥30).
- `low20d_bounce`: close prints a 20-session low then the NEXT session closes above the prior session's close.
- `stoch2w_cross`: 2W-grid StochRSI (canon 14/3/3) %K crosses up through %D with both <20 at the prior completed 2W bar (the PSS incumbent gauge shape).
All three: canon oscillator core only (one RSI family — indicator-core law), completed bars, close basis; spec-hashed in the registry.

## §6. Pilot addendum (ruling 3 applied)

- **B (Barrick Mining, NYSE)** collected into the program-owned plane `data/stock_identity/ohlcv/B.parquet` via `collectors._stock_ohlc.fetch_ohlc` (`auto_adjust=True`, full listing history; provenance manifest extended). Identity note: the tape is the continuous Barrick NYSE listing through its renames (ABX→2019-01-02→GOLD→2025-05-09→B — one instrument, key migrations; #5613 receipts). B joins the **pilot-class set** (design-touched). B never entered the W1 universe snapshot, so it is in neither the blind arm nor SI-SEALED-CAL-P1 **by construction** — sealed hashes untouched, verified by test.
- **Miner probe roster (for future §10 emergence work): NEM, AEM, PAAS, WPM, AG, B.** GOLD is struck from the miner role and re-labeled **"reused-ticker hygiene case study (bullion dealer instrument)"** — it remains a pilot member (the frozen W1 exclusion lists reference it) and its dossier is REGENERATED with the true Gold.com/A-Mark identity, the ruling citation, and a dated correction note. The W1 registration file is not edited (its §4 text is hash-pinned by `partition_procedure_sha256`); this addendum is the governing correction record.
- **B's W1-layer artifacts** (fingerprint snapshot, state series, episode catalog, dossier) are generated with the FROZEN W1 constants + fingerprint spec; B's cross-sectional percentiles rank against the frozen W1 asof universe distribution (documented as such — descriptive display, not a re-draw). The W1 pilot artifacts for the other 21 names are not regenerated.
- Untouched here (sibling lane): `config.yml` acks (#5613), `gold_miners` basket membership, any `data/baskets/**` write.

## §7. Leak fixtures (green before any family's events ship)

Per family: (i) **truncation invariance** — events computed on `df.iloc[:k]` are the identical prefix of events computed on the full frame (path_risk_signals CAUSALITY LAW shape); (ii) **shift audit** — shifting the input tape by one session shifts every event stamp accordingly (no absolute-date leakage), reusing the existing RUL-31 test shapes where present; (iii) **feed-truncation** (F6-style) on every recomputed family. Ledger-extracted families (CB/REBUY ledger rows, SEA, washout ledger) get (iv) **append-only conformance**: extraction is a pure filter of the store (no row mutation, keep-FIRST honored).

## §8. Deliverables + tests

- `engine/stock_identity/replay/` — `__init__.py`, `grid.py` (2D/3D/weekly bucketing exactly matching each producer's own convention incl. the Macro absolute-anchor `_tf_grid` vs Terminal `resample("2B")` pair), one module per family group (`grey_dot.py`, `confirmed_buy.py`, `tiers.py`, `washout_turn.py`, `reclaim_waiver.py`, `bottom_watch.py`, `starter.py`, `sea.py`, `naive.py`), `events.py` (schema/edges/ids), `attribution.py`.
- `scripts/stock_identity_replay_pilot.py` — CLI (stage-resumable): registry → per-family extraction over the 22 pilot names → leak fixtures → events + edges + attribution + inventory counts; `scripts/stock_identity_pilot_addendum.py` — B collection + B W1-layer artifacts + GOLD dossier regeneration.
- Artifacts: `data/stock_identity/expert_events/{family_registry.json, pilot_events_v0.parquet, event_edges_v0.parquet, attribution_v0.parquet, inventory_v0.md}` (+ B rows in the W1-layer stores as clearly-versioned additions: `fingerprints/addendum_b_fingerprint.parquet`, `state/addendum_b_state.parquet`, `episodes/addendum_b_catalog.parquet`), dossiers `B.md/.svg` + regenerated `GOLD.md/.svg`.
- Tests `tests/test_stock_identity_replay*.py`: firewall amendment (identity layer total, replay allowlist exact), leak fixtures on synthetic frames, event-id determinism, Class-P zero-rows, no-ruler-metric guard (banned columns: lead_lag, price_dist, mae, capture, recall, precision, composite, fit, rank, best), attribution-window correctness on synthetic episodes, B-not-in-sealed-lists, schema-vocabulary conformance. Wired into the same trial-ledger guards CI job (minimal-deps law: no matplotlib in test import paths).
- STARTER resolution + parity counts land in `inventory_v0.md` + this doc's §9 fill.

## §9. Results

Built 2026-08-14 over the 22-name pilot (W1's 21 + `B`) at the frozen W1 asof **2026-08-13**. Artifacts: `data/stock_identity/expert_events/{family_registry.json, pilot_events_v0.parquet, event_edges_v0.parquet, attribution_v0.parquet, inventory_v0.md}`. **31,119 events · 64 typed edges · 34,491 attribution rows**, coverage 22/22 names. Era split (`DNR:LAW-ERA-SPLIT`, never pooled): 14,846 pre-2010 · 16,273 post-2010. Every count below is an inventory or join count — **W2 publishes no ruler metric**, and no lead/lag, distance, MAE, capture, recall, precision, composite, fit, rank or best exists as a column, key or identifier in anything this wave produced (test-enforced, `tests/test_stock_identity_replay.py::TestNoRulerContent`).

### 9.1 Family table

| family_key | class | era pin | first available | events | names | provenance | fixtures |
|---|:--:|---|---|---:|---:|---|---|
| `grey_dot_macro` | R | `sq-abs-session-2026-08-06` | — | 730 | 21 | 730 recomputed | green |
| `grey_dot_terminal` | B | `gc_v2_wo2` | — | 2,719 | 21 | 2,719 recomputed | green |
| `confirmed_buy` | R | `sq-abs-session-2026-08-06` | — | 1,839 | 21 | 367 ledger · 1,472 recomputed | green |
| `rebuy` | R | `sq-abs-session-2026-08-06` | — | 87 | 9 | 87 ledger | green |
| `reclaim_waiver` | R | `us_prophet_v2` | **2026-08-13** | **0** | 0 | — | green (vacuous — see §9.6) |
| `weekly_washout_turn` | R | `washout_turn.v1` | 2026-08-05 | 652 | 20 | 12 ledger · 640 recomputed | green + 1 declared exemption |
| `sea_event_classes` | R | `pre2010` / `post2010` | — | 10,384 | 15 | 10,384 ledger | green |
| `bottom_watch_terminal` | B | `gc_v2_wo2` | — | 206 | 20 | 206 recomputed | green |
| `starter_signature` | R | `union-admission-v1-2026-08-11` | — | 2,559 | 21 | 2,559 recomputed | green |
| `tier_cascade_t1` | B | `abs-session-2026-08-06` | — | 2,122 | 21 | 2,122 recomputed | green |
| `tier_cascade_t2` | B | `abs-session-2026-08-06` | — | 236 | 21 | 236 recomputed | green |
| `tier_cascade_t3` | B | `abs-session-2026-08-06` | — | 28 | 14 | 28 recomputed | green |
| `tier_cascade_t4` | B | `abs-session-2026-08-06` | — | 47 | 16 | 47 recomputed | green |
| `rsi30_cross` | R | `si-naive-comparators-v0-2026-08-14` | — | 1,480 | 22 | 1,480 recomputed | green |
| `low20d_bounce` | R | `si-naive-comparators-v0-2026-08-14` | — | 7,437 | 22 | 7,437 recomputed | green |
| `stoch2w_cross` | R | `si-naive-comparators-v0-2026-08-14` | — | 593 | 21 | 593 recomputed | green |
| `starter_pending` / `_failed` / `_converted` | **P** | `union-admission-v1-2026-08-11` | — | **0** | 0 | — | n/a (zero rows by law) |
| `amber_early` | **P** | `terminal-935389d4-2026-08-11` | 2026-08-11 | **0** | 0 | — | n/a |
| `door_r_rearm` | **P** | prospective-only by charter | — | **0** | 0 | — | n/a |
| `turn_watch_deck` | **P** | nightly artifact only | — | **0** | 0 | — | n/a |
| `gc_v2_scores` | **P** | per-request computation | — | **0** | 0 | — | n/a |
| `radar_c1_c2` | **P** | live-forward only | — | **0** | 0 | — | n/a |

Every era pin is read off the producing module at import time, not typed in (`ANCHOR_ERA`, `SCHEMA`, `UNION_ADMISSION_ERA`); a producer edit moves the family's `spec_hash` and its identity with it. Class P families are enumerated **with zero rows, test-enforced** — structural absence, never negative evidence.

### 9.2 STARTER consequence matrix — **NOT_PIT_RECONSTRUCTABLE**

The licensing context (basket washout state ∈ {WASHED_OUT, BASING, TURNING} **OR** leader-pullback state ∈ {PULLBACK, RESET_TURN}) is **not** point-in-time reconstructable from committed artifacts. Evidence, read from what the producer itself reads:

| artifact | role | dated history? | as_of |
|---|---|:--:|---|
| `site/basketdata/us_basket_turn.json` (`us_early_turn.load_basket_turn_membership`) | basket state | **NO** — keyed by basket, one `as_of` | 2026-08-13 |
| `site/anticipationdata/us_leader_pullback.json` (`us_early_turn.load_leader_pullback_states`) | leader-pullback state | **NO** — keyed by ticker, one `as_of` | 2026-08-13 |
| `data/baskets/membership_history.parquet` | membership | 1 snapshot date, with `[added, removed)` intervals | 2026-08-13 |
| `data/**/*basket_turn*` | a dated state store | **none found** | — |

Both context artifacts are nightly-overwritten single vintages; no dated basket-state store exists anywhere under `data/`. PIT **membership** does exist (the `added`/`removed` intervals) — but membership is not what licenses a STARTER; the basket's washout **state on the fire date** is, and recomputing that over history would be a new construction with its own gates, not a read of a committed artifact.

**Consequence applied, exactly as pre-registered:** `starter_pending` / `starter_failed` / `starter_converted` **reclassify to Class P** (zero rows, no synthetic context, no backfill), and the admission **signature** ships separately as its own honestly-named family `starter_signature` (Class R, 2,559 events over 21 names, era `union-admission-v1-2026-08-11` recorded as the SPEC era). Never merged, never partially faked.

### 9.3 Grey-dot twin parity (counts, not a verdict)

Compared on `signal_known_ts` — the decision date both implementations key on. **The two families stay separate regardless of these counts.**

**Total over 21 names: 654 agreeing fire dates · 76 macro-only · 2,065 terminal-only** (macro 730, terminal 2,719). Agreement is **89.6% of the macro population** but only **24.1% of the terminal population** — the twin fires ~3.7× as often. Per name (top by disagreement): KO 66/5/253, MCD 67/8/235, WMT 65/4/199, NEM 59/10/170, B 57/7/163, MSFT 50/4/146, REGN 46/9/137, MCK 38/4/118, NVDA 31/4/107, WPM 22/4/75; full table in `inventory_v0.md`.

Four measured divergence axes, all recorded in the registry's `parity_notes`: (1) **oscillator family** — `signal_quality` imports `engine.technicals.rsi` (bare `ewm`), the locked-spec port pins `engine.canon` (SMA-seeded RMA, == Pine `ta.rsi`); (2) **2D bucketing** — absolute session anchor vs calendar `resample("2B")` with a PIT searchsorted join; (3) **the rising leg** — Macro needs TWO rising 2D histogram bars on the prior CLOSED bar, the Terminal spec exactly ONE strictly-greater bar; (4) **the RSI ceiling** — Macro carries `rsi14 < 65`, the Terminal spec's dot has no such leg. (3) and (4) are the obvious drivers of the 3.7× ratio. **Named deviation:** the port cuts 3D bars on the Macro absolute anchor because the Terminal's per-symbol listing anchor (`bar_anchor`) is not reproducible from anything committed in this repo — the anchor axis is held fixed, not measured, so these counts are not a complete twin comparison.

### 9.4 Grey-dot dual series (as-recorded / as-restated)

730 as-recorded fires; **61 (8.4%) carry `in_washout_context = true`** — the fires today's promotion rule would carve out to `amber_early`; 669 remain as the as-restated raw-dot reading. The carve-out ships as 61 `promoted_by` edges to the bottom-watch events; **no row is deleted**, so both readings come out of one store. `amber_early` itself stays Class P with zero rows — the flag says what the rule WOULD have done, and is never labelled as that family's history.

### 9.5 Attribution join coverage (the only published aggregate)

Window join on `signal_known_ts ∈ [leg_start − P_pre, resolution]` under W1's **frozen `P_pre = 5`** (read from `si_constants_v1.json`, never set here). Censored/unresolved episodes attribute normally; unattributed events are **RETAINED** with a null episode edge, because the §7.3 unconditional block needs them at PR-3.

**12,843 of 31,119 events attributed (41.3%).** Per family: `rsi30_cross` 1,056/1,480 (71.4%) · `low20d_bounce` 4,418/7,437 (59.4%) · `bottom_watch_terminal` 107/206 (51.9%) · `starter_signature` 1,265/2,559 (49.4%) · `grey_dot_macro` 353/730 (48.4%) · `grey_dot_terminal` 1,153/2,719 (42.4%) · `weekly_washout_turn` 245/652 (37.6%) · `stoch2w_cross` 178/593 (30.0%) · `sea_event_classes` 3,037/10,384 (29.2%) · `tier_cascade_t2` 69/236 (29.2%) · `tier_cascade_t3` 8/28 (28.6%) · `tier_cascade_t4` 13/47 (27.7%) · `confirmed_buy` 436/1,839 (23.7%) · `tier_cascade_t1` 486/2,122 (22.9%) · `rebuy` 19/87 (21.8%).

These are **counts, not localization**: a higher share means more of a family's fires land inside some identity episode, and says nothing about where inside. The ruler is PR-3's object.

### 9.6 Fixture results (registration §7)

All nine family groups **GREEN on every applicable check**. Recomputed families run four fixtures (`truncation_invariance`, `shift_audit_start_invariance`, `shift_audit_forming_bar`, `feed_truncation`) on real pilot tapes in the CLI and on a deterministic synthetic tape in `tests/test_stock_identity_replay_leak.py`; ledger families additionally run `append_only_conformance`. Each fixture is also run against a **deliberately broken detector** built to violate exactly its property and is required to reject it — a guard that has never rejected anything is not evidence.

**Deviation of record — the shift audit.** The registration's literal phrasing ("shifting the input tape by one session shifts every event stamp accordingly") is not satisfiable here and should not be: every grid in this repo is **calendar-anchored by ratified design** (`_tf_grid` buckets on `session_positions(date) // n`; the weekly/monthly legs resample on the calendar), so re-hanging the same closes on later dates re-phases the buckets *by design* — measured on NVDA, a one-session shift moves 35 dots to 42, and even a phase-preserving 6-session shift moves them because the W-FRI leg re-groups. Demanding otherwise would demand the R-SQ1 repair be undone. The registration also instructs "reusing the existing RUL-31 test shapes where present", and the house's RUL-31 instruments (`tests/test_entry_primitives_a3.py`, `tests/test_bottom_sensors_a3.py`) are truncation-invariance plus the completed-bar test — there is no date-shift test in them. The shift audit is therefore implemented as those two shapes: **start-invariance** (dropping 37 leading sessions must not move events — the exact property the absolute anchor was adopted to guarantee, and the one the retired `3B` binning failed by relocating ~80% of NVDA's dates) and **forming-bar** (an appended in-progress bar may not change a completed event). Both test the property the literal phrasing was reaching for: *an event may not depend on anything but the tape up to its own known-ts.*

**One declared exemption, mechanism named:** `weekly_washout_turn` is exempt from `shift_audit_start_invariance` because `engine.washout_turn`'s depth percentile is a **declared whole-sample statistic** — its own `_evaluate` documents it as "percent of the FULL weekly line history strictly BELOW bar j" — so the reference distribution legitimately depends on how much history exists, and a cross near the 15th-percentile gate flips when leading history is dropped (measured on a synthetic tape: 8/18 events, 44%). This is **past-data window dependence, not future leakage**: the organ's three leak fixtures are green, the replay walks one fixed full per-name prefix chain so the window is constant across the whole extraction, and a test asserts the unexempted check still fails (an exemption nobody would notice going stale is worse than no exemption). Start-invariance elsewhere is a rate against a 5% ceiling rather than exact equality, for a second documented producer property — `engine.technicals.rsi` is a bare `ewm` with an expanding warm-up from bar 0, which `engine.canon.rma`'s own docstring names as flipping near-threshold crosses; the defect the fixture guards against is two orders of magnitude larger.

**One construction repaired by its own fixture.** `stoch2w_cross` was first built on `resample("2W-FRI")`, which phases its two-week bins from the series' first row; the start audit caught it relocating 32/104 events by exactly one week. It now pairs calendar-anchored weekly bars on an **absolute week index** (`label.toordinal() // 7 // 2`), which is a function of the calendar alone — the Radar contract's "never calendar-anchored `resample('2W-FRI')`" rule, arrived at the hard way.

### 9.7 Ledger extraction coverage (counts)

| store | families | emitted / in store | note |
|---|---|---:|---|
| `data/signal_archive/track_record.parquet` | `confirmed_buy`, `rebuy` | **454 / 1,160** | see below |
| `data/washout_turn/ledger.jsonl` | `weekly_washout_turn` | 12 / 13 | the 13th row is a state this family does not recognise |
| `data/stock_events/**` | `sea_event_classes` | 10,384 / 10,384 | pure filter, keep-FIRST |

The confirmed-buy gap is a **known-ts law consequence, measured**: a §7 marker is labelled with its 3D bucket's OPEN date, and rows minted before the `sq-abs-session-2026-08-06` anchor era carry labels from the RETIRED `3B` resample, whose synthetic left-edge bins are not labels of the current absolute-anchor grid. `signal_quality.marker_last_session` refuses them and a guessed `known_ts` would break the law, so they are **counted rather than stamped**. Measured split: **117/117 (100%) of era-stamped rows resolve; 337/1,043 (32.3%) of pre-era-stamp rows do.** The deeper recompute arm covers that history at full depth under `field_origin=replay_recomputed` with `spec_postdates_history=true`, and carries `scored_authority=false` because it is the pre-filter confluence cross, not the filtered verdict.

### 9.8 Reclaim-waiver era receipts

`site/factordata/basket_washout_state.json` is a **single nightly vintage**, `as_of = 2026-08-13`, and `reclaim_waiver_for` refuses any marker outside `[as_of, as_of + 5 sessions]` in both directions — a state published after a label was knowable may never relieve it. 7 of 22 pilot names qualify at notch 20 in that vintage (AEM, AG, GOLD, HL, NEM, PAAS, UEC); **0 markers of any name became knowable inside the one-vintage window, so the family ships 0 rows** with the reason attached per name. A zero here is a **structural absence** — the state history was never kept — never evidence that the waiver does nothing. Manufacturing pre-`as_of` rows would require inventing peer-group state, which §3 forbids by name.

### 9.9 Pilot addendum receipts (ruling 3)

- **`B` (Barrick Mining, NYSE) collected**: `data/stock_identity/ohlcv/B.parquet`, **10,454 rows, 1985-02-13 → 2026-08-13**, via `collectors._stock_ohlc.fetch_ohlc` (`auto_adjust=True`, `period='max'`). The 1985 first print is itself the receipt for the lineage claim: this is the continuous Barrick NYSE listing, not a 2025 fragment. `ohlcv/manifest.json` **extended** (BABA and WPM untouched) with B's provenance plus the `ABX → GOLD (2019-01-02) → B (2025-05-09)` lineage note and the pointer that both retired symbols are today occupied by DIFFERENT instruments.
- **B's W1-layer artifacts as separate addendum files**, built with the frozen constants and fingerprint spec: `fingerprints/addendum_b_fingerprint.parquet`, `state/addendum_b_state.parquet` (10,454 rows), `episodes/addendum_b_catalog.parquet` (**193 episodes**), receipts at `addendum/pilot_addendum_v1.json`. Percentiles rank against the **frozen W1 asof cross-section** (2,780 names); B is inserted for its own ranking only and no W1 percentile is recomputed. The W1 pilot stores for the other 21 names are **not** rewritten — test-enforced.
- **B is in no sealed list by construction** (it never entered the W1 universe snapshot): blind arm, SI-SEALED-CAL-P1, the universe snapshot and the frozen pilot list are all clean, and all four W1 hashes (`blind_sha256`, `calibration_sha256`, `fingerprint_spec_hash`, `partition_procedure_sha256`) plus `universe_sha256` **recompute byte-identical through W1's own hashing functions** after the whole W2 build.
- **`GOLD` dossier regenerated** (`GOLD.md` + `GOLD.svg`) with the true identity: Gold.com, Inc. (fka A-Mark; `AMRK → GOLD` 2025-12-02), tape = A-Mark's spinoff listing 2014-03-17→, role **"reused-ticker hygiene case study (bullion dealer instrument)"**, a dated 2026-08-14 correction note citing the ruling and #5613, and a rewritten hygiene block. The identity header calls it a miner nowhere; the word survives only inside the correction that withdraws that reading and points at `B` — test-enforced. W1's registration text is untouched (its §4 is hash-pinned), so this addendum is the governing correction record.
- **`B` dossier** written as `B.md` + `B.png` — the chart exceeded the module's 300 KB SVG commit limit and fell back to PNG, which ruling 6 accepts (mixed SVG/PNG dossiers, no conversion work).
- **Miner probe roster** recorded as NEM, AEM, PAAS, WPM, AG, **B**; GOLD is struck from it.

### 9.10 Standing obligations carried forward (not built here)

The **Dead Instrument Control Set** (≥5 identity-resolved terminated US instruments with full historical adjusted OHLCV) remains a separately registered future act that **BLOCKS PR-5/Q1**. Every event in this store belongs to a surviving instrument — `survivorship_biased: true`, `dead_name_coverage_pct: 0.0` on the table-level vintage stamp — and **no cohort claim may be made over it until that set exists**.

## §10. Not done unless (contract gates)

Post-W1 operator return completed ✓ (this wave's authorization). Every replayed family: era pin + spec hash + leak fixtures green. Family keys minted from receipts. No synthetic history for any Class P family (zero-row test). Zero ruler metrics/fit content (test-enforced). G-8 diff clean (imports only). Sealed W1 objects byte-identical (test compares hashes). Records: WS wave + dated handoff; `agentos.py validate` 0 errors. End at CI handoff — **W3 is not started** (operator return ends this wave's authority).
