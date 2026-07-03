# P1b probes — run inline by the orchestrator (2026-07-03 06:35-07:00 PT)

*The three supplementary probe agents died on a session limit; Fable ran them inline. Raw command
outputs in the session transcript; key numbers below. Panel: `data/china_search/closes.parquet`
through 2026-07-03 (worktree, post-reset to origin/main b243b678cd).*

## Probe 1 — Owner-read reproduction (DECISIVE: all three reproduce)

Computed with production primitives only (`confluence_tiers._stoch_rsi_kd`, `._rsi_macd`,
`cycles._tf_state`, `signal_gate.gate`) on W-FRI / 2W-FRI resamples:

| Owner claim (OWNER_RATIONALE §1) | Our primitive says | Verdict |
|---|---|---|
| 300725 "1W washout just formed a bullish crossover" | 1W StochRSI bull cross **2026-06-26** (1 wk-bar ago) from **d=9.3**; 8-bar k/d min 2.5 | **REPRODUCED** |
| 300725 "2W washout" | 2W stoch 24, `stoch_cross_up=True`, macd_curl_up, hist negative | **REPRODUCED** |
| 300725 "traded in range 2 years, weak cycles" | 2y range 24.5-52.6, spot at 46%; 2W macd_pos=False | **REPRODUCED** |
| 603129 "already ran, we're late" | 3D gate `eligible=False ticks=3` ("no longer a fresh entry"); spot at 83% of 2y range | **REPRODUCED** |
| 688306 "about to ACTUALLY do a 2W MACD crossover" | 2W `_tf_state`: **`macd_approaching_up=True, macd_bars_to_cross=4.9`**; RSI-MACD m−s=−0.12, slope +0.64/bar → **cross projected in ~0.2 2W-bars** | **REPRODUCED** |
| 688306 "3D and 1W okay" | 3D gate T2 eligible ticks=2; 1W k=81/d=62 constructive | **REPRODUCED** |

**Conclusion:** the W-tier setup layer requires NO new math — `cycles._tf_state` already emits
`approaching_up`/`bars_to_cross`/`stoch_cross_up` on any resampled grid. The owner's playbook is
automatable with existing primitives (masterplan F2/W1).

**New bug caught:** the as_of 07-03 board shows 603129 as T1/ticks=2 while a live `gate()` on the
same panel says ineligible/ticks=3 — the freshness-contract defect (W0.6), observed red-handed.

## Probe 2 — Board appearance history (git walk of `site/factordata/china_standouts.json`)

| as_of | n | 300725 | 603129 | 688306 |
|---|---|---|---|---|
| 06-16 | 110 | – | – | – |
| 06-17 | 110 | – | **69** | – |
| 06-22 | 110 | – | – | – |
| 06-23 | 110 | – | – | **24** |
| 06-24 | 110 | – | – | – |
| 06-25 | 110 | – | – | – |
| 06-26 | **46** | – | – | – |
| 06-29 | **11** | – | – | – |
| 06-30 | 110 | **2** | **1** | 5 |
| 07-01 | 110 | 2 | **–** | 8 |
| 07-02 | 110 | 3 | 2 | 4→– (intra-day) |
| 07-03 | 110 | **1** | **2** | **3** |

Findings: (1) **flicker** — names appear/vanish/reappear (688306 five transitions in 8 sessions);
(2) **board-width collapse** — n=46 on 06-26 and n=11 on 06-29 (the silent coverage-drop hole,
caught live → W0.7 guard); (3) **surfacing lag ≠ gate lag** — gates fired 06-22/24 (688306 even
cameoed #24 on 06-23) but stable visible ranks only arrived 06-30 when washout_2w (+0.50, the
biggest bonus) flipped — *after* +14.6% of 603129's move. The late bonus is the gatekeeper of
visibility (masterplan F3). (4) Owner's guess "picked it up 5-8 days ago" for 603129: the *gate*
was eligible 06-24 (7 trading days before 07-03) — owner's memory matches the gate, not the board,
which only ranked it 06-30. (5) On 07-03 the board's top-3 = the owner's three exemplars in order.

## Probe 3 — Narrative feasibility (superseded by shipped #1054 + membership facts)

- **#1054 (`engine/china_narrative_radar.py`, merged today by a sibling session)** already computes
  the narrative layer's core: per-THS-basket 63d narrative momentum (descriptive, §754/§773-tagged),
  washout↔euphoria position, member clean-entry lists, and the **validated global-AI weekly
  confirmer** (t=3.27, per-basket honesty tags: cpo=validated, pcb=partial, storage/adv_pkg=2024+-
  only). Display-only, own page, feeds the picker nothing → masterplan F4/W2 wires its per-name
  tags into the board, log-first.
- **Membership facts from the exemplar forensics:** 300725 in THS "Synthetic Biology" (+18.9%
  rel20) but the board TWD axis reads "no data" (join dead, W0.5); 688306 in 16 THS baskets
  (Solid-State Battery +35.6%); **603129 in zero THS concepts** (coverage hole, W0.5).
- **Global healthcare read-through** (owner's 300725 tailwind): no machinery exists yet; the
  AI-semis→CPO precedent (t=3.27) is the recipe → W2 phase-0.
