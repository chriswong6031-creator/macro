# Cross-Asset Confirmation — using bonds & FX to CONFIRM (not front-run) the equity regime

**Status:** SHIPPED (this session). Display-first, validate-before-scoring.
**Goal:** Stop wasting the forex & bond dashboards. They sit at the *fast* end of the macro
complex — but mostly **coincident, not leading** (see §2); only credit/EBP and the curve have a
defensible, noisy leading horizon. Their signal vectors were orphaned — read by nothing in the
quant engine and (for bonds) not even by the AI master brain. This layer wires them in as a
**confirmation + fragility-watch** lens on the equity/macro regime (NOT a crash predictor).

---

## 1 · The one-line problem

The repo already builds two rich, calibrated signal vectors:

- `data/bonds/bond_health.json` — curve taxonomy + NTFS, credit distress ladder (HY/IG/EBP),
  MOVE bands + `move_leads_vix`, un-inversion alarms, a credit×curve **cycle_phase**, sovereign
  fragmentation, and a **`drivers_for`** hand-off (`credit_canary`, `risk_off_gate`) built
  *explicitly* "for the cross-asset master brain."
- `data/forex/latest.json` — a dollar-first **regime** ("US growth premium" / risk-on/off),
  `favored` currencies, and per-pair conviction (EM carry pairs = USD/MXN, USD/BRL; the China
  proxy USD/CNH).

**Neither feeds the deterministic engine or (for bonds) the AI brain.** Forex contributes a
single `dxy` 20-day-momentum leg to the display-only RORO composite; the bonds engine's leading
reads are absent. `engine/conditions.py` recomputes a *crude* bond read inline from raw FRED
(`curve_tp_adj`, `hy_oas`) and never touches `^MOVE` (which is loaded into the feature frame and
then ignored by the macro engine — see `engine/inputs.py`).

## 2 · Why bonds & FX are worth the wiring (the thesis — honestly graded)

Bonds and FX **price the discount rate, default risk, and the global dollar**, so they belong to
the *fast* end of the macro complex. But the literature (cited below) is blunt about how much of
this is genuinely *leading* vs merely *coincident* — and I graded every chain so the page does
not overclaim. The verdicts (STRONG / MODERATE / WEAK-or-COINCIDENT) drive the framing: this is a
**cross-asset confirmation + fragility-watch**, NOT a "bonds predict the equity crash" tool.

- **Credit → equities/economy — MODERATE (genuine but noisy lead).** The Excess Bond Premium
  (Gilchrist-Zakrajšek 2012) — the risk-appetite residual of credit spreads — carries ~all of
  credit's recession-forecast power; the Fed runs it as a **12-month-ahead** recession-prob model.
  Real-world it often moves *with* equity stress, so it's a same-family confirmation more than a
  clean independent forecaster.
- **Curve / NTFS → recession — MODERATE-to-STRONG.** The near-term forward spread (Engstrom-Sharpe
  2018) statistically *dominates* 2s10s for recession prediction (~12mo horizon). The
  **un-inversion** is often the truer real-time alarm than the inversion itself — but the popular
  "dis-inversion leads by ~66 days" day-count is **unsourced practitioner folklore** and is NOT
  asserted anywhere here.
- **Rates-vol vs equity-vol (MOVE vs VIX) — WEAK / mostly folklore.** The cleanest lead-lag test
  (CFA Institute, 20y daily, Granger) finds **VIX leads MOVE, not the reverse** — except when both
  are already above their ~75th pctile (acute stress). So `move_leads_vix` is framed as a
  *coincident stress configuration*, predictive only in an already-stressed regime — never "bonds
  warn equities first."
- **Dollar / EM-FX vs risk-off — WEAK-as-leading / STRONG-as-coincident.** BIS work
  (Avdjiev-Bruno-Koch-Shin; Hofmann-Shim-Shin) makes the dollar a powerful *global risk factor*,
  but via **endogenous co-movement** — the dollar move *is* the tightening (risk-taking channel).
  Contemporaneous, not a forecaster. The "dollar smile" is a descriptive heuristic, not an
  empirical lead-lag result.
- **FX carry crash — MODERATE (coincident-to-slightly-leading, a fragility gauge).**
  Brunnermeier-Nagel-Pedersen: carry returns are negatively skewed and crash when funding
  liquidity dries up — a stress *amplifier* that mostly coincides with the risk-off.
- **Stock-bond correlation regime — STRONG but descriptive.** AQR: the regime sign is set by
  inflation-news vol *relative to* growth-news vol (R²≈71%), not the inflation level. A slow,
  persistent *regime classifier*, not a timing lead. Live it reads "breakdown" (+0.67) — bonds are
  NOT hedging equities, a risk-budgeting fact worth stating.

> **Honest prior:** only credit/EBP and the NTFS have a defensible (and noisy) *leading* horizon;
> MOVE-vs-VIX, dollar/EM-FX and carry are **coincident confirmation / fragility gauges**, and the
> stock-bond corr is a regime descriptor. So this layer ships **DISPLAY-ONLY** and only promotes a
> leg to a *scored* gate if Phase-0 proves *incremental* forward edge — which, given how much of
> this is coincident, I expect to fail for most legs (and the page will say so).

### 2a · Literature (primary sources, for the honesty box)

1. Credit/EBP — Gilchrist & Zakrajšek, *AER* 102(4) 2012 (NBER w17021); Fed FEDS Note "Updating the
   Recession Risk and the Excess Bond Premium" (2016). **MODERATE leading.**
2. NTFS — Engstrom & Sharpe, FEDS 2018-055 / "(Don't Fear) The Yield Curve" (2018). **MODERATE-STRONG;**
   the 66-day dis-inversion stat is **unverified folklore.**
3. MOVE vs VIX — CFA Institute "Volatility Signals: Do Equities Forecast Bonds?" (Granger, 20y):
   **VIX→MOVE, not the reverse (ex-acute-stress). WEAK.**
4. Dollar as global risk factor — BIS WP 695 / 775 / 1031 (Avdjiev/Bruno/Koch/Shin; Hofmann/Shim/Shin).
   **Coincident (endogenous co-movement), not leading.**
5. Carry crashes — Brunnermeier, Nagel & Pedersen, *NBER Macro Annual 2008* (w14473). **MODERATE, fragility gauge.**
6. Stock-bond corr — AQR "A Changing Stock-Bond Correlation" (inflation-vs-growth news vol; R²≈71%).
   **STRONG but descriptive, not a timing lead.**

## 3 · What is genuinely independent (a critical correction)

`bond_health.json` reuses `engine.conditions`, so its `recession_risk`, `drawdown_risk`, and
`stock_bond_corr` are **byte-identical to the equity-side `conditions` values**. Comparing those
would be a tautology (always "agree"). The genuinely *independent* bond signals are:

- **cycle_phase** (curve×credit clock: recession/early/mid/late) — computed differently from the
  equity `cycle_tag` (curve+OAS+breadth). *Live divergence: bonds "late" vs equity "mid".*
- curve **move_taxonomy** + **NTFS**, credit **distress_band** + direction, **MOVE band** +
  **move_leads_vix**, **uninversion_alarm** / **bull_steepener_uninversion**, **repo_stress**,
  sovereign **euro_frag** / **jgb** state, and the `drivers_for` gates.

And from FX: the **regime** label, **risk** (on/off), **favored**, and the **EM-stress** read
(USD/MXN + USD/BRL conviction) + the **CNH** China-proxy.

So the confirmation engine compares the **leading, independent** bond/FX reads to the equity
regime — never the shared recession/drawdown numbers.

## 4 · The engine (`engine/cross_asset_confirm.py`)

A display-only **leaf**, mirroring `engine/signal_stack.py` (pure-ish, bilingual, graceful,
never raises, **feeds nothing scored**). `snapshot(latest, root=None) -> dict`:

1. **Cycle / regime agreement.** Map the equity quad+cycle_tag and the bond cycle_phase to a
   shared late↔early axis; flag agreement vs divergence (e.g. bonds "late" + equity "mid" →
   "bonds see late-cycle first").
2. **Risk-appetite agreement.** Combine FX `risk` + bond credit `direction` + MOVE band into a
   leading risk read; compare to the equity `roro_state` / `drawdown_risk.band`. Confirm vs diverge.
3. **Leading divergence / early-warning (the payload).** A list of leading tells firing **while
   the equity gauges are still calm** — `credit_canary` (HY widening from tight), `move_leads_vix`,
   `uninversion_alarm`, EM-FX stress, dollar-regime shift, `euro_frag` widening, `repo_stress`.
   Each is a binary/graded flag with a plain-English meaning + the asset that owns it.

Output contract → `latest["cross_asset_confirm"]`:

```jsonc
{
  "verdict": "confirm | diverge | mixed | unknown",
  "headline_en": "...", "headline_zh": "...",
  "confidence": "low|medium|high",       // = breadth of agreement, NOT a forecast
  "agree_pct": 0,                         // share of leading legs confirming the equity read
  "legs": [ {key,label_en,label_zh,equity_en,leading_en,dir,tone,tier} ],
  "early_warning": [ {key,en,zh,severity,owner} ],   // leading tells the equity gauges miss
  "cycle": {"equity":"mid","bonds":"late","fx":"...","note_en":"..."},
  "to_brain": { ...compact summary the master brain ingests... },
  "note_en": "Display-only cross-asset confirmation; never scored. ..."
}
```

## 5 · Integration points

- **`engine/run.py`** — attach `latest["cross_asset_confirm"] = snapshot(latest)` after
  `turning_point` (additive try/except, never fatal). It needs `latest` because it compares
  against the equity regime already computed there.
- **`engine/master_brain.py`** — add a **bonds backdrop** (`_bonds_backdrop()` reading the
  bond-specific cycle/pillar states, alarms, `drivers_for` — NOT the duplicated recession/drawdown
  numbers) + the `cross_asset_confirm` read to the macro lens, and a slim bonds backdrop to the
  china/btc lenses; enrich the forex summary. Update the macro system prompt to name bonds as the
  leading layer. Context-only — the brain feeds nothing scored.
- **`templates/dashboard.html.j2`** (mode="macro") — a bilingual "Cross-Asset Confirmation"
  panel after signal-stack, reading `latest.cross_asset_confirm`. Honest "leading markets,
  display-only" framing.
- **`config.yml` `cross_asset_confirm:`** — thresholds (MOVE/credit bands, EM-stress score cut),
  with in-code fallbacks so a missing block never breaks the run.

## 6 · Validation plan (Phase-0) — the gate before anything is scored

`scripts/cross_asset_confirm_phase0.py`. The question: **do the leading bond/FX divergence configs
have INCREMENTAL forward edge on equity outcomes, beyond what `drawdown_risk` already captures?**

- Reconstruct each leading flag **causally** over history (no look-ahead — same lag discipline as
  `conditions.py`; FRED/Yahoo as-of).
- Outcome = forward SPY drawdown (63d) and forward regime transition; the "divergence config" =
  equity `drawdown_risk` low/RORO risk-on **while** ≥2 leading tells fire.
- Measure: hit-rate / mean forward drawdown of the divergence config vs base rate; **incremental**
  IC and a logit with `drawdown_risk` already in (does the cross-asset flag add anything?).
- Split-half (split 2013, the bonds-calibration boundary) + a forward-window embargo around the
  split; CONFIRMED requires **both** halves meaningful, not just sign-stable (the bonds-calibration
  bar). Analysis is restricted to the window where the credit/rates-vol inputs exist. Multiple
  `ci_excludes_base` tests are run, so a single marginal pass is treated as weak (no formal FDR
  applied — stated honestly rather than over-corrected on a display-only leaf).
- **Decision rule:** robust incremental edge → promote that one leg to a *validated* gate
  (candidate: add `^MOVE` to the RORO composite, or a bond-FX early-warning gate into
  `drawdown_risk`). No robust edge (the likely outcome — the bonds composite already ≈ the
  drawdown_risk leg alone) → stays DISPLAY-ONLY and the page says so. Write
  `reports/cross-asset-confirm-phase0.md`.

## 6a · Phase-0 result (RAN — verdict: DISPLAY-ONLY, confirmed)

`scripts/cross_asset_confirm_phase0.py`, split 2013, forward-63d S&P drawdown target:

- `lead_caution` (0–3 bond leading flags) standalone IC = **0.107 full / 0.175 pre / 0.021 post**
  → DIRECTIONAL (worked pre-2013, faded after — the classic over-fit tell).
- **Decisive test** — incremental partial IC of `lead_caution` vs forward-dd *controlling for the
  existing `drawdown_risk` gauge*: **0.053 full / 0.11 pre / −0.003 post**. After the gauge we
  already have, the cross-asset caution adds ~**nothing** in the modern half.
- Divergence-within-calm-equity-days lift **+2.9pp** (P(dd10) 0.096 vs base 0.067) but the
  block-bootstrap CI lower bound (0.037) is **below** base → not robust (`ci_excludes_base=False`).
- Cycle divergence (bonds later-cycle than equities): **−4.1pp** — does NOT predict more drawdown.

**Decision: DISPLAY-ONLY (confirmed). Nothing is wired into the score.** This matches the
literature (§2 — these reads are largely coincident) and the existing bonds calibration (the bond
composite ≈ the `drawdown_risk` leg alone). The confirmation panel is a context / early-attention
read and a richer input to the AI synthesis brain — never a scored gate. Report:
`reports/cross-asset-confirm-phase0.md`.

## 7 · Honesty bar

These are **leading-but-noisy, regime-dependent, often coincident** reads. The panel is a
confirmation/early-warning *context*, not a trade signal or measured alpha — sample sizes on
macro turns are small and FX/credit history is crash-dominated. The layer ships before any
scored wiring, deliberately, to validate the architecture on real data first — and says so.
