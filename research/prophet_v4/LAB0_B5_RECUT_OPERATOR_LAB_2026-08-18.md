# LAB-0 — B5 RECUT: PROPHET OPERATOR LAB (B5A) vs EARLY ENTRY DESK (B5B)

**Authority:** Chairman commission, 2026-08-18 (operator chat, verbatim program charter held by the
commissioning Fable session). **Status:** records-only amendment — this document plus the paired
edits to `WAVE_GRAPH_AND_MERGE_ORDER.md`, `WS-PROPHET-US-V4-RECOVERY.md`,
`WS-LIVE-ENTRY-RADAR.md`, and `DEC:PROPHET-LAB-B5A-RECUT` change zero runtime bytes.
**Pinned main at authoring:** `a7cfd4bef589`.
**Decision record:** `DEC:PROPHET-LAB-B5A-RECUT`.

---

## §0 What LAB-0 does

The Chairman commissioned an operator-only **LIVE | LAB** mode inside the U.S. Prophet experience
so exact early-entry candidates can be visually inspected in real time, plus — as a separate
capability — migration of the production U.S. Prophet page onto the frozen R4/MP-1 reference
design. This is **NOT** a promotion of any early-entry detector into Prophet authority, and it is
**NOT** gated on 10–20 trading days of outcome maturation: candidates become visible to the
Chairman immediately, with honest observation-class labeling (§4).

V4-B5 ("Early Entry Desk MVP", deps B3+B4) conflated two different capabilities. LAB-0 recuts it:

| Wave | What it is | Deps | Authority |
|---|---|---|---|
| **V4-B5A** — Prophet Operator Lab | Operator-only observational surface: LIVE\|LAB mode, six Lab boards, read-only projection of canonical Radar output over the Prophet page | **No B3/B4 dependency.** Needs: R-LAB-1 (Radar W4.1 transport, external under `WS:LIVE-ENTRY-RADAR`), P-LAB-API, D-LAB-R5 RIG, P-MP1-SHELL | **Zero.** Read/filter/join/decorate only |
| **V4-B5B** — authoritative Early Entry Desk | The desk MVP with Prophet-side authority semantics (lifecycle, availability lanes) that masterplan §21 B5 described | **Retains B3, B4** — unchanged | Whatever B3/B4 grant it, adjudicated then |

**Non-completion rule (binding):** shipping B5A completes **neither B5B nor B6**. B6 (Radar
observation-only activation with full-RTH-session proof) remains its own wave; the operational
arming of Radar W4 that the Lab needs (§6) contributes evidence toward B6 but does not close it.
B5B later **adopts** B5A's plumbing (API, controller, boards) instead of rebuilding it.

---

## §1 Architecture law (frozen)

Prophet Lab is a **presentation/projection layer over canonical Radar output**.

- Radar owns detector truth. Prophet Lab may **read / filter / join / decorate** only.
- The Lab has **zero** ranking, gating, sizing, plan-origination, signal-origination, or
  Prophet-mutation authority.
- **No second detector implementation. No second StochRSI. No second market-data plane. No second
  Radar scheduler. No F1 Fusion. No C2 voting.** (F1_FUSION remains Radar's reserved slot;
  cross-detector display union/intersection in §3 is set arithmetic on already-minted events, not
  fusion, and mints nothing.)
- **No retrospective evidence relabeled live-forward** (§4).
- Default sort = newest first. "Research Priority" ordering is optional/nonblocking decoration —
  never a launch dependency, never a new ranking.

## §2 DNR confrontation (by name)

- `DNR:KILL-PROPHET-POP-MERGE` — the Lab never changes the graded-board population and never
  blends conviction×timing into one ranking. Lab boards are a separate authenticated operator
  surface projected from Radar stores; `us_standouts.json` / `us_board_ledger` inputs are
  untouched. The P-MP1-SHELL wave re-checks MP-1's population re-source against this row before
  executing (wave-graph §3 MP-1 rule, unchanged).
- `DNR:KILL-WASHOUT-TURN` — the Lab arms nothing. The `lab-g0-c2a-v1` board is a **display set
  intersection** of independently minted G0 and C2a events: view `detector_id = null`, zero
  events/episodes/scores minted, no washout×turn detector construction is created or promoted.
- `DNR:KILL-OUTCOME-AUDITION` — the Lab API must not read forward outcomes for ranking; no
  per-name selection of anything by outcome exists on any Lab surface.
- Radar landmine (WS record): expert identities are never flattened — one visual card may carry
  multiple `experts[]`, each preserving exact detector/event identity
  (`DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED`).

---

## §3 Lab board definitions (frozen product contract)

Six boards, all returned in one API response (client switching is instant):

| Board id | Definition |
|---|---|
| `lab-g0-v1` | exact `G0_GREY_DOT@1` |
| `lab-c1-v1` | `C1_1D_LIVE_WASHOUT@1`, current nonterminal episode |
| `lab-c2a-v1` | `C2_1D_TURN@1` / `c2a_kd_cross` |
| `lab-c2-variants-v1` | `c2a_kd_cross`, `c2b_k_slope`, `c2c_higher_k_low`, `c2d_hist_trough`, `c2e_hist_curvature`, `c2f_rebound_atr` — expert identities remain separate |
| `lab-g0-c2a-v1` | display set intersection only; view `detector_id = null`; mints zero events/episodes/scores |
| `lab-all-early-v1` | union G0 + C1 + C2a–f; one visual ticker card may contain multiple `experts[]`; **excludes C3/C5 in V1** |

Default sort = newest first (`sort_ts` + explicit basis). Research Priority optional/nonblocking.

## §4 G0 honesty + observation-class contract (frozen)

Preserve, end to end (store → API → UI):

- `signal_ts` always; `signal_known_ts` **only when the emitter supplied it**; `null` when it did
  not. **Never reconstruct a missing `known_ts`.**

Product observation class (new, Lab-plane metadata — never written into the immutable event):

- `retrospective_seed` — any historical event visible at commissioning, unless proven newly
  observed after a continuous live baseline. Seeds are shown to the Chairman immediately, but
  `evidence_eligible = false` and measured Lab→Prophet lead = `null`, always.
- `live_forward` — a genuinely new live observation. `first_observed_at` = the actual Radar W4
  spool **envelope `pass_ts`** that first carried the `event_id`. The immutable
  `mastermind.entry_event.v1` event is **never mutated** to carry this transport fact — first
  observation is derived at the consumption/projection plane.

Only true `live_forward` observations may ever show a measured Lab→Prophet lead.

## §5 API contract sketch (frozen at P-LAB-API build)

`GET /api/prophet/lab/v1` — authenticated read-only, existing site-full pattern
(`require_user` → `enforce_site_full(always=True)`), `Cache-Control: private,no-store`. Lab
candidates never appear in anonymous HTML. Reads canonical Radar live output + canonical Prophet
plan/index data + existing board-read/stock-library enrichment + observation metadata only. Must
not: run detector formulas, read forward outcomes for ranking, generate a Prophet plan, alter any
store. Response = `prophet.lab_board/v1`: generation/source health, an **all-false authority
block**, all six boards, per-row ticker/name/sector/spark, `sort_ts` + basis,
`observation_class`, `experts[]` with exact detector/event identity, and a Prophet comparison
(current membership/lifecycle/stance, first recorded/published, signal anchor, entry date,
measured lead only for true live-forward). Kill switch: `PROPHET_LAB_DISABLED` stands the API
down independently of Radar's own `ENTRY_RADAR_LIVE_ENABLE`.

## §6 Program waves and execution order

1. **LAB-0** (this PR) — records only.
2. In parallel:
   **A. R-LAB-1** — Radar W4.1 live-transport correction. Executes as **Radar-owned joint work
   under `WS:LIVE-ENTRY-RADAR` (wave W4.1)** per the wave-graph §4.3 pattern: fix the
   confirmed-lane transport (live_eval's `pack.probe_set["nightly_lanes"]` read vs an unpopulated
   admission-summary field — prefer `entry_radar.live_pack/v2` with explicit `confirmed_lanes`
   inside the final pack hash), preserve exact G0 events from `EntryEventStore.events()` through
   `PendingDelta.events` → spool-before-consume, fix the W4 `entry_radar.events/v1` envelope vs W5
   top-level `mastermind.entry_event.v1` expectation so W5 consumes the real envelope and derives
   first-observation time from envelope `pass_ts`, add an end-to-end contract test
   (`live_ledger.build_event_payload()` → `reconcile_entry_radar.read_spool_events()`). W5 stays
   the sole durable `data/entry_radar/` writer. **No detector spec hash changes; Prophet protected
   paths byte-clean.** Baseline discipline: do not merge W4.1 against a knowingly red W4 test
   baseline — #5897 (open at authoring) lands or is reconciled first.
   **B. D-LAB-R5** — reference design + fresh independent RIG R5 starting from the frozen R4
   Prophet reference (no broad redesign; adds LIVE|LAB, six selectors, retrospective/live
   distinction, empty/stale/unavailable states, Prophet comparison, EN/ZH, dark/light, mobile).
   Builder/design author cannot self-approve; production blockers re-censused, not copied from R4.
   **C. P-LAB-API** — fixture-based implementation of §5.
3. **Radar live commissioning** after R-LAB-1 (operator arm; §0 non-completion rule applies to B6).
4. **P-MP1-SHELL** — after R5 passes, execute MP-1 on the production U.S. Prophet shell under
   MP-1's own law (stocks mode only; no Prophet engine/ranking/scoring change; lifecycle from the
   published plan book; Candidates separate; non-US byte parity; server-side paid withholding
   kept; no theme.css change unless separately authorized).
5. **P-LAB-UI** — after API + R5 + shell + a functional Radar source: generalize the W-L1 dynamic
   board mechanism into ONE `ProphetBoardController` (sole painter of the principal grid; state =
   `desiredMode LIVE|LAB`, `liveSource NIGHTLY|PROVISIONAL`, `labSelection`, `labPayload`).
   W-L1 poller only updates controller provisional state and never repaints while LAB is
   selected; LAB→LIVE selects the best lawful LIVE board **now** (never a pre-LAB snapshot); LAB
   stale/unavailable stays visibly LAB — never a silent LIVE fallback under a LAB label; fresh
   page defaults LIVE; lazy Lab fetch on first click; bearer via `MDXAuth.client()`; no-store;
   ~60s refresh while visible; request-generation/AbortController race protection; purge payload
   + DOM on entitlement loss/signout; `LiveQuotes.refresh()` after dynamic mounts.
6. **Production verification**, then return to the Chairman with the live URL + operator guide.

**Deployment boundary:** Terminal slice directory must be verified on the live VPS before
configuration (likely `/opt/terminal/terminal/public/data` — UNVERIFIED until checked live).
Full-RTH cadence evidence and H10/H21 maturation are **not** prerequisites for exposing the Lab.

## §7 Rollback

- Radar's own switches disable the source without touching Prophet: the staging/arming gate
  (`ENTRY_RADAR_LIVE_ENABLE`, W4 deploy plan) and the kill switch
  (`ENTRY_RADAR_LIVE_DISABLED` env + `KILL` file, `engine/entry_radar/live_eval.py:125-126`).
- `PROPHET_LAB_DISABLED` stands down the Lab API independently.
- Fresh UI always defaults LIVE; retained nightly DOM is the runtime restore target.
- The MP-1 shell migration is independently revertible.
- The Lab can never mutate Prophet state (there is no code path to roll back on that axis — §1).

## §8 Spawn discipline (applies to every Lab-program spawn)

One independently useful capability per PR. Before each spawn: refresh `origin/main`; check
active-PR collision on owned paths; name the workstream owner; list exact allowed paths; inline
acceptance tests; provide STOP conditions. Builder never self-merges flagship UI; independent
reviewer for semantic/runtime work; independent design authority for the RIG.
