"""One-time heal: move current-state stores off a RETIRED ticker onto the live one.

WHY THIS EXISTS
---------------
``breadth.ticker_fixups`` in config.yml ran BACKWARDS for two S&P 500 names — it
"repaired" the symbol that trades into the symbol that does not:

  * Marsh McLennan — real NYSE symbol change MMC -> MRSH on 2026-01-14 (same
    CUSIP 571748102, same listing), misdiagnosed in config as Wikipedia vandalism
    and repaired MRSH -> MMC. Wrong for ~7 months.
  * Fiserv — renamed FISV -> FI in 2023, then BACK FI -> FISV on 2025-11-11. The
    2023-era fixup FISV -> FI was never re-pointed. Wrong for ~9 months.

The producer is fixed (the map now points retired -> live, and
``scripts/check_symbol_rename_drift.py`` fails CI if it ever inverts again). But
the committed stores were written under the retired key and the fix alone never
rewrites them, so without this heal the universe keeps pointing at a symbol with
no listing and no price while every vendor-fed store sits on the live one.

WHAT IT DOES, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------
Re-keys CURRENT-STATE stores only — the ones that assert "this is what the
company is NOW":

  data/baskets/membership.json, data/baskets/extras.parquet,
  data/breadth/constituents.parquet, data/breadth/ticker_sectors.parquet,
  data/breadth/{_closes,_high,_low,_volume}_cache.parquet

It does NOT touch, by design:

  * data/breadth/sp1500_pit_membership.parquet — already CORRECT. It carries the
    closed MMC interval (1996-01-02 -> 2026-01-14) AND the open MRSH interval
    (2026-01-14 -> NaT). It is the only store in the repo that models the rename
    properly, and it is the reference the drift check grades everything else
    against. Rewriting it would destroy the evidence.
  * Append-only forward ledgers — data/qledger/claims.jsonl (13 open MMC-scoped
    claims, check_by 2026-10-08..10-29), data/name_score/us_calls,
    data/hub/signal_snapshots.jsonl. Operator ruling 2026-08-05: STRAND under the
    retired key and disclose, do not re-key. They stay gradeable because
    ``engine.ai_desk._close_series`` resolves a retired symbol to the live one's
    bars (lib/symbol_aliases).
  * Point-in-time filing history — data/quiver/*, data/sec_insider/*. A 13F filed
    in 2024 really did say "MMC". Readers resolve identity through
    lib.symbol_aliases instead of having their history rewritten.

PRICE COLUMNS ARE RE-PULLED, NOT RENAMED
----------------------------------------
A rename alone would carry the hole forward. The live column is re-downloaded
over the cache's FULL existing index in one request, because ``collectors.breadth``
refreshes only a ``period="1mo"`` window and ``combine_first``s it, while
``ma50``/``ma200``/NH-NL all use ``min_periods == window``: one NaN anywhere in a
trailing 200-bar window silently drops that name out of ``pct_above_200`` entirely.
Measured before this heal: MRSH was NaN from 2026-06-19 (316/345 non-null) and MMC
was 0/345 — so the universe's key had no price at all. Downloading the whole window
in ONE call also puts the column on a single adjustment basis, which is what the
split-seam repair exists to fix (see collectors/breadth module comment).

SAFETY
------
- Idempotent: a second run re-reads and finds nothing to do.
- Never invents rows. The cache INDEX is an enforced invariant — the re-pulled
  series is reindexed onto the existing dates, so only one column's values change
  and the matrix shape cannot move.
- Never drops a retired column that still holds data the live one lacks; it is
  merged (live wins on overlap) before the retired column is removed.
- A failed download leaves the file untouched rather than writing a hole.
- ``--check`` reports without writing (used to prove the heal is complete).

Usage:
    python3 scripts/heal_retired_symbol_keys.py --check
    python3 scripts/heal_retired_symbol_keys.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, symbol_aliases  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("heal_retired_symbol_keys")

_CACHES = {
    "_closes_cache.parquet": "Close",
    "_high_cache.parquet": "High",
    "_low_cache.parquet": "Low",
    "_volume_cache.parquet": "Volume",
}


def _download(symbols: list[str], index: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """{field: frame[symbol]} covering `index`, or {} when the feed gives nothing.

    One request per run for the whole window, so every column lands on a single
    price-adjustment basis (auto_adjust back-adjusts only what it downloads).
    """
    import yfinance as yf
    span_d = int((index.max() - index.min()).days) + 10
    period = "2y" if span_d <= 720 else ("5y" if span_d <= 1800 else "max")
    try:
        raw = yf.download(symbols, period=period, auto_adjust=True,
                          progress=False, group_by="column", threads=False)
    except Exception as e:  # noqa: BLE001 — a feed failure must leave the store untouched
        log.warning("download failed (%s) — no cache column rewritten", e)
        return {}
    if raw is None or not len(raw):
        log.warning("download returned nothing — no cache column rewritten")
        return {}
    lvl0 = (raw.columns.get_level_values(0)
            if isinstance(raw.columns, pd.MultiIndex) else raw.columns)
    out: dict[str, pd.DataFrame] = {}
    for field in set(_CACHES.values()):
        if field not in lvl0:
            continue
        f = raw[field]
        if isinstance(f, pd.Series):
            f = f.to_frame(symbols[0])
        f.index = pd.to_datetime(f.index)
        out[field] = f
    return out


def heal_caches(pairs: dict[str, str], check: bool) -> int:
    """Merge each retired price column into its live one and re-pull the full window."""
    bdir = config.data_dir() / "breadth"
    live_wanted = sorted(set(pairs.values()))
    idx = None
    for fname in _CACHES:
        p = bdir / fname
        if p.exists():
            idx = pd.read_parquet(p).index
            break
    if idx is None:
        log.info("no breadth cache present — nothing to heal")
        return 0
    fetched = {} if check else _download(live_wanted, idx)
    changed = 0

    for fname, field in _CACHES.items():
        p = bdir / fname
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        n_rows, n_cols_before = len(df), len(df.columns)
        touched = False

        for retired, live in pairs.items():
            has_r, has_l = retired in df.columns, live in df.columns
            if not has_r and not has_l:
                continue
            r_n = int(df[retired].notna().sum()) if has_r else 0
            l_n = int(df[live].notna().sum()) if has_l else 0
            if check:
                log.info("%s: %s=%d/%d non-null, %s=%d/%d non-null",
                         fname, retired, r_n, n_rows, live, l_n, n_rows)
                continue
            # keep whatever the retired column holds that the live one lacks
            if has_r and has_l:
                df[live] = df[live].combine_first(df[retired])
            elif has_r:
                df[live] = df[retired]
            if has_r:
                df = df.drop(columns=[retired])
                touched = True

            f = fetched.get(field)
            if f is not None and live in getattr(f, "columns", []):
                # Fill ONLY the dates this cache actually covers. The four caches
                # have different windows on a shared index — closes is the deep
                # ~345-session matrix, while high/low/volume are a ~51-session
                # rolling capture sitting on a 777-row index left over from an
                # older era. Filling the whole index would hand this one ticker
                # ~10x its peers' history and make it a cross-sectional outlier in
                # everything that reads these caches. "Covered" = a row where at
                # least half the columns have data.
                active = df.notna().sum(axis=1) >= (0.5 * df.shape[1])
                s = f[live].reindex(df.index).where(active)   # INDEX INVARIANT
                old = df[live] if live in df.columns else None
                new = s.combine_first(old) if old is not None else s
                before = int(old.notna().sum()) if old is not None else 0
                after = int(new.notna().sum())
                # Write only when a real GAP closes. yfinance restates adjusted
                # closes by fractions of a cent between requests, so comparing
                # values would rewrite the file on every run forever and the heal
                # would never be idempotent. Filling holes is this script's job;
                # continuously restating prices is the nightly collector's.
                # (FISV keeps one permanent hole at 2025-11-12, the session after
                # its FI -> FISV rename — the vendor has no bar there and 7 other
                # tickers miss the same date. An unfillable gap must not loop.)
                if old is None or after > before:
                    log.info("%s: %s re-pulled %d -> %d non-null (of %d covered rows)",
                             fname, live, before, after, int(active.sum()))
                    df[live] = new
                    touched = True

        if touched:
            assert len(df) == n_rows, f"{fname}: row count moved {n_rows} -> {len(df)}"
            assert len(df.columns) <= n_cols_before, f"{fname}: gained columns"
            df.to_parquet(p)
            changed += 1
            log.info("%s: rewritten (%d rows, %d cols)", fname, len(df), len(df.columns))
    return changed


def heal_frames(pairs: dict[str, str], check: bool) -> int:
    """Re-key the current-state parquet stores. Each holds the ticker differently,
    so the location is named per store rather than guessed."""
    d = config.data_dir()
    targets = [
        (d / "breadth" / "constituents.parquet", "index"),    # symbol is the index
        (d / "breadth" / "ticker_sectors.parquet", "ticker"),  # a 'ticker' column
        (d / "baskets" / "extras.parquet", "columns"),         # one column per ticker
    ]
    changed = 0
    for p, where in targets:
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        n_rows = len(df)

        if where == "index":
            hits = {r: l for r, l in pairs.items() if r in df.index}
        elif where == "columns":
            hits = {r: l for r, l in pairs.items() if r in df.columns}
        else:
            hits = ({r: l for r, l in pairs.items() if (df[where] == r).any()}
                    if where in df.columns else {})
        if not hits:
            continue
        if check:
            log.info("%s: would re-key %s (in %s)", p.name, hits, where)
            continue

        # A re-key must never collide with an existing live key and silently
        # merge two rows into one — check before writing, not after.
        if where == "index":
            clash = [l for l in hits.values() if l in df.index]
            assert not clash, f"{p.name}: live key already in index: {clash}"
            df = df.rename(index=hits)
        elif where == "columns":
            clash = [l for l in hits.values() if l in df.columns]
            assert not clash, f"{p.name}: live key already a column: {clash}"
            df = df.rename(columns=hits)
        else:
            df[where] = df[where].replace(hits)

        assert len(df) == n_rows, f"{p.name}: row count moved {n_rows} -> {len(df)}"
        df.to_parquet(p)
        changed += 1
        log.info("%s: re-keyed %s (%d rows preserved)", p.name, hits, n_rows)
    return changed


def heal_membership(pairs: dict[str, str], check: bool) -> int:
    """Re-key ``baskets[*].members[*].ticker`` in data/baskets/membership.json.

    Member count per basket is an enforced invariant — this relabels a member, it
    never adds or drops one. Each touched basket also gets a ``changelog`` entry,
    because a curated basket's membership history is read by humans and a ticker
    silently becoming a different string looks like a roster change.
    """
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return 0
    doc = json.loads(p.read_text())
    baskets = doc.get("baskets", doc)
    if not isinstance(baskets, dict):
        return 0

    hits: dict[str, list[str]] = {}
    for bname, b in baskets.items():
        if not isinstance(b, dict) or not isinstance(b.get("members"), list):
            continue
        members = b["members"]
        n = len(members)
        live_already = {m.get("ticker") for m in members if isinstance(m, dict)}
        new = []
        for m in members:
            t = m.get("ticker") if isinstance(m, dict) else m
            if t in pairs:
                live = pairs[t]
                # relabelling onto a ticker the basket ALREADY holds would make
                # one member two — refuse rather than create a duplicate
                assert live not in live_already, (
                    f"{bname}: {t} -> {live} but {live} is already a member")
                hits.setdefault(bname, []).append(f"{t}->{live}")
                new.append({**m, "ticker": live} if isinstance(m, dict) else live)
            else:
                new.append(m)
        assert len(new) == n, f"{bname}: member count moved {n} -> {len(new)}"
        if bname in hits and not check:
            b["members"] = new
            if isinstance(b.get("changelog"), list):
                b["changelog"].append({
                    "date": "2026-08-05", "action": "rekey",
                    "note": "Ticker rename, not a roster change: "
                            + ", ".join(hits[bname])
                            + ". Same company, same CUSIP, same listing — the old "
                              "symbol was retired by the exchange.",
                })
    if not hits:
        return 0
    if check:
        log.info("membership.json: would re-key %s", hits)
        return 0
    p.write_text(json.dumps(doc, indent=2))
    log.info("membership.json: re-keyed %s", hits)
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report without writing")
    a = ap.parse_args()

    pairs = symbol_aliases.rename_map()
    if not pairs:
        log.info("no retired->live pairs configured — nothing to heal")
        return 0
    log.info("retired -> live: %s", pairs)

    n = 0
    n += heal_caches(pairs, a.check)
    n += heal_frames(pairs, a.check)
    n += heal_membership(pairs, a.check)
    log.info("%s: %d store(s) %s", "CHECK" if a.check else "HEAL", n,
             "would change" if a.check else "rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
