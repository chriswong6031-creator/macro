"""One-time heal: re-key Beijing 92xxxx rows written under a wrong exchange suffix.

WHY THIS EXISTS
---------------
`collectors/china_analyst.to_ticker` — the shared A-share mapper a dozen Eastmoney
collectors import — tested Shanghai with a bare ``c[0] in ("6", "9")``. The ``9`` is
there for Shanghai's 900xxx B-shares, but the Beijing Stock Exchange has issued 92xxxx
codes since the 2023 renumbering, so every Beijing name was stamped ``.SS`` — a ticker
no exchange has issued — and could never reach the mapper's own ``.BJ`` branch.

The producer is fixed. These stores, however, ACCRUE (``collectors/_drip.append_snapshot``,
keep-last on ``(date_col, ticker)``), so the fix alone never rewrites history: without
this heal the same company stays split across two keys by era, and the rendered site
keeps serving dead tickers (site/china_special_situations.html prints the ticker as the
lead identity of an unlock row, with no company name beside it).

An earlier era of the mapper sent 92xxxx to ``.SZ`` instead — visible as a clean date
boundary in china_zt_pool (``.SZ`` through 2026-06-25, ``.SS`` from 2026-07-01). BOTH
wrong suffixes are healed.

SAFETY
------
- Idempotent: a second run is a no-op (it re-reads and finds nothing to rewrite).
- Never invents rows. Only rewrites the suffix of a ticker whose 6-digit body already
  starts with 92, and only when the current suffix is the known-wrong ``.SS``/``.SZ``.
- STRICTLY LABEL-ONLY. Row count is an enforced invariant: the rewrite must leave
  ``len(df)`` untouched or the file is not written. No de-duplication is performed —
  several of these stores legitimately carry MULTIPLE rows per ``(asof, ticker)``
  (china_preannounce keys by 预测指标/quarter, china_buyback by plan), so applying the
  collectors' keep-last dedup here would silently destroy real rows rather than heal a
  label. It is also unnecessary: no store holds a single pre-existing ``.BJ`` row, so
  relabelling ``.SS``/``.SZ`` -> ``.BJ`` cannot create a collision that did not already
  exist in exactly the same shape under the wrong suffix. The invariant is what proves
  it, on every run, per file.
- ``--check`` reports without writing (used to prove the heal is complete).
- Where the store also retains the raw Eastmoney code column (``股票代码``), the rewrite
  is cross-checked against it and a mismatch aborts that file rather than guessing.

Scope note: data/cn_holder_sales/* also carries 92xxxx rows, but that lane has its own
two mappers and its own ``.SH``/``.SZ`` suffix vocabulary (not the ``.SS``/``.SZ``/``.BJ``
used here) and is consumed only by the d2/d4 phase0 research scripts. It needs its own
producer fix first and is deliberately NOT touched by this heal.

Usage:
    python3 scripts/heal_cn_beijing_tickers.py --check
    python3 scripts/heal_cn_beijing_tickers.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# Stores written by collectors/china_analyst.to_ticker. Raw-code column (where the store
# retains one) is used to cross-check the rewrite.
STORES: list[tuple[str, str | None]] = [
    ("data/china_analyst/forecast.parquet", None),
    ("data/china_block_trades/detail.parquet", None),
    ("data/china_buyback/buyback.parquet", None),
    ("data/china_lhb/detail.parquet", None),
    ("data/china_lhb/events.parquet", None),
    ("data/china_lhb/history.parquet", None),
    ("data/china_preannounce/forecast.parquet", "股票代码"),
    ("data/china_unlocks/detail.parquet", "股票代码"),
    ("data/china_zt_pool/pool.parquet", None),
]

# A 6-digit body starting with 92, carrying one of the two known-wrong suffixes.
BAD = re.compile(r"^(92\d{4})\.(SS|SZ)$")


def _heal_series(s: pd.Series) -> tuple[pd.Series, int]:
    """Rewrite 92xxxx.SS / 92xxxx.SZ -> 92xxxx.BJ. Returns (healed, n_changed)."""
    out = s.astype(str).str.replace(BAD, r"\1.BJ", regex=True)
    return out, int((out != s.astype(str)).sum())


def heal_file(rel: str, code_col: str | None, *, write: bool) -> tuple[int, str]:
    path = ROOT / rel
    if not path.exists():
        return 0, "missing"
    df = pd.read_parquet(path)
    if "ticker" not in df.columns:
        return 0, "no ticker column"

    before = df["ticker"].astype(str)
    healed, n = _heal_series(before)
    if n == 0:
        return 0, "clean"

    # Cross-check against the retained raw Eastmoney code where the store kept one:
    # every row we are about to rewrite must have a raw code that really starts with 92.
    if code_col and code_col in df.columns:
        touched = before != healed
        raw = df.loc[touched, code_col].astype(str).str.extract(r"(\d{6})", expand=False)
        bad = raw[~raw.fillna("").str.startswith("92")]
        if len(bad):
            return 0, f"ABORT: {len(bad)} rewrite(s) disagree with {code_col}"

    # A healed key must not land on a pre-existing .BJ row. None of these stores holds
    # one, but assert it per-file rather than trusting the survey that said so.
    if before.str.endswith(".BJ").any():
        return 0, "ABORT: store already holds .BJ rows — collision risk, heal by hand"

    if not write:
        return n, f"would rewrite {n}"

    rows_before = len(df)
    df["ticker"] = healed
    if len(df) != rows_before:  # belt-and-braces; a label rewrite cannot change length
        return 0, f"ABORT: row count moved {rows_before} -> {len(df)}"
    df.to_parquet(path, index=False)
    return n, f"rewrote {n} (rows {rows_before} unchanged)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing (exit 1 if anything would)")
    args = ap.parse_args()

    total, aborted = 0, False
    for rel, code_col in STORES:
        n, note = heal_file(rel, code_col, write=not args.check)
        total += n
        if note.startswith("ABORT"):
            aborted = True
        if n or note not in ("clean", "missing"):
            print(f"  {rel:<45s} {note}")

    if aborted:
        print("\nheal ABORTED on at least one store — nothing written for it.")
        return 2
    if args.check:
        print(f"\n--check: {total} row(s) still carry a wrong Beijing suffix.")
        return 1 if total else 0
    print(f"\nhealed {total} row(s) across {len(STORES)} stores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
