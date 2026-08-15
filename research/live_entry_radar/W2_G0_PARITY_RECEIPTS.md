# W2 / PR-2 — G0 Grey Dot consumption + parity receipts (2026-08-14)

Session: `live-entry-radar-w2-pr2-26fe57` (Fable, W2 commissioning handoff). Everything here
was generated with the Terminal emitter staged **verbatim from `charting-app origin/master`
@ `82cb8cbf799fc3a91c9bee0f11a4db718fde68eb`** (per PR-0's stale-checkout prohibition) on
git-canonical Macro deep-store feeds. Raw probe outputs: `W2_F6_FROZEN_FORM_RESULTS.json`,
`W2_F6_LAWS_RESULTS.json`, `W2_F6_DETECTION_POWER.json`, `W2_PARITY_REPORT.json` (this dir).
Contract consequences are recorded append-only as §18 A4.

## 1. Freshness gate (run FIRST, per the commissioning §2)

| surface | state | receipt |
|---|---|---|
| Shared deep store, git-canonical (`data/stocks/*.parquet` @ `origin/main` = `9ea1bcb6844c`) | **CURRENT** — NVDA/NFLX/TSLA all end **2026-08-13** (last completed session at generation time); daily-collection lane alive (`c52b647d499f` "data: daily collection 2026-08-14") | `git show origin/main:data/stocks/<S>.parquet` → max index |
| Primary checkout working tree (`/Users/chriswong/Documents/Cluade/Macro Dashboard/data/stocks/`) | **STALE at 2026-07-08** — an unpulled working tree, NOT a production staleness. This resolves W0's unverified claim: the census's "5-week-stale store" was the reading checkout. | direct read, rows 6906/6069/4030 |
| Census vintage reconstruction | Commit `4f68f8d95030` ("data: daily collection 2026-07-09") reproduces the census feed exactly (NVDA ends 2026-07-08, 6906 rows) — used as the frozen Track-A-parity vintage | vintage extraction + row/date match |
| Terminal slice artifacts (`terminal/public/data/<SYM>.slice.json`) | **NOT verified live this session** — production artifacts live on the VPS lane; the local charting-app checkout is code-stale and its generated artifacts were not trusted. The adapter therefore carries the freshness gate IN CODE (fail-closed on every consumption; §18 A4.2 `as_of` semantics), and fixture slices were generated from the governed emitter directly. | design decision, this doc §4 |

**Named proof surfaces affected by the un-receipted production artifact:** none of the W2
parity claims depend on a live production slice — parity is pinned against the governed
emitter at `origin/master` on canonical feeds. What remains unproven until PR-4/first VPS
read: that the production slice writer's deployed revision matches `origin/master` and that
its feeds are the canonical store (`(source_hash, signal_era)` pinning + the freshness gate
are the in-code enforcement for exactly that read).

## 2. F6 first — execution order and findings

Commissioning order honored: the frozen F6 ran **before** any parity table was derived,
against the FROZEN Track A §2.6 dot tables (not freshly derived values).

1. **Frozen form falsified:** 20/28 completed-bar dots ≥2025 stay visible at
   truncate-at-`ts` (`W2_F6_FROZEN_FORM_RESULTS.json`). Not a leak — no post-`ts` data
   exists in a feed truncated at `ts`; these are lawful provisional fires on 1-session
   partial 3D bars. The 8 that vanish are bars where the 1-session provisional value does
   not cross. NVDA 2026-07-07 (partial at the vintage edge) probed separately: absent at
   trunc@ts, later completed and SURVIVED (present in the fresh feed's completed set).
2. **Corrected law family (contract A4.1), measured:**
   - F6b immutability behind the edge: **0 violations / 337 probes** — 337 probed of the
     panel's 346 completed dots; **9 are unprobeable by construction** (their truncation
     point falls below the emitter's own ≥90-3D-bar minimum history — null printed, not
     hidden). Real 26-session extension moved **zero** completed dots (134 NVDA /
     132 NFLX / 80 TSLA — completed-bar counts; NVDA's raw all-history count is 135
     including the 2026-07-07 dot, whose bar was PARTIAL at the census vintage and is
     therefore excluded from every completed-set probe; it completed in the fresh feed
     and survived).
   - F6a′ known-ts honesty: 333/337 visible at trunc@`known_ts`; the 4 exceptions
     retro-materialize exactly one session later (verified absent@K → present@K+1 →
     immutable: NVDA 2005-02-18, 2007-04-05; NFLX 2011-12-12; TSLA 2013-10-17). The
     settle allowance is bounded to these four enumerated sites (A4.1); a new one in any
     future regeneration is a reportable finding.
   - F6c edge provisionality: the committed NFLX truncation fixture pair pins it
     (cut@ts=2026-06-26: watch event carries `known_ts`=06-26 == feed edge → provisional;
     cut@known=2026-06-30: `known_ts`=06-30 settled; fresh: final). Finality is per-event
     immutability, never population completeness (a settle-window dot may be absent from
     the current slice entirely).
3. **Detection power, honestly:** the truncation probes **do not fire on the pre-#392
   leaking map at all** (pre: 0 F6a′ failures / 0 edge flips vs post's 4+4) — its defect
   is a knowability mislabel (bucket-first-session rows consult content through close+1),
   which is extension-stable; a regression toward the label-join would present as the
   settle allowance becoming unnecessary, itself a tell. The leak IS discriminated by the
   known-answer footprint: **39 full-feed dot dates differ across the panel (25 post-only
   + 14 pre-only**; NVDA 133↔134, NFLX 124↔132, TSLA 78↔80; e.g. TSLA 2026-01-20 exists
   pre-fix only). The committed full 40-dot side-channel tables + F1/F2/F4 are therefore
   the standing tripwire against label-join regressions (NFLX's pre/post diffs all predate
   2025, so the ≥2025 window alone would not catch them — the full-table assertions do).
   My first two probe designs failed in instructive ways recorded in
   `W2_F6_DETECTION_POWER.json` + session notes: a `known_ts`-keyed filter went vacuous
   on pre-fix output, and early-history truncations tripped the engine's own ≥90-bar
   minimum-history refusal — both were probe defects, fixed before any conclusion was
   drawn. The `sweep` field in that JSON is itself one of the failed designs (statistically
   underpowered, zero hits both eras) — marked VACUOUS in the file; it must never be
   re-read as evidence of no leak.

## 3. Parity verdict — EXACT at the census vintage; invariant under extension

`W2_PARITY_REPORT.json` verdicts, all three names:

- `track_a_exact_at_vintage: true` — raw `early_dots()` ≥2025 reproduces Track A §2.6
  **byte-for-byte** (8 NVDA / 11 NFLX / 10 TSLA) at feed `4f68f8d95030`.
- `watch_exact_at_vintage: true` — NFLX's 4 bottom-watch events (ts/known_ts/kind) exact;
  NVDA/TSLA empty as frozen.
- `final_dots_invariant_under_extension: true` — zero drift on `known_ts` ≤ 2026-07-08
  under the real 26-session extension to 2026-08-13.
- New signals in the extension window (lawful, `known_ts` > 07-08): NVDA dot 2026-07-31;
  NFLX dot 2026-07-28 **+ blocked_trigger watch 2026-07-28/known 07-30** (see §5); TSLA
  dot 2026-07-30.
- Identity on every generated doc: `signal_era gc_v2_wo2`,
  `source_hash sha256:f27a407bea861a221…` (= `source_hash("", FLAGSHIP_PARAMS)` under the
  emitter's own convention; fixture `provenance.json` carries the full value).

Fresh-feed frozen fixture populations (≥2025, committed): NVDA 9 dots / 0 watches;
NFLX 12 dots / 5 watches; TSLA 11 dots / 0 watches.

## 4. Fixture artifacts (committed under `tests/fixtures/entry_radar/`)

Real `mastermind.indicator/v1` documents in the production slim shape
(`{"indicator": doc}`, heavy `series`/`gates`/`bars` dropped exactly as
`ingest/gen_slices_all.py` does), generated by `contracts.indicator_contract` with the full
`build_v2` emission; `override_gate=None` ⇒ pre-fence bit-identical emission (the
`build_v2` docstring's own guarantee), no stamper, no side effects; cohort inputs None ⇒
`score_basis "partial"` (recipe scores are NOT parity surface). Files: `NVDA.slice.json`,
`NFLX.slice.json`, `TSLA.slice.json` (feed_end 2026-08-13),
`NFLX.trunc_ts_2026-06-26.slice.json`, `NFLX.trunc_known_2026-06-30.slice.json`,
`provenance.json` (SHAs, vintages, hashes).

## 5. Family census — minted from producer receipts (contract A4.3)

Entry-event families observed in the generated NFLX doc (counts all-history):
BOTTOM_WATCH/`early_dot`/`washout_early_watch` ×13 · BOTTOM_WATCH/`blocked_trigger`/
`washout_trigger_watch` ×10 · BUY×{`take` 15, `block` 17, `regime_blocked` 18} ·
REBUY×{`take` 5, `block` 5} · RECLAIM×{`reclaim` 38, `block_repair` 2,
`stop_sweep_reclaim` 41} · SELL(`structure_stop`) ×85 (exit-side, excluded from
entry_event.v1 by design). `override_take` / `reclaim_override_take` / `pending` do not
occur on this panel's tape — they are minted from code receipts (A4.3) and covered by
synthetic unit fixtures, never by invented history.

**De-dup specimen:** NFLX 2026-07-28 — raw dot AND blocked_trigger watch on one bar; the
side channel RETAINS the date (suppression removes only `kind=="early_dot"` promotions:
`confluence_v2.py` `promoted_dot_dates` → `unpromoted_early_dots`), so the
`dedup_suppressed_by` edge is ts-join-synthesizable in-cap (A4.4). F3's 2026-02-20 is the
complementary negative (blocked_trigger, no dot fired — provably, in-cap). All-history the
panel carries three synthesizable pairs (NFLX 2018-12-26, 2026-07-28; TSLA 2022-06-22).

**Same-bar multiplicity specimen (contract A4.6):** NVDA emits two `stop_sweep_reclaim`
events on each of 2000-09-15, 2007-10-31, 2016-06-30 — one per reclaimed structure-stop
anchor (`anchor_ts` differs). Event addressing therefore carries the emitter's `anchor_ts`
as a discriminator; two events the emitter itself cannot distinguish remain a loud append
refusal, never a merge.

**Generation-time known_ts receipts for side-channel dots** (raw-function truth, ≥2026,
deliberately NOT injected into events per A4.5): NVDA 2026-01-21→01-23, 2026-07-07→07-09,
2026-07-31→08-04 · NFLX 2026-02-06→02-10, 2026-02-25→02-27, 2026-05-18→05-20,
2026-06-09→06-11, 2026-06-26→06-30, 2026-07-28→07-30 · TSLA 2026-02-05→02-09,
2026-02-24→02-26, 2026-03-30→04-01, 2026-07-30→08-03. Full set incl. 2025 in
`W2_PARITY_REPORT.json`.

## 6. Reconstructability classification by family (Class R = historically replayable)

| family (producer key) | producer / era receipt | first available | historical replayability | irreversible loss |
|---|---|---|---|---|
| raw grey dot (`early_dots` mask) | `confluence_v2._early_dot_mask` + availability join; artifact channel born #392 `935389d4` 2026-08-11 | mask: **Class R** from bars (deep store, ≥90-3D-bar warm-up); artifact channel: 40-cap tail only | **Class R** via §3.2 locked-spec fallback; artifact-only consumers bounded by the 40-cap | pre-cap grey history absent from artifacts; recoverable only by fallback recomputation |
| washout-promoted EARLY (`BOTTOM_WATCH`/`early_dot`) | `bottom_watch_events` (#392) | **zero history before `935389d4` (2026-08-11)** as an emitted family; mask+context Class R from bars | Class R (bars-only construction) but family_era stamps the emitted-family birth; earlier reconstructions are `radar_derived`, never emitter history | none beyond era honesty |
| blocked-trigger watch (`BOTTOM_WATCH`/`blocked_trigger`) | same | same | same; de-dup edge in-cap only (A4.4) | dot-coincidence for pre-cap bars |
| oracle BUY/REBUY `take`/`block`/`pending` | keeper verdicts, `_keeper_verdict_ex` | pre-fence era (`SIGNAL_ERA_PRE` slices exist in the wild) | Class R from bars for the verdict math; artifact history spans emitter eras — `signal_era` pinning mandatory, never pool | era boundaries |
| `override_take` | `washout_override` gc_v2_wo1 (`07244dff`) | 2026-08 era fence | **prospective-only as emitted events** (gate state + basket artifact dependent); zero invented rows | gate-state dependence |
| `reclaim_override_take` | keeper waiver gc_v2_wo2 (`e152fd85`) | era fence | same as above | same |
| RECLAIM `reclaim`/`block_repair` | reclaim lane promotion (scored since 2026-07-16, `contracts.py` comment) | lane promotion date; display-tier before | Class R from bars for the rule; `scored` flag era-dependent (pre-promotion slices carry scored:false) | scored-flag era |
| RECLAIM `stop_sweep_reclaim` | `stop_sweep_reclaim_events`, always `scored:false` | its commit era | Class R from bars | none |
| Radar C1–C5 | Radar's own (PR-3+) | future | n/a here | n/a |

**Zero invented historical rows** for prospective-only families is enforced in code: the
W2 store never synthesizes events outside artifact/fixture ingestion, and family_era rides
every event.

## 7. Boundary + authority

Prophet protected paths untouched (clean-diff receipt in the PR body; guard test extends
W1's). Every W2 artifact carries the DRL display-tier authority convention all-false. No
per-security selection, no outcome statistics, no routing (`DNR:KILL-OUTCOME-AUDITION`
untouched; Stock Identity boundary intact). SELL/warnings excluded from entry events —
exit-side, recorded in A4.3.
