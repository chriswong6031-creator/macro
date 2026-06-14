# US "Standout Individual Stocks" → alpha-aware setup score (China parity)

*Status: BUILT (this branch). Gap analysis → design → validation framing → what shipped.*

## 1. The question

> The China dashboard ranks per-stock **alpha sector rank + a setup score** to surface
> *Top setups* and *Alpha leaders*. Do we have that on the US side? How else can we
> improve the macro dashboard's *Standout Individual Stocks* section with data/models
> we already possess?

## 2. What we found (gap analysis)

| Capability | China A-share board | US macro "Standout" section (before) |
|---|---|---|
| Sector-neutral residual alpha engine | ✅ `engine/residual_alpha.py` | ✅ **same engine** → `site/factordata/alpha.json` (1500 names) |
| Per-stock **alpha sector rank** (`#k/n`) | ✅ shown on cards | ⚠️ computed in `alpha.json`, **not surfaced on standouts** |
| **Setup score** (alpha × cycle timing) | ✅ `build_china_library._setup_score` | ❌ **absent** — no `setups.json`, no score |
| "Top setups" board (confluence shortlist) | ✅ `china.html` | ❌ none |
| "Alpha leaders" board | ✅ `china.html` | ✅ but only on the **separate** `discovery.html` |
| Standout ranking input | alpha + timing | **pure cycle-timing `|eq_score|`** only |
| Sector diversity on the board | n/a | ❌ one hot sector could fill all 24 cards |

**Verdict:** the US had the *alpha engine* and a *separate* alpha leaderboard
(`discovery.html`), but the front-page **Standout Individual Stocks** section was a
pure price-cycle timing board that **ignored the residual alpha it already computes**.
China was actually *ahead* here — it fuses selection (alpha) × timing (cycle) into a
single setup score and surfaces both boards together. We port that to the US.

## 3. The key difference from China (why this is not a blind copy)

The blend weight on residual momentum **must differ by market** because the validated
microstructure differs:

- **US equities** — sector-neutral residual momentum is a **positive-IC *context* leg**:
  a robust cross-sectional leader (PIT de-biased IC ≈ .012) but **not** a standalone edge
  (de-contaminated L/S Sharpe ≤ 0, nothing clears FDR — `research/RESIDUAL_ALPHA_MOMENTUM.md` §4).
  So on the US side momentum **leads** the selection and the cycle is the entry/timing
  overlay → `US_ALPHA_WEIGHT = 0.7`.
- **A-shares** — ~35y deep history **kills** cross-sectional momentum; short-term
  **reversal** is the validated effect (`research/CHINA_HK_STOCK_SIGNALS.md`). So the
  residual is demoted to a light quality tiebreaker → `CN_ALPHA_WEIGHT = 0.35`, and the
  score leads with the cycle entry + mean-reversion (pullback) overlay.

The `pullback` / `extended` direction is the **same** in both markets (a leader on a
recent pullback is the constructive entry; a just-spiked one is reversal risk). Only the
residual's weight changes.

**Honest framing (carried onto the UI):** this is **not a new statistical edge**. Both
libraries *re-rank* an already-validated alpha cross-section by **when** (the calibrated
cycle-timing engine + the alpha engine's reversal overlay). The claim is **confluence** —
"a sector-neutral leader you'd also want to buy *today*" — not a fresh signal.

## 4. The setup score

```
setup = alpha_weight · alpha_z                      # selection (sector-neutral residual momentum)
      + URG[urgency]                                # cycle entry timing  (now/imminent +0.9, soon +0.45, exit/avoid −0.9)
      + EQDIR[eq_dir]                               # cycle direction     (up +0.35, down −0.35)
      + ENTRY[alpha_entry]                          # reversal overlay    (pullback +0.7, extended −0.7)
```

- **Top setups (buy):** `alpha_z ≥ 0.5` leaders, **ranked by `alpha` desc** (see §9 — the
  setup-blend ranking was tested and reverted), top 12.
- **Laggards:** `alpha_z ≤ −0.3`, ranked by `alpha` asc, top 6.

Shared, parameterized implementation: `engine/setups.py` (`setup_score`, `timing_tilt`,
`rank_setups`). China's old inline `_setup_score` is refactored onto it with a **parity
test** (`alpha_weight=0.35` reproduces the prior output exactly).

## 5. What shipped

1. **`engine/setups.py`** — shared setup-score + ranking, US-vs-China weight documented; unit-tested (`tests/test_setups.py`), China parity asserted.
2. **`scripts/build_stock_library.py`** — computes the US setup score per name (alpha already attached), writes **`site/factordata/setups.json`** (`buy` + `laggards`), adds `a` (alpha-z) to `index.json` for client-side ranking. Mirrors `build_china_library`.
3. **`scripts/build_china_library.py`** — refactored onto `engine/setups.py` (behavior identical).
4. **`scripts/build_site.py`** — the macro **Standout** section now:
   - attaches per-name **alpha** (z, sector rank `#k/n`, reversal overlay) to each standout (fresh, inline — alpha already in scope via `build_sector_pages(alpha=…)`);
   - computes a **setup score** per card and **re-ranks within each urgency tier** by it (alpha-aware), falling back to timing-only when a name has no residual;
   - applies a **soft per-sector cap** (≤5) so one hot sector can't crowd the board;
   - loads `setups.json` and passes a broad **Top setups** board to the template (graceful if absent; one-build lag since `build_library` runs at the end of `build_site`).
5. **`templates/dashboard.html.j2`** — standout cards gain an **alpha line** (`α +0.82 · #3/40 · pullback`); a new **"Top setups (S&P 1500)"** board fuses selection × timing across the full universe; a **"Alpha leaders →"** link to `discovery.html`. i18n + CSS added.

## 6. Validation / rigor

- No new statistical claim: the score is a deterministic blend of two **already-validated**
  legs (residual alpha = context leg; cycle ladder = calibrated timing). Framed as
  confluence on the UI, mirroring China's caveat.
- `engine/setups.py` is pure/deterministic and unit-tested; China parity locked by test.
- PIT/survivorship are handled **upstream** (the alpha engine is causal/lagged; the cycle
  engine is point-in-time). The setup score adds no look-ahead.

## 7. Confluence confirmers (BUILT — second pass)

Three confirmer/context legs layered on top of the setup score (the score itself stays a
clean, interpretable alpha×timing — confirmers never enter it):

1. **Insider Form-4 buy-cluster chip** — `engine.equity_factors.insider_signals` returns
   per-ticker net open-market buying as **bps of market cap** (the validated `net_mcap_bps`
   construction — Phase-0 PIT FDR survivor in the mid-cap habitat; see
   `research/INSIDER_FACTOR.md` / [[insider-factor-phase0]]) plus the **distinct-insider
   CLUSTER count**. `build_insider_data` writes `site/factordata/insider_signals.json`; the
   chip (👤 N) fires when **≥2 distinct insiders net-bought** (a genuine cluster). It
   naturally lights up on the mid-cap setups (INDV 👤6, CASY 👤2) and stays dark on the
   megacap holdings — exactly its validated habitat. Labeled a *confirmer* (orthogonal
   long-only conviction), **not** a standalone sizer.
2. **Factor composite tiebreaker** — `factors.json .table[].composite` (value/quality/
   low-vol …) attached as `factor_z` and used as a **light secondary sort key** in both
   `action_board` and `rank_setups`: it settles near-ties, never overrides the validated
   setup (factors are crowded / post-publication-decayed). Shown as a `factor` column on
   the Top setups board so it's visible even when it doesn't move the order.
3. **Dual-class dedup** — `engine.setups.dedupe_dual_class` collapses GOOG+GOOGL,
   BRK-A/B, … to the best-ranked variant by normalised company name (share-class tokens
   stripped, corporate suffixes kept to avoid collapsing distinct firms). Applied in
   `action_board` and `rank_setups`; frees a board slot for a genuinely different name.

## 9. Phase-0 validation → the ranking was REVERTED to α (honest negative result)

`scripts/setup_score_phase0.py` → `reports/setup-score-phase0.md`. Point-in-time on the
**survivorship-clean deep S&P-500 panel** (PIT membership + folded-in delisted names),
production residual-alpha windows (252/252/21, shrink 0.66), **141 monthly rebalances
2014–2026, ~448 names/date**, cycle leg computed causally (`analyze(close[:d])`, cached).
Four signals, rank-IC + quintile L/S + DSR, at 21d & 63d:

| signal | 21d mean IC | 63d mean IC |
|---|--:|--:|
| **alpha** (baseline) | **+0.0101** | **+0.0231** |
| alpha + reversal overlay | +0.0093 | +0.0227 |
| timing only (no α) | −0.0046 | −0.0058 |
| setup (shipped blend) | −0.0013 | +0.0107 |

**Verdict: NEUTRAL / cosmetic.** The cycle-timing/reversal blend does **not** improve
forward-return ranking — it **dilutes** α (halves the IC at 63d, erases it at 21d), and
timing-only IC is negative (the cycle leg is **risk placement, not return prediction** —
exactly what its own calibration says). So:

- **The board now ranks by `alpha`** (`rank_setups(rank_by="alpha")`; macro cards order
  within their cycle tier by `alpha_z`). The cycle/pullback timing and the `setup` column
  are kept as **displayed risk-placement context** (when to enter), not ranking drivers.
- **UI copy softened** to "grouped by cycle entry, ranked by sector-neutral momentum (α)"
  / "α leaders at a constructive entry", with the validation finding stated in the help.
- **China is unchanged** — `rank_by="setup"` (default) preserves its *separately validated*
  reversal-led construction (A-shares mean-revert; [[china-hk-stock-signals]]).

No edge is claimed that the evidence doesn't support. The board's value is the (validated,
context-leg) α selection + the (calibrated) cycle risk placement — surfaced together,
honestly labelled.

## 10. Recommended next (not built)

- **Per-equity GEX** (tiered) → vol-regime / pin context on the highest-conviction names.
- **Insider SELL caution** — deliberately omitted: insider selling is far noisier than
  buying (10b5-1 / diversification), so surfacing it would imply false precision.
