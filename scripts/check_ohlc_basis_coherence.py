#!/usr/bin/env python3
"""Guard: the breadth OHLC caches must share ONE adjustment basis.

WHY (2026-08-06 split-basis incident). The breadth universes keep four sibling wide
matrices per namespace — ``_closes_cache.parquet`` plus the ADDITIVE OHLCV extras
``_high_cache`` / ``_low_cache`` / ``_volume_cache`` (collectors/breadth.py
``_download_closes`` stashes them, ``fetch()`` persists them). yfinance
``auto_adjust=True`` back-adjusts ONLY the window it downloads, so a split or a
large dividend re-bases the fresh 1mo window while the cached history keeps the old
basis. ``BreadthAdapter._merge_refreshed`` and ``scripts/heal_breadth_split_seams.py``
both repair that — but BOTH scan ``seam_suspects`` over the CLOSES matrix alone, and
the extras are only ever rewritten as a SIDE EFFECT of a ticker the CLOSES scan
flagged (``_merge_refreshed`` grafts the re-pull's extras; the healer rewrites
``ex[t]`` for the closes-flagged list).

That leaves a hole exactly the shape of this incident: **a basis split confined to
high/low is invisible to every scanner in the tree.** The closes matrix stays
self-consistent, so nothing flags it, while high/low sit on a different basis for
the same dates. Two concrete ways in:

  * ``_merge_refreshed`` line-graft filter ``t in w.columns`` — a ticker the CLOSES
    re-pull healed but whose FRESH-window extras frame lacks the column (yfinance
    returned no High for it in that batch) gets healed closes and keeps poisoned
    extras. No warning: the closes half succeeded.
  * ``heal_breadth_split_seams.heal`` rewrites the extras only for tickers the
    closes scan flagged, and reindexes the re-pull onto the EXISTING ``ex.index``
    — so a healed closes column can be paired with extras that were never touched.

Nothing downstream notices, because the common consumers are close-only. The single
exception is ATR, whose true range is ``max(H-L, |H-C_prev|, |L-C_prev|)`` — with
H/L on a basis ~30% away from C, TR is dominated by the basis gap and ATR blows up
silently. Known ATR-side consumers: scripts/build_pick_lab.py,
scripts/calibrate_bottom_radar.py, scripts/residual_momentum_phase0.py.

WHAT IT CHECKS (pure arithmetic on the committed caches — no network). For every
``data/<ns>/`` holding all three of closes/high/low, over the cells where all three
are present, the OHLC invariant ``low <= close <= high``. Findings are split into
two tiers, because the panels carry a permanent floor of isolated bad bars from
yfinance's own rounding on ex-dividend dates (17 such bars across the three US
panels at 2026-08-06, worst 2.5%) and a guard that reds on those is a scheduled red,
not a tripwire:

  SPLIT (fatal, exit 3)  a ticker whose worst violation is >= --hard-tol (10%), OR
                         which violates on >= --share-tol (20%) of its overlapping
                         bars with at least --min-bad-bars (5) of them. No genuine
                         bar closes 10% outside its own range, and no data-quality
                         noise hits a fifth of a ticker's history. The 2026-08-06
                         signature — REZI at close/high 1.29-1.44 on 773 of 773
                         bars — trips both limbs by an order of magnitude.
  NOISE (::warning)      anything else above the float floor. Printed with ticker,
                         date and magnitude so the floor stays visible and cannot
                         drift upward unseen. Never gates.

Also fatal: ``low > high`` on a present pair (a swapped or mismatched write).

Deliberately NOT checked: coverage. The extras stores are forward-accruing by design
(collectors/breadth.py: "Deep history is impossible ... the store grows forward from
first collection"), so high/low legitimately carry a fraction of the closes history —
a median 55 bars against 777 at 2026-08-06. Asserting coverage here would red every
night for a documented property.

A marker JSON (data/quality/ohlc_basis_coherence.json) records every evaluation.

Exit codes: 0 coherent (noise tier allowed), 3 split detected (annotated), 2 unexpected
error OR a refusal (no panel found AND data/ is sparse-omitted — see scripts/sparse_guard.py).
``--selftest`` runs synthetic assertions over the classifier and exits 0/1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.sparse_guard import refuse_if_vacuous, trees_for  # noqa: E402

# float-comparison floor: below this a "violation" is parquet round-tripping, not data.
EPS = 1e-6
# a close this far outside its own [low, high] is a different adjustment basis, full stop.
HARD_TOL = 0.10
# ...or a violation rate no data-quality noise reaches, over enough bars to mean it.
SHARE_TOL = 0.20
MIN_BAD_BARS = 5

FIELDS = ("closes", "high", "low")


def discover_panels(data_dir: Path) -> list[str]:
    """Namespaces under data/ carrying the full closes+high+low triple, sorted."""
    if not data_dir.is_dir():
        return []
    return sorted(
        d.name for d in data_dir.iterdir()
        if d.is_dir() and all((d / f"_{f}_cache.parquet").exists() for f in FIELDS)
    )


def classify(closes: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
             hard_tol: float = HARD_TOL, share_tol: float = SHARE_TOL,
             min_bad_bars: int = MIN_BAD_BARS) -> list[dict]:
    """Pure decision: per-ticker OHLC verdicts over the all-present cells.

    Returns one record per VIOLATING ticker (clean tickers are omitted), each with
    ``verdict`` in {"split", "noise"}. Kept free of IO so --selftest can drive it
    with synthetic frames and the daily lane cannot diverge from the test.
    """
    cols = sorted(set(closes.columns) & set(high.columns) & set(low.columns))
    idx = closes.index.intersection(high.index).intersection(low.index)
    if not cols or idx.empty:
        return []
    C, H, L = closes.loc[idx, cols], high.loc[idx, cols], low.loc[idx, cols]
    present = C.notna() & H.notna() & L.notna()

    # fractional excess outside the bar's own range; 0 where the invariant holds.
    over = (C / H.where(H > 0) - 1.0).where(present & (C > H))
    under = (L / C.where(C > 0) - 1.0).where(present & (C < L))
    inverted = (L / H.where(H > 0) - 1.0).where(present & (L > H))
    excess = pd.concat([over, under, inverted]).groupby(level=0).max()
    bad = excess > EPS

    n_present = present.sum()
    n_bad = bad.sum()
    out: list[dict] = []
    for t in cols:
        if not n_bad[t]:
            continue
        col = excess[t].dropna()
        col = col[col > EPS]
        worst_date = col.idxmax()
        worst = float(col.max())
        bars, nbad = int(n_present[t]), int(n_bad[t])
        share = nbad / bars if bars else 0.0
        split = worst >= hard_tol or (share >= share_tol and nbad >= min_bad_bars)
        out.append({
            "ticker": t,
            "verdict": "split" if split else "noise",
            "bad_bars": nbad,
            "bars": bars,
            "bad_share": round(share, 4),
            "worst_excess": round(worst, 6),
            "worst_date": str(pd.Timestamp(worst_date).date()),
            "inverted_bars": int((inverted[t] > EPS).sum()),
        })
    out.sort(key=lambda r: (r["verdict"] != "split", -r["worst_excess"]))
    return out


def _read(panel_dir: Path, field: str) -> pd.DataFrame:
    return pd.read_parquet(panel_dir / f"_{field}_cache.parquet")


def _write_marker(data_dir: Path, payload: dict) -> None:
    try:
        p = data_dir / "quality" / "ohlc_basis_coherence.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2))
    except Exception as e:  # noqa: BLE001 — the marker is advisory, never the gate
        # bare print, not a logger: a prefixed record is dropped by GitHub (CLAUDE.md).
        print(f"::warning title=ohlc-basis-marker::marker write failed ({e})", flush=True)


def run(data_dir: Path, panels: list[str] | None = None, hard_tol: float = HARD_TOL,
        share_tol: float = SHARE_TOL, min_bad_bars: int = MIN_BAD_BARS) -> int:
    names = panels if panels is not None else discover_panels(data_dir)
    if not names:
        # A sparse session worktree omits data/, so discover_panels sees no namespace
        # and this path exits 0 over nothing — a vacuous pass on the split-basis
        # tripwire. Refuse BEFORE the marker write: a write into an omitted tree does
        # not MODIFY the committed artifact, it REPLACES it (measured 2026-08-13 in
        # this very repo — data/quality/ohlc_basis_coherence.json 7,901 bytes -> 58,
        # the same shape that truncated a 7.3 MB parquet to 45 KB).
        refusal = refuse_if_vacuous(0, trees_for(data_dir), "ohlc-basis-coherence-vacuous")
        if refusal:
            return 2
        print("::warning title=ohlc-basis-coherence::no breadth panel carries the "
              "closes+high+low triple — nothing to check", flush=True)
        _write_marker(data_dir, {"panels": {}, "splits": 0, "status": "no_panels"})
        return 0

    marker: dict = {"panels": {}, "splits": 0, "status": "coherent"}
    splits: list[tuple[str, dict]] = []
    noise = 0
    for name in names:
        d = data_dir / name
        try:
            findings = classify(_read(d, "closes"), _read(d, "high"), _read(d, "low"),
                                hard_tol, share_tol, min_bad_bars)
        except Exception as e:  # noqa: BLE001 — one unreadable panel must not blind the rest
            print(f"::warning title=ohlc-basis-coherence::{name}: unreadable "
                  f"({e}) — panel skipped", flush=True)
            marker["panels"][name] = {"status": "unreadable", "error": str(e)}
            continue
        panel_splits = [f for f in findings if f["verdict"] == "split"]
        panel_noise = [f for f in findings if f["verdict"] == "noise"]
        noise += len(panel_noise)
        splits.extend((name, f) for f in panel_splits)
        marker["panels"][name] = {
            "status": "split" if panel_splits else "coherent",
            "split_tickers": len(panel_splits),
            "noise_tickers": len(panel_noise),
            "findings": findings[:50],
        }
        for f in panel_noise[:5]:
            print(f"::warning title=ohlc-basis-noise::{name}/{f['ticker']}: close outside "
                  f"[low, high] on {f['bad_bars']}/{f['bars']} bar(s), worst "
                  f"{f['worst_excess']:.2%} on {f['worst_date']} — isolated bad bar, "
                  f"below the {hard_tol:.0%} split threshold", flush=True)

    marker["splits"] = len(splits)
    marker["noise_tickers"] = noise
    if splits:
        marker["status"] = "split"
        _write_marker(data_dir, marker)
        for name, f in splits[:20]:
            print(f"::error title=ohlc-basis-split::{name}/{f['ticker']}: high/low sit on a "
                  f"DIFFERENT adjustment basis than closes — close outside [low, high] on "
                  f"{f['bad_bars']}/{f['bars']} bars ({f['bad_share']:.0%}), worst "
                  f"{f['worst_excess']:.2%} on {f['worst_date']}. ATR over this panel is "
                  f"dominated by the basis gap. Heal: python scripts/heal_breadth_split_seams.py "
                  f"--data-dir {data_dir} --universes {name}", flush=True)
        if len(splits) > 20:
            print(f"::error title=ohlc-basis-split::…and {len(splits) - 20} more "
                  f"split ticker(s) — see data/quality/ohlc_basis_coherence.json", flush=True)
        return 3

    _write_marker(data_dir, marker)
    print(f"OHLC basis coherent across {len(names)} panel(s): {', '.join(names)} "
          f"({noise} isolated bad-bar ticker(s) below the split threshold)", flush=True)
    return 0


def _selftest() -> int:
    """Synthetic assertions over the classifier — the shapes this guard exists for."""
    idx = pd.date_range("2024-01-01", periods=60, freq="B")

    def frame(vals: dict) -> pd.DataFrame:
        return pd.DataFrame(vals, index=idx)

    base = pd.Series(100.0, index=idx)
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    # 1. clean panel -> no findings at all.
    r = classify(frame({"A": base}), frame({"A": base * 1.02}), frame({"A": base * 0.98}))
    check("clean panel yields findings", r == [])

    # 2. REZI shape: close ~1.35x high across the whole history -> split.
    r = classify(frame({"R": base * 1.35}), frame({"R": base}), frame({"R": base * 0.98}))
    check("REZI-shaped basis split not classified split",
          len(r) == 1 and r[0]["verdict"] == "split" and r[0]["bad_bars"] == 60)

    # 3. one isolated 2.5% bad bar (the ex-dividend rounding floor) -> noise, not split.
    h = base * 1.02
    h.iloc[3] = base.iloc[3] * 0.975
    r = classify(frame({"N": base}), frame({"N": h}), frame({"N": base * 0.98}))
    check("isolated bad bar escalated to split",
          len(r) == 1 and r[0]["verdict"] == "noise" and r[0]["bad_bars"] == 1)

    # 4. small-magnitude split: 3% off but on every bar -> caught by the share limb.
    r = classify(frame({"S": base * 1.03}), frame({"S": base}), frame({"S": base * 0.9}))
    check("low-magnitude whole-history split missed by the share limb",
          len(r) == 1 and r[0]["verdict"] == "split")

    # 5. share limb needs volume: 4 bad bars out of 6 present is 67% but under min_bad_bars.
    short = pd.date_range("2024-01-01", periods=6, freq="B")
    c = pd.DataFrame({"T": 100.0}, index=short)
    hh = pd.DataFrame({"T": [99.0, 99.0, 99.0, 99.0, 101.0, 101.0]}, index=short)
    ll = pd.DataFrame({"T": 90.0}, index=short)
    r = classify(c, hh, ll)
    check("min_bad_bars floor not honoured",
          len(r) == 1 and r[0]["verdict"] == "noise" and r[0]["bad_bars"] == 4)

    # 6. inverted low>high on a present pair is a finding.
    r = classify(frame({"I": base}), frame({"I": base * 0.90}), frame({"I": base * 1.10}))
    check("inverted low>high not reported",
          len(r) == 1 and r[0]["inverted_bars"] == 60)

    # 7. NaN cells are excluded, never counted as violations.
    c2 = base.copy()
    c2.iloc[:30] = float("nan")
    r = classify(frame({"A": c2}), frame({"A": base * 1.02}), frame({"A": base * 0.98}))
    check("NaN closes produced findings", r == [])

    # 8. disjoint columns / empty overlap -> no crash, no findings.
    check("disjoint columns crashed",
          classify(frame({"A": base}), frame({"B": base}), frame({"C": base})) == [])

    for f in failures:
        print(f"selftest FAIL: {f}", flush=True)
    print(f"selftest: {8 - len(failures)}/8 assertions passed", flush=True)
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data",
                    help="the data/ directory whose breadth caches to check")
    ap.add_argument("--panels", nargs="*", default=None,
                    help="namespaces to check (default: every data/<ns>/ with the triple)")
    ap.add_argument("--hard-tol", type=float, default=HARD_TOL,
                    help="fractional excess outside [low, high] that is a split outright")
    ap.add_argument("--share-tol", type=float, default=SHARE_TOL,
                    help="violating-bar share that is a split regardless of magnitude")
    ap.add_argument("--min-bad-bars", type=int, default=MIN_BAD_BARS,
                    help="minimum violating bars before the share limb can fire")
    ap.add_argument("--selftest", action="store_true",
                    help="run synthetic classifier assertions and exit")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    try:
        return run(args.data_dir, args.panels, args.hard_tol, args.share_tol,
                   args.min_bad_bars)
    except Exception as e:  # noqa: BLE001 — an unexpected crash is exit 2, not a false green
        print(f"::error title=ohlc-basis-coherence::guard crashed ({e})", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
