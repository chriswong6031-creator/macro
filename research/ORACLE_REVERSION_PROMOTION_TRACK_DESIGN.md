# Oracle Reversion Promotion Track — Design (for build)

**Status:** design, 2026-07-05. The wire that lifts the validated reversion base
(`research/ORACLE_REVERSION_VALIDATED.md`, 10 signals in `data/oracle/compounds/registry.jsonl`)
from a display-only *library* into Oracle's live surface (`oracle_state.json`) and
thence to the Neural Web — **under the Neural Web constitution**, without an LLM
originating any escalation.

## 1. The problem (the missing wire)

The reversion signals are backtest-validated (6-leg gauntlet PASS, cost-robust) and
sit in `registry.jsonl` at `status: screened`. But:
- `engine/oracle/live.py` builds `oracle_state.json` from **episodes only** — it never
  reads the compound registry, so the signals never reach the live surface.
- The Neural Web consumes Oracle **through** `oracle_state.json` (`engine/neuralweb/contradictions.py`
  reads `site/basketdata/oracle_state.json`), not through the registry.
- The one existing scanner that reads the registry — `scripts/oracle_promotion_scan.py`
  — grades on the **63-day** economic floor, which is the *wrong ruler* for reversion
  signals (they score ~0 at 63d by construction; that is the whole reframe).

So the signals are a parallel research library with no path to the surface. This track
is that path.

## 2. Constraints — what the design MUST respect

- **Backtest ≠ live edge (house law).** A gauntlet PASS is a promotion *candidate*, not a
  validated live edge. Nothing ranks on a backtest alone.
- **Constitution Article 1 — no origination.** An LLM (me, the cortex) may never originate
  a signal/score/escalation. Every tier promotion must be produced by a **deterministic**
  gate on measured evidence, adjudicated by the operator/Fable — never written by an LLM.
- **Constitution Article 2 — perimeter by surface.** Ranking / priority / attention is the
  "money path" and requires earned authority. **Display tier may annotate, never rank.**
- **Constitution Article 3 — authority on Wilson-CI lower bounds; lapses on silence.**
  Escalation is granted by `engine/neuralweb/constitution.py::grant_authority`:
  `wilson_lower(hits, n, z=1.645) / base_rate > 1.25`. The same gate that governs
  `can_force` and the cortex's A2 earn-in. Authority **lapses** if the signal goes silent
  or its live CI decays. An LLM **may de-escalate** a calibrated key, never escalate.
- **Right ruler.** Live grading uses the **reversion metric** (absolute ret_exit at the
  ~21-session hold, WR, MFE/MAE asym, regime-split) — NOT 63d. This track *bypasses* the
  63d `oracle_promotion_scan.py` entirely.
- **Nightly is the sole advancer of forward ledgers (house law).** The live forward ledger
  is written only by the nightly lane; intraday lanes discard.

## 3. The authority ladder

A reversion signal climbs by *earning a live forward track record* — not by backtest.

| Level | Where | Gate to reach it | Article-2 surface |
|---|---|---|---|
| **L0 Library** | `registry.jsonl` `reversion` block | 6-leg gauntlet PASS (already done) | none (research doc) |
| **L1 Display** | `oracle_state.json` → `reversion_signals[]` | just L0 + fired on the latest date | **display** — annotate "fired today", show backtest stats + "live: accruing, no authority". Operator may act at own conviction; NW cortex cites as CONTEXT only |
| **L2 Accrual** | `data/oracle/reversion_forward/` | continuous; every L1 fire is recorded + graded at +21 sessions | none (shadow ledger) |
| **L3 Confirmer** | `oracle_state` tier flips to `confirmer` | `grant_authority` PASS on **live** stats (§5) | **confirmer** — may add weight to an already-ranked signal; may NOT rank alone |
| **L4 Scored** | `oracle_state` tier flips to `scored` | higher live-n + tighter CI (§5) | **scored** — may contribute to ranking / attention (the money path) |
| **Lapse** | back to Display | Article 3: silence (no fires in N days) OR live CI decays below the L3 bar | de-escalation may be LLM-triggered; never re-escalated by LLM |

The jump that matters is **L2 → L3**: it is the only place backtest-validated signals
gain money-path authority, and it is gated purely on the *live* Wilson bound + operator
adjudication. Everything below L3 is safe under Article 2 today.

## 4. Components to build

1. **`scripts/oracle_reversion_forward_ledger.py`** (nightly, single-writer). For each L0
   compound with a `reversion` block, evaluate its entry rule on the latest panel date
   (tier-s and tier-m); append new fires to `data/oracle/reversion_forward/<compound_id>.jsonl`
   as rows `{compound_id, node, fire_date, exec_date, exit_date=fire+21, tier, regime, ret_exit,
   mfe, mae, matured:bool}`; on each run, **grade** rows whose exit_date ≤ today (fill
   ret_exit/mfe/mae, set matured=true). Reuses `_per_entry_rows` from
   `scripts/oracle_reversion_screen.py` so live grading == backtest grading. Discard on
   intraday lanes. Register as a `shadow`-tier artifact in `config/synapse.yml`.

2. **`engine/oracle/live.py` extension** — add a `reversion_signals` block to
   `oracle_state.json` (bump to `oracle_state.v2` or write a sidecar
   `oracle_reversion_state.json` to avoid touching the episode contract). Per compound:
   ```
   {id, mechanism, cluster, universe.tier, authority_level: "display|confirmer|scored",
    fired_today: [nodes], backtest: {asym, wr, ret_exit, n}, live: {n, wr, wr_ci_low,
    asym, base_rate, lift_lb}, article2_surface}
   ```
   Reads the registry + the L2 forward ledger + the granted authority (below). L1 display
   rows require only that the rule fired today; the `live` block is honest even at n=0.

3. **`scripts/oracle_reversion_promotion_scan.py`** — the reversion analog of the 63d
   scanner. Reads the registry (`reversion`-block compounds) + the L2 ledger, computes live
   stats, calls `grant_authority` (§5), and writes candidates to
   `data/oracle/reversion_promotion_queue.json` for **Fable adjudication** — **NEVER
   auto-promotes** (mirrors `oracle_promotion_scan.py`'s discipline). Emits a
   `data/neuralweb/governance.jsonl` event for every proposed tier transition (Article-2
   event). Nightly step after the forward ledger.

4. **`research/ORACLE_REVERSION_PROMOTION_PREREG.md`** — the **frozen** live-promotion floor
   (§5), pre-registered BEFORE any live accrual matures, so the L3 bar cannot be tuned to a
   result. (Same discipline as the gate prereg + Amendment 1.)

5. **Constitution wiring** — reuse `engine/neuralweb/constitution.py::grant_authority`
   verbatim (do not fork the gate). The reversion signal's `hits/n/base_rate` feed it; the
   returned grant + `lift_lb` drive the tier. Authority is stored per-compound (e.g.
   `data/oracle/reversion_authority.json`) written only by the deterministic scanner.

6. **`config/synapse.yml` registration** — new artifacts: `oracle_reversion_state`
   (display), `reversion_forward_ledger` (shadow), `reversion_promotion_queue` (infrastructure),
   `reversion_authority` (infrastructure). `oracle_state` gains the `reversion_signals` key if
   inlined.

## 5. The pre-registered LIVE promotion floor (the Wilson gate)

For the **L2 → L3 (confirmer)** grant, feed `grant_authority(hits, n, base_rate)`:
- **`n`** = count of **matured** live fires for the compound (exit_date ≤ today), regime-scoped
  for single-regime signals (bear-tape accrues only in risk-off — its clock is regime-gated).
- **`hits`** = live fires with `ret_exit > 0` (the WR definition).
- **`base_rate`** = the **unconditional** trailing 21-session win-rate on the same universe
  (buy-anytime rate). This makes the gate measure live **entry-timing lift over random**, the
  same thing the placebo tests in backtest — not just "> coin flip" in a bull era.
- **Grant** iff `wilson_lower(hits, n, z=1.645) / base_rate > 1.25` **AND** `n ≥ 25`
  (matches the NW's existing earn-in floors — cortex A2, `can_force`).
- **L3 → L4 (scored)** additionally requires `n ≥ 60` and `asym_live ≥ 1.3` (a live haircut
  from the 1.5 backtest bar, for live noise + costs).
- **Lapse (Article 3):** de-escalate to Display if no fire in 90 sessions OR the live
  `lift_lb` falls back below 1.25 at the current n.

Freeze these constants in the prereg. The backtest gauntlet PASS remains a hard
precondition (a compound with no `reversion` block never enters the ladder).

## 6. Phase sequencing

**P0 — Accrual (build first; it is the long pole).** Ship the forward ledger + nightly grader.
Zero surface change. Authority cannot be earned until fires accrue and mature (weeks-to-months),
so this clock must start before anything else is useful. Freeze the prereg (§5) here.

**P1 — Display (safe, immediately useful).** Ship the `oracle_state` `reversion_signals` block
at **display tier only**. The operator sees "validated reversion setups firing today" on an
Oracle page (honestly labelled backtest + accruing); the NW cortex can cite them as **context**.
No ranking, no alerts → no Article-2 event. This delivers value on day one while L2 accrues.

**P2 — Scanner + queue.** Ship `oracle_reversion_promotion_scan.py` + the queue + governance
events. It runs nightly, but with thin live data it will (honestly) queue **nothing** until
accrual matures — exactly like the kernel/cortex machinery that is "armed, not fired".

**P3 — Escalation (earned).** When a compound clears §5 on live data, the scanner queues it;
the operator/Fable adjudicates; on approval a governance event flips its `oracle_state` tier
display → confirmer (→ scored later). Only now does it touch the money path. Article-3 lapse
runs continuously thereafter.

## 7. What the operator + the Neural Web get at each phase

- **After P1:** the operator has a live "reversion setups firing now" annotation (act at own
  conviction — respects the low-n trading style, since display tier has no n floor). The NW
  cortex/contradiction detector can *see and cite* the signals as context. **This alone closes
  the "can't tell where the work went" gap** — the library becomes visible on the surface.
- **After P3:** earned signals begin to *confirm/rank* inside Oracle's live output and, through
  `oracle_state`, add weight in the Neural Web's synthesis — but only the ones that proved
  themselves live, only via the deterministic Wilson gate, only after adjudication.

## 8. Honest caveats

- **Earn-in delay is real and correct.** No signal reaches L3 until ~25 matured live fires.
  For selective signals (RSLAG ~2 nodes/date; bear-tape gated to rare risk-off) that is weeks
  to months. This is the constitution working as designed, not a defect.
- **Live will be worse than backtest.** Expect the era-inflated tier-M magnitudes (M1_OIL
  +12%, RSLAG +9.8%, SRM +5.6%) to regress live; the Wilson *lower* bound is the conservative
  bar precisely for this. The L1 display block must show backtest and live side by side and
  never conflate them.
- **Single-regime clocks are regime-gated.** Bear-tape signals only accrue evidence in
  risk-off; their earn-in pauses in calm tapes. Grade and gate them on risk-off fires only.
- **Cluster authority, not signal authority (open question for adjudication).** The base is
  ~7 independent bets, not 10 (see the independence map). Consider granting authority at the
  *cluster* level (dollar-relief, V-bottom, oil, rs-laggard) so correlated siblings don't
  double-count on the money path. Flag for the operator's ruling at P3.
- **This is Oracle's build, but the L2→L3 gate is Neural-Web-governed.** P0-P2 live entirely in
  `engine/oracle/` + `scripts/`. Only the authority grant reaches into `engine/neuralweb/constitution.py`
  (reused, not forked) and `governance.jsonl`. That is the exact seam where the rotation lobe
  hands off to the brain's governance.

---

**One-line summary:** build the accrual ledger + display surfacing now (safe, useful), let the
signals *earn* live track records, and let the existing constitution gate — not an LLM — decide
when a proven signal graduates onto the money path.
