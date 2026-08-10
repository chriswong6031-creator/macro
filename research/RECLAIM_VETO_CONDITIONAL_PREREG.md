# Reclaim-veto conditional override — PRE-REGISTRATION

**Frozen:** 2026-08-10 (operator: "yes do it" — extend the ratified basket-washout construction to
the reclaim-veto family) — **before any results were computed.**
**Family:** `reclaim_veto_conditional_v1`. Two arms, separate gates, separate era fences.
**Authority:** `research/prophet_us_audit/RECLAIM_VETO_PACKET_2026-08-05.md` §9 sanctions exactly
this construction class ("the veto relaxing only under a measured continuation-regime state …
through its own prereg, with the era stamp") — this document is that prereg. Complies with
`DNR:KILL-200DMA-RECLAIM-VETO-FLAT` (this is the named revival path, not a flat drop). Shared
machinery, definitions, and repaired aggregation are inherited from
`research/BLOCKED_ENTRY_CONDITIONAL_PREREG.md` §1/§6/§7 (the gauntleted A1b construction: LOO
basket-peer washout state, threshold grid, repaired ruler) — restated here only where they differ.

## §1 The family and the two arms

The reclaim-veto family = counter-trend buy refusals requiring a 200-day reclaim-and-hold:
- **Arm T (Terminal keeper):** charting-app `confluence_v2` keeper `block` verdicts with
  counter-trend reclaim reasons ("failed reclaim-and-hold", "counter-trend, no 200-reclaim/hold").
  Fires that passed `bear_block` but failed the CT legs. Bearish-divergence keeper blocks are a
  DIFFERENT leg — excluded from the cohort, disclosed. (Live exemplars: HL 2026-06-16 @15.96,
  06-25 @15.40.)
- **Arm P (Prophet US `signal_quality._buy_filter`):** the packet's refusal set — same production
  function called twice, `refused = on=="block" with CT_RECLAIM_FAIL/CT_BOTH_FAIL AND off=="take"`
  (the isolation `research/prophet_us_audit/reclaim_veto_packet.py` implements; reuse it). (Live
  exemplar: NEM refused 2026-08-05/08-07.)
- **Out of scope:** CN/HK names (600547, 002716, 9988) — no CN/HK basket-washout state exists;
  their arms require their own construction. HK already runs `hk_prophet_v2` (veto dropped flat).

## §2 Construction under test (both arms)

> Waive the reclaim leg for a fire whose name **qualifies in the basket-washout state** (LOO
> `names`-map peer-median drawdown ≤ −THR%, THR ∈ {15,20,25,30}, PIT at the fire's known date) —
> everywhere else the veto stands unchanged.

Execution ruler (inherited, repaired): PIT entry next session; stop = 3-bar washout low −
0.5×ATR14 (m FIXED); intrabar fills PRIMARY; +10R cap; censored-unstopped excluded from levels;
equal-notional mean beside every R read; clustering = episode×name AND episode; date-clustered
shown for continuity only.

**Data basis: PRODUCTION bars are PRIMARY** (Gate-B finding: local 2014-truncated tapes mis-phase
1,263 of 2,454 names; the fetched production basis in the session scratchpad `regrade/` runs to
IPO). Local deep stores may extend the design era where production lacks pre-IPO-feed history —
any such use disclosed per arm.

## §3 Gates (per arm, independently; held-out 2019+, design ≤2018)

- Qualifying-cell capped-R CI > 0 on BOTH clustering units (episode×name and episode-clustered).
- (Qualifying − non-qualifying complement) difference CI > 0.
- Equal-date-weighted read sign-positive with CI excluding 0.
- **Ex-COVID premium positive** (drop 2020-02-15..2020-06-30 fires) AND leave-one-episode-out
  minimum > 0 — a cell that dies ex-COVID is dead (blocked-entry F1 law).
- Coverage floor: fire-weighted basket∪sector mapping ≥60%.
- Episode honest-N: cells with <5 held-out episodes are EPISODE-THIN — reported, not shippable.
- **Coverage gate (adjudication law):** the rule evaluated on the motivating exemplars — Arm T:
  HL 06-16/06-25; Arm P: NEM 2026-08-05 — per threshold, and current-regime membership stated.
  A threshold that refuses all motivating exemplars does not ship at that notch regardless of
  gates.
- Multiplicity: Arm-T and Arm-P gates are this family's only promotion-bearing tests; everything
  else (depth bands, density, dead-arm) is disclosure. Dead-name arm (blocked-entry §7 A1b-dead
  spec) required for level honesty; sp1500 scope disclosed.

## §4 Decision rules

- **Arm T PASS + operator ratification →** charting-app keeper waives the CT reclaim legs for
  qualifying fires, emitting a distinct entry class (sibling of `override_take`, reason naming the
  reclaim waiver), behind a **new era stamp `gc_v2_wo2`** (never pooled with `gc_v2`/`gc_v2_wo1`);
  forward-ledger accrual from night one.
- **Arm P PASS + operator ratification →** `engine/signal_quality._buy_filter` waives the reclaim
  leg when the name qualifies (veto otherwise intact), behind the packet-§7 fence:
  **`us_prophet_v1 → us_prophet_v2`** via the `BOARD_DEFINITION` pattern
  (`engine/hk_board_rank.BOARD_DEFINITION` precedent) — the US board pre/post are different
  products and their forward ledgers never pool.
- **Either arm FAIL →** that arm's waiver construction closes (construction-scoped; ore law); the
  veto stands there; the packet's ≥60-session re-run (~late Oct 2026) remains lawful future input.
- Any outcome: results + receipts commit beside this file; exemplars reported as named rows.

## §5 Ratification log

- *(empty at freeze)*
