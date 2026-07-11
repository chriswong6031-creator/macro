# Index Hybrid Momentum (IHM) — RSI-MACD at the regime layer + global turn confluence

Status: MASTERPLAN (W0). Adjudicated by Fable, 2026-07-11, from an operator brief on the
Hang Seng June→July 2026 turn. Program tag: IHM-R1..R14. Forward family: `index_momentum_v1`.

---

## 0. Operator brief (verbatim intent) and what the evidence shows

The operator watched the Hang Seng bottom (22,672 on 2026-06-26) and rally to ~24,175 by
07-10 on a TradingView **RSI-MACD hybrid** (TH_RSIMACD+: RSI(14) → EMA14−EMA60 → signal
EMA5) tracked at 1D/2D/3D, and asked: (a) upgrade "engines still using pure MACD to
calculate turns" to the hybrid, system-wide; (b) add depth-of-oversold context (crosses
from ≈−8/−9 marked bear-market lows; crosses from −3/−5 were bull traps); (c) use
histogram velocity for early detection; (d) track US Mag 7 and Hang Seng together —
one confirms the other; US-only strength (the semis episode) is not broad risk-on.

Every empirical claim in the brief was reproduced on real data (§2). The census (§3)
found the repo **already ships this exact hybrid** at the per-stock/sector layer — the
gap is the **index/regime layer**, which still runs pure price MACD(12,26,9).

## 1. Doctrine position

Display-tier program under the context-accrual law: everything here ships as context and
forward-ledger accrual, **authority all-false** (no rank/gate/size/escalate). The one
authority surface implicated — the market_state trend leg — is handled as a **shadow**
(IHM-R6): computed alongside, logged, promoted only through a pre-registered study.
Nulls are printed. LLMs originate nothing.

## 2. Evidence of record (2026-07-11 study; yfinance ^HSI/^GSPC 1990→, cross-checked
against house stores `data/hk/_HSI.parquet` 1986→)

### 2.1 The operator's HSI readings reproduce

| Claim | Data | Verdict |
|---|---|---|
| 1D hybrid bull cross "July 3" | Cross 2026-07-03, macd −8.03 at cross | CONFIRMED exact |
| Bottom "June 29-30" | Low close 22,672 on 06-26; retest 22,881 on 06-30 | CONFIRMED (shelf 06-26..30) |
| Depth "−8, consistent with bear lows" | 2026 1D min −9.33 (06-26); 2D min −9.22 (07-02) | CONFIRMED |
| "−11 during 2020 covid" | 2D-grid min Mar-2020 = **−11.11** | CONFIRMED exact (operator's chart = 2D grid) |
| Histogram velocity: "rising from Jun 30, positive Jul 6" | 1D hist −1.26 (06-26) → −0.54 (06-30) → +0.51 (07-03); 2D flips on the 07-06/07-08 bar (anchor-phase dependent) | CONFIRMED shape |
| Two 1D bull traps at "−3 and −5" | 06-02 cross @ −2.86 → **−11.5%** fwd20; 03-12/16/25 cluster @ −5.3..−5.8 → fizzled ≈0% by fwd40 | CONFIRMED |
| "2D cross ~3 ticks ago, 3D crossing now" | 2D hist positive on the 07-08 bar; 3D hist −0.17 on 07-10 (cusp) | CONFIRMED (±1 bar anchor phase) |

### 2.2 Depth-at-cross separates bottoms from traps (HSI 1D, all bull crosses 1990→)

| macd @ cross | n | fwd20 med / WR | fwd60 med / WR |
|---|---|---|---|
| ≤ −8 (deep washout) | 82 | **+1.8% / 65%** | +2.0% / 64% |
| (−8, −6] | 43 | +0.1% / 51% | +3.8% / 63% |
| (−6, −4] — **trap zone** | 62 | −0.4% / 48% | **−0.8% / 44%** |
| (−4, −2] | 61 | +2.3% / 67% | +1.6% / 58% |
| (−2, 0] | 61 | +0.7% / 52% | −1.3% / 44% |
| > 0 | 133 | +1.1% / 56% | +2.6% / 59% |

Post-2010 era split (era-split law, DT-R16): same shape; trap zone worsens (fwd60 med
−3.8%, WR 32%; n=31). Deep bucket holds (fwd20 WR 62%, n=30). Caveat: events cluster
inside bear episodes; these are descriptive display-tier stats — any promotion runs
episode-aware inference per DT-R14 (within-month episode-label permutation).

Historical 1D depth minima at major lows: 1997 −14.8, 2002 −14.3, 2008 −12.2,
2011 −8.5, 2015 −12.0, 2018 −11.9, 2020 −13.6, 2022 −13.6, 2025-04 −12.7, 2026-06 −9.3.
The indicator is bounded (RSI-space), so depths are comparable across indices — 10y minima
all sit ≈−15..−18 for SPX/QQQ/SOXX/HSI/KOSPI/TWII/Mag7. This cross-market comparability
is a structural advantage over price-MACD (price-scale dependent) and the core reason the
hybrid belongs at the index layer.

### 2.3 US confirmation is a durability discriminator, not a 20-day one

HK deep bull crosses (≤−6) split by US confirmation (SPX hybrid hist rising over 3
sessions or macd>signal at HK cross date):

| Era | US-confirmed | Unconfirmed |
|---|---|---|
| full | n=107, fwd60 **+3.6% / 66%** | n=18, fwd60 +0.3% / 50% |
| post-2010 | n=45, fwd60 +1.8% / 59% | n=6, fwd60 −1.6% / 33% |

**Honest null (printed):** naive joint *state* conditioning (US momentum-on AND HK
momentum-on as standing states) does NOT predict HSI fwd20 (post-2015: WR 48% both-on vs
54% both-off; mean-reversion dominates states). The confluence construct is valid only at
**turn events from depth** — this null is why IHM-R4 is event-based, not state-based.

### 2.4 "Global washout turn" tag lands on the right dates

HK deep cross + SPX deep cross (≤−4) within the prior 10 sessions, last instances:
2018-02-22, 2019-06-06, 2019-08-19, 2020-02-11, **2020-03-24**, 2020-10-05, 2021-03-18,
**2022-10-05**, **2023-03-17**, **2025-04-17**, **2026-07-03** (current event qualifies).
n=50 full-history; medians do not beat HK-alone deep crosses (fwd20 +0.7%/63% vs
+1.1%/59%) — the tag's value is **context** (macro-washout identification), not excess
return. Ships as a chip, never a score.

### 2.5 The 2026 cross-market episode (operator's "liquidity suck") is real

| Window | Mag7eq | SOXX | SPX | HSI | KOSPI | TWII |
|---|---|---|---|---|---|---|
| 2026 YTD (→07-10) | +5.4% | **+85.5%** | +10.5% | **−8.2%** | +73.5% | +54.5% |
| 05-01 → 06-27 | **−6.7%** | +26.7% | +1.7% | **−13.1%** | +21.3% | +9.5% |
| 06-27 → 07-10 (the turn) | **+6.6%** | −5.4% | +1.8% | **+5.0%** | −10.9% | +0.8% |

The current HK rally co-moves with **Mag 7** (which itself washed out to −10.98 on the
hybrid in June and turned), while SOXX/KOSPI roll over — a rotation signature, not broad
global risk-on. A roster-wide "breadth of turn" count (IHM-R4c) makes this readable at a
glance. As of 07-10: HSI +2.41 hist / Mag7 +2.03 / QQQ fresh cross / SPX above signal;
SOXX −0.60 / KOSPI −1.19 (2nd pctile depth) / TWII −0.77.

## 3. Census of record (what computes what today)

- The TH_RSIMACD+ hybrid **already exists, Pine-faithful, frozen 14/14/60/5**:
  `engine/canon.py:405` (canonical), used by `coiled.py`, `confluence_tiers.py`,
  `signal_quality.py`, `postcross.py`, `donor.py`, and Oracle P8 via
  `research/signal_engine/confluence.py`. The production per-stock buy gate (T1
  "MACD-2D × StochRSI-3D") is 2B RSI-MACD × 3B StochRSI. StochRSI (not pure stoch, not
  pure RSI) is likewise already house-wide. **The operator's requested construction is
  the house per-stock standard.**
- **Still pure price MACD(12,26,9)**: (a) the index/regime tape — `cycles.py:197`
  `macd_parts` + K-only `stoch_rsi` + RSI(14), consumed by `market_state.py:110`
  `_tf_sign` (+1 iff macd_pos AND rsi≥50) at D/3D/W/M (weights .15/.15/.40/.30) for
  SPY/QQQ/IWM, CN (000001.SS/510300.SS/399001.SZ), HK (**^HSI**/^HSCE/3033.HK) — the
  trend leg is 0.24 of the headline market state; (b) `mtf_upturn.py` daily/W/2W legs
  (3B leg is already hybrid via signal_quality); (c) `htf_durability`/`htf_oscillators`
  2W MACD; (d) `btc_signals`.
- **Risk Radar / Ignition Radar have no index-momentum inputs at all** (by design:
  credit/vol/breadth/positioning; `market_confirmed` = C1–C7 FROZEN,
  `risk_radar_market_catalysts.py:1407`; C9–C12 display-only).
- No 2B grid exists at the index layer (per-stock T2 uses 2B; `cycles.mtf_snapshot` is
  D/3D/W/M). No depth/velocity/cross-quality fields exist anywhere.
- Impl hygiene flags (recorded, not fixed here): `engine/technicals.rsi` is
  ewm-adjust=True (non-Pine); `oracle/ratio_lens.py` carries a third inline StochRSI;
  `cycles.stoch_rsi` is K-only. IHM computes exclusively via `engine.canon`.
- Data: all roster index histories are git-tracked parquet (`data/hk/_HSI.parquet`
  1986→, `_HSCE` 1993→, `data/intl/_KS11` 1996→, `_TWII` 1997→, `data/yahoo/`
  SPY/QQQ/SOXX/SMH/EWY/EWT, `data/baskets/ohlcv/` Mag7 members 2014→).

## 4. Boundary map (consume, don't duplicate)

| Neighbor | Owns | IHM relation |
|---|---|---|
| Turn-Sensitivity (TSU, `mtf_upturn.v1`) | per-stock/basket multi-TF turn legs | UNTOUCHED. IHM is index-grain only. Findings handed to TSU as a proposed pre-registered leg-comparison U-item (IHM-R7) |
| Mag7 Command (M7C, ACTIVE) | Mag-7 cohort regime organ, cap-weighted composite (M7C-R2), fragmentation | IHM consumes the `mag7_regime.v1` composite once merged; until then an equal-weight member-close carrier series from `data/baskets/ohlcv` (indicator carrier only, NOT a second regime organ) |
| hk_global / hk_global_beta | US→HK slope-z composite (SPY one of 7 factors), per-stock SPY-beta | Complementary: hk_global reads standing risk LEVELS; IHM-R4 reads TURN EVENTS from depth. No shared fields |
| Ratio Lens | tech/AI pairwise ratios (mag7/ai_semis etc.) | No cross-country pairs in either program; no collision |
| Ignition/RRX (frozen) | K-of-8 breadth ignition, C9–C12 context chips | IHM adds NOTHING to K. Any ignition-adjacent surface is a separate display-only context chip in the C9–C12 idiom (IHM-R5) |
| Oracle P8 | sector weekly StochRSI washout gauntlet compound | Untouched; IHM index events are a different grain, display-tier |
| W-ARM (US_STOCKS_UPGRADE, adjudicated NOT PROMOTED) | weekly RSI-MACD per-stock arm trigger | Not re-litigated: IHM makes no per-stock authority claim (IHM-R9) |

## 5. Rulings

- **IHM-R1 (organ).** New `engine/index_momentum.py` → `index_momentum.v1`, display-tier.
  Roster v1: US SPY, QQQ, IWM, SOXX, MAG7 carrier; HK ^HSI, ^HSCE, HSTECH(3033.HK);
  CN 000001.SS, 510300.SS, 399001.SZ; INTL ^KS11, ^TWII. Grids: **1D, 2B, 3B, W-FRI**
  (house resample conventions; completed bars only). Per index×grid, all via
  `engine.canon`: rsi_macd {macd, signal, hist}, stochrsi {k, d}, and derived fields:
  `hist_vel3` (hist − hist[3]), `depth_pctile` (macd vs trailing 10y), cross events
  (both directions) with `depth_at_cross` + quality tag. Artifact
  `data/index_momentum/latest.json` + history parquet; synapse-registered.
- **IHM-R2 (depth-context law).** Any surfaced cross carries depth context. Frozen v1
  classification: `washout_turn` = cross with depth_at_cross ≤ 10th pctile (≈ raw ≤−8 on
  HSI); `trap_zone` = depth in the (−6,−4] band (≈ 25th–45th pctile); else `ordinary`.
  Percentile is primary (bounded-but-regime-varying; absolute-anchor caution per the
  R-SP21 precedent); raw value always shown alongside for TV parity.
- **IHM-R3 (velocity).** `fast_reclaim_from_depth` display flag: depth ≤ p10 within the
  last 10 bars AND hist_vel3 ≥ +0.9 (the HSI 06-30→07-03 signature, calibrated
  descriptively in W1 and frozen before any surface ships). Early-detection is a display
  claim only until the ledger says otherwise.
- **IHM-R4 (global turn confluence, event-based).** Three tags, display-only:
  (a) `us_confirm` on any HK/CN washout_turn (SPX hybrid hist rising 3-sessions or
  macd>signal); (b) `global_washout_turn` (HK washout_turn + SPX deep cross ≤−4 within
  prior 10 sessions); (c) `turn_breadth` = roster count with hist>0 incl. fresh-cross
  markers — the broad-risk-on vs single-market-rotation read. The §2.3 state-conditioning
  null is binding: no standing-state confluence scores, ever.
- **IHM-R5 (authority fence).** index_momentum.v1 feeds NO K-count, NO scare leg, NO
  market_state component, NO allocation/rank/gate/size. Ignition `market_confirmed`
  C1–C7 semantics untouched. Any future authority claim goes through IHM-R12 preregs.
- **IHM-R6 (market_state shadow).** W3 computes a parallel hybrid trend sign per
  index×TF — `+1 iff rsi_macd.macd > signal AND stochrsi_k ≥ stochrsi_d` (frozen v1
  shadow definition) — next to the production `_tf_sign`, and appends
  {date, index, tf, prod_sign, shadow_sign, divergence} nightly to
  `data/index_momentum/trend_shadow.parquet`. Production behavior unchanged. Promotion
  to replace the trend leg requires the IHM-R12a study + operator ratification.
- **IHM-R7 (TSU handoff).** mtf_upturn legs unchanged. IHM registers a proposed TSU
  U-item: pre-registered comparison of the daily price-MACD leg vs a daily RSI-MACD leg
  on the existing per-stock forward ledger (same events grammar, same ruler). TSU owns
  scheduling; kill/adopt is theirs.
- **IHM-R8 (canonical impl).** All IHM math via `engine.canon` (SMA-seeded Pine-faithful
  RSI). The technicals/ratio_lens/cycles impl divergences are recorded as tech-debt
  flags, out of scope here.
- **IHM-R9 (no re-litigation).** W-ARM (weekly RSI-MACD per-stock arm) adjudication
  stands. Election/midterm seasonality stays a US-only Risk-Radar modulator per its
  ruling; IHM ships no seasonal signal — the operator's "summer of george / pre-midterm
  pressure" framing lives in narrative surfaces only.
- **IHM-R10 (surfaces are mockups-first).** W2 builds NOTHING until mockups are ratified
  (terminal-UI quality bar). Glance tier per docs/DESIGN_DOCTRINE.md: stance words
  ("Turning up from washed-out levels — watch, don't chase"), indicator mechanics demoted
  to data-tip-en/zh; no `title=` bilingual text; state names from the sanctioned
  vocabulary. Candidate homes: macro Market-State island tray row; HK tape strip; a
  Mag7×HSI confluence chip near the recovery panel (C9–C12 idiom).
- **IHM-R11 (self-grading).** Every surfaced washout_turn / global_washout_turn accrues
  to a forward ledger (fwd20/fwd60 absolute + vs SPY, index grain), expected-NULL
  framing, printed on the eventual surface (audit idiom of ignition_audit).
- **IHM-R12 (promotion preregs — the only paths to authority).**
  (a) trend-leg swap: shadow vs production sign divergence days, scored on subsequent
  index fwd returns at the D/3D/W/M ruler weights; episode-aware inference (DT-R14);
  operator ratifies any swap. (b) depth-gated cross quality (HSI + SPX + KOSPI panels):
  washout_turn vs trap_zone forward separation with episode-label permutation.
  (c) us_confirm durability at the 60d ruler (horizon_role pre-declared — §2.3 shows the
  effect lives at 60d, not 20d). None of these run before 2026-08.
- **IHM-R13 (naming).** User-facing: "Momentum (hybrid)" / 「动能（混合）」 only in
  Tier-2; Tier-1 never says MACD/RSI. Internal: `index_momentum.v1`. The word
  "validated" is not used anywhere.
- **IHM-R14 (render budget).** Whole organ is ≤13 series × 4 grids of vector math on
  in-repo parquet — target <5s wall; runs inside the existing US engine lane after
  store freshness gates; no new collectors (all inputs already collected).

## 6. Waves

| Wave | Scope | PR lane |
|---|---|---|
| W0 | this masterplan | docs (this PR) |
| W1 | `engine/index_momentum.py` + artifact + tests + nightly wiring (display-dark: artifact only, no UI) | builder, DRAFT until Fable review |
| W2 | surfaces — mockups first (IHM-R10), then macro/HK/us_stocks chips + tray rows | after mockup ratification |
| W3 | market_state trend shadow ledger (IHM-R6) | small engine PR |
| W4 | TSU handoff note + ledger first-read | docs |

## 7. Clocks

- 2026-07-25: first ledger read (W1 artifact accruing ≥10 sessions; verify the 07-03 HSI
  event graded correctly).
- 2026-08-15: shadow-ledger first divergence review; decide whether IHM-R12a prereg is
  worth registering.
- 2026-10-15: program review — promote, extend, or park.

## 8. Kill-registry appends

None. Nothing here kills a topic; the §2.3 state-conditioning null is recorded in this
doc (binding on IHM-R4 construction) but is a construction choice, not a family kill.
