"""Phase-0: should an EXTENDED LEADER get a ⅓ STARTER instead of avoid/0?

The board zeroes a name that trips the absolute extension brake (pct_vs_200dma >= 30%,
engine/stock_score._STRETCH_BLOCK) — verdict "Extended — don't chase; wait for a pullback",
suggested size = avoid/0. The proposed move-3 follow-on flips that to a ⅓ STARTER now + add
the rest on a pullback, for a non-parabolic leader in the 30–~47% gray zone. That CHANGES what
the board recommends, so it must clear a gate before shipping — the >35%-over-200d cohort is
exactly the one the brake's own deep-PIT calibration found has the WORST forward return and the
DEEPEST drawdown (engine/stock_score:388).

This harness simulates, on the gray-zone momentum-leader cohort at monthly rebalances, four
entry rules over a forward hold, and compares their tail-aware outcomes:

  FULL_NOW    full size at the rebalance (the chase the brake forbids — the deterrent baseline)
  STARTER_ADD ⅓ now; add the rest at the first pullback to the 25%-over-200d line within K days
  WAIT_FULL   0 now; full ONLY if it pulls back to that line within K days, else miss it
  AVOID       0 (the current behaviour)

GO (flip justified) only if STARTER_ADD is risk-adjusted attractive vs AVOID *and* not much
deeper in drawdown than WAIT_FULL. Deep survivorship-clean PIT cache when present (CI); falls
back to the available ~3y S&P-1500 cache locally (SURVIVORSHIP-BIASED — biases the starter to
look BETTER than it is, so a NO-GO here is strong; a GO here would need the deep run to confirm).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("leader_starter_size_phase0")

# cohort = the flip's target: gray-zone, non-parabolic, momentum-leading
GRAY_LO, GRAY_HI = 0.30, 0.47    # % above the 200d MA (== _STRETCH_BLOCK .. ~where the zone gets a chase-deep)
PARAB_Z = 2.0                    # ext_z >= this is parabolic — never eligible for a starter
MOM_Q = 0.60                     # 12-1 momentum top 40% within the eligible set = a "leader"
WARN_MULT = 1.25                 # pullback target = 200d × 1.25 (the move-3 "out of the chase zone" line)
HOLD = 63                        # forward hold (trading days)
ADD_WIN = 21                     # the pullback (the add / the wait-entry) must land within this many days
START_FRAC = 1.0 / 3.0


def load_closes() -> tuple[pd.DataFrame, str]:
    """(closes, source-label). Deep survivorship-clean PIT cache if built, else the live ~3y cache."""
    try:
        from lib import config
        from scripts.residual_alpha_phase0 import _closes_deep
        c = _closes_deep()
        if c is not None and not c.empty:
            for fn in ("_closes_delisted.parquet", "_closes_delisted_1500.parquet"):
                p = config.data_dir() / "breadth" / fn
                if p.exists():
                    c = pd.concat([c, pd.read_parquet(p)], axis=1)
                    c = c.loc[:, ~c.columns.duplicated()]
            return c.sort_index(), "deep survivorship-clean PIT"
    except Exception as e:  # noqa: BLE001
        log.info("deep cache unavailable (%s) — falling back", e)
    from engine import group_flow
    s = group_flow._setup("us")
    if not s:
        raise SystemExit("no close cache available")
    return s["closes"].sort_index(), "available S&P-1500 cache (~3y, SURVIVORSHIP-BIASED)"


def _signals(px: pd.DataFrame):
    sma200 = px.rolling(200, min_periods=150).mean()
    ext = px / sma200 - 1.0
    extz = (ext - ext.rolling(252, min_periods=150).mean()) \
        / ext.rolling(252, min_periods=150).std().replace(0, np.nan)
    pret = px.shift(21) / px.shift(252) - 1.0           # 12-1 momentum (the leadership axis)
    return sma200, ext, extz, pret


def _month_ends(idx: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(idx, index=idx)
    return [g.iloc[-1] for _, g in s.groupby([idx.year, idx.month])]


def _sim_one(path: np.ndarray, pb: float, k: int):
    """path = entry-normalised closes [1.0, d+1, ... d+H]. pb = pullback target return (<0).
    Returns {rule: (terminal_ret, max_drawdown)} for the four rules."""
    r = path[1:] / path[:-1] - 1.0                      # daily simple returns, len H
    H = len(r)
    # first day (1..k) the close reaches the pullback line
    hit = np.where(path[1:k + 1] <= 1.0 + pb)[0]
    hstar = int(hit[0] + 1) if len(hit) else None       # 1-based day index, or None

    def equity(expo):                                   # expo: array len H of exposure per day
        e, peak, mdd = 1.0, 1.0, 0.0
        for h in range(H):
            e *= 1.0 + expo[h] * r[h]
            peak = max(peak, e)
            mdd = min(mdd, e / peak - 1.0)
        return e - 1.0, mdd

    full = np.ones(H)
    if hstar is None:
        starter = np.full(H, START_FRAC)                # never added → stays ⅓
        wait = np.zeros(H)                              # never entered → flat cash
    else:
        starter = np.where(np.arange(1, H + 1) > hstar, 1.0, START_FRAC)
        wait = np.where(np.arange(1, H + 1) > hstar, 1.0, 0.0)
    return {
        "FULL_NOW": equity(full),
        "STARTER_ADD": equity(starter),
        "WAIT_FULL": equity(wait),
        "AVOID": (0.0, 0.0),
    }, (hstar is not None)


def run(px, sma200, ext, extz, pret, hold=HOLD, k=ADD_WIN):
    idx = px.index
    pos_of = {d: i for i, d in enumerate(idx)}
    grid = [d for d in _month_ends(idx) if pos_of[d] >= 300 and pos_of[d] + hold < len(idx)]
    rules = ["FULL_NOW", "STARTER_ADD", "WAIT_FULL", "AVOID"]
    rets = {ru: [] for ru in rules}
    dds = {ru: [] for ru in rules}
    pulled, n_entries = 0, 0
    pxv = px.values
    for d in grid:
        pos = pos_of[d]
        e_d, ez_d, mom_d = ext.loc[d], extz.loc[d], pret.loc[d]
        elig = e_d.index[e_d.notna() & ez_d.notna() & mom_d.notna()
                         & sma200.loc[d].notna()]
        if len(elig) < 20:
            continue
        mom_cut = mom_d[elig].quantile(MOM_Q)
        cohort = [t for t in elig
                  if GRAY_LO <= e_d[t] < GRAY_HI and ez_d[t] < PARAB_Z and mom_d[t] >= mom_cut]
        for t in cohort:
            j = px.columns.get_loc(t)
            entry = pxv[pos, j]
            fwd = pxv[pos + 1:pos + 1 + hold, j]
            if not np.isfinite(entry) or entry <= 0 or np.isnan(fwd).any():
                continue
            target = sma200.loc[d, t] * WARN_MULT
            pb = target / entry - 1.0
            if pb >= 0:                                  # target above spot → no pullback to add at
                continue
            path = np.concatenate([[1.0], fwd / entry])
            out, did_pull = _sim_one(path, pb, k)
            for ru in rules:
                rets[ru].append(out[ru][0]); dds[ru].append(out[ru][1])
            pulled += int(did_pull); n_entries += 1
    return rets, dds, pulled, n_entries, len(grid)


def _summary(rets, dds):
    rows = {}
    for ru in rets:
        r = np.array(rets[ru]); d = np.array(dds[ru])
        if not len(r):
            continue
        mean_dd = float(d.mean())
        rows[ru] = {
            "mean_ret": round(float(r.mean()) * 100, 2),
            "median_ret": round(float(np.median(r)) * 100, 2),
            "p5_ret": round(float(np.percentile(r, 5)) * 100, 2),
            "mean_dd": round(mean_dd * 100, 2),
            "p5_dd": round(float(np.percentile(d, 5)) * 100, 2),
            "hit": round(float((r > 0).mean()) * 100, 1),
            "ret_per_dd": round(float(r.mean() / abs(mean_dd)), 2) if mean_dd < 0 else None,
        }
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=HOLD)
    ap.add_argument("--add-window", type=int, default=ADD_WIN)
    args = ap.parse_args()

    px, src = load_closes()
    sma200, ext, extz, pret = _signals(px)
    rets, dds, pulled, n, n_grid = run(px, sma200, ext, extz, pret, args.hold, args.add_window)
    if not n:
        print("no cohort entries — universe/cache too thin")
        return 1
    rows = _summary(rets, dds)

    print(f"\n=== Leader ⅓-starter Phase-0 — {src} ===")
    print(f"span {px.index.min().date()}..{px.index.max().date()} · {n_grid} rebalances · "
          f"{n} gray-zone-leader entries (ext {int(GRAY_LO*100)}–{int(GRAY_HI*100)}% over 200d, "
          f"not parabolic, top-40% momentum) · hold {args.hold}d · pullback within {args.add_window}d")
    print(f"pullback-to-the-line hit rate: {pulled/n*100:.0f}%  (how often WAIT/ADD actually fills the add)\n")
    hdr = f"{'rule':<13}{'mean_ret':>9}{'median':>8}{'p5_ret':>8}{'mean_dd':>9}{'p5_dd':>8}{'hit%':>7}{'ret/dd':>8}"
    print(hdr); print("-" * len(hdr))
    for ru in ("FULL_NOW", "STARTER_ADD", "WAIT_FULL", "AVOID"):
        m = rows.get(ru, {})
        print(f"{ru:<13}{m.get('mean_ret','—'):>9}{m.get('median_ret','—'):>8}{m.get('p5_ret','—'):>8}"
              f"{m.get('mean_dd','—'):>9}{m.get('p5_dd','—'):>8}{m.get('hit','—'):>7}"
              f"{str(m.get('ret_per_dd','—')):>8}")

    st, wa = rows.get("STARTER_ADD", {}), rows.get("WAIT_FULL", {})
    # GO criteria: starting a ⅓ now must (1) carry positive expectancy, (2) be risk-adjusted at
    # least as good as waiting fully, and (3) not deepen drawdown much past the wait.
    go = bool(st and st["mean_ret"] > 0
              and (st.get("ret_per_dd") or -9) >= (wa.get("ret_per_dd") or -9)
              and st["mean_dd"] >= wa.get("mean_dd", -99) * 1.25)
    verdict = "GO — flip _suggested_size to a ⅓ starter for gray-zone leaders" if go else \
        "NO-GO — keep avoid/0; the starter does not pay for its drawdown on this cohort"
    print(f"\nVERDICT: {verdict}")
    print("NOTE: the brake's own deep-PIT calibration already found this cohort (>35% over 200d) has "
          "the WORST forward return + DEEPEST drawdown (engine/stock_score:388). A NO-GO is the "
          "expected, brake-consistent result; the shipped buy-zone stays DISPLAY-ONLY.")
    if "SURVIVORSHIP" in src:
        print("CAVEAT: ran on the survivorship-biased ~3y cache (biases the starter UP). Re-run in CI "
              "with the deep cache (scripts.residual_alpha_fetch) before trusting any GO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
