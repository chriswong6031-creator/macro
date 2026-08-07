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

WHY IT RUNS MORE THAN ONCE
--------------------------
The first heal (#4590) merged at 02:15 on 2026-08-05. The nightly asia collect lane had
already checked the repo out, and committed at 02:27 from that PRE-heal tree — rewriting
``china_lhb/detail.parquet`` and ``china_lhb/events.parquet`` wholesale and reverting the
heal on exactly those two files (the other seven were not written by that run and stayed
healed). The producer was never the problem the second time round: the 08-06 and 08-07
collections appended correct ``.BJ`` rows on top, leaving the store split across both
keys. A checkout-before-merge race can do this again, so this script is a maintained
tool, not a one-shot.

SAFETY
------
- Idempotent: a second run is a no-op (it re-reads and finds nothing to rewrite).
- Never invents rows. Only rewrites the suffix of a ticker whose 6-digit body already
  starts with 92, and only when the current suffix is the known-wrong ``.SS``/``.SZ``.
- LABEL-ONLY BY DEFAULT. Row count is an enforced invariant: the rewrite must leave
  ``len(df)`` untouched or the file is not written. Blanket de-duplication is never
  performed — several of these stores legitimately carry MULTIPLE rows per
  ``(asof, ticker)`` (china_preannounce keys by 预测指标/quarter, china_buyback by plan,
  china_lhb/history.parquet by ``(date, ticker, reason)``), so applying the collectors'
  keep-last dedup there would silently destroy real rows rather than heal a label.
- THE ONE EXCEPTION — a stale row whose live twin already exists. Since the producer fix
  landed, these stores accrue correct ``.BJ`` rows, so a store can now hold BOTH
  ``920117.SS`` and ``920117.BJ`` for one ``(date, company)``: the same event observed
  once under the dead key and once under the live one. Relabelling alone would mint a
  duplicate. Such a row is dropped rather than relabelled, but ONLY when all of the
  following hold, checked per file, per run — otherwise the file aborts untouched:
    * the store declares a natural PIT key (the ``date_col`` its collector hands
      ``_drip.append_snapshot``, which de-dups ``(date_col, ticker)`` keep-LAST), and
    * that key is ALREADY unique in the store on disk, proving it is a real key here, and
    * every stale row PRECEDES its live twin, so the drop is exactly what the collectors'
      own keep-last rule would do on the next append, and
    * no ``(key, Beijing code)`` observation is lost — the coverage set is compared
      before and after, and an unequal set aborts the file.
  Rows are only ever dropped where the surviving twin carries the same ``(key, code)``.
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

# Stores written by collectors/china_analyst.to_ticker, as
# ``(path, raw-code cross-check column, natural PIT key column)``.
#
# The raw-code column (where the store retains one) cross-checks the rewrite. The key
# column is the ``date_col`` the store's collector hands ``_drip.append_snapshot``, which
# de-dups ``(date_col, ticker)`` keep-LAST — it is what makes a stale/live twin pair
# resolvable. Declare it ONLY where that pair is genuinely the store's key:
#   china_lhb/detail  -> append_snapshot(OUT, rows, date_col="asof")
#   china_lhb/events  -> append_snapshot(EVENTS, ev, date_col="date")
#   china_zt_pool     -> append_snapshot(OUT, rows, date_col="date")
# ``None`` means the store legitimately holds several rows per (date, ticker) and a
# collision there must be resolved by hand, not guessed: china_preannounce keys by
# 预测指标/quarter, china_buyback by plan, china_lhb/history by (date, ticker, reason)
# (scripts/backfill_china_lhb.py), china_analyst and china_unlocks likewise carry
# duplicate (asof, ticker) pairs on disk today.
STORES: list[tuple[str, str | None, str | None]] = [
    ("data/china_analyst/forecast.parquet", None, None),
    ("data/china_block_trades/detail.parquet", None, None),
    ("data/china_buyback/buyback.parquet", None, None),
    ("data/china_lhb/detail.parquet", None, "asof"),
    ("data/china_lhb/events.parquet", None, "date"),
    ("data/china_lhb/history.parquet", None, None),
    ("data/china_preannounce/forecast.parquet", "股票代码", None),
    ("data/china_unlocks/detail.parquet", "股票代码", None),
    ("data/china_zt_pool/pool.parquet", None, "date"),
]

# A 6-digit body starting with 92, carrying one of the two known-wrong suffixes.
BAD = re.compile(r"^(92\d{4})\.(SS|SZ)$")


def _heal_series(s: pd.Series) -> tuple[pd.Series, int]:
    """Rewrite 92xxxx.SS / 92xxxx.SZ -> 92xxxx.BJ. Returns (healed, n_changed)."""
    out = s.astype(str).str.replace(BAD, r"\1.BJ", regex=True)
    return out, int((out != s.astype(str)).sum())


def _twin_mask(df: pd.DataFrame, key_col: str, before: pd.Series,
               healed: pd.Series) -> pd.Series:
    """Stale rows whose healed key lands on a row that is ALREADY correctly keyed `.BJ`.

    Each one is the same ``(key, Beijing code)`` observation recorded twice — once under
    the dead suffix, once under the live one — so relabelling it would mint a duplicate.
    """
    keys = df[key_col].astype(str)
    live_bj = before.str.endswith(".BJ")
    live = set(zip(keys[live_bj], before[live_bj]))
    landing = pd.Series(list(zip(keys, healed)), index=df.index)
    return (before != healed) & landing.map(lambda k: k in live)


def _coverage(keys: pd.Series, ticker: pd.Series) -> set:
    """The ``(key, Beijing 6-digit code)`` pairs a store observes. Invariant across a
    heal: relabelling must not lose a single Beijing name-day, whatever the suffix."""
    body = ticker.str.extract(r"^(92\d{4})\.", expand=False)
    keep = body.notna()
    return set(zip(keys[keep], body[keep]))


def heal_file(rel: str, code_col: str | None, key_col: str | None,
              *, write: bool) -> tuple[int, str]:
    path = ROOT / rel
    if not path.exists():
        return 0, "missing"
    df = pd.read_parquet(path).reset_index(drop=True)
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

    # Does any healed key land on a row that is already correctly keyed? Under the first
    # heal no store held a `.BJ` row at all, so the mere presence of one was treated as
    # unsafe. It no longer is — every store accrues `.BJ` rows now — so the question is
    # narrowed to whether a healed key actually COLLIDES with a live one.
    drop = pd.Series(False, index=df.index)
    if before.str.endswith(".BJ").any():
        if not (key_col and key_col in df.columns):
            return 0, ("ABORT: store holds .BJ rows and declares no unique PIT key — "
                       "a collision here cannot be resolved mechanically, heal by hand")
        drop = _twin_mask(df, key_col, before, healed)
        if drop.any():
            keys = df[key_col].astype(str)
            # The store's own key must ALREADY be unique, or collapsing a pair is not a
            # de-duplication at all — it is the row destruction this script refuses to do.
            if df.duplicated(subset=[key_col, "ticker"]).any():
                return 0, (f"ABORT: ({key_col}, ticker) is already non-unique in this "
                           "store — collapsing twins would destroy real rows")
            # keep-LAST equivalence: the stale row must PRECEDE its live twin, so this
            # drop is exactly what _drip.append_snapshot would do on the next append.
            pos = pd.Series(range(len(df)), index=df.index)
            for k_key, k_tick in set(zip(keys[drop], healed[drop])):
                stale = pos[drop & (keys == k_key) & (healed == k_tick)]
                live = pos[before.str.endswith(".BJ") & (keys == k_key) & (before == k_tick)]
                if not len(live) or stale.max() > live.min():
                    return 0, (f"ABORT: stale {k_tick} on {k_key} does not precede its "
                               ".BJ twin — keep-last is ambiguous, heal by hand")

    n_drop = int(drop.sum())
    if not write:
        note = f"would rewrite {n}"
        return n, note + (f" (incl. {n_drop} stale twin(s) to drop)" if n_drop else "")

    rows_before = len(df)
    cover_before = _coverage(df[key_col].astype(str), before) if key_col and key_col in df.columns else None

    out = df.assign(ticker=healed)[~drop].reset_index(drop=True)

    if len(out) != rows_before - n_drop:
        return 0, f"ABORT: row count moved {rows_before} -> {len(out)} (expected -{n_drop})"
    if cover_before is not None:
        after = out["ticker"].astype(str)
        if _coverage(out[key_col].astype(str), after) != cover_before:
            return 0, "ABORT: heal would lose a (key, Beijing code) observation"
        if out.duplicated(subset=[key_col, "ticker"]).any():
            return 0, f"ABORT: ({key_col}, ticker) is not unique after the heal"
    out.to_parquet(path, index=False)
    if n_drop:
        return n, (f"rewrote {n - n_drop}, dropped {n_drop} stale twin(s) "
                   f"(rows {rows_before} -> {len(out)})")
    return n, f"rewrote {n} (rows {rows_before} unchanged)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing (exit 1 if anything would)")
    args = ap.parse_args()

    total, aborted = 0, False
    for rel, code_col, key_col in STORES:
        n, note = heal_file(rel, code_col, key_col, write=not args.check)
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
