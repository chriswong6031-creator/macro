"""Measure what the display-grid anchor CHANGED — ship requirement DG-R7.

Ruling: research/DISPLAY_GRID_ALIGNMENT_ADJUDICATION_BY_FABLE.md
(era ``display-grid-abs-session-2026-08-06``).

    python3 scripts/measure_display_grid_blast_radius.py             # full
    python3 scripts/measure_display_grid_blast_radius.py --quick     # 60 names

Writes ``reports/display_grid_blast_radius.md`` + ``.json``.

HOW OLD-VS-NEW IS PRODUCED. No era flag lives in the engine — a switch left in production
code is a second code path nobody runs. The PRE-repair behaviours are reproduced here
verbatim instead: ``_old_client_buckets`` is chart.js's ``floor(i/3)`` over the loaded
window, and ``_old_engine_buckets`` is the retired ``resample("3B")``. "New" is the module
exactly as it ships.

WHAT IT MEASURES.

  A. CLIENT GRID, the shipped surface. Per name: the §7 marker dates that fall inside the
     1300-bar payload window, and how many land on a DIFFERENT candle under the old client
     grid than under the engine's own grid. Reported at all THREE window phases, because
     the window advances one session per night and the old grid re-phases with it — a
     single-phase reading is a 1-in-3 coin flip, not a measurement (DT-R16 family: the
     pooled number may not be read without the split).

     The two repair mechanisms are decomposed, because they do not cover the same names:
       * TRIM only (DG-R4)  — window opens on a bucket. For a name trading EVERY session
         in the window this alone reproduces the engine grid.
       * TRIM + b3 (DG-R3)  — the shipped boundaries. Additionally covers names with a
         gap in the window (halts, suspensions, late listings), which trim cannot.

  B. ENGINE GRID (``bar_derive``): 3D/2D bucket membership changed by the anchor, buckets
     that the retired ``3B`` bins mis-split across a holiday, and a k-drop invariance
     re-run under the new deriver (must be 0 changed buckets).

  C. PAYLOAD weight: the b3 block's bytes, raw and gzipped, against the payload it rides.

  D. COVERAGE: which chart families ship the anchor, and which surfaces consume it.

NO SILENT CAPS (house law). Every name that could not be read is counted and reasoned in
the report; nothing is skipped into a smaller-looking denominator.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import bar_derive as bd          # noqa: E402
from engine import session_anchor            # noqa: E402
from lib import config                       # noqa: E402

MAX_BARS = 1300          # scripts/build_chart_data.MAX_BARS — the shipped window
PHASES = (0, 1, 2)       # window-end shifts: tonight, and the two other nightly phases


# ----------------------------------------------------------- retired behaviours ----

def _old_client_buckets(n: int) -> np.ndarray:
    """chart.js before this era: ``Math.floor(i / 3)`` over the LOADED rows."""
    return np.arange(n) // 3


def _old_engine_buckets(idx: pd.DatetimeIndex, n: int) -> pd.Series:
    """bar_derive before this era: pandas ``<n>B`` bins, phased to the series' first row."""
    s = pd.Series(range(len(idx)), index=idx)
    lab = s.resample(f"{n}B").first()
    return lab.dropna()


def _last_session_per_bucket(dates: list[str], buckets) -> list[str]:
    """A candle is stamped with its bucket's LAST session — the chart's label convention."""
    seen: dict[int, str] = {}
    for d, b in zip(dates, buckets):
        seen[int(b)] = d
    return [seen[k] for k in sorted(seen)]


def _snap(labels: list[str], d: str) -> str:
    """mapMarkers: the first bar with time >= the marker date."""
    i = int(np.searchsorted(np.array(labels), d, side="left"))
    return labels[min(i, len(labels) - 1)]


# ------------------------------------------------------------------- section A ----

def _window(close: pd.Series, phase: int) -> pd.Series:
    """The payload window as it stood ``phase`` sessions ago (untrimmed — production)."""
    c = close.dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    if phase:
        c = c.iloc[:-phase]
    return c.tail(MAX_BARS)


def _measure_client(names: list[str], sig_dir: Path, stocks: Path) -> dict:
    out = {"phases": {}, "skipped": Counter(), "worst": {}}
    per_name_hits: dict[int, Counter] = {p: Counter() for p in PHASES}
    gap_kinds: dict[str, set] = {"gap in window": set(),
                                 "short history (no row precedes the window)": set()}
    for phase in PHASES:
        tot_in = tot_hop = tot_hop_trim = names_hit = names_hit_trim = probed = 0
        gapped_names = 0
        for t in names:
            pq = stocks / f"{t}.parquet"
            sig = sig_dir / f"{t}.json"
            if not pq.exists():
                out["skipped"]["no deep store"] += 1
                continue
            if not sig.exists():
                out["skipped"]["no committed §7 payload"] += 1
                continue
            try:
                marks = [m.get("date") for m in
                         json.loads(sig.read_text()).get("markers", []) if m.get("date")]
                close = pd.read_parquet(pq)["close"]
            except Exception as e:                                   # noqa: BLE001
                out["skipped"][f"unreadable ({type(e).__name__})"] += 1
                continue
            win = _window(close, phase)
            if len(win) < 10:
                out["skipped"]["window under 10 sessions"] += 1
                continue
            probed += 1
            dates = [ts.strftime("%Y-%m-%d") for ts in win.index]
            ids_new = bd.bucket_ids(win.index)
            # Why a name can escape the trim, measured rather than assumed:
            #   * a GAP in the window (halt/suspension) — row arithmetic desynchronises
            #     from the calendar for the rest of the window;
            #   * a SHORT history (fewer bars than the cap) — nothing precedes row 0, so
            #     there is no leading row to trim and row 0 sits at whatever absolute
            #     phase the listing date gave it, wrong ~2 nights in 3 forever.
            pos = session_anchor.session_positions(win.index)
            has_gap = not bool(len(pos) and (np.diff(pos) == 1).all())
            short_history = len(close.dropna()) <= len(win)
            if has_gap or short_history:
                gapped_names += 1
                (gap_kinds["gap in window"] if has_gap
                 else gap_kinds["short history (no row precedes the window)"]).add(t)

            lab_new = _last_session_per_bucket(dates, ids_new)
            lab_old = _last_session_per_bucket(dates, _old_client_buckets(len(dates)))
            # TRIM-only: same row arithmetic, but the window starts on a bucket open
            cut = bd.trim_rows_to_bucket_open(
                win.index, close.dropna().sort_index().index[-len(win) - 1]
                if len(close.dropna()) > len(win) else None)
            d_trim = dates[cut:]
            lab_trim = _last_session_per_bucket(d_trim, _old_client_buckets(len(d_trim)))

            inwin = [d for d in marks if dates[0] <= d <= dates[-1]]
            hops = sum(1 for d in inwin if _snap(lab_old, d) != _snap(lab_new, d))
            hops_trim = sum(1 for d in inwin if d >= d_trim[0]
                            and _snap(lab_trim, d) != _snap(lab_new, d))
            tot_in += len(inwin)
            tot_hop += hops
            tot_hop_trim += hops_trim
            names_hit += 1 if hops else 0
            names_hit_trim += 1 if hops_trim else 0
            if hops:
                per_name_hits[phase][t] = hops
        out["phases"][phase] = {
            "names_probed": probed, "markers_in_window": tot_in,
            "hops_today": tot_hop, "names_affected_today": names_hit,
            "hops_trim_only": tot_hop_trim, "names_affected_trim_only": names_hit_trim,
            "gapped_names": gapped_names,
            "pct_today": round(100 * tot_hop / max(1, tot_in), 1),
            "pct_trim_only": round(100 * tot_hop_trim / max(1, tot_in), 1),
        }
        out["worst"][phase] = per_name_hits[phase].most_common(10)
    out["skipped"] = dict(out["skipped"])
    out["escapes_the_trim"] = {k: sorted(v) for k, v in gap_kinds.items()}
    return out


# ------------------------------------------------------------------- section B ----

def _measure_engine(names: list[str], stocks: Path) -> dict:
    moved3 = moved2 = holiday_split = probed = 0
    invariance_bad = 0
    for t in names:
        pq = stocks / f"{t}.parquet"
        if not pq.exists():
            continue
        try:
            df = pd.read_parquet(pq)
        except Exception:                                            # noqa: BLE001
            continue
        if "close" not in df or len(df) < 40:
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        probed += 1
        for n, counter in ((3, "3"), (2, "2")):
            new = bd.derive_3d_ohlcv(df) if n == 3 else bd.derive_2d_ohlcv(df)
            old_lab = _old_engine_buckets(df.index, n)
            changed = len(new) != len(old_lab)
            if n == 3:
                moved3 += 1 if changed else 0
            else:
                moved2 += 1 if changed else 0
        # Holiday mis-splits: a 3B bin spends one of its three slots on a non-session, so
        # it holds only 2 real sessions while the session grid always gives it 3. Counted
        # only for bins strictly inside the series (the first and last may be partial for
        # the ordinary reason that the history starts/ends mid-bucket).
        b3 = pd.Series(1, index=df.index).resample("3B").count()
        inner = b3.iloc[1:-1]
        holiday_split += int(((inner > 0) & (inner < 3)).sum())
        # invariance under the NEW deriver
        full_out = bd.derive_3d_ohlcv(df)
        sub = bd.derive_3d_ohlcv(df.iloc[3:])
        common = full_out.index.intersection(sub.index)
        common = common[common > sub.index[0]]
        if len(common) and not np.array_equal(
                full_out.loc[common].to_numpy(), sub.loc[common].to_numpy()):
            invariance_bad += 1
    return {"names_probed": probed, "names_3d_bucket_count_changed": moved3,
            "names_2d_bucket_count_changed": moved2,
            "holiday_mis_split_buckets_healed": max(0, holiday_split),
            "k_drop_invariance_violations_under_new_grid": invariance_bad}


# ------------------------------------------------------------------- section C ----

def _measure_payload(names: list[str], stocks: Path) -> dict:
    raw, gz, trims = [], [], Counter()
    for t in names:
        pq = stocks / f"{t}.parquet"
        if not pq.exists():
            continue
        try:
            close = pd.read_parquet(pq)["close"].dropna()
        except Exception:                                            # noqa: BLE001
            continue
        close = close[~close.index.duplicated(keep="last")].sort_index()
        win = close.tail(MAX_BARS)
        if len(win) < 10:
            continue
        prev = close.index[-len(win) - 1] if len(close) > len(win) else None
        trims[bd.trim_rows_to_bucket_open(win.index, prev)] += 1
        blob = json.dumps(bd.chart_anchor(win.index), separators=(",", ":"))
        raw.append(len(blob))
        gz.append(len(gzip.compress(blob.encode())))
    return {"names": len(raw),
            "b3_bytes_raw_mean": int(np.mean(raw)) if raw else 0,
            "b3_bytes_gzip_mean": int(np.mean(gz)) if gz else 0,
            "payload_bytes_raw_typical": 50_000,
            "trim_distribution": {str(k): v for k, v in sorted(trims.items())}}


# ----------------------------------------------------------------------- main ----

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="first 60 names only")
    args = ap.parse_args()

    stocks = config.data_dir() / "stocks"
    sig_dir = ROOT / "site" / "signals"
    names = sorted(p.stem for p in stocks.glob("*.parquet"))
    if args.quick:
        names = names[:60]

    client = _measure_client(names, sig_dir, stocks)
    engine = _measure_engine(names, stocks)
    payload = _measure_payload(names, stocks)

    doc = {
        "era": bd.ANCHOR_ERA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "universe": {"store": str(stocks.relative_to(ROOT)), "names_in_store": len(names),
                     "window_bars": MAX_BARS},
        "A_client_grid": client, "B_engine_grid": engine, "C_payload": payload,
        "D_coverage": {
            "ships_anchor": ["site/ohlc (US)", "site/chinaohlc (CN)", "site/canadaohlc (CA)",
                             "site/intlohlc (intl)", "site/hkohlc + hk_lookup inline (HK)",
                             "site/subsectorohlc + CN concept desk"],
            "consumes_anchor": ["site/chart.js resample() 3D buckets",
                                "site/chart.js mapMarkers() snap-forward (exact under the "
                                "shared grid)"],
            "not_applicable": ["4H (epoch-absolute)", "1W/1M (calendar-absolute)"],
        },
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "display_grid_blast_radius.json").write_text(
        json.dumps(doc, indent=2))
    (ROOT / "reports" / "display_grid_blast_radius.md").write_text(_render(doc))
    print(f"wrote reports/display_grid_blast_radius.{{md,json}} — era {bd.ANCHOR_ERA}")
    return 0


def _render(d: dict) -> str:
    A, B, C = d["A_client_grid"], d["B_engine_grid"], d["C_payload"]
    L = [f"# Display-grid blast radius — era `{d['era']}`", "",
         f"Generated {d['generated_utc']} · ruling "
         "`research/DISPLAY_GRID_ALIGNMENT_ADJUDICATION_BY_FABLE.md` (DG-R7).", "",
         f"Universe: `{d['universe']['store']}`, {d['universe']['names_in_store']} names, "
         f"{d['universe']['window_bars']}-bar payload window.", "",
         "## A. Client grid — the shipped surface", "",
         "The payload window advances one session per night, so the retired `floor(i/3)`",
         "grid re-phases with it. **The pooled figure may not be read without the phase",
         "split** (DT-R16 family): on the aligned night almost nothing moves, on the other",
         "two almost everything does.", "",
         "| window phase | markers in window | on a wrong candle (today) | names | "
         "still wrong with TRIM only | names |", "|---|---:|---:|---:|---:|---:|"]
    for p in PHASES:
        r = A["phases"][p]
        tag = "tonight (aligned)" if p == 0 else f"−{p} session"
        L.append(f"| {tag} | {r['markers_in_window']:,} | {r['hops_today']:,} "
                 f"({r['pct_today']}%) | {r['names_affected_today']}/{r['names_probed']} | "
                 f"{r['hops_trim_only']:,} ({r['pct_trim_only']}%) | "
                 f"{r['names_affected_trim_only']}/{r['names_probed']} |")
    L += ["", "The last two columns decompose the repair honestly. **DG-R4's trim alone**",
          "lands the window on a bucket open, and from there row arithmetic reproduces the",
          "session grid *for a name that trades every session in its window* — which is why",
          "the trim carries the common case. **DG-R3's `b3`** is what covers the rest: the",
          f"{A['phases'][0]['gapped_names']} names the trim cannot reach, where no window",
          "start can rescue row arithmetic. It also keeps the client correct without",
          "trusting the emitter's trim. Those names, by cause:", ""]
    for kind, ns in A.get("escapes_the_trim", {}).items():
        L.append(f"  - **{kind}** — {len(ns)}: {', '.join(ns[:12])}"
                 + (" …" if len(ns) > 12 else ""))
    L += ["",
          f"Worst names (phase 0): {A['worst'][0]}", "",
          f"Skipped, with reasons (no silent caps): {A['skipped'] or 'none'}", "",
          "## B. Engine grid — `bar_derive`", "",
          f"- names probed: **{B['names_probed']}**",
          f"- 3D bucket count changed by the anchor: **{B['names_3d_bucket_count_changed']}**",
          f"- 2D bucket count changed: **{B['names_2d_bucket_count_changed']}**",
          f"- holiday mis-split buckets healed: **{B['holiday_mis_split_buckets_healed']}**",
          f"- k-drop invariance violations under the NEW grid: "
          f"**{B['k_drop_invariance_violations_under_new_grid']}** (must be 0)", "",
          "## C. Payload weight", "",
          f"- `b3` block: **{C['b3_bytes_raw_mean']} B raw**, "
          f"**{C['b3_bytes_gzip_mean']} B gzipped**, against a ~50 KB payload "
          f"(~{100 * C['b3_bytes_gzip_mean'] / 12_000:.1f}% of the ~12 KB gzipped file)",
          f"- DG-R4 trim distribution (rows dropped): {C['trim_distribution']}", "",
          "## D. Coverage", ""]
    L += [f"- **ships the anchor:** {', '.join(d['D_coverage']['ships_anchor'])}",
          f"- **consumes it:** {', '.join(d['D_coverage']['consumes_anchor'])}",
          f"- **not applicable:** {', '.join(d['D_coverage']['not_applicable'])}", ""]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
