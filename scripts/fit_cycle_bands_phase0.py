"""W2.8 Phase-0: Fit DC/IC cycle bands from measured trough spacing.

Loads available price tapes for equity, crypto, and fx asset classes,
runs find_troughs() per tape, computes trough-to-trough spacings, then
derives DC/IC bands from median ± ½ IQR. Outputs
data/regime/cycle_bands_fit.json and prints a comparison vs the
hardcoded CYCLE_PRESETS constants.

Pure-read, never fatal — individual tape failures are logged and skipped.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# ── path bootstrap so script runs from the repo root ────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import find_troughs, CYCLE_PRESETS  # noqa: E402
from engine.inputs import yahoo_closes                   # noqa: E402
from lib import config                                   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("fit_cycle_bands")


# ── country ETFs from country_cycles (import guard — might not be available) ─
def _country_tickers() -> list[str]:
    try:
        from engine.country_cycles import COUNTRIES
        return list(COUNTRIES.keys())
    except Exception:
        return ["EWG", "EWJ", "EWZ", "FXI", "EWA", "EWH", "EWU", "EWQ",
                "EWL", "EWP", "EWI", "EWN", "EWD", "EWS", "EWC"]


# ── equity sector ETFs (hard-coded to match CYCLE_PRESETS "equity" class) ────
_SECTOR_ETFS = ["XLK", "XLC", "XLY", "XLF", "XLI", "XLB", "XLE", "XLV", "XLP", "XLU", "XLRE"]
_FX_TICKERS   = ["UUP", "FXE", "FXB", "FXY", "FXC", "FXF", "FXA", "DXY"]
_CRYPTO_TICKERS = ["BTC-USD"]


def _bday_spacing(troughs: list[pd.Timestamp], close: pd.Series) -> list[int]:
    """Trading-day counts between consecutive troughs."""
    idx = close.index
    spaces = []
    for i in range(1, len(troughs)):
        lo = troughs[i - 1]
        hi = troughs[i]
        if lo in idx and hi in idx:
            spaces.append(int(((idx >= lo) & (idx <= hi)).sum()) - 1)
    return [s for s in spaces if s > 0]


def _cal_spacing(troughs: list[pd.Timestamp]) -> list[int]:
    """Calendar-day counts between consecutive troughs (for 24/7 crypto)."""
    spaces = []
    for i in range(1, len(troughs)):
        spaces.append((troughs[i] - troughs[i - 1]).days)
    return [s for s in spaces if s > 0]


def _band_from_spacings(spaces: list[int]) -> tuple[int, int]:
    """DC band: [max(10, int(median - 0.5*IQR)), int(median + 0.5*IQR)]."""
    if not spaces:
        return (0, 0)
    arr = np.array(spaces, dtype=float)
    median = float(np.median(arr))
    q1, q3 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
    iqr = q3 - q1
    lo = max(10, int(median - 0.5 * iqr))
    hi = int(median + 0.5 * iqr)
    hi = max(lo + 1, hi)
    return (lo, hi)


def _ic_band_from_weekly(weekly_spaces: list[int]) -> tuple[int, int]:
    """IC band directly from weekly-trough spacing: [Q1, Q3]."""
    if not weekly_spaces:
        return (0, 0)
    arr = np.array(weekly_spaces, dtype=float)
    q1 = max(4, int(np.percentile(arr, 25)))
    q3 = int(np.percentile(arr, 75))
    q3 = max(q1 + 1, q3)
    return (q1, q3)


def _fit_asset_class(
    tickers: list[str],
    closes: pd.DataFrame,
    crypto: bool = False,
) -> dict:
    """Fit DC/IC bands for a collection of tickers."""
    all_dc_spaces: list[int] = []
    all_ic_spaces: list[int] = []
    n_series = 0
    skipped = []

    for tk in tickers:
        if tk not in closes:
            log.debug("fit: %s not in close panel — skipped", tk)
            skipped.append(tk)
            continue
        s = closes[tk].dropna()
        if len(s) < 260:
            log.debug("fit: %s too thin (%d) — skipped", tk, len(s))
            skipped.append(tk)
            continue

        # DC spacings on DAILY series
        try:
            troughs = find_troughs(s)
            if len(troughs) >= 2:
                if crypto:
                    spaces = _cal_spacing(troughs)
                else:
                    spaces = _bday_spacing(troughs, s)
                all_dc_spaces.extend(spaces)
        except Exception as e:
            log.warning("fit: %s daily troughs failed: %s", tk, e)

        # IC spacings on WEEKLY series
        try:
            if crypto:
                # crypto uses 3-calendar-day bars; for IC use weekly resampled
                w = s.resample("W-FRI").last().dropna()
            else:
                w = s.resample("W-FRI").last().dropna()
            wt = find_troughs(w, window=6, min_gap=8)
            if len(wt) >= 2:
                w_spaces = [int(((w.index >= wt[i-1]) & (w.index <= wt[i])).sum()) - 1
                            for i in range(1, len(wt))]
                w_spaces = [x for x in w_spaces if x > 0]
                all_ic_spaces.extend(w_spaces)
        except Exception as e:
            log.warning("fit: %s weekly IC troughs failed: %s", tk, e)

        n_series += 1

    dc_band = _band_from_spacings(all_dc_spaces)
    ic_band = _ic_band_from_weekly(all_ic_spaces)

    log.info("fit: %d series, %d DC spacings, %d IC spacings | DC %s IC %s",
             n_series, len(all_dc_spaces), len(all_ic_spaces), dc_band, ic_band)
    if skipped:
        log.info("fit: %d tickers skipped (missing/thin): %s", len(skipped), skipped[:8])

    return {
        "dc_band": list(dc_band),
        "ic_band_w": list(ic_band),
        "n_troughs": len(all_dc_spaces),
        "n_series": n_series,
        "method": "median±½IQR",
        "fitted_on": str(date.today()),
    }


def main() -> None:
    log.info("=== fit_cycle_bands_phase0: loading yahoo_closes ===")
    try:
        closes = yahoo_closes()
    except Exception as e:
        log.error("Cannot load yahoo_closes: %s", e)
        sys.exit(1)

    if closes is None or closes.empty:
        log.error("yahoo_closes returned empty — cannot fit")
        sys.exit(1)

    log.info("Close panel: %d rows × %d columns", len(closes), len(closes.columns))

    # ── equity ────────────────────────────────────────────────────────────────
    eq_tickers = _SECTOR_ETFS + _country_tickers()
    eq_tickers = list(dict.fromkeys(eq_tickers))   # deduplicate, order-stable
    log.info("equity: %d tickers", len(eq_tickers))
    eq_fit = _fit_asset_class(eq_tickers, closes, crypto=False)

    # ── crypto ────────────────────────────────────────────────────────────────
    log.info("crypto: %d tickers", len(_CRYPTO_TICKERS))
    cr_fit = _fit_asset_class(_CRYPTO_TICKERS, closes, crypto=True)

    # ── fx ────────────────────────────────────────────────────────────────────
    log.info("fx: %d tickers (looking for any available)", len(_FX_TICKERS))
    fx_fit = _fit_asset_class(_FX_TICKERS, closes, crypto=False)

    # ── write output ──────────────────────────────────────────────────────────
    today = str(date.today())
    out = {
        "equity": eq_fit,
        "crypto": cr_fit,
        "fx": fx_fit,
        "_meta": {
            "fitted_on": today,
            "note": ("W2.8 phase-0 band fit — fallback constants remain in "
                     "engine/cycles.py CYCLE_PRESETS"),
        },
    }

    out_dir = config.data_dir() / "regime"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cycle_bands_fit.json"
    out_path.write_text(json.dumps(out, indent=2))
    log.info("Wrote %s", out_path)

    # ── comparison table ──────────────────────────────────────────────────────
    print("\n=== Fitted vs Asserted Cycle Bands (W2.8 Phase-0) ===\n")
    header = f"{'Class':<10}  {'Asserted DC':>14}  {'Fitted DC':>12}  {'Asserted IC_W':>14}  {'Fitted IC_W':>12}  {'N troughs':>10}  {'N series':>9}"
    print(header)
    print("-" * len(header))
    for kind, fit_d in [("equity", eq_fit), ("crypto", cr_fit), ("fx", fx_fit)]:
        preset = CYCLE_PRESETS.get(kind, {})
        adc  = preset.get("dc_band", ("?", "?"))
        aic  = preset.get("ic_band_w", ("?", "?"))
        fdc  = tuple(fit_d["dc_band"])
        fic  = tuple(fit_d["ic_band_w"])
        nt   = fit_d["n_troughs"]
        ns   = fit_d["n_series"]
        # flag if fitted band differs meaningfully from asserted
        dc_flag  = " *" if fdc != (0, 0) and (abs(fdc[0] - adc[0]) > 4 or abs(fdc[1] - adc[1]) > 4) else "  "
        ic_flag  = " *" if fic != (0, 0) and (abs(fic[0] - aic[0]) > 4 or abs(fic[1] - aic[1]) > 4) else "  "
        print(f"{kind:<10}  {str(adc):>14}  {str(fdc)+dc_flag:>14}  {str(aic):>14}  {str(fic)+ic_flag:>14}  {nt:>10}  {ns:>9}")
    print("\n* = fitted band differs from asserted by >4 bars/weeks on at least one edge")
    print(f"\nArtifact: {out_path}")


if __name__ == "__main__":
    main()
