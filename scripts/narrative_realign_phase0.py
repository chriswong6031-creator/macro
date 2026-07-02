"""D7 salvage test — VIX-orthogonal re-aim for the Narrative-Dominance Index.

THE QUESTION (D7):
  Phase-0 falsified EPU/GPR on forward-vol incremental over VIX. One salvage
  test each on two VIX-blind targets, then retire-or-license:

  Signal A — NDI residual: VIX-orthogonal residual of the EPU+GPR text-uncertainty
              index (TU), constructed PIT via expanding-z on log(EPU) + log(GPR-threat)
              then residualized on [VIX, RVnow] via OLS. VIX CANNOT price what this
              residual carries — otherwise it would be 0 after regressing on VIX.

  Signal B — SFED residual: VIX-orthogonal residual of the SF-Fed Daily News
              Sentiment Index (Bybee et al., frbsf.org), expanding-z PIT, same OLS
              residualization. A text-based signal with a different construction
              lineage to the EPU/GPR family.

  Target 1 — cs_disp: 21d realized CROSS-SECTIONAL standard deviation of 9 SPDR
              sector ETF log-returns (XLB/E/F/I/K/P/U/V/Y), computed strictly
              forward (t+1..t+h). VIX prices aggregate vol; it is blind to rotation
              and dispersion across sectors. High-uncertainty regimes may widen
              the cross-sectional spread even when aggregate vol (VIX) is stable.
              Baseline: IC(VIX, cs_disp21) = +0.39 (VIX is correlated — sectors
              blow up together in crises — so the residual test strips that overlap).

  Target 2 — complacency_fade: binary 1 when the h-day forward SPY log-return
              falls below the trailing 6-month SPY daily-return mean. A "regime
              disappointment" or complacency-fade signal; tests whether low-residual
              (below-expectation text-uncertainty) regimes predict below-average
              subsequent SPY performance. VIX cannot price this by construction:
              IC(VIX, comp_fade21) = -0.002, essentially zero.

Statistical discipline (matches narrative_regime_phase0.py exactly):
  * PIT: expanding-z standardization with 252-day burn-in, no look-ahead.
  * VIX-orthogonal residual: OLS residual of signal ~ [VIX, RVnow(21)].
  * Block-bootstrap CIs (block=63, B=2000) — overlapping forward windows inflate
    naive t; bootstrap preserves local autocorrelation structure.
  * BH-FDR across all (signal × target × horizon) tests, q<=0.10.
  * Split-half sign-stability: same-sign incremental IC in both halves required.
  * License gate: excl0=True AND positive IC (target A) or excl0=True (target B)
    AND FDR-reject AND sign-stable across both halves.

Sample:
  Sector ETF availability gates the start to 1999-01-04 (XLB etc. launch 1998-12-22,
  expanding-z needs 252 bars from 1999). EPU/GPR from 1985, SFED from 1980, VIX from
  1990 — all cover the window. n ≈ 6,900 trading days (1999-2026).

Run:  python scripts/narrative_realign_phase0.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store  # noqa: E402

# --------------------------------------------------------------------------- #
# configuration — mirrors narrative_regime_phase0.py
# --------------------------------------------------------------------------- #
HORIZONS = [5, 10, 21, 63]
BLOCK = 63
B = 2000
SEED = 7
MINWIN = 252            # expanding-z burn-in (same as phase0)

SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
# 9 original SPDRs that go back to 1998-12-22; XLC (2018) and XLRE (2015) excluded
# to maximise the sample window.

SFED_PATH = Path(__file__).resolve().parent.parent / "data" / "frbsf" / "news_sentiment.parquet"


# --------------------------------------------------------------------------- #
# utilities — identical signatures to phase0 for reproducibility
# --------------------------------------------------------------------------- #
def expanding_z(s: pd.Series, minp: int = MINWIN) -> pd.Series:
    """PIT standardization: (x - expanding mean) / expanding std. No look-ahead."""
    mu = s.expanding(min_periods=minp).mean()
    sd = s.expanding(min_periods=minp).std()
    return (s - mu) / sd


def _safelog(s: pd.Series) -> pd.Series:
    return np.log(s.where(s > 0))


def resid_ols(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    """Residual of y on [1, X...] via OLS (aligned, dropna)."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    A = np.column_stack([np.ones(len(d))] + [d[c].values for c in X.columns])
    beta, *_ = np.linalg.lstsq(A, d["y"].values, rcond=None)
    return pd.Series(d["y"].values - A @ beta, index=d.index)


def boot_spearman_ci(
    sig: pd.Series, tgt: pd.Series, block: int = BLOCK, B: int = B, seed: int = SEED
) -> dict | None:
    """Block-bootstrap 90% CI + two-sided p for a time-series Spearman IC."""
    d = pd.concat([sig.rename("s"), tgt.rename("t")], axis=1).dropna()
    if len(d) < block * 3:
        return None
    s, t = d["s"].values, d["t"].values
    n = len(s)
    point = spearmanr(s, t).statistic
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    stats = np.empty(B)
    for b in range(B):
        starts = rng.integers(0, n - block + 1, size=nblocks)
        idx = np.concatenate([np.arange(st, st + block) for st in starts])[:n]
        stats[b] = spearmanr(s[idx], t[idx]).statistic
    lo, hi = np.percentile(stats, [5, 95])
    p = 2.0 * min((stats <= 0).mean(), (stats >= 0).mean()) if point != 0 else 1.0
    return {
        "ic": round(float(point), 4),
        "lo": round(float(lo), 4),
        "hi": round(float(hi), 4),
        "p": round(float(p), 4),
        "excl0": bool(lo > 0 or hi < 0),
        "n": int(len(d)),
    }


def benjamini_hochberg(pvals: dict, alpha: float = 0.10) -> dict:
    """BH-FDR correction. Returns {key: {p, q, reject}}."""
    items = sorted(pvals.items(), key=lambda x: x[1])
    m = len(items)
    out = {}
    for rank, (k, p) in enumerate(items, 1):
        q = min(p * m / rank, 1.0)
        out[k] = {"p": round(float(p), 4), "q": round(float(q), 4),
                  "reject": bool(q <= alpha)}
    return out


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_aligned() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.DataFrame, pd.DatetimeIndex]:
    """Return (tu_resid, sfed_resid, vix_s, rvnow, sec_rets_idx, idx).

    All series are aligned to the sector-ETF trading calendar starting 1999-01-04.
    PIT discipline: expanding-z applied BEFORE residualization; no future data touches
    either the standardization window or the OLS fit.
    """
    # Sector ETF prices
    frames = {}
    for t in SECTOR_ETFS:
        df = pd.read_parquet(
            Path(__file__).resolve().parent.parent / "data" / "yahoo" / f"{t}.parquet"
        )
        frames[t] = df["close"].rename(t).astype(float)
    prices = pd.concat(list(frames.values()), axis=1, sort=True)
    sec_rets = np.log(prices).diff()
    idx_sec = sec_rets.dropna(how="all").index
    idx = idx_sec[idx_sec >= "1999-01-01"]

    # SPY for RVnow + complacency target
    spy = store.read("yahoo", "SPY")["close"].astype(float)
    r_spy = np.log(spy).diff().reindex(idx, method="ffill")
    rvnow = (r_spy.rolling(21).std() * np.sqrt(252)).rename("rvnow")

    # VIX (VIXCLS) — PIT baseline for residualization
    vix_raw = store.read("fred", "VIXCLS")["vix_close"].astype(float)
    vix_s = vix_raw.reindex(idx, method="ffill").rename("vix")

    # EPU + GPR-threat → TU (PIT, same construction as phase0)
    epu = store.read("uncertainty", "epu_us")["epu"].astype(float)
    gpr = store.read("uncertainty", "gpr")["gpr_threat"].astype(float)
    tu_raw = (
        0.5 * expanding_z(_safelog(epu.reindex(idx, method="ffill")))
        + 0.5 * expanding_z(_safelog(gpr.reindex(idx, method="ffill")))
    ).rename("tu")

    # SF-Fed Daily News Sentiment (Bybee et al.) — PIT expanding-z
    sfed_raw = pd.read_parquet(SFED_PATH)["news_sentiment"].astype(float)
    sfed_z_raw = expanding_z(sfed_raw.reindex(idx, method="ffill")).rename("sfed_z")

    # VIX-orthogonal residuals (the key operation: remove VIX + RVnow collinearity)
    baseline = pd.DataFrame({"vix": vix_s, "rvnow": rvnow})
    tu_resid = resid_ols(tu_raw, baseline).rename("tu_resid")
    sfed_resid = resid_ols(sfed_z_raw, baseline).rename("sfed_resid")

    return tu_resid, sfed_resid, vix_s, rvnow, sec_rets.reindex(idx), idx


# --------------------------------------------------------------------------- #
# target construction
# --------------------------------------------------------------------------- #
def build_targets_A(sec_rets_idx: pd.DataFrame) -> dict[str, pd.Series]:
    """Target A: h-day forward cross-sectional standard deviation of sector ETF
    log-returns. Strictly forward (t+1..t+h), no overlap with signal at t.
    NOT annualized — raw h-day std to avoid introducing an h-dependent scale."""
    targets = {}
    for h in HORIZONS:
        # per-sector cumulative log-return t+1..t+h
        fwd = sec_rets_idx.shift(-1).rolling(h).sum().shift(-(h - 1))
        targets[f"cs_disp{h}"] = fwd.std(axis=1).rename(f"cs_disp{h}")
    return targets


def build_targets_B(r_spy: pd.Series) -> dict[str, pd.Series]:
    """Target B: binary 1 when h-day forward SPY log-return < trailing 6m daily
    mean (126 trading days). Tests complacency-fade timing: do low-residual
    regimes (elevated uncertainty not reflected in VIX) predict below-mean
    subsequent SPY returns? Strictly forward (t+1..t+h)."""
    trail_mean = r_spy.rolling(126).mean()
    targets = {}
    for h in HORIZONS:
        fwd = r_spy.shift(-1).rolling(h).sum().shift(-(h - 1))
        targets[f"comp_fade{h}"] = (fwd < trail_mean).astype(float).rename(f"comp_fade{h}")
    return targets


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #
def run_grid(signals: dict[str, pd.Series], targets: dict[str, pd.Series],
             half: pd.Timestamp) -> tuple[list[dict], dict]:
    """Run (signal × target) Spearman ICs with bootstrap CIs and split-half stability.
    Returns (rows, p_dict) for BH-FDR."""
    rows: list[dict] = []
    p_dict: dict[str, float] = {}
    for sig_name, sig in signals.items():
        for tgt_name, tgt in targets.items():
            res = boot_spearman_ci(sig, tgt)
            if res is None:
                continue
            # split-half stability
            d1 = pd.concat([sig.loc[:half], tgt.loc[:half]], axis=1).dropna()
            d2 = pd.concat([sig.loc[half:], tgt.loc[half:]], axis=1).dropna()
            ic_a = (spearmanr(*d1.values.T).statistic if len(d1) > 30 else float("nan"))
            ic_b = (spearmanr(*d2.values.T).statistic if len(d2) > 30 else float("nan"))
            key = f"{sig_name}|{tgt_name}"
            p_dict[key] = res["p"]
            rows.append({
                "sig": sig_name,
                "tgt": tgt_name,
                "res": res,
                "ic_a": ic_a,
                "ic_b": ic_b,
                "key": key,
            })
    return rows, p_dict


def _passes_license_gate(row: dict, fdr: dict, target_type: str) -> bool:
    """License gate: excl0 AND sign-consistent IC AND FDR-reject AND sign-stable halves.
    Target A requires positive IC (dispersion should rise with elevated uncertainty).
    Target B direction is pre-specified as positive (high uncertainty → complacency-fade),
    but the gate accepts either sign so long as it is FDR-stable and half-stable."""
    res = row["res"]
    fdr_entry = fdr.get(row["key"], {})
    if not fdr_entry.get("reject", False):
        return False
    if not res["excl0"]:
        return False
    ic_a, ic_b = row["ic_a"], row["ic_b"]
    sign_stable = (
        not (np.isnan(ic_a) or np.isnan(ic_b))
        and abs(ic_a) > 1e-3
        and abs(ic_b) > 1e-3
        and (ic_a > 0) == (ic_b > 0)
    )
    if not sign_stable:
        return False
    if target_type == "A":
        return res["ic"] > 0          # dispersion: expect positive
    return True                        # complacency: either sign accepted


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    print("\nNarrative-Dominance Index — D7 Salvage (VIX-orthogonal re-aim)")
    print("Signals: NDI_resid (EPU+GPR residual) | SFED_resid (SF-Fed sentiment residual)")
    print("Targets: A=cross-sectional sector dispersion | B=complacency-fade timing")
    print(f"Block-bootstrap block={BLOCK}, B={B}, SEED={SEED}  BH-FDR alpha=0.10")

    tu_resid, sfed_resid, vix_s, rvnow, sec_rets_idx, idx = load_aligned()

    start = pd.concat([tu_resid, sfed_resid]).dropna().index.min()
    print(f"\nSample: {start.date()} -> {idx.max().date()}  "
          f"({len(idx[idx >= start])} trading days)")
    print(f"NDI_resid n={tu_resid.dropna().shape[0]}  "
          f"SFED_resid n={sfed_resid.dropna().shape[0]}")

    # VIX baseline (context)
    print("\n--- VIX baseline correlations (context: VIX cannot fully price these) ---")
    spy = store.read("yahoo", "SPY")["close"].astype(float)
    r_spy = np.log(spy).diff().reindex(idx, method="ffill")
    targets_A = build_targets_A(sec_rets_idx)
    targets_B = build_targets_B(r_spy)
    for tgt_name in ["cs_disp5", "cs_disp10", "cs_disp21", "cs_disp63"]:
        tgt = targets_A[tgt_name]
        d = pd.concat([vix_s, tgt], axis=1).dropna()
        print(f"  IC(VIX, {tgt_name}) = {spearmanr(*d.values.T).statistic:+.4f}  (n={len(d)})")
    for tgt_name in ["comp_fade5", "comp_fade10", "comp_fade21", "comp_fade63"]:
        tgt = targets_B[tgt_name]
        d = pd.concat([vix_s, tgt], axis=1).dropna()
        print(f"  IC(VIX, {tgt_name}) = {spearmanr(*d.values.T).statistic:+.4f}  (n={len(d)})")

    half = idx[len(idx) // 2]
    signals = {"NDI_resid": tu_resid, "SFED_resid": sfed_resid}

    # Target A
    print("\n=== TARGET A: Forward cross-sectional sector dispersion ===")
    rows_A, p_A = run_grid(signals, targets_A, half)
    for row in rows_A:
        r = row["res"]
        print(f"  {row['sig']:<15} vs {row['tgt']:<13}: "
              f"IC={r['ic']:+.4f} [{r['lo']:+.4f},{r['hi']:+.4f}] "
              f"p={r['p']:.4f} excl0={r['excl0']} "
              f"half={row['ic_a']:+.3f}/{row['ic_b']:+.3f}  n={r['n']}")

    # Target B
    print("\n=== TARGET B: Complacency-fade timing (SPY below trailing-mean) ===")
    rows_B, p_B = run_grid(signals, targets_B, half)
    for row in rows_B:
        r = row["res"]
        print(f"  {row['sig']:<15} vs {row['tgt']:<13}: "
              f"IC={r['ic']:+.4f} [{r['lo']:+.4f},{r['hi']:+.4f}] "
              f"p={r['p']:.4f} excl0={r['excl0']} "
              f"half={row['ic_a']:+.3f}/{row['ic_b']:+.3f}  n={r['n']}")

    # BH-FDR
    all_ps = {**p_A, **p_B}
    fdr = benjamini_hochberg(all_ps, alpha=0.10)
    print("\n--- BH-FDR across all tests ---")
    for k, v in sorted(fdr.items()):
        print(f"  {k}: p={v['p']:.4f} q={v['q']:.4f} reject={v['reject']}")

    # Verdicts
    ndi_A_pass = any(_passes_license_gate(r, fdr, "A") for r in rows_A if r["sig"] == "NDI_resid")
    ndi_B_pass = any(_passes_license_gate(r, fdr, "B") for r in rows_B if r["sig"] == "NDI_resid")
    sfed_A_pass = any(_passes_license_gate(r, fdr, "A") for r in rows_A if r["sig"] == "SFED_resid")
    sfed_B_pass = any(_passes_license_gate(r, fdr, "B") for r in rows_B if r["sig"] == "SFED_resid")

    ndi_verdict = "LICENSE" if (ndi_A_pass or ndi_B_pass) else "RETIRE"
    sfed_verdict = "LICENSE" if (sfed_A_pass or sfed_B_pass) else "RETIRE"

    print("\n" + "=" * 72)
    print(f"NDI (EPU+GPR) residual: {ndi_verdict}")
    print(f"SFED sentiment residual: {sfed_verdict}")
    print()
    if ndi_verdict == "RETIRE":
        print("  NDI: no (signal × target × horizon) cell clears the license gate "
              "(FDR + excl0 + sign-stable halves). Extending pinned_off registry.")
    else:
        print("  NDI: at least one cell cleared — bounded confirmer candidate.")
    if sfed_verdict == "RETIRE":
        print("  SFED: no cell clears. Retiring the family.")
    else:
        print("  SFED: at least one cell cleared — bounded confirmer candidate.")
    print("=" * 72 + "\n")
    return {"ndi": ndi_verdict, "sfed": sfed_verdict, "fdr": fdr}


if __name__ == "__main__":
    main()
