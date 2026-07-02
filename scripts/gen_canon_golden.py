"""Regenerate tests/golden/canon_vectors.json — the committed golden vectors for engine/canon.

Run ONLY after a DELIBERATE canon math change; the committed vectors are the contract
every consumer is diffed against (audit #7 #12 #28 #40).  A silent change to canon that
also regenerates these vectors would defeat the point — so review the JSON diff.

Usage:  python scripts/gen_canon_golden.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import canon

OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "canon_vectors.json"


def _f(seq, nd=6):
    return [None if pd.isna(x) else round(float(x), nd) for x in np.asarray(seq)]


def build() -> dict:
    rng = np.random.RandomState(42)
    G: dict = {"_meta": {
        "note": "Golden vectors for engine/canon.py. Regenerate ONLY via "
                "scripts/gen_canon_golden.py after a DELIBERATE math change; a diff here "
                "means a consumer will silently drift (audit #7 #12 #28 #40)."}}

    # 1 · net_liquidity_bn (3-term billions) + dollar_liquidity_roc framing
    idx = pd.date_range("2023-01-01", periods=12)
    walcl = np.round(np.linspace(7000, 7120, 12), 2)
    rrp = np.round(np.linspace(60, 42, 12), 2)
    tga = np.round(np.linspace(480, 530, 12), 2)
    nl = canon.net_liquidity_bn(pd.Series(walcl, idx), pd.Series(rrp, idx), pd.Series(tga, idx))
    G["net_liquidity_bn"] = {
        "inputs": {"walcl_bn": walcl.tolist(), "rrp_bn": rrp.tolist(), "tga_bn": tga.tolist()},
        "expected": _f(nl.to_numpy(), 4)}
    G["dollar_liquidity_roc"] = {"window_d": 3,
                                 "expected": _f(canon.dollar_liquidity_roc(nl, 3).to_numpy(), 4)}

    # 2 · credit impulse level (1st deriv) + accel (2nd deriv) — the label-collision fix
    def _ms(vals, start="2020-01-31"):
        return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="ME"))
    tsf = np.round(100 + np.cumsum(rng.randn(48)) * 3 + np.arange(48) * 2.0, 3)
    G["credit_impulse"] = {
        "inputs": {"tsf_total": tsf.tolist()},
        "level_expected": _f(canon.credit_impulse_level(_ms(tsf)).to_numpy()),
        "accel_expected": _f(canon.credit_impulse_accel(_ms(tsf)).to_numpy())}

    # 3 · vix_term (one basis: VIX/VIX3M)
    vix = np.round(np.array([14, 18, 22, 30, 16, 19.5]), 3)
    v3 = np.round(np.array([18, 19, 20, 24, 18, 19]), 3)
    G["vix_term"] = {"inputs": {"vix": vix.tolist(), "vix3m": v3.tolist()},
                     "expected": _f(canon.vix_term(pd.Series(vix), pd.Series(v3)).to_numpy()),
                     "scalar_20_19": round(canon.vix_term_scalar(20, 19), 6)}

    # 4 · sector_macro_beta_blend (shadow; retires the impossible XLC=1.0)
    prior = {"XLF": 1.0, "XLC": 1.0, "XLK": 0.39, "XLU": -0.29, "XLE": 0.16,
             "Communications": 1.0}
    measured = {"XLF": 0.55, "XLK": 0.12, "XLU": -0.10, "XLE": 0.05}
    mn = {"XLF": 300, "XLK": 300, "XLU": 120, "XLE": 300}
    G["sector_macro_beta_blend"] = {
        "inputs": {"prior": prior, "measured": measured, "measured_n": mn, "shrink_k": 8.0},
        "expected": canon.sector_macro_beta_blend(prior, measured, shrink_k=8.0, measured_n=mn)}

    # 5 · corrected confluence primitives on a deterministic price series
    px = np.round(100 * np.exp(np.cumsum(rng.randn(400) * 0.015)), 4)
    pxs = pd.Series(px, pd.bdate_range("2021-01-01", periods=400))
    G["confluence_primitives"] = {
        "inputs": {"close": px.tolist(), "start": "2021-01-01", "freq": "B"},
        "rma14_tail": _f(canon.rma(pxs, 14).to_numpy()[-10:]),
        "ema14_tail": _f(canon.ema(pxs, 14).to_numpy()[-10:]),
        "rsi14_tail": _f(canon.rsi(pxs, 14).to_numpy()[-10:]),
        "session3_len": int(len(canon.resample_sessions(pxs, 3)[0])),
        "session3_last_date": str(canon.resample_sessions(pxs, 3)[0].index[-1].date())}
    return G


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
