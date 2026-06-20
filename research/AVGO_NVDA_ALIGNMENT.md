# Cross-system alignment — AVGO & NVDA (dashboard ↔ Mastermind)

*Trigger:* the macro **single-stock dashboard** and the **Mastermind "Opus Brain" portfolio bot**
gave starkly inverted reads on two Mag-7 semis, so neither system's user could tell which was right:

| | dashboard (single-stock) | Mastermind (portfolio) | Mastermind research |
|---|---|---|---|
| **NVDA** | **97** score, but verdict "Constructive — building a base" | **REJECTED** ("distribution / expensive divergence") | "add" (PEG ~0.25 contradicts the engine) |
| **AVGO** | **50** "Neutral — no clear edge" | **BUY** (confluence +0.33, sized 5%) | **67/100** |

## Ground truth (objective research)
An independent fundamentals/technicals sweep put **both names at ~62/100, verdict "buy"**:
* **NVDA** ~22× forward on consensus (PEG ~0.47 — the 16.6×/0.27 thesis was overstated but the
  direction is right), 81% rev growth, clean Strong-Buy consensus (+42% to target), base-building
  *not* genuine distribution. The dashboard's high rank is fair; the Mastermind reject is wrong.
* **AVGO** fair-to-modestly-cheap on FY27 non-GAAP (~23×), exceptional AI growth, but real risks
  (Google concentration, VMware leverage, the June crash). The dashboard's 50 is too low; Mastermind's
  67 is about right.

So **both systems had a defect, in opposite directions**: the dashboard under-scored AVGO and
mis-presented NVDA's 97; the Mastermind engine false-rejected NVDA.

## Root causes (traced in code)

### Dashboard (`engine/stock_score.py`)
1. **Quality axis blended cheapness + volatility.** The fallback averaged `value` and `low_vol`
   into the "durability" axis — so an expensive, volatile growth leader was penalised on *quality*
   for being correctly expensive/volatile (AVGO quality z −0.70). The docstring says the axis is
   DURABILITY; the code contradicted it.
2. **A collapsed SUE leg cancelled a strong revision.** SUE's cross-sectional edge collapsed on
   deep PIT history (the engine's own `reports/sue-deep-history-phase0.md`), yet at 0.30 weight a
   slightly-negative SUE rank dragged AVGO's selection from a strong revision (+1.14) down to 0.24.
3. **Anticipation was never scored.** The forward cone (AVGO: ~+11% median upside vs ~−7% average
   drawdown — the user's "high upside / low downside") is computed but never reaches the conviction
   score — a visible contradiction (favourable cone, "Neutral 50").
4. **Score vs verdict were decoupled.** The 0-100 score is a within-board *percentile*; the verdict
   is an absolute z-tier. NVDA ranked 97th-pct (composite 0.58) but its selection z (0.84) hadn't
   cleared the absolute "high" bar, so the verb read "Constructive" — "97" was misread as absolute.

### Mastermind (`portfolio/lenses.py`)
5. **Valuation lens was PEG-blind.** Direction came from the raw value-factor z (P/B, P/S, EY),
   which structurally flags every hyper-growth leader "expensive" (NVDA value_z −1.05 from ~32× P/B);
   `forward_pe` was fetched but never read. This (a) subtracted a bull and (b) armed the "distribution"
   divergence (`lead=bull + valuation=bear + flows_13f=bear`).
6. **13F flow lens had no min-sample gate.** A 1-name margin across ~4 curated VIP funds fired "bear"
   (NVDA: 1 buying vs 2 selling; TigerGlobal's +9.1% add was tagged "hold", uncounted) — noise for a
   mega-cap with thousands of holders.
   * Net: NVDA confluence = (6 bull − 5 bear)/11 = **0.091 < 0.30 gate → rejected**. And a *high*
     dashboard score was perversely the trigger that armed the distribution check (`lead=bull`).

## Fixes

### Dashboard
* **Quality = durability only** — drop `value` + `low_vol` from the quality fallback.
* **Reweight the EDGE** — SUE 0.30→0.18, analyst revisions 0.20→0.32 (SUE collapsed; revisions are
  literature-strong), so a strong revision is no longer cancelled by a thin negative SUE.
* **Anticipation risk-shape tilt** — a small bounded entry tilt from the cone's upside/downside
  *asymmetry* (never its direction — p_up is ~a coin-flip), mirroring the Mastermind `asymmetry` lens.
* **Honesty notes** — a "score is a percentile rank" note when band=high but the verdict isn't
  high-conviction, and a "favourable risk cone" note when the cone is good but the score is muted.

### Mastermind
* **Growth-adjusted valuation** — `_valuation_dir` consults PEG (forward P/E vs revenue CAGR); a
  cheap-for-growth leader (low PEG) is no longer "bear".
* **13F min-sample/margin gate** — `_flows_13f_dir` requires a ≥2 net margin to fire a direction.

## Verified result (rebuild + decision re-run)
* Dashboard **AVGO 50 → 65** (band neutral → constructive; selection 0.24 → 0.49; favourable-cone
  note fires). Dashboard **NVDA** verdict "Constructive — building a base" → **"Leader · accounting
  watch — confirm before adding"** (selection 0.84 → 1.27 cleared the high bar → score/verdict now
  coherent).
* Mastermind **NVDA confluence 0.091 → 0.400, `size_authority` hold → up → now SIZED** (distribution
  divergence gone); **AVGO** unchanged (0.50, still bought).

Both systems now land near the ~62 ground truth and agree: **AVGO and NVDA are both buys.** No new
validated alpha is claimed — the dashboard changes are corrections + an honest risk-shape tilt; the
Mastermind changes remove two tight-factor false-negatives.

## Honest residuals (not "fixed", by design)
* AVGO's factor-quality is genuinely weak (VMware debt/goodwill, expensive, volatile) — the 65 comes
  from the corrected selection + the favourable cone, not from pretending the leverage away. A
  goodwill-adjusted GP/(tangible assets) profitability leg would sharpen it but needs a `goodwill`
  column the EDGAR cache doesn't yet carry (follow-up).
* NVDA's 98 is still a *percentile*; the new note makes that explicit rather than re-scaling every
  market's score to an absolute (a larger, separate change).
