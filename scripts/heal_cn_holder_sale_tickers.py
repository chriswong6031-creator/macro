"""One-time heal: re-key data/cn_holder_sales/* onto the house A-share vocabulary.

WHY THIS EXISTS
---------------
Both producers of this lane (`collectors/cn_holder_sale_calendar._clean` and the
now-retired fork in `scripts/_download_cn_holder.py`) stamped the exchange suffix with a
bare ``code.startswith("6") -> .SH, else -> .SZ``. Two things were wrong with it:

1. **Beijing.** The Beijing Stock Exchange has issued 92xxxx codes since the 2023
   renumbering, and carries 4xxxxx / 8xxxxx from the NEEQ transfers. All of them fell
   into the ``else`` branch and were stamped ``.SZ`` — a Shenzhen ticker for a Beijing
   listing. (Shanghai's 900xxx B-shares went to ``.SZ`` for the same reason; none are
   in the store today, so that half is latent, not present.)
2. **The suffix itself.** The comment above the mapper said ``.SH`` was there "to match
   price store naming". It never did: ``data/china_stocks_raw`` is 100% ``.SS``/``.SZ``
   and has never held a ``.SH`` file. ``scripts/d4_*`` carry an explicit ``.SH -> .SS``
   shim (AM-5) to paper over it; ``scripts/d2_cn_holder_sale_phase0.py`` does not, and
   so joined **0 of 14,411** Shanghai events — the loss surfaced as a plausible
   "absent from price store" coverage percentage rather than an error.

The producers are fixed and now share `collectors.china_ths_concepts.to_suffixed`. This
heals the two files they already wrote.

SAFETY
------
- **STRICTLY LABEL-ONLY, and no de-duplication, ever.** This store legitimately holds
  many rows per ticker (97,959 raw rows over 4,713 tickers — one row per sale, per
  holder, per window), so a keep-last dedup keyed on the ticker would delete real
  history rather than heal a label. That is not hypothetical: an earlier draft of the
  sibling `scripts/heal_cn_beijing_tickers.py` did exactly that and silently destroyed
  ~6,500 legitimate rows. Nothing here groups, sorts, drops, or reindexes.
- The new ticker is **recomputed from SECURITY_CODE** through the same mapper the fixed
  producer uses, not regex-patched — so a healed file is byte-for-byte what a re-run of
  the collector would now write. The 6-digit body is cross-checked against
  SECURITY_CODE first, and a disagreement aborts that file rather than guessing.
- Four invariants are enforced per file, before anything is written, and re-verified by
  re-reading the file from disk afterwards. Any failure aborts that file:
    1. row count identical,
    2. column list identical (same names, same order),
    3. a SHA-256 of every non-``ticker`` column identical,
    4. the multiset of 6-digit code bodies identical.
  Invariant 3 is the load-bearing one: it proves no column other than the label moved.
- Idempotent: a second run recomputes the same tickers, finds nothing changed, and
  writes nothing.
- No collision check is needed or meaningful here — unlike the keep-last accruing stores
  `heal_cn_beijing_tickers.py` handles, this lane has no unique key on ticker and no
  dedup step anywhere in its pipeline, so relabelling cannot merge two rows.

Usage:
    python3 scripts/heal_cn_holder_sale_tickers.py --check
    python3 scripts/heal_cn_holder_sale_tickers.py
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.china_ths_concepts import to_suffixed  # noqa: E402

# Both files carry SECURITY_CODE, so both rewrites are cross-checkable.
STORES: list[str] = [
    "data/cn_holder_sales/raw.parquet",
    "data/cn_holder_sales/windows.parquet",
]

# The only suffixes a pre-heal row may carry. Anything else means this file was not
# written by the mapper described above and must not be rewritten blind.
KNOWN_WRONG = {"SH", "SZ"}


def _col_hash(s: pd.Series) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(s, index=False).values.tobytes()
    ).hexdigest()


def _fingerprint(df: pd.DataFrame) -> dict[str, str]:
    """SHA-256 per column, excluding the label we are allowed to move."""
    return {c: _col_hash(df[c]) for c in df.columns if c != "ticker"}


def _bodies(s: pd.Series) -> Counter:
    return Counter(s.astype(str).str.rsplit(".", n=1).str[0])


def heal_file(rel: str, *, write: bool) -> tuple[int, str]:
    path = ROOT / rel
    if not path.exists():
        return 0, "missing"
    df = pd.read_parquet(path)
    for col in ("ticker", "SECURITY_CODE"):
        if col not in df.columns:
            return 0, f"ABORT: no {col} column"

    before = df["ticker"].astype(str)
    code = df["SECURITY_CODE"].astype(str).str.strip().str.zfill(6)

    # The label must already agree with the raw Eastmoney code; if it does not, the
    # file holds something this heal does not understand.
    body_before = before.str.rsplit(".", n=1).str[0]
    mismatch = int((body_before != code).sum())
    if mismatch:
        return 0, f"ABORT: {mismatch} ticker body/SECURITY_CODE disagreement(s)"

    after = code.map(to_suffixed)
    touched = after != before
    n = int(touched.sum())
    if n == 0:
        return 0, "clean"

    stale = set(before[touched].str.rsplit(".", n=1).str[-1]) - KNOWN_WRONG
    if stale:
        return 0, f"ABORT: unexpected pre-heal suffix(es) {sorted(stale)}"

    # --- invariants, computed before the write ----------------------------------
    rows_before, cols_before = len(df), list(df.columns)
    fp_before, bodies_before = _fingerprint(df), _bodies(before)

    healed = df.copy()
    healed["ticker"] = after
    checks = _verify(healed, rows_before, cols_before, fp_before, bodies_before)
    if checks:
        return 0, f"ABORT: {checks}"

    moves = Counter(
        f"{a.rsplit('.', 1)[-1]}->{b.rsplit('.', 1)[-1]}"
        for a, b in zip(before[touched], after[touched])
    )
    detail = ", ".join(f"{k} {v}" for k, v in sorted(moves.items()))
    if not write:
        return n, f"would rewrite {n} ({detail})"

    healed.to_parquet(path, index=False)

    # --- re-verify against what actually landed on disk --------------------------
    reread = pd.read_parquet(path)
    checks = _verify(reread, rows_before, cols_before, fp_before, bodies_before)
    if checks:
        return n, f"WROTE BUT FAILED RE-READ: {checks}"
    if not reread["ticker"].astype(str).equals(after.reset_index(drop=True)):
        return n, "WROTE BUT FAILED RE-READ: ticker column differs from intent"
    return n, f"rewrote {n} ({detail}); rows {rows_before} unchanged, re-read verified"


def _verify(
    df: pd.DataFrame,
    rows: int,
    cols: list[str],
    fp: dict[str, str],
    bodies: Counter,
) -> str:
    """Return "" if every label-only invariant holds, else the first failure."""
    if len(df) != rows:
        return f"row count moved {rows} -> {len(df)}"
    if list(df.columns) != cols:
        return "column list changed"
    now = _fingerprint(df)
    moved = [c for c in fp if now.get(c) != fp[c]]
    if moved:
        return f"non-ticker column(s) changed: {moved}"
    if _bodies(df["ticker"]) != bodies:
        return "6-digit code bodies changed"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing (exit 1 if anything would)")
    args = ap.parse_args()

    total, aborted = 0, False
    for rel in STORES:
        n, note = heal_file(rel, write=not args.check)
        total += n
        if note.startswith(("ABORT", "WROTE BUT")):
            aborted = True
            print(f"::error title=cn-holder-heal::{rel} {note}", flush=True)
        if n or note not in ("clean", "missing"):
            print(f"  {rel:<40s} {note}")

    if aborted:
        print("\nheal ABORTED on at least one store.")
        return 2
    if args.check:
        print(f"\n--check: {total} row(s) still carry a wrong suffix.")
        return 1 if total else 0
    print(f"\nhealed {total} row(s) across {len(STORES)} stores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
