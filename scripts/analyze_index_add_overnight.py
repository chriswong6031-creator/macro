"""WHERE in the day does the S&P pure-add run-up happen? — overnight vs intraday.

The index-add announcement run-up ([-5,0], pure/net-new cohort) is real gross but a
net-of-cost mirage for the typical name (scripts/validate_index_reconstitution.py).
Mase-Reading and the practitioner literature locate the residual NET edge in the
announcement-CLOSE→next-OPEN OVERNIGHT gap (≈+4.4% overnight vs ≈0 next-day intraday),
which a slow 5-day hold can't capture. This script tests that decomposition on OUR data:
for each PURE add it splits the 5 trading days after the [-5,0] entry into
  overnight_t = log(open_t / close_{t-1})   and   intraday_t = log(close_t / open_t)
and aggregates the mean overnight-sum vs intraday-sum. If the run-up is overnight-
dominated, the only capturable net edge requires a close-buy / open-sell execution that
needs the LIVE announcement feed + forward accrual (no historical announcement dates) —
i.e. it confirms why the leg ships display-only today.

Outputs: reports/index-add-overnight-decomposition.md + an `overnight` block merged into
data/index_reconstitution/validation_gate.json. Uses yfinance daily OHLC (cached).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V  # noqa: E402
from engine.index_changes import classify_cohort, pit_history  # noqa: E402
from lib import config  # noqa: E402
import scripts.validate_index_reconstitution as R  # noqa: E402

log = logging.getLogger("overnight")
_WIN = R._ANNOUNCE_WINDOW          # (-5, 0): entry at close[-5], the 5 days held are [-4..0]


def _dir() -> Path:
    p = config.data_dir() / "index_reconstitution"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_ohlc(tickers: list[str]) -> dict:
    """{'open': DataFrame, 'close': DataFrame} daily, cached. Mirrors fetch_prices'
    attempted-cache discipline (mark only responded batches)."""
    cache = _dir() / "ohlc.parquet"
    att_path = _dir() / "ohlc_attempted.json"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    attempted = (set(json.loads(att_path.read_text()))
                 if (cache.exists() and att_path.exists()) else set())
    # a symbol is "have" only if BOTH open| and close| survived the >20-obs filter — otherwise it
    # can't be decomposed and must stay in `need` for a re-fetch (don't collapse the namespace).
    open_syms = {c.split("|", 1)[1] for c in have.columns if c.startswith("open|")}
    close_syms = {c.split("|", 1)[1] for c in have.columns if c.startswith("close|")}
    have_syms = open_syms & close_syms
    need = sorted(set(tickers + ["SPY"]) - have_syms - attempted)
    if need:
        import yfinance as yf
        got, B, newly = {}, 150, set()
        for i in range(0, len(need), B):
            chunk = need[i:i + B]
            try:
                raw = yf.download(chunk, start="2018-10-01", interval="1d",
                                  progress=False, threads=False, auto_adjust=True)
            except Exception as e:  # noqa: BLE001
                log.warning("ohlc batch %d failed: %s — retry next run", i, e)
                continue
            newly |= set(chunk)
            if raw is None or raw.empty:
                continue
            for field in ("Open", "Close"):
                sub = raw[field] if isinstance(raw.columns, pd.MultiIndex) else raw
                if isinstance(sub, pd.Series):
                    sub = sub.to_frame(chunk[0])
                for c in sub.columns:
                    s = sub[c].dropna()
                    if len(s) > 20:
                        got[f"{field.lower()}|{c}"] = s
            log.info("ohlc batch %d/%d", i // B + 1, (len(need) + B - 1) // B)
        if got:
            new = pd.DataFrame(got)
            have = new if have.empty else have.join(new, how="outer")
            have.to_parquet(cache)
        if newly:
            att_path.write_text(json.dumps(sorted(attempted | newly)))
    op = have[[c for c in have.columns if c.startswith("open|")]].rename(
        columns=lambda c: c.split("|", 1)[1])
    cl = have[[c for c in have.columns if c.startswith("close|")]].rename(
        columns=lambda c: c.split("|", 1)[1])
    return {"open": op, "close": cl}


def _decompose(ticker, d, op, cl) -> tuple | None:
    """(overnight_logsum, intraday_logsum) over the 5 trading days after the [-5,0] entry,
    SPY-relative. Anchors on the first trading day on/AFTER the effective date, then looks
    back over [-5,0] (matches validate_index_reconstitution._abn). GROSS (no execution cost)."""
    if ticker not in cl.columns or "SPY" not in cl.columns or ticker not in op.columns:
        return None
    o, c = op[ticker].dropna(), cl[ticker].dropna()
    so, sc = op["SPY"].dropna(), cl["SPY"].dropna()
    idx = c.index[c.index >= d]
    if len(idx) == 0:
        return None
    e = c.index.get_loc(idx[0])
    a = _WIN[0]                                       # -5
    if e + a < 1 or e >= len(c):
        return None
    on_sum = intr_sum = 0.0
    for k in range(a + 1, _WIN[1] + 1):              # days held: [-4 .. 0]
        i = e + k
        if i < 1 or i >= len(c):
            return None
        t, tp = c.index[i], c.index[i - 1]
        try:
            on = np.log(o.loc[t] / c.loc[tp]) - np.log(so.asof(t) / sc.asof(tp))
            it = np.log(c.loc[t] / o.loc[t]) - np.log(sc.asof(t) / so.asof(t))
        except Exception:  # noqa: BLE001
            return None
        if not (np.isfinite(on) and np.isfinite(it)):
            return None
        on_sum += float(on)
        intr_sum += float(it)
    return on_sum, intr_sum


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ev = R.load_events()
    adds = ev[ev["kind"] == "add"].copy()
    pit = pit_history()
    adds["cohort"] = [classify_cohort(r.ticker, r.d, r.index, pit) for r in adds.itertuples(index=False)]
    pure = adds[adds["cohort"] == "pure"]
    log.info("fetching OHLC for %d pure-add targets…", pure["ticker"].nunique())
    ohlc = fetch_ohlc(sorted(pure["ticker"].unique()))
    op, cl = ohlc["open"], ohlc["close"]

    rows = []
    for r in pure.itertuples(index=False):
        dec = _decompose(r.ticker, r.d, op, cl)
        if dec is not None:
            rows.append((r.d, dec[0], dec[1]))
    df = pd.DataFrame(rows, columns=["d", "overnight", "intraday"])
    df["mo"] = df["d"].dt.to_period("M").astype(str)

    def _stat(col):
        m = df.groupby("mo")[col].mean()
        nw = V.newey_west_tstat(m.values, lags=min(4, max(1, len(m) // 4)))
        t = nw.get("t")
        return {"mean": round(float(df[col].mean()), 4),
                "share": None, "hac_t": round(float(t), 2) if t is not None else None}
    on, intr = _stat("overnight"), _stat("intraday")
    total = on["mean"] + intr["mean"]
    if total:
        on["share"] = round(on["mean"] / total, 2)
        intr["share"] = round(intr["mean"] / total, 2)
    log.info("pure-add [-5,0] decomposition (n=%d): overnight %.4f (t=%s) vs intraday %.4f (t=%s)",
             len(df), on["mean"], on["hac_t"], intr["mean"], intr["hac_t"])

    overnight_block = {"n": int(len(df)), "window": list(_WIN),
                       "overnight_logsum": on, "intraday_logsum": intr,
                       "overnight_dominated": bool(on["mean"] > intr["mean"] and on["mean"] > 0),
                       "gross_only": True,
                       "note": ("the pure-add run-up is OVERNIGHT-dominated (GROSS) — it accrues in "
                                "the close→open gaps, not intraday. Capturing it would need a close-buy/"
                                "open-sell execution on the live announcement feed (forward accrual); "
                                "the open-auction spread + impact on these small-cap names is UNMODELED, "
                                "so this overnight figure is a GROSS UPPER BOUND, not a net edge"
                                if on["mean"] > intr["mean"] and on["mean"] > 0 else
                                "the run-up is not overnight-dominated on our data")}

    # merge into the gate (degrade-safe)
    gp = _dir() / "validation_gate.json"
    if gp.exists():
        gate = json.loads(gp.read_text())
        gate["overnight"] = overnight_block
        gp.write_text(json.dumps(gate, indent=2))

    rp = Path(__file__).resolve().parent.parent / "reports"
    rp.mkdir(parents=True, exist_ok=True)
    (rp / "index-add-overnight-decomposition.md").write_text("\n".join([
        "# S&P pure-add run-up — overnight vs intraday decomposition", "",
        f"_Pure/net-new additions, {len(df)} events, [-5,0] window, **GROSS** SPY-relative "
        "log-returns summed over the 5 held days. Tests WHERE the run-up accrues (not net of cost)._", "",
        "| Component | mean logsum (GROSS) | share of total | HAC-t |", "|--|--:|--:|--:|",
        f"| overnight (open/prev-close) | {on['mean']} | {on['share']} | {on['hac_t']} |",
        f"| intraday (close/open) | {intr['mean']} | {intr['share']} | {intr['hac_t']} |",
        "", f"_{overnight_block['note']}._", "",
    ]))
    log.info("report -> %s", rp / "index-add-overnight-decomposition.md")


if __name__ == "__main__":
    main()
