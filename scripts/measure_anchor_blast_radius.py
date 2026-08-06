"""Measure what the absolute session anchor CHANGED, per production loader — charter §SHIP 1.

Ruling: research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md
(era ``abs-session-2026-08-06``).

    .venv/bin/python scripts/measure_anchor_blast_radius.py            # every universe
    .venv/bin/python scripts/measure_anchor_blast_radius.py --quick    # stocks + ohlcv only

Writes ``reports/session_anchor_blast_radius.md`` + ``.json``.

HOW OLD-VS-NEW IS PRODUCED. There is NO era flag in the engine — a switch left in production
code is a second code path nobody runs. Instead the PRE-repair ``_tf_bars`` and
``_completed_resample`` are frozen VERBATIM below (copied from e6d3ead09af, the commit before
the repair) and monkeypatched into ``engine.confluence_tiers`` for the duration of a
measurement pass. "new" is the module exactly as it ships.

WHAT IT MEASURES
  1. stocks/          old->new tier transition matrix, veto flips, eligible delta
  2. baskets/ohlcv/   same, on the 2014-start loader
  3. massive_stock_day the real scan-tier universe via engine.us_scan_universe's own floor
  4. depth views      stocks/ truncated to 345 and 777 trailing bars (the breadth/smallcap
                      cache depths that reach cascade() in production)
  5. CN panel         data/china_search/closes.parquet, market="CN"
  6. HK stores        data/hk/*.HK.parquet, market="HK"
  plus: stocks/ vs ohlcv/ AGREEMENT before and after (the NUE/PEP/ECL/SW/WMT quintet printed
  by name), a NEW-anchor start-invariance re-run on real data (must be 0 flips), and the
  345-bar depth residual bucketed by reason.

NO SILENT CAPS (house law). Every universe reports the names it could not read and WHY; a
store that is absent from the checkout is named in the report and annotated, never skipped
into a smaller-looking denominator.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import confluence_tiers as ct          # noqa: E402
from engine.confluence_tiers import MIN_HISTORY    # noqa: E402

#: The five names the audit called out: buyable from data/stocks and rejected from
#: baskets/ohlcv the same night (or inverted). They are the report's headline table.
QUINTET = ("NUE", "PEP", "ECL", "SW", "WMT")
#: Depth views that reach cascade() in production (breadth cache / smallcap cache).
DEPTH_VIEWS = (345, 777)
#: Fields a verdict is compared on.
FIELDS = ("tier", "not_topped", "eligible")


# --------------------------------------------------------------------------- #
# FROZEN pre-repair implementations (verbatim, e6d3ead09af) + the era switch
# --------------------------------------------------------------------------- #

def _tf_bars_legacy(daily, n, market="US"):      # noqa: ARG001 — market ignored ON PURPOSE
    """The pre-repair grid: pandas bins anchored to the SERIES' FIRST timestamp.

    ``market`` is accepted and DISCARDED, which is itself part of the measured delta: before
    the repair every market was bucketed by the same market-blind calendar-business-day rule.
    """
    s = daily.resample(f"{n}B").last().dropna()
    known = daily.resample(f"{n}B").apply(
        lambda x: x.dropna().index.max()).reindex(s.index).dropna()
    return s.reindex(known.index), pd.Series(pd.to_datetime(known.values), index=known.index)


def _completed_resample_legacy(daily: pd.Series, rule: str):
    """The pre-repair completed-bucket resample — pandas for BOTH W-FRI and 2W-FRI, so the
    fortnight phase follows the series start."""
    last_obs = daily.index.max()
    raw = daily.resample(rule).last().dropna()
    raw = raw[raw.index <= last_obs]
    known = (
        daily.resample(rule)
        .apply(lambda x: x.dropna().index.max())
        .reindex(raw.index)
        .dropna()
    )
    raw = raw.reindex(known.index)
    known_dt = pd.Series(pd.to_datetime(known.values), index=known.index)
    return raw, known_dt


@contextmanager
def legacy_anchor():
    """Run the block with the PRE-repair bucketing in force."""
    new_tf, new_cr = ct._tf_bars, ct._completed_resample
    ct._tf_bars, ct._completed_resample = _tf_bars_legacy, _completed_resample_legacy
    try:
        yield
    finally:
        ct._tf_bars, ct._completed_resample = new_tf, new_cr


def _verdict(c: pd.Series, market: str, era: str) -> dict:
    if era == "old":
        with legacy_anchor():
            v = ct.cascade(c, market=market)
    else:
        v = ct.cascade(c, market=market)
    return {f: v.get(f) for f in FIELDS}


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #

def _close_from_parquet(path: Path) -> pd.Series | None:
    try:
        df = pd.read_parquet(path, columns=["close"])
    except Exception:
        try:
            df = pd.read_parquet(path)
        except Exception:
            return None
    col = "close" if "close" in df.columns else (df.columns[0] if len(df.columns) else None)
    if col is None:
        return None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if not isinstance(s.index, pd.DatetimeIndex):
        try:
            s.index = pd.to_datetime(s.index)
        except Exception:
            return None
    return s.sort_index()


def _file_universe(directory: Path, pattern: str = "*.parquet") -> list[Path]:
    return sorted(directory.glob(pattern)) if directory.is_dir() else []


# --------------------------------------------------------------------------- #
# workers (module-level so a process Pool can pickle them)
# --------------------------------------------------------------------------- #

def _job_from_path(args):
    """(path, market, tail) -> {ticker, old, new, bars, last} or a skip record."""
    path, market, tail = args
    c = _close_from_parquet(Path(path))
    ticker = Path(path).stem
    if c is None:
        return {"ticker": ticker, "skip": "unreadable"}
    if tail:
        c = c.iloc[-tail:]
    if len(c) < MIN_HISTORY:
        return {"ticker": ticker, "skip": f"under MIN_HISTORY ({len(c)} bars)"}
    return {"ticker": ticker, "bars": len(c), "last": str(c.index.max().date()),
            "old": _verdict(c, market, "old"), "new": _verdict(c, market, "new")}


def _job_from_series(args):
    """(ticker, values, dates, market) -> the same record, for wide-panel sources."""
    ticker, values, dates, market = args
    c = pd.Series(values, index=pd.DatetimeIndex(dates)).dropna()
    if len(c) < MIN_HISTORY:
        return {"ticker": ticker, "skip": f"under MIN_HISTORY ({len(c)} bars)"}
    return {"ticker": ticker, "bars": len(c), "last": str(c.index.max().date()),
            "old": _verdict(c, market, "old"), "new": _verdict(c, market, "new")}


def _run(jobs, fn, workers: int):
    if workers > 1 and len(jobs) > 16:
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers) as ex:
                return list(ex.map(fn, jobs, chunksize=8))
        except Exception as exc:            # noqa: BLE001 — parallelism never decides a result
            print(f"[blast] pool failed ({exc}) — serial fallback", file=sys.stderr)
    return [fn(j) for j in jobs]


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #

def _summarize(name: str, records: list[dict], *, note: str = "") -> dict:
    graded = [r for r in records if r and "skip" not in r]
    skipped = [r for r in records if r and "skip" in r]
    transitions = Counter()
    veto_flips, elig_old, elig_new, tier_flips = 0, 0, 0, 0
    flipped_names: list[dict] = []
    for r in graded:
        o, n = r["old"], r["new"]
        transitions[(str(o["tier"]), str(n["tier"]))] += 1
        if o["tier"] != n["tier"]:
            tier_flips += 1
        if bool(o["not_topped"]) != bool(n["not_topped"]):
            veto_flips += 1
        elig_old += bool(o["eligible"])
        elig_new += bool(n["eligible"])
        if o != n:
            flipped_names.append({"ticker": r["ticker"], "bars": r["bars"],
                                  "old": o, "new": n})
    asof = max((r["last"] for r in graded), default=None)      # store date, not wall clock
    return {
        "universe": name,
        "note": note,
        "n_read": len(records),
        "n_graded": len(graded),
        "n_skipped": len(skipped),
        "skip_reasons": dict(Counter(r["skip"].split(" (")[0] for r in skipped)),
        "asof_store": asof,
        "tier_flips": tier_flips,
        "tier_flip_pct": round(100.0 * tier_flips / len(graded), 2) if graded else None,
        "veto_flips": veto_flips,
        "veto_flip_pct": round(100.0 * veto_flips / len(graded), 2) if graded else None,
        "eligible_old": elig_old,
        "eligible_new": elig_new,
        "eligible_delta": elig_new - elig_old,
        "transitions": {f"{a}->{b}": n for (a, b), n in sorted(transitions.items())
                        if a != b},
        "flipped_names": sorted(flipped_names, key=lambda r: r["ticker"]),
    }


# --------------------------------------------------------------------------- #
# universes
# --------------------------------------------------------------------------- #

def universe_files(name: str, directory: Path, market: str, workers: int,
                   *, tail: int | None = None, pattern: str = "*.parquet",
                   note: str = "") -> dict:
    paths = _file_universe(directory, pattern)
    if not paths:
        print(f"::warning title=blast-radius-universe-absent::{name}: "
              f"{directory.relative_to(ROOT)} holds no {pattern} — universe NOT measured",
              flush=True)
        return {"universe": name, "note": f"ABSENT: no {pattern} under "
                f"{directory.relative_to(ROOT)} in this checkout", "n_read": 0,
                "n_graded": 0, "unavailable": True}
    jobs = [(str(p), market, tail) for p in paths]
    return _summarize(name, _run(jobs, _job_from_path, workers), note=note)


def universe_scan_tier(workers: int) -> dict:
    """The REAL massive_stock_day scan universe, resolved by us_scan_universe's own floor."""
    from engine import us_scan_universe as usu
    if not usu.store_available(ROOT):
        d = usu.store_dir(ROOT)
        n = len(list(d.glob("*.parquet"))) if d.is_dir() else 0
        print("::warning title=blast-radius-scan-tier-absent::massive_stock_day is "
              "R2-canonical and not restored in this checkout — scan tier NOT measured",
              flush=True)
        return {"universe": "massive_stock_day (scan tier)", "unavailable": True,
                "n_read": 0, "n_graded": 0,
                "note": (f"ABSENT: {d.relative_to(ROOT)} holds {n} per-ticker parquets "
                         "(R2-canonical; restored only in a lane that pulls it). The scan-tier "
                         "delta is UNMEASURED here — run this script in a restored lane.")}
    tickers, disclosure = usu.resolve(ROOT)
    d = usu.store_dir(ROOT)
    jobs = [(str(d / f"{t}.parquet"), "US", None) for t in tickers]
    out = _summarize("massive_stock_day (scan tier)", _run(jobs, _job_from_path, workers),
                     note="floor + listing rule from engine.us_scan_universe.resolve")
    out["floor_disclosure"] = disclosure
    return out


def universe_cn(workers: int) -> dict:
    p = ROOT / "data" / "china_search" / "closes.parquet"
    if not p.exists():
        print("::warning title=blast-radius-cn-absent::data/china_search/closes.parquet "
              "missing — CN panel NOT measured", flush=True)
        return {"universe": "CN china_search panel", "unavailable": True,
                "n_read": 0, "n_graded": 0, "note": "ABSENT: data/china_search/closes.parquet"}
    wide = pd.read_parquet(p)
    if not isinstance(wide.index, pd.DatetimeIndex):
        wide.index = pd.to_datetime(wide.index)
    dates = wide.index.to_numpy()
    jobs = [(str(col), wide[col].to_numpy(), dates, "CN") for col in wide.columns]
    return _summarize(
        "CN china_search panel", _run(jobs, _job_from_series, workers),
        note=("old era = the market-BLIND business-day resample every market used to get; "
              "new era = the Shanghai reference calendar. That IS the shipped CN delta."))


# --------------------------------------------------------------------------- #
# cross-store agreement + invariance + depth residual
# --------------------------------------------------------------------------- #

def store_agreement(workers: int) -> dict:
    """stocks/ vs baskets/ohlcv/ on the SHARED last date, BEFORE and AFTER. Target: 0 after."""
    a_dir, b_dir = ROOT / "data" / "stocks", ROOT / "data" / "baskets" / "ohlcv"
    shared = sorted({p.stem for p in _file_universe(a_dir)}
                    & {p.stem for p in _file_universe(b_dir)})
    rows, disagree = [], {"old": Counter(), "new": Counter()}
    quintet_rows = []
    for t in shared:
        ca, cb = _close_from_parquet(a_dir / f"{t}.parquet"), _close_from_parquet(b_dir / f"{t}.parquet")
        if ca is None or cb is None:
            continue
        last = min(ca.index.max(), cb.index.max())
        ca, cb = ca[ca.index <= last], cb[cb.index <= last]
        if len(ca) < MIN_HISTORY or len(cb) < MIN_HISTORY:
            continue
        rec = {"ticker": t, "last": str(last.date()),
               "bars_stocks": len(ca), "bars_ohlcv": len(cb)}
        for era in ("old", "new"):
            va, vb = _verdict(ca, "US", era), _verdict(cb, "US", era)
            rec[era] = {"stocks": va, "ohlcv": vb}
            for f in FIELDS:
                if va[f] != vb[f]:
                    disagree[era][f] += 1
        rows.append(rec)
        if t in QUINTET:
            quintet_rows.append(rec)
    return {
        "n_shared_names": len(rows),
        "disagreements_old": dict(disagree["old"]),
        "disagreements_new": dict(disagree["new"]),
        "quintet": sorted(quintet_rows, key=lambda r: QUINTET.index(r["ticker"])),
        "asof_store": max((r["last"] for r in rows), default=None),
    }


def _job_invariance(args):
    path, k = args
    c = _close_from_parquet(Path(path))
    if c is None or len(c) < MIN_HISTORY + k:
        return None
    a, b = _verdict(c, "US", "new"), _verdict(c.iloc[k:], "US", "new")
    return {"ticker": Path(path).stem,
            "tier_flip": a["tier"] != b["tier"],
            "veto_flip": bool(a["not_topped"]) != bool(b["not_topped"]),
            "elig_flip": bool(a["eligible"]) != bool(b["eligible"])}


def new_anchor_invariance(workers: int, k: int = 3) -> dict:
    """The claim, re-run on REAL data under the shipped engine: dropping k leading bars must
    move nothing. Anything but 0/0/0 means the anchor is still leaking."""
    jobs = [(str(p), k) for p in _file_universe(ROOT / "data" / "stocks")]
    recs = [r for r in _run(jobs, _job_invariance, workers) if r]
    return {"k_bars_dropped": k, "n_names": len(recs),
            "tier_flips": sum(r["tier_flip"] for r in recs),
            "veto_flips": sum(r["veto_flip"] for r in recs),
            "eligible_flips": sum(r["elig_flip"] for r in recs),
            "flipped": [r["ticker"] for r in recs if r["tier_flip"] or r["veto_flip"]]}


def _job_depth_residual(args):
    path, tail = args
    c = _close_from_parquet(Path(path))
    if c is None or len(c) < MIN_HISTORY:
        return None
    full = _verdict(c, "US", "new")
    cut = c.iloc[-tail:]
    if len(cut) < MIN_HISTORY:
        return None
    short = _verdict(cut, "US", "new")
    if full == short:
        return None
    nulls = ct.cascade(cut)["null_legs"] or {}
    reason = "wbull-arm (weekly confirm not yet knowable)" if "wbull" in nulls else "other"
    return {"ticker": Path(path).stem, "full": full, "short": short,
            "reason": reason, "null_legs": sorted(nulls)}


def depth_residual(workers: int, tail: int) -> dict:
    """Names whose truncated-to-``tail`` verdict differs from full depth under the NEW anchor.

    This is a DEPTH effect, not an anchor effect (R8): a shallower window genuinely cannot
    compute the deeper legs, and says so in null_legs. Disclosed, not fixed.
    """
    jobs = [(str(p), tail) for p in _file_universe(ROOT / "data" / "stocks")]
    recs = [r for r in _run(jobs, _job_depth_residual, workers) if r]
    return {"tail_bars": tail, "n_differing": len(recs),
            "by_reason": dict(Counter(r["reason"] for r in recs)),
            "names": sorted(recs, key=lambda r: r["ticker"])}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def _u_line(u: dict) -> str:
    if u.get("unavailable"):
        return f"| {u['universe']} | — | — | — | — | **not measured** |"
    return (f"| {u['universe']} | {u['n_graded']} | {u['tier_flips']} "
            f"({u['tier_flip_pct']}%) | {u['veto_flips']} ({u['veto_flip_pct']}%) | "
            f"{u['eligible_old']} → {u['eligible_new']} ({u['eligible_delta']:+d}) | "
            f"{u['asof_store']} |")


def render_md(res: dict) -> str:
    L: list[str] = []
    L.append("# Absolute session anchor — blast radius\n")
    L.append(f"Era `{res['anchor_era']}` · ruling "
             "`research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`\n")
    L.append(f"Generated {res['generated_utc']} · store as-of dates are per-universe "
             "(read from the stores, never the wall clock).\n")

    L.append("\n## 1. Old → new, per production loader\n")
    L.append("| universe | graded | tier flips | veto flips | eligible | store as-of |")
    L.append("|---|---:|---:|---:|---|---|")
    for u in res["universes"]:
        L.append(_u_line(u))
    for u in res["universes"]:
        if u.get("note"):
            L.append(f"\n- **{u['universe']}** — {u['note']}")
        if u.get("skip_reasons"):
            L.append(f"  - not graded: {u['n_skipped']} ({u['skip_reasons']})")

    L.append("\n## 2. Tier transition matrices (changed cells only)\n")
    for u in res["universes"]:
        if u.get("unavailable"):
            continue
        L.append(f"\n**{u['universe']}** — {u['transitions'] or 'no tier changed'}")

    ag = res["store_agreement"]
    L.append("\n## 3. stocks/ vs baskets/ohlcv/ — the defect's live symptom\n")
    L.append(f"{ag['n_shared_names']} shared names, aligned to each pair's shared last date "
             f"(store as-of {ag['asof_store']}).\n")
    L.append("| field | disagreements BEFORE | disagreements AFTER |")
    L.append("|---|---:|---:|")
    for f in FIELDS:
        L.append(f"| {f} | {ag['disagreements_old'].get(f, 0)} | "
                 f"{ag['disagreements_new'].get(f, 0)} |")
    L.append("\n### The audit quintet\n")
    L.append("| name | bars stocks / ohlcv | BEFORE stocks | BEFORE ohlcv | "
             "AFTER stocks | AFTER ohlcv |")
    L.append("|---|---|---|---|---|---|")

    def _fmt(v):
        return f"{v['tier']}/nt={v['not_topped']}/e={v['eligible']}"
    for r in ag["quintet"]:
        L.append(f"| {r['ticker']} | {r['bars_stocks']} / {r['bars_ohlcv']} | "
                 f"{_fmt(r['old']['stocks'])} | {_fmt(r['old']['ohlcv'])} | "
                 f"{_fmt(r['new']['stocks'])} | {_fmt(r['new']['ohlcv'])} |")

    inv = res["new_anchor_invariance"]
    L.append("\n## 4. Start-invariance re-run on real data (NEW anchor)\n")
    L.append(f"`cascade(c)` vs `cascade(c.iloc[{inv['k_bars_dropped']}:])` over "
             f"{inv['n_names']} data/stocks names: **{inv['tier_flips']} tier flips, "
             f"{inv['veto_flips']} veto flips, {inv['eligible_flips']} eligibility flips**.")
    if inv["flipped"]:
        L.append(f"\n- STILL FLIPPING: {inv['flipped']}")

    L.append("\n## 5. Depth residual (honest, NOT an anchor effect)\n")
    for dr in res["depth_residual"]:
        L.append(f"\n- **{dr['tail_bars']}-bar view**: {dr['n_differing']} of "
                 f"{res['universes'][0]['n_graded']} names differ from full depth under the "
                 f"NEW anchor — by reason {dr['by_reason'] or '{}'}. A shallower window "
                 f"genuinely cannot compute the deeper legs; every one is disclosed in "
                 f"`null_legs` (R8 keeps this a depth effect, not something the anchor fixes).")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="stocks/ + ohlcv/ + agreement only (skips scan tier, CN, HK, depths)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    w = args.workers
    print(f"[blast] workers={w} era={ct.ANCHOR_ERA}", file=sys.stderr)

    universes = [
        universe_files("data/stocks", ROOT / "data" / "stocks", "US", w,
                       note="the deep US loader (1960s-2000s starts)"),
        universe_files("data/baskets/ohlcv", ROOT / "data" / "baskets" / "ohlcv", "US", w,
                       note="the 2014-start US loader"),
    ]
    depth = []
    if not args.quick:
        for tail in DEPTH_VIEWS:
            universes.append(universe_files(
                f"data/stocks @{tail} bars", ROOT / "data" / "stocks", "US", w, tail=tail,
                note=f"stocks/ truncated to the trailing {tail} bars (a production cache depth)"))
        universes.append(universe_scan_tier(w))
        universes.append(universe_cn(w))
        universes.append(universe_files("HK stores", ROOT / "data" / "hk", "HK", w,
                                        pattern="*.HK.parquet",
                                        note="data/hk/*.HK.parquet, market=HK"))
        depth = [depth_residual(w, t) for t in DEPTH_VIEWS]

    res = {
        "anchor_era": ct.ANCHOR_ERA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "min_history": MIN_HISTORY,
        "universes": universes,
        "store_agreement": store_agreement(w),
        "new_anchor_invariance": new_anchor_invariance(w),
        "depth_residual": depth,
    }
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "session_anchor_blast_radius.json").write_text(json.dumps(res, indent=2, default=str))
    (out / "session_anchor_blast_radius.md").write_text(render_md(res))
    print(f"[blast] wrote {out / 'session_anchor_blast_radius.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
