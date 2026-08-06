"""Blast radius of era ``cyc-abs-session-2026-08-06`` — the cycle-ladder absolute anchor.

Ruling: ``research/CYCLES_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`` (ship requirement 1).
Mirrors ``scripts/measure_sq_anchor_blast_radius.py`` (the R-SQ4 pattern): the OLD
construction is frozen VERBATIM in this file and monkeypatched in for the OLD pass, so
the comparison is old-grid-vs-new-grid with everything else held fixed.

Measures, per production loader (deep data/stocks; 2014-start baskets/ohlcv; the ~345-bar
rolling breadth cache; the 2021-start CN search panel; the HK/CA index stores):

* ladder STATE flips and ``signal_date`` re-keys (the ladder-log phantom-row surface);
* ``mtf_alignment`` tier / admission (aligned) flips — the standout-strip SELECTION gate;
* cross-loader same-night agreement BEFORE and AFTER (deep vs ohlcv, deep vs breadth
  cache) — the live symptom: two loaders, one name, one night, two stories;
* ``calibrate_ladder`` old-vs-new per-state table drift on a bounded deep panel, plus the
  fixed-vs-slid window agreement (R-CY6b — the intra-run re-anchoring, healed);
* the ladder-log cutover simulated against a COPY of the real log (R-CY5): appended
  re-draw rows vs suppressed re-key duplicates, so the one-time insertion is a measured
  bound, not a hope;
* a NEW-anchor start-invariance re-run (k = 1..3) — must be 0 movers.

Writes ``reports/cycles_anchor_blast_radius.md`` + ``.json``. Store as-of dates are read
from the stores, never the wall clock. Absent universes are announced with a GitHub
``::warning`` (the A5 precedent), never silently skipped.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import cycles, ticker_alerts  # noqa: E402
from lib import config  # noqa: E402

REPORT_MD = Path("reports/cycles_anchor_blast_radius.md")
REPORT_JSON = Path("reports/cycles_anchor_blast_radius.json")

#: fields compared per name; signal_date is the ladder-log key, tier/aligned the board gate
_FIELDS = ("state", "signal_date", "tier", "aligned", "score")


def _old_bars(daily: pd.Series, tf: str, market: str = "US") -> pd.Series:
    """The RETIRED construction, frozen verbatim: pandas bins phased to the series' first
    timestamp (`resample(tf3)` in mtf_snapshot, `resample("3B")` in calibrate_ladder,
    `origin='start_day'` day-bins for crypto's "3D")."""
    return daily.dropna().resample(tf).last().dropna()


def _summary(close: pd.Series, high: pd.Series | None, kind: str, market: str) -> dict:
    a = cycles.analyze(close, high, kind=kind, market=market)
    lad = a.get("ladder") or {}
    al = lad.get("alignment") or {}
    return {"state": lad.get("state"), "signal_date": lad.get("signal_date"),
            "tier": al.get("tier"), "aligned": bool(al.get("aligned")),
            "score": lad.get("score")}


def _one(task: tuple) -> dict | None:
    """Worker: OLD and NEW summaries for one name. `series` may carry (close, high)."""
    name, close, high, kind, market = task
    c = close.dropna()
    if len(c) < 300:
        return None
    try:
        real = cycles._anchor_bars
        cycles._anchor_bars = _old_bars
        try:
            old = _summary(c, high, kind, market)
        finally:
            cycles._anchor_bars = real
        new = _summary(c, high, kind, market)
        return {"name": name, "old": old, "new": new, "asof": str(c.index.max().date())}
    except Exception as e:  # noqa: BLE001 — a broken series is reported, never fatal
        return {"name": name, "error": str(e)[:120]}


def _invariance(task: tuple) -> dict | None:
    """Worker: NEW-anchor start-invariance for one name (k = 1..3)."""
    name, close, high, kind, market = task
    c = close.dropna()
    if len(c) < 320:
        return None
    try:
        base = _summary(c, high, kind, market)
        flips = []
        for k in (1, 2, 3):
            h = high.iloc[k:] if high is not None else None
            got = _summary(c.iloc[k:], h, kind, market)
            if any(base[f] != got[f] for f in _FIELDS):
                flips.append(k)
        return {"name": name, "flips": flips}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "error": str(e)[:120]}


def _fixed_vs_slid(task: tuple) -> dict | None:
    """Worker: calibrate-window agreement, old grid vs new (R-CY6b). At each eval point
    the ladder state from the 600-bar window is compared with the 590-bar one — under
    the old resample the two windows carried differently-phased 3D grids."""
    name, close, _high, _kind, market = task
    c = close.dropna()
    if len(c) < 800:
        return None

    def _state(sub: pd.Series) -> str | None:
        try:
            cyc = cycles.cycle_state(sub)
            mtf = {"D": cycles._tf_state(sub),
                   "3D": cycles._tf_state(cycles._anchor_bars(sub, "3B", market)),
                   "W": cycles._tf_state(sub.resample("W-FRI").last().dropna())}
            early = cycles.early_signals(sub, cyc, mtf)
            return (cycles.ladder_state(cyc, mtf, early) or {}).get("state")
        except Exception:  # noqa: BLE001
            return None

    out = {}
    real = cycles._anchor_bars
    for label, bars in (("old", _old_bars), ("new", real)):
        cycles._anchor_bars = bars
        try:
            agree = total = 0
            for i in range(700, len(c) - 1, 50):
                a = _state(c.iloc[max(0, i - 600): i + 1])
                b = _state(c.iloc[max(0, i - 590): i + 1])
                if a is not None and b is not None:
                    total += 1
                    agree += int(a == b)
            out[label] = (agree, total)
        finally:
            cycles._anchor_bars = real
    return {"name": name, **out}


def _calibrate_pair(panel: dict[str, pd.Series], market: str) -> dict:
    real = cycles._anchor_bars
    cycles._anchor_bars = _old_bars
    try:
        old = cycles.calibrate_ladder(panel, market=market)
    finally:
        cycles._anchor_bars = real
    new = cycles.calibrate_ladder(panel, market=market)
    return {"old": old, "new": new}


def _flip_stats(rows: list[dict]) -> dict:
    ok = [r for r in rows if r and "old" in r]
    errs = [r for r in rows if r and "error" in r]
    n = len(ok)
    state_flips = [r for r in ok if r["old"]["state"] != r["new"]["state"]]
    rekeys = [r for r in ok if r["old"]["state"] == r["new"]["state"]
              and r["old"]["signal_date"] != r["new"]["signal_date"]]
    tier_flips = [r for r in ok if r["old"]["tier"] != r["new"]["tier"]]
    adm_flips = [r for r in ok if r["old"]["aligned"] != r["new"]["aligned"]]
    score_moves = sum(1 for r in ok if r["old"]["score"] != r["new"]["score"])
    return {
        "graded": n, "errors": len(errs),
        "state_flips": len(state_flips),
        "signal_date_rekeys": len(rekeys),
        "tier_flips": len(tier_flips),
        "admission_flips": len(adm_flips),
        "score_moves": score_moves,
        "asof": max((r["asof"] for r in ok), default=None),
        "state_flip_examples": [
            {"name": r["name"], "old": r["old"]["state"], "new": r["new"]["state"]}
            for r in state_flips[:8]],
        "admission_flip_examples": [
            {"name": r["name"], "old": r["old"]["tier"], "new": r["new"]["tier"]}
            for r in adm_flips[:8]],
    }


def _load_deep(root: Path) -> list[tuple]:
    tasks = []
    for f in sorted(glob.glob(str(root / "stocks/*.parquet"))):
        t = Path(f).stem
        df = pd.read_parquet(f)
        if "close" not in df.columns:
            continue
        kind = "crypto" if t.endswith("-USD") else "equity"
        tasks.append((t, df["close"], df.get("high"), kind, "US"))
    return tasks


def _load_ohlcv(root: Path) -> list[tuple]:
    tasks = []
    for f in sorted(glob.glob(str(root / "baskets/ohlcv/*.parquet"))):
        t = Path(f).stem
        df = pd.read_parquet(f)
        if "close" not in df.columns:
            continue
        tasks.append((t, df["close"], df.get("high"), "equity", "US"))
    return tasks


def _load_wide(path: Path, market: str) -> list[tuple]:
    if not path.exists():
        return []
    wide = pd.read_parquet(path)
    return [(str(c), wide[c], None, "equity", market) for c in wide.columns]


def _load_index_store(root: Path, sub: str, market: str) -> list[tuple]:
    tasks = []
    for f in sorted(glob.glob(str(root / sub / "*.parquet"))):
        df = pd.read_parquet(f)
        if "close" not in df.columns:
            continue
        tasks.append((Path(f).stem, df["close"], df.get("high"), "equity", market))
    return tasks


def _cross(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """Same-name agreement between two loaders, old vs new, on state + tier."""
    a = {r["name"]: r for r in rows_a if r and "old" in r}
    b = {r["name"]: r for r in rows_b if r and "old" in r}
    shared = sorted(set(a) & set(b))
    out = {"shared": len(shared)}
    for era in ("old", "new"):
        dis_state = [t for t in shared if a[t][era]["state"] != b[t][era]["state"]]
        dis_tier = [t for t in shared if a[t][era]["tier"] != b[t][era]["tier"]]
        out[era] = {"state_disagreements": len(dis_state),
                    "tier_disagreements": len(dis_tier),
                    "state_examples": dis_state[:10]}
    return out


def _ladder_cutover(deep_rows: list[dict]) -> dict:
    """R-CY5, empirically: seed a temp log with the REAL store's rows (a copy — the real
    file is never written), append tonight's post-era rows, count what the seam guard
    suppressed vs appended. Falls back to a synthetic pre-era seed built from the OLD
    summaries when the real store is absent."""
    real_log = config.data_dir() / "ticker_alerts" / "ladder_log.parquet"
    ok = [r for r in deep_rows if r and "old" in r and r["new"]["state"]]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "ladder_log.parquet"
        if real_log.exists():
            pd.read_parquet(real_log).to_parquet(tmp)
            seed = "real_store_copy"
        else:
            pd.DataFrame([
                {"asset": r["name"], "signal_date": r["old"]["signal_date"] or r["asof"],
                 "state": r["old"]["state"], "prev_state": "", "action": "", "label": "",
                 "urgency": "", "score": 0, "dir": "neutral", "asof": r["asof"]}
                for r in ok if r["old"]["state"]]).to_parquet(tmp)
            seed = "synthetic_old_rows"
        orig = ticker_alerts._ladder_path
        ticker_alerts._ladder_path = lambda: tmp
        try:
            before = len(pd.read_parquet(tmp))
            rows = [ticker_alerts.ladder_row(
                r["name"],
                {"state": r["new"]["state"], "signal_date": r["new"]["signal_date"],
                 "anchor_era": cycles.ANCHOR_ERA, "score": r["new"]["score"] or 0},
                r["asof"]) for r in ok]
            added = ticker_alerts.write_ladder_log_batch(rows)
            after = len(pd.read_parquet(tmp))
        finally:
            ticker_alerts._ladder_path = orig
    candidates = len([r for r in rows if r])
    return {"seed": seed, "candidate_rows": candidates, "appended": added,
            "suppressed_or_duplicate": candidates - added,
            "log_rows_before": before, "log_rows_after": after}


def _fmt_universe_table(stats: dict[str, dict]) -> list[str]:
    L = ["| universe | graded | state flips | signal_date re-keys | tier flips | "
         "admission flips | score moves | store as-of |",
         "|---|---:|---:|---:|---:|---:|---:|---|"]
    for name, s in stats.items():
        L.append(f"| {name} | {s['graded']} | {s['state_flips']} "
                 f"({100 * s['state_flips'] / max(s['graded'], 1):.1f}%) | "
                 f"{s['signal_date_rekeys']} | {s['tier_flips']} | {s['admission_flips']} | "
                 f"{s['score_moves']} | {s['asof']} |")
    return L


def main() -> int:
    root = config.data_dir()
    workers = max(4, (os.cpu_count() or 8) - 2)
    universes: dict[str, list[tuple]] = {}

    universes["data/stocks (deep US)"] = _load_deep(root)
    universes["data/baskets/ohlcv (2014-start US)"] = _load_ohlcv(root)
    cache = root / "breadth" / "_closes_cache.parquet"
    universes["breadth _closes_cache (~345-bar rolling)"] = (
        _load_wide(cache, "US") if cache.exists() else [])
    universes["china_search closes (2021-start CN)"] = _load_wide(
        root / "china_search" / "closes.parquet", "CN")
    universes["data/hk index store (HK)"] = _load_index_store(root, "hk", "HK")
    universes["data/canada index store (CA)"] = _load_index_store(root, "canada", "CA")

    for name, tasks in universes.items():
        if not tasks:
            print(f"::warning title=cycles-anchor-blast-radius::universe absent in this "
                  f"checkout, not measured: {name}", flush=True)

    results: dict[str, list[dict]] = {}
    stats: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for name, tasks in universes.items():
            if not tasks:
                continue
            rows = list(ex.map(_one, tasks, chunksize=8))
            results[name] = rows
            stats[name] = _flip_stats(rows)
            print(f"[measure] {name}: {stats[name]['graded']} graded, "
                  f"{stats[name]['state_flips']} state flips, "
                  f"{stats[name]['admission_flips']} admission flips", flush=True)

        # cross-loader same-night agreement (deep vs ohlcv, deep vs breadth cache)
        cross = {}
        deep_key = "data/stocks (deep US)"
        for other in ("data/baskets/ohlcv (2014-start US)",
                      "breadth _closes_cache (~345-bar rolling)"):
            if results.get(deep_key) and results.get(other):
                cross[f"deep ∩ {other}"] = _cross(results[deep_key], results[other])

        # NEW-anchor start-invariance re-run — must be 0 movers
        inv_rows = list(ex.map(_invariance, universes[deep_key], chunksize=8))
        movers = [r for r in inv_rows if r and r.get("flips")]
        inv = {"names": len([r for r in inv_rows if r and "flips" in r]),
               "movers": len(movers), "mover_names": [r["name"] for r in movers][:10]}
        print(f"[measure] invariance re-run: {inv['movers']}/{inv['names']} movers", flush=True)

        # fixed-vs-slid calibration-window agreement, old vs new (R-CY6b)
        fv_tasks = [t for t in universes[deep_key][::20] if len(t[1].dropna()) >= 800][:12]
        fv_rows = [r for r in ex.map(_fixed_vs_slid, fv_tasks) if r]
    fv = {"names": len(fv_rows)}
    for era in ("old", "new"):
        agree = sum(r[era][0] for r in fv_rows)
        total = sum(r[era][1] for r in fv_rows)
        fv[era] = {"agree": agree, "total": total,
                   "pct": round(100 * agree / max(total, 1), 2)}

    # calibrate_ladder old-vs-new table drift on a bounded deep panel
    deep_panel = {t: c for (t, c, _h, k, _m) in universes[deep_key]
                  if k == "equity" and len(c.dropna()) >= 1500}
    panel = dict(sorted(deep_panel.items())[::max(1, len(deep_panel) // 40)][:40])
    cal = _calibrate_pair(panel, "US")
    cal_drift = {}
    for st in sorted(set(cal["old"]) | set(cal["new"])):
        o, nw = cal["old"].get(st), cal["new"].get(st)
        cal_drift[st] = {
            "n": [o and o["n"], nw and nw["n"]],
            "hit_pct": [o and o["hit_pct"], nw and nw["hit_pct"]],
            "avg_fwd_pct": [o and o["avg_fwd_pct"], nw and nw["avg_fwd_pct"]],
            "dd_med_pct": [o and o["dd_med_pct"], nw and nw["dd_med_pct"]]}

    # the ladder-log cutover, against a copy of the real store
    cutover = _ladder_cutover(results[deep_key])

    # ---------------------------------------------------------------- report ----
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    L = ["# cycle-ladder absolute session anchor — blast radius", "",
         f"Era `{cycles.ANCHOR_ERA}` · ruling "
         "`research/CYCLES_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`", "",
         f"Generated {now} · store as-of dates are per-universe (read from the stores, "
         "never the wall clock).", "",
         "Every number is measured through `cycles.analyze()` — the path the nightly "
         "libraries, the standout strip's `bottoming-alignment` key and the ladder log "
         "actually read — with the retired `resample` construction frozen verbatim in "
         "this script and monkeypatched in for the OLD pass.", "",
         "## 1. Old → new, per production loader", ""]
    L += _fmt_universe_table(stats)
    L += ["",
          "`state flips` = the ladder's headline read re-draws ONCE at cutover (R-CY4's "
          "disclosed cost). `signal_date re-keys` = same standing state, walk-back date "
          "moved — the phantom-row class the R-CY5 seam guard suppresses at ingestion. "
          "`admission flips` = the standout-strip SELECTION verdict (`aligned`) changed — "
          "the board-surface stake that made this the highest-priority sibling.", ""]
    for name, s in stats.items():
        if s["state_flip_examples"]:
            L.append(f"- **{name}** state-flip examples: " + "; ".join(
                f"{e['name']} {e['old']}→{e['new']}" for e in s["state_flip_examples"]))
        if s["admission_flip_examples"]:
            L.append(f"- **{name}** admission-flip examples: " + "; ".join(
                f"{e['name']} {e['old'] or '—'}→{e['new'] or '—'}"
                for e in s["admission_flip_examples"]))
    L += ["", "## 2. Cross-loader same-night agreement — the live symptom", "",
          "| pair | shared | state disagreements BEFORE | AFTER | tier disagreements "
          "BEFORE | AFTER |", "|---|---:|---:|---:|---:|---:|"]
    for pair, c in cross.items():
        L.append(f"| {pair} | {c['shared']} | {c['old']['state_disagreements']} | "
                 f"{c['new']['state_disagreements']} | {c['old']['tier_disagreements']} | "
                 f"{c['new']['tier_disagreements']} |")
    L += ["",
          "A residual AFTER is a cross-store PRICE difference or a genuine DEPTH effect "
          "(the deep store sees decades the cache cannot), never a grid one — the anchor "
          "guarantees one grid per name; it cannot make two stores agree about what a "
          "close was.", "",
          "## 3. calibrate_ladder — intra-run re-anchoring healed (R-CY6)", "",
          f"Fixed-vs-slid window ladder-state agreement over {fv['names']} deep names "
          f"(600- vs 590-bar windows at 50-bar eval steps): "
          f"**OLD {fv['old']['pct']}%** ({fv['old']['agree']}/{fv['old']['total']}) → "
          f"**NEW {fv['new']['pct']}%** ({fv['new']['agree']}/{fv['new']['total']}). "
          "The residual under NEW is daily-indicator EWM warm-up (window-length "
          "sensitivity, pre-existing and unchanged), not bin phase.", "",
          f"Per-state table drift, {len(panel)}-name deep panel (old → new):", "",
          "| state | n | hit_pct | avg_fwd_pct | dd_med_pct |", "|---|---|---|---|---|"]
    for st, d in cal_drift.items():
        def _p(v):
            return f"{v[0]} → {v[1]}" if v[0] != v[1] else f"{v[0]}"
        L.append(f"| {st} | {_p(d['n'])} | {_p(d['hit_pct'])} | {_p(d['avg_fwd_pct'])} | "
                 f"{_p(d['dd_med_pct'])} |")
    L += ["",
          "The shipped `ladder_calibration.json` files are PRE-era measurements re-baked "
          "on their normal schedule (`recalibrate.py`, `calibrate_china.py`, "
          "`calibrate_hk.py`) — cells now carry `anchor_era` so a consumer can tell "
          "which grid measured them (R-CY4).", "",
          "## 4. The ladder-log cutover (R-CY5), simulated on a store copy", "",
          f"Seed: {cutover['seed']} ({cutover['log_rows_before']} rows). Tonight's "
          f"post-era batch: {cutover['candidate_rows']} candidate rows → "
          f"**{cutover['appended']} appended** (genuine re-draws + fresh transitions), "
          f"**{cutover['suppressed_or_duplicate']} suppressed** (exact duplicates + "
          "era re-key images inside the 4-day seam tolerance). The real store was read "
          "from a copy and never written.", "",
          "## 5. Start-invariance under the NEW anchor (must be 0)", "",
          f"{inv['movers']} / {inv['names']} deep US names move ANY of (state, "
          "signal_date, tier, aligned, score) on a 1-3 leading-bar drop."]
    if inv["movers"]:
        L.append(f"MOVERS (regression!): {inv['mover_names']}")
    L += ["", "Universes measured in this checkout; an absent universe is announced with "
          "a `::warning`, never silently skipped (the A5 precedent).", ""]

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(L), encoding="utf-8")
    payload = {"era": cycles.ANCHOR_ERA, "generated": now, "universes": stats,
               "cross_loader": cross, "fixed_vs_slid": fv, "calibrate_drift": cal_drift,
               "ladder_cutover": cutover, "invariance": inv}
    REPORT_JSON.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"[measure] wrote {REPORT_MD} + {REPORT_JSON}", flush=True)
    if inv["movers"]:
        print("::error title=cycles-anchor-invariance::NEW-anchor invariance re-run "
              f"found {inv['movers']} movers — the anchor is leaking", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
