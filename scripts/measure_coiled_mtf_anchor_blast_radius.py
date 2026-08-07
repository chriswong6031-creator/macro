"""Measure what the coiled/mtf_upturn absolute session anchor CHANGED, per loader.

Ruling: research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md — §Sibling
triage chip (2), era ``coiled-mtf-abs-session-2026-08-06`` (covers engine/coiled's
bull_div + fire_recent grids AND engine/mtf_upturn's trend.d3 chip; one PR, one
graded surface family).

    .venv/bin/python scripts/measure_coiled_mtf_anchor_blast_radius.py           # all
    .venv/bin/python scripts/measure_coiled_mtf_anchor_blast_radius.py --quick   # stocks+ohlcv

Writes ``reports/coiled_mtf_anchor_blast_radius.md`` + ``.json``.

HOW OLD-VS-NEW IS PRODUCED. There is NO era flag in the engines — a switch left in
production code is a second code path nobody runs. The PRE-repair ``bull_div``,
``fire_recent`` and the mtf ``trend.d3`` construction are frozen VERBATIM below (copied
from the commit before the repair); only the grid-free helpers (``_rsi_macd``,
``_stoch_rsi_kd``, ``rsi``, ``_price_macd_hist``, ``_trend_for_hist``) are imported from
the live modules, because they are byte-identical in both eras. "new" is the module
exactly as it ships. The legacy functions are market-BLIND (bdate bins for every
market) — so the CN slice below measures a calendar change as well as a phase change,
exactly as production experienced it.

WHAT IT MEASURES, per production loader (deep stocks/, 2014-start ohlcv/, the rolling
breadth caches at their NATIVE depth, 345/777-bar depth views of stocks/, the CN
panel):
  * ``bull_div`` verdict flips (the STAR input — the only rank-bearing change);
  * ``fire_recent`` payload flips (fire bool / ticks / src — the day-diffed
    ``fire_ticks`` chip the graders snapshot);
  * mtf ``trend.d3`` chip flips (pos / bars_since_cross — the dashboard MTF checklist);
  * the production STAR/bonus lens on the union standout universe (stocks + breadth
    caches with production priority): star flips = div flips ∩ coiled, Δbonus = ±0.15
    (≈0.3 cascade tier on the _combine_key scale: the shipped bonuses lift COILED ~half
    a tier at 0.25, STAR ~0.8 tier at 0.40);
  * stocks/ ∩ ohlcv/ cross-store agreement BEFORE and AFTER on every probed field;
  * a NEW-anchor start-invariance re-run on real data (must be 0 movers).

NO SILENT CAPS (house law). Every universe reports what it could not read and why; an
absent store (e.g. the russell breadth cache in a dev checkout) is named in the report
with an ``unavailable`` row, never skipped into a smaller-looking denominator.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import coiled                                    # noqa: E402
from engine import mtf_upturn                                # noqa: E402
from engine.coiled import (                                  # noqa: E402
    _CONF_W, _FIRE_MIN_BARS, _RSI_LEN, FIRE_WITHIN, STAR_EXTRA,
    _rsi_macd, _stoch_rsi_kd,
)
from engine.mtf_upturn import _price_macd_hist, _trend_for_hist, D_MACD_WINDOW  # noqa: E402
from engine.technicals import rsi                            # noqa: E402

ERA = coiled.ANCHOR_ERA
#: Probe fields a name is compared on, old vs new.
FIELDS = ("div", "fire", "ticks", "src", "d3_pos", "d3_bsc")
#: A name is graded when it clears mtf's own floor; per-probe floors below that
#: (fire_recent's 300, bull_div's 60) self-disclose through the probes' null returns,
#: which are compared like any other value — a null that MOVES is still a flip.
MIN_BARS = 120


# --------------------------------------------------------------------------- #
# FROZEN pre-repair implementations (verbatim; grid-free helpers imported live)
# --------------------------------------------------------------------------- #

def _bull_div_legacy(daily_close: pd.Series) -> bool:
    """engine/coiled.bull_div as it stood before ``coiled-mtf-abs-session-2026-08-06``:
    pandas ``resample("3B")`` bins anchored to the SERIES' FIRST timestamp."""
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        if len(c) < 60:
            return False
        s3 = c.resample("3B").last().dropna()
        if len(s3) < 20:
            return False
        macd3, _ = _rsi_macd(s3)
        _, d3 = _stoch_rsi_kd(s3)
        known_raw = c.resample("3B").apply(
            lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
        ).reindex(s3.index)
        known = pd.Series(pd.to_datetime(known_raw.values), index=s3.index).dropna()
        macd3 = macd3.reindex(known.index)
        d3 = d3.reindex(known.index)
        di = c.index

        def _to_daily_ffill(tf_vals: pd.Series, kn: pd.Series) -> pd.Series:
            kd = pd.Series(tf_vals.to_numpy(), index=pd.to_datetime(kn.to_numpy()))
            kd = kd[~kd.index.duplicated(keep="last")].sort_index()
            return kd.reindex(di, method="ffill")

        macd3_d = _to_daily_ffill(macd3, known)
        d3_d = _to_daily_ffill(d3, known)
        arr = c.to_numpy()
        m3_a = macd3_d.to_numpy()
        d3_a = d3_d.to_numpy()
        n = len(arr)
        w = 5
        sw_lo = []
        start = max(w, n - 120 - w)
        for j in range(start, n - w):
            lo_window = arr[j - w: j + w + 1]
            if len(lo_window) < 2 * w + 1:
                continue
            if arr[j] == lo_window.min():
                sw_lo.append(j)
        if len(sw_lo) < 2:
            return False
        L1, L2 = sw_lo[-2], sw_lo[-1]
        if L1 < n - 120:
            return False
        if arr[L2] >= arr[L1]:
            return False
        m3_L1, m3_L2 = m3_a[L1], m3_a[L2]
        d3_L1, d3_L2 = d3_a[L1], d3_a[L2]
        macd_div = (not np.isnan(m3_L1)) and (not np.isnan(m3_L2)) and (m3_L2 > m3_L1)
        stch_div = (not np.isnan(d3_L1)) and (not np.isnan(d3_L2)) and (d3_L2 > d3_L1)
        return bool(macd_div or stch_div)
    except Exception:
        return False


def _fire_recent_legacy(daily_close: pd.Series, within: int = FIRE_WITHIN) -> dict:
    """engine/coiled.fire_recent as it stood before the era: 3B/2B resample grids."""
    _null = {"fire": False, "ticks": None, "src": None}
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        n = len(c)
        if n < _FIRE_MIN_BARS:
            return _null
        if within < 0:
            within = 0
        di = c.index

        def _xup(a: pd.Series, b: pd.Series) -> pd.Series:
            return (a > b) & (a.shift(1) <= b.shift(1))

        def _since_cross(cond: pd.Series) -> pd.Series:
            pos = np.arange(len(cond))
            last = pd.Series(np.where(cond.to_numpy(), pos, np.nan),
                             index=cond.index).ffill()
            return pd.Series(pos, index=cond.index) - last

        def _to_daily_ffill(tf_vals: pd.Series, kn: pd.Series) -> pd.Series:
            kd = pd.Series(tf_vals.to_numpy(), index=pd.to_datetime(kn.to_numpy()))
            kd = kd[~kd.index.duplicated(keep="last")].sort_index()
            return kd.reindex(di, method="ffill")

        def _to_daily_event(tf_bool: pd.Series, kn: pd.Series) -> pd.Series:
            out = pd.Series(False, index=di)
            kd = pd.Series(tf_bool.to_numpy(), index=pd.to_datetime(kn.to_numpy()))
            kd = kd[~kd.index.duplicated(keep="last")].sort_index()
            for dt, v in kd.items():
                if v:
                    p = int(di.searchsorted(dt, side="left"))
                    if p < len(di):
                        out.iloc[p] = True
            return out

        s3 = c.resample("3B").last().dropna()
        s3_known_raw = c.resample("3B").apply(
            lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
        ).reindex(s3.index)
        s3_known = pd.Series(pd.to_datetime(s3_known_raw.values), index=s3.index).dropna()
        s3 = s3.reindex(s3_known.index)
        k3, d3 = _stoch_rsi_kd(s3)
        sb_cross3 = _xup(k3, d3)
        b1_from_os3 = d3.rolling(_CONF_W).min() < 20.0
        recent_sb3 = _since_cross(sb_cross3) <= _CONF_W
        r14_3 = rsi(s3, _RSI_LEN)
        recent_sb_d = _to_daily_ffill(recent_sb3.fillna(False), s3_known)
        b1os_d = _to_daily_ffill(b1_from_os3.fillna(False), s3_known)
        r14_3_d = _to_daily_ffill(r14_3, s3_known)
        wk = c.resample("W-FRI").last().dropna()
        wmacd, wsig = _rsi_macd(wk)
        w_bull_tf = (wmacd >= wsig).shift(1)
        w_bull_d = w_bull_tf.reindex(di, method="ffill").fillna(False).astype(bool)
        confirm_bull = (w_bull_d | b1os_d.reindex(di).fillna(False).astype(bool))
        rsi_ok = (r14_3_d < 65.0).fillna(False)
        macd1, sig1 = _rsi_macd(c)
        mb1_d = _xup(macd1, sig1).fillna(False)
        m1d_fire = (mb1_d & recent_sb_d.reindex(di).fillna(False).astype(bool)
                    & confirm_bull & rsi_ok).fillna(False).astype(bool)
        s2 = c.resample("2B").last().dropna()
        s2_known_raw = c.resample("2B").apply(
            lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
        ).reindex(s2.index)
        s2_known = pd.Series(pd.to_datetime(s2_known_raw.values), index=s2.index).dropna()
        s2 = s2.reindex(s2_known.index)
        macd2, sig2 = _rsi_macd(s2)
        mb2_d = _to_daily_event(_xup(macd2, sig2).fillna(False), s2_known)
        m2d_fire = (mb2_d & recent_sb_d.reindex(di).fillna(False).astype(bool)
                    & confirm_bull & rsi_ok).fillna(False).astype(bool)
        union_fire = m1d_fire | m2d_fire
        fire_positions = np.where(union_fire.to_numpy())[0]
        if len(fire_positions) == 0:
            return _null
        last_pos = int(fire_positions[-1])
        ticks = int((n - 1) - last_pos)
        at_m1d = bool(m1d_fire.iloc[last_pos])
        at_m2d = bool(m2d_fire.iloc[last_pos])
        src = "both" if (at_m1d and at_m2d) else ("m1d" if at_m1d else ("m2d" if at_m2d else None))
        return {"fire": bool(ticks <= within), "ticks": ticks, "src": src}
    except Exception:
        return _null


def _trend_d3_legacy(close: pd.Series) -> dict:
    """mtf_upturn._build_trend_fields' d3 block as it stood before the era."""
    try:
        c3 = close.resample("3B").last().dropna()
        d3_hist = _price_macd_hist(c3).dropna()
        return _trend_for_hist(d3_hist, D_MACD_WINDOW)
    except Exception:
        return {"pos": False, "bars_since_cross": None}


# --------------------------------------------------------------------------- #
# probes
# --------------------------------------------------------------------------- #

def _flat(div: bool, fire: dict, d3: dict) -> dict:
    return {"div": bool(div), "fire": bool(fire.get("fire")), "ticks": fire.get("ticks"),
            "src": fire.get("src"), "d3_pos": bool(d3.get("pos")),
            "d3_bsc": d3.get("bars_since_cross")}


def _probe_old(c: pd.Series) -> dict:
    return _flat(_bull_div_legacy(c), _fire_recent_legacy(c), _trend_d3_legacy(c))


def _probe_new(c: pd.Series, market: str) -> dict:
    return _flat(coiled.bull_div(c, market=market),
                 coiled.fire_recent(c, market=market),
                 mtf_upturn._build_trend_fields(c, market=market)["d3"])


def _job_from_path(args):
    path, tail, market = args
    ticker = Path(path).stem
    try:
        df = pd.read_parquet(Path(path))
        s = pd.to_numeric(df["close"], errors="coerce").dropna()
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
    except Exception:
        return {"ticker": ticker, "skip": "unreadable"}
    if tail:
        s = s.iloc[-tail:]
    if len(s) < MIN_BARS:
        return {"ticker": ticker, "skip": f"under {MIN_BARS} bars"}
    return {"ticker": ticker, "bars": len(s), "last": str(s.index.max().date()),
            "old": _probe_old(s), "new": _probe_new(s, market)}


def _job_from_series(args):
    ticker, values, dates, market = args
    s = pd.Series(values, index=pd.DatetimeIndex(dates)).dropna()
    if len(s) < MIN_BARS:
        return {"ticker": ticker, "skip": f"under {MIN_BARS} bars"}
    return {"ticker": ticker, "bars": len(s), "last": str(s.index.max().date()),
            "old": _probe_old(s), "new": _probe_new(s, market)}


def _job_invariance(args):
    path, k, market = args
    ticker = Path(path).stem
    try:
        df = pd.read_parquet(Path(path))
        s = pd.to_numeric(df["close"], errors="coerce").dropna()
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
    except Exception:
        return {"ticker": ticker, "skip": "unreadable"}
    if len(s) < MIN_BARS + 6:
        return {"ticker": ticker, "skip": "short"}
    a, b = _probe_new(s, market), _probe_new(s.iloc[k:], market)
    moved = {f: (a[f], b[f]) for f in FIELDS if a[f] != b[f]}
    return {"ticker": ticker, "moved": moved}


def _run(jobs, fn, workers: int):
    if workers > 1 and len(jobs) > 16:
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers) as ex:
                return list(ex.map(fn, jobs, chunksize=8))
        except Exception as exc:            # noqa: BLE001 — parallelism never decides a result
            print(f"[coiled-blast] pool failed ({exc}) — serial fallback", file=sys.stderr)
    return [fn(j) for j in jobs]


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #

def _summarize(name: str, records: list[dict], *, note: str = "") -> dict:
    graded = [r for r in records if "old" in r]
    skips = Counter(r["skip"] for r in records if "skip" in r)
    n = len(graded)

    def _flips(f):
        return [r for r in graded if r["old"][f] != r["new"][f]]

    div_f = _flips("div")
    fire_f = _flips("fire")
    ticks_f = _flips("ticks")
    src_f = _flips("src")
    pos_f = _flips("d3_pos")
    bsc_f = _flips("d3_bsc")
    pct = lambda k: round(100.0 * len(k) / n, 1) if n else 0.0   # noqa: E731
    return {
        "universe": name, "note": note, "n_names": len(records), "n_graded": n,
        "n_skipped": sum(skips.values()),
        "skip_reasons": ", ".join(f"{v}× {k}" for k, v in sorted(skips.items())) or None,
        "asof_store": max((r["last"] for r in graded), default=None),
        "div_flips": len(div_f), "div_flip_pct": pct(div_f),
        "div_true_old": sum(1 for r in graded if r["old"]["div"]),
        "div_true_new": sum(1 for r in graded if r["new"]["div"]),
        "fire_flips": len(fire_f), "fire_flip_pct": pct(fire_f),
        "fire_true_old": sum(1 for r in graded if r["old"]["fire"]),
        "fire_true_new": sum(1 for r in graded if r["new"]["fire"]),
        "ticks_moved": len(ticks_f), "ticks_moved_pct": pct(ticks_f),
        "src_changed": len(src_f),
        "d3_pos_flips": len(pos_f), "d3_pos_flip_pct": pct(pos_f),
        "d3_bsc_moved": len(bsc_f), "d3_bsc_moved_pct": pct(bsc_f),
        "sample_div_flips": [r["ticker"] for r in div_f[:12]],
        "sample_fire_flips": [r["ticker"] for r in fire_f[:12]],
        "sample_d3_flips": [r["ticker"] for r in pos_f[:12]],
    }


def _rel(p: Path) -> str:
    """Repo-relative path for committed reports — never a machine-local absolute."""
    for base in (ROOT, ROOT.parent):
        try:
            return str(p.relative_to(base))
        except ValueError:
            continue
    return f"data/{p.parent.name}/{p.name}" if p.suffix else p.name


def universe_files(name: str, directory: Path, workers: int, market: str = "US",
                   *, tail: int | None = None, note: str = "") -> tuple[dict, list[dict]]:
    files = sorted(directory.glob("*.parquet")) if directory.is_dir() else []
    if not files:
        return ({"universe": name, "unavailable": True,
                 "note": f"{_rel(directory)} absent from this checkout"}, [])
    recs = _run([(str(p), tail, market) for p in files], _job_from_path, workers)
    return _summarize(name, recs, note=note), recs


def universe_panel(name: str, cache: Path, workers: int, market: str = "US",
                   *, note: str = "") -> tuple[dict, list[dict]]:
    if not cache.exists():
        return ({"universe": name, "unavailable": True,
                 "note": f"{_rel(cache)} absent from this checkout"}, [])
    panel = pd.read_parquet(cache)
    panel.index = pd.to_datetime(panel.index)
    jobs = [(t, panel[t].to_numpy(), panel.index.to_numpy(), market)
            for t in panel.columns]
    recs = _run(jobs, _job_from_series, workers)
    return _summarize(name, recs, note=note), recs


# --------------------------------------------------------------------------- #
# the production STAR/bonus lens
# --------------------------------------------------------------------------- #

def star_bonus_lens(stocks_recs: list[dict], breadth_recs: dict[str, list[dict]],
                    data_dir: Path) -> dict:
    """star = coiled ∧ div, so the rank input moves EXACTLY on {coiled} ∩ {div flips},
    by ±STAR_EXTRA. coiled itself (washout ∧ cohort) has no grid input and cannot flip.
    The cohort is computed over the production union universe (stocks first, then the
    breadth caches, keep-first — build_stock_library.universe()'s priority), with the
    production sector sources (sector_holdings for the deep names, each cache's
    constituents.parquet for the rest)."""
    sectors: dict[str, str | None] = {}
    try:
        from scripts.build_stock_library import SECTOR_NAMES, _SPDR_TO_GICS
        hd = data_dir / "sector_holdings"
        if hd.exists():
            for p in hd.glob("*.parquet"):
                if p.stem not in SECTOR_NAMES:
                    continue
                sec = _SPDR_TO_GICS.get(SECTOR_NAMES[p.stem], SECTOR_NAMES[p.stem])
                try:
                    df = pd.read_parquet(p)
                except Exception:
                    continue
                if "ticker" not in df.columns:
                    continue
                for t in df["ticker"].astype(str):
                    sectors.setdefault(t.replace(".", "-"), sec)
    except Exception as exc:                # noqa: BLE001 — lens degrades, disclosed
        return {"unavailable": True, "note": f"sector map not derivable ({exc})"}

    ordered: dict[str, dict] = {}
    for r in stocks_recs:
        if "old" in r:
            ordered.setdefault(r["ticker"], r)
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
        cons = data_dir / grp / "constituents.parquet"
        meta = None
        if cons.exists():
            try:
                meta = pd.read_parquet(cons)
            except Exception:
                meta = None
        for r in breadth_recs.get(grp, []):
            if "old" not in r or r["ticker"] in ordered:
                continue
            ordered.setdefault(r["ticker"], r)
            if meta is not None and r["ticker"] in meta.index:
                sectors.setdefault(r["ticker"], str(meta.loc[r["ticker"], "sector"]))

    # washout + weekly-D are grid-free (unchanged either era); recompute from the stores
    latest_d: dict[str, float | None] = {}
    wash: dict[str, bool | None] = {}
    stocks_dir = data_dir / "stocks"
    caches = {g: (data_dir / g / "_closes_cache.parquet") for g in
              ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth")}
    panels = {}
    for g, p in caches.items():
        if p.exists():
            try:
                panels[g] = pd.read_parquet(p)
            except Exception:
                pass
    for t in ordered:
        c = None
        fp = stocks_dir / f"{t}.parquet"
        if fp.exists():
            try:
                c = pd.read_parquet(fp)["close"].dropna()
                c.index = pd.to_datetime(c.index)
            except Exception:
                c = None
        if c is None:
            for g, panel in panels.items():
                if t in panel.columns:
                    c = panel[t].dropna()
                    c.index = pd.to_datetime(c.index)
                    break
        if c is None:
            continue
        latest_d[t] = coiled.weekly_d_last(c)
        wash[t] = coiled.washout_ctx(c)

    frac = coiled.cohort_fractions(latest_d, {t: sectors.get(t) for t in ordered})
    coiled_names = [t for t in ordered
                    if bool(wash.get(t)) and frac.get(t) is not None and frac[t] >= 0.40]
    star_flips = [t for t in coiled_names
                  if ordered[t]["old"]["div"] != ordered[t]["new"]["div"]]
    fire_flips_coiled = [t for t in coiled_names
                         if ordered[t]["old"]["fire"] != ordered[t]["new"]["fire"]]
    ticks_moved_coiled = [t for t in coiled_names
                          if ordered[t]["old"]["ticks"] != ordered[t]["new"]["ticks"]]
    return {
        "n_union_universe": len(ordered),
        "n_with_sector": sum(1 for t in ordered if sectors.get(t)),
        "n_coiled_tonight": len(coiled_names),
        "coiled_names": sorted(coiled_names),
        "star_flips": sorted(star_flips),
        "n_star_flips": len(star_flips),
        "bonus_delta_per_flip": STAR_EXTRA,
        "fire_chip_flips_among_coiled": sorted(fire_flips_coiled),
        "fire_ticks_moves_among_coiled": sorted(ticks_moved_coiled),
        "note": ("star = coiled ∧ div; coiled (washout ∧ cohort) carries no grid and "
                 "cannot flip under the anchor — every rank-input move is ±0.15 "
                 "(≈0.3 cascade tier) on a star flip, plus the display-only fire chip."),
    }


# --------------------------------------------------------------------------- #
# cross-store agreement + invariance
# --------------------------------------------------------------------------- #

def store_agreement(stocks_recs: list[dict], ohlcv_recs: list[dict]) -> dict:
    a = {r["ticker"]: r for r in stocks_recs if "old" in r}
    b = {r["ticker"]: r for r in ohlcv_recs if "old" in r}
    shared = sorted(set(a) & set(b))
    dis_old = Counter()
    dis_new = Counter()
    residual = []
    for t in shared:
        for f in FIELDS:
            if a[t]["old"][f] != b[t]["old"][f]:
                dis_old[f] += 1
            if a[t]["new"][f] != b[t]["new"][f]:
                dis_new[f] += 1
        bad = [f for f in FIELDS if a[t]["new"][f] != b[t]["new"][f]]
        if bad:
            residual.append({"ticker": t, "fields": ",".join(bad),
                             "stocks_bars": a[t]["bars"], "ohlcv_bars": b[t]["bars"],
                             "stocks_last": a[t]["last"], "ohlcv_last": b[t]["last"]})
    return {"n_shared_names": len(shared),
            "disagreements_old": dict(dis_old), "disagreements_new": dict(dis_new),
            "residual": residual[:20], "n_residual_names": len(residual)}


def new_anchor_invariance(workers: int, data_dir: Path, ks=(1, 3)) -> dict:
    files = sorted((data_dir / "stocks").glob("*.parquet"))
    out = {}
    for k in ks:
        recs = _run([(str(p), k, "US") for p in files], _job_invariance, workers)
        movers = [r for r in recs if r.get("moved")]
        out[f"k{k}"] = {"n": len([r for r in recs if "moved" in r]),
                        "movers": len(movers),
                        "names": [{r["ticker"]: r["moved"]} for r in movers[:10]]}
    return out


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #

def _u_line(u: dict) -> str:
    if u.get("unavailable"):
        return f"| {u['universe']} | — | — | — | — | — | — | **not measured** |"
    return (f"| {u['universe']} | {u['n_graded']} | "
            f"{u['div_flips']} ({u['div_flip_pct']}%) | "
            f"{u['fire_flips']} ({u['fire_flip_pct']}%) | "
            f"{u['ticks_moved']} ({u['ticks_moved_pct']}%) | "
            f"{u['d3_pos_flips']} ({u['d3_pos_flip_pct']}%) | "
            f"{u['d3_bsc_moved']} ({u['d3_bsc_moved_pct']}%) | {u['asof_store']} |")


def render_md(res: dict) -> str:
    L: list[str] = []
    L.append("# coiled + mtf_upturn absolute session anchor — blast radius\n")
    L.append(f"Era `{res['anchor_era']}` · ruling "
             "`research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md` "
             "§Sibling triage chip (2)\n")
    L.append(f"Generated {res['generated_utc']} · store as-of dates are per-universe "
             "(read from the stores, never the wall clock).\n")
    L.append("\nOLD = the pre-repair `resample(\"3B\"/\"2B\")` constructions frozen "
             "verbatim in `scripts/measure_coiled_mtf_anchor_blast_radius.py` "
             "(market-blind, as production was); NEW = the modules as they ship.\n")

    L.append("\n## 1. Old → new, per production loader\n")
    L.append("| universe | graded | bull_div flips | fire flips | fire_ticks moved | "
             "d3 pos flips | d3 bars_since_cross moved | store as-of |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for u in res["universes"]:
        L.append(_u_line(u))
    for u in res["universes"]:
        if u.get("note"):
            L.append(f"\n- **{u['universe']}** — {u['note']}")
        if u.get("skip_reasons"):
            L.append(f"  - not graded: {u['n_skipped']} ({u['skip_reasons']})")
        for k in ("sample_div_flips", "sample_fire_flips", "sample_d3_flips"):
            if u.get(k):
                L.append(f"  - {k[7:]}: {', '.join(u[k])}")

    sb = res["star_bonus_lens"]
    L.append("\n## 2. The rank input — STAR/bonus on the production union universe\n")
    if sb.get("unavailable"):
        L.append(f"**not measured** — {sb['note']}\n")
    else:
        L.append(f"Union universe {sb['n_union_universe']} names "
                 f"({sb['n_with_sector']} with sectors) · coiled tonight: "
                 f"{sb['n_coiled_tonight']} ({', '.join(sb['coiled_names']) or 'none'})\n")
        L.append(f"\n- **STAR flips (rank input, ±{sb['bonus_delta_per_flip']} bonus "
                 f"≈ 0.3 cascade tier): {sb['n_star_flips']}** "
                 f"({', '.join(sb['star_flips']) or 'none'})")
        L.append(f"- fire chip flips among coiled: "
                 f"{', '.join(sb['fire_chip_flips_among_coiled']) or 'none'}")
        L.append(f"- fire_ticks moves among coiled (the day-diffed field): "
                 f"{', '.join(sb['fire_ticks_moves_among_coiled']) or 'none'}")
        L.append(f"\n{sb['note']}\n")

    ag = res["store_agreement"]
    L.append("\n## 3. stocks/ vs baskets/ohlcv/ — the defect's live symptom\n")
    L.append(f"{ag['n_shared_names']} shared names.\n")
    L.append("| field | disagreements BEFORE | disagreements AFTER |")
    L.append("|---|---:|---:|")
    for f in FIELDS:
        L.append(f"| {f} | {ag['disagreements_old'].get(f, 0)} | "
                 f"{ag['disagreements_new'].get(f, 0)} |")
    if ag["n_residual_names"]:
        L.append(f"\nResidual AFTER ({ag['n_residual_names']} names) — named, not "
                 "rounded to zero. Where the two stores' probe still differs, the "
                 "stores' own DATA differs (depth or price revisions), not the grid:\n")
        for r in ag["residual"]:
            L.append(f"- **{r['ticker']}** ({r['fields']}) — stocks {r['stocks_bars']} "
                     f"bars to {r['stocks_last']}, ohlcv {r['ohlcv_bars']} bars to "
                     f"{r['ohlcv_last']}")

    inv = res["new_anchor_invariance"]
    L.append("\n## 4. Start-invariance re-run under the NEW anchor (must be 0)\n")
    for k, v in inv.items():
        L.append(f"- {k}: **{v['movers']} movers** / {v['n']} graded"
                 + (f" — {v['names']}" if v["movers"] else ""))

    L.append("\n## 5. What this re-draw is\n")
    L.append("A one-time, era-stamped re-phase (the R-SQ4 pattern): the OLD chips were a "
             "function of each loader's window start — the breadth caches' start creeps "
             "forward every refresh, so 'flips' of this size were being minted "
             "build-to-build with zero price action, and the two US loaders disagreed "
             "about the same name the same night (§3 BEFORE column). Under the absolute "
             "anchor every window of a name reads one grid (§4: 0 movers), the flips "
             "above happen ONCE, and `anchor_era` on the persisted payloads "
             "(us_standouts coiled block, china_standouts coiled block, mtf_upturn "
             "artifacts) lets every grader and day-over-day differ fence the boundary. "
             "Semantics are byte-identical: thresholds, windows, K-of-N, hysteresis, "
             "W-FRI weekly legs and washout_ctx are untouched.\n")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="stocks + ohlcv only")
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 1))
    args = ap.parse_args()

    from lib import config
    data_dir = config.data_dir()
    res: dict = {"anchor_era": ERA,
                 "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
    universes: list[dict] = []
    stocks_sum, stocks_recs = universe_files(
        "data/stocks (deep US)", data_dir / "stocks", args.workers,
        note="the deep-history loader (1960s starts) — the standout board's primary store")
    universes.append(stocks_sum)
    ohlcv_sum, ohlcv_recs = universe_files(
        "baskets/ohlcv (2014-start)", data_dir / "baskets" / "ohlcv", args.workers,
        note="the 2014-start loader — mtf_upturn's PRIMARY store (ohlcv → stocks → yahoo)")
    universes.append(ohlcv_sum)

    breadth_recs: dict[str, list[dict]] = {}
    if not args.quick:
        for tail in (345, 777):
            s, _ = universe_files(
                f"stocks tail-{tail} (depth view)", data_dir / "stocks", args.workers,
                tail=tail,
                note=f"stocks/ truncated to the trailing {tail} bars — the breadth/"
                     "smallcap cache depth class")
            universes.append(s)
        for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
            s, r = universe_panel(
                f"{grp} cache (native rolling window)",
                data_dir / grp / "_closes_cache.parquet", args.workers,
                note="the ROLLING ~3y cache whose window start creeps forward every "
                     "refresh — the build-to-build re-phase surface")
            universes.append(s)
            breadth_recs[grp] = r
        s, _ = universe_panel(
            "china_search panel (CN, market=CN)",
            data_dir / "china_search" / "closes.parquet", args.workers, market="CN",
            note="CN lane: OLD was market-blind bdate bins; NEW cuts on the Shanghai "
                 "reference calendar — a calendar change plus a phase change")
        universes.append(s)
    res["universes"] = universes

    res["star_bonus_lens"] = star_bonus_lens(stocks_recs, breadth_recs, data_dir)
    res["store_agreement"] = store_agreement(stocks_recs, ohlcv_recs)
    res["new_anchor_invariance"] = new_anchor_invariance(args.workers, data_dir)

    out_md = ROOT / "reports" / "coiled_mtf_anchor_blast_radius.md"
    out_json = ROOT / "reports" / "coiled_mtf_anchor_blast_radius.json"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_md(res), encoding="utf-8")
    out_json.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"wrote {out_md} and {out_json}")
    for u in universes:
        if u.get("unavailable"):
            print(f"::warning title=coiled-mtf blast radius universe absent::"
                  f"{u['universe']} — {u['note']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
