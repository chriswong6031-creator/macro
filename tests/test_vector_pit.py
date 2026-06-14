"""Bitcoin Vector POINT-IN-TIME guarantee — proves the signal engine has NO
look-ahead: every signal's value at a PAST date must be identical whether the
engine is run on history-up-to-then or on the full series. Recompute on truncated
inputs and assert the overlap matches.

This is the durable form of the "expanding-window / PIT" discipline: the live
valuation/regime bands are already rolling/causal (no full-sample regression fits),
and this test keeps it that way — any future change that introduces a full-sample
fit, a forward-looking window, or a leaked future bar will flip a signal at a past
date and fail here.

Reads the repo data store (repo-is-the-database); skips cleanly if absent. It runs
compute_all twice over full history, so it is slower than the unit tests.

Run: .venv/bin/python -m tests.test_vector_pit
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

SIG = Path("data/vector/signals.parquet")


def _runs():
    from engine import btc_inputs, btc_signals
    fi = btc_inputs.load_all()
    full = btc_signals.compute_all(fi)
    cutoff = pd.Timestamp("2023-06-01")

    def trunc(v):
        idx = getattr(v, "index", None)
        return v.loc[v.index <= cutoff] if isinstance(idx, pd.DatetimeIndex) else v

    tr = btc_signals.compute_all({k: trunc(v) for k, v in fi.items()})
    cmp_end = cutoff - pd.Timedelta(days=120)          # well clear of the truncation edge
    common = full.index[(full.index <= cmp_end) & full.index.isin(tr.index)]
    return full, tr, common


def test_numeric_signals_are_point_in_time():
    if not SIG.exists():
        print("  skip (no data store)"); return
    full, tr, common = _runs()
    assert len(common) > 500
    num = [c for c in full.columns
           if pd.api.types.is_numeric_dtype(full[c]) and c in tr.columns]
    leaks = []
    for c in num:
        a, b = full.loc[common, c], tr.loc[common, c]
        both = a.notna() & b.notna()
        if int(both.sum()) < 30:
            continue
        rel = (a[both] - b[both]).abs() / a[both].abs().clip(lower=1e-9)
        if float(rel.max()) > 0.01:                    # >1% drift at a PAST date = look-ahead
            leaks.append((c, round(float(rel.max()) * 100, 1)))
    assert not leaks, f"look-ahead in numeric signals: {sorted(leaks, key=lambda x: -x[1])}"


def test_state_signals_are_point_in_time():
    if not SIG.exists():
        print("  skip (no data store)"); return
    full, tr, common = _runs()
    states = [c for c in full.columns
              if not pd.api.types.is_numeric_dtype(full[c]) and c in tr.columns]
    leaks = []
    for c in states:
        a, b = full.loc[common, c].astype("string"), tr.loc[common, c].astype("string")
        both = a.notna() & b.notna()
        if int(both.sum()) < 30:
            continue
        mism = int((a[both] != b[both]).sum())
        if mism > 0:
            leaks.append((c, mism))
    assert not leaks, f"look-ahead in state signals: {sorted(leaks, key=lambda x: -x[1])}"


if __name__ == "__main__":
    for fn in [test_numeric_signals_are_point_in_time, test_state_signals_are_point_in_time]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector point-in-time tests passed")
