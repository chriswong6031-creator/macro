"""End-of-collection coverage audit: does every configured ticker actually EXIST on disk
with enough history to be usable?

config.yml names hundreds of tickers across sector/ETF/theme/constituent/index lists, but a
name in the config is a promise, not a guarantee — a collector can silently skip a delisted
symbol, a feed can rename a ticker, a wide store can drop a column. This audit walks every
configured cohort and, per ticker, asks one question: is there a series here with at least
cfg['universe_min_bars'] (250) rows?

Each cohort is one Universe (audit_common.Universe). The cohorts are backed by DIFFERENT
stores (per-ticker parquet dirs, wide single-parquet column tables, per-ticker JSON snapshots),
so resolution is abstracted behind RESOLVERS. A resolver, given a ticker, returns one of:
  ("ok", bars)            found & counted  -> bars < min => u.fail("short: ...")
  ("missing", None)       not found        -> see missing policy below
  ("unreadable", err)     found but corrupt/locked -> always u.fail (distinct from absent)
  ("nobars", None)        found, count indeterminate (in the universe but price in the
                          git-excluded breadth cache, or a snapshot w/o a price array)
                          -> NOT a fail; u.flag(..., "nobars", ...) informational
  ("store_unavailable",.) the backing store itself is absent -> the WHOLE universe is
                          skipped=True (never mass-fail a cohort for a missing store)

MISSING POLICY depends on the store's COMPLETENESS:
  - COMPLETE per-ticker stores (data/yahoo for US ETFs; the membership table for themes) — a
    configured ticker absent here is a real config error (typo / delisted) -> u.fail.
  - COVERAGE-LIMITED stores (the *_search close-matrices and the HK chart JSONs deliberately
    cover a capped set) — "not in this store" usually means "outside the coverage set", not
    corruption -> u.flag("missing", ...). A present-but-TRUNCATED series (< min_bars) is still
    a hard u.fail, because that IS a real data problem.

A resolver checks store presence ONCE up front; if absent the universe is marked skipped
(n=0, note set) before any per-ticker work. This is what keeps the audit honest on a partial
checkout: an absent store is a "we didn't collect this here", not "every ticker is broken".

GUARD: data/china_stocks & data/hk_stocks hold only latest.json (no per-ticker parquet); a
per-ticker-parquet resolver pointed at such a dir yields store_unavailable, never crashes.

DETERMINISTIC, idempotent, READ-ONLY over the stores (writes only data/quality/universe_audit.json).
Run:    python -m scripts.audit_universe
Import: from scripts import audit_universe
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from lib import config
from scripts import audit_common as ac

log = logging.getLogger("audit.universe")


# --- safe-name (mirror lib.store._path, so a passed-in data_dir override works) -----------

def _safe(name: str) -> str:
    """Replicate the store's unsafe-char map inline (^=/space -> _) so resolvers honor a
    data_dir override instead of leaning on the global store path."""
    return name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")


# --- resolvers --------------------------------------------------------------------------
#
# A resolver is a small object with:
#   .available -> bool   (is the backing store present? checked ONCE per universe)
#   .store     -> str    (human label for fail/skip messages)
#   .bars(ticker) -> (status, value)   one of the four statuses above
# run() never asks a resolver about a ticker when .available is False.


class ParquetDirResolver:
    """Per-ticker parquet under <data_dir>/<group>/<safe>.parquet. The dir must exist and
    actually hold .parquet files; a dir with only latest.json (china_stocks / hk_stocks) is
    treated as no per-ticker store -> store_unavailable (the required GUARD)."""

    def __init__(self, data_dir: Path, group: str):
        self.data_dir = data_dir
        self.group = group
        self.dir = data_dir / group
        self.store = f"data/{group}"
        self.available = self.dir.is_dir() and any(self.dir.glob("*.parquet"))

    def bars(self, ticker: str):
        p = self.dir / f"{_safe(ticker)}.parquet"
        if not p.exists():
            return ("missing", None)
        try:
            df = pd.read_parquet(p)
        except Exception as e:  # corrupt/locked file — a real problem, distinct from absent
            return ("unreadable", f"{e}")
        return ("ok", len(ac.clean_index(df)))


class MultiParquetDirResolver:
    """Per-ticker parquet that may live in one of several stores. The bar count is the DEEPEST
    across all stores that hold the ticker (a name can sit in data/stocks as a shallow recent
    backfill AND in data/baskets/ohlcv with full history — the depth is what 'exists with >= N
    bars' means). Available if ANY candidate dir holds parquet files; an unreadable file in a
    store is reported only if NO store has a readable series."""

    def __init__(self, data_dir: Path, groups: list[str]):
        self.resolvers = [ParquetDirResolver(data_dir, g) for g in groups]
        self.store = " | ".join(r.store for r in self.resolvers)
        self.available = any(r.available for r in self.resolvers)

    def bars(self, ticker: str):
        best = None
        unreadable = None
        for r in (r for r in self.resolvers if r.available):
            status, val = r.bars(ticker)
            if status == "ok":
                best = int(val) if best is None else max(best, int(val))
            elif status == "unreadable":
                unreadable = val
            # "missing" here -> just try the next store
        if best is not None:
            return ("ok", best)
        if unreadable is not None:
            return ("unreadable", unreadable)
        return ("missing", None)


class WideParquetResolver:
    """A single wide parquet whose COLUMNS are tickers (china_search / canada_search closes).
    Loaded once and cached; bars = non-null count of the ticker's column; absent column =>
    missing. The file itself absent => store_unavailable."""

    def __init__(self, data_dir: Path, rel_path: str):
        self.path = data_dir / rel_path
        self.store = f"data/{rel_path}"
        self.available = self.path.exists()
        self._df: pd.DataFrame | None = None
        if self.available:
            try:
                self._df = ac.clean_index(pd.read_parquet(self.path))
            except Exception as e:
                log.warning("wide store %s unreadable: %s", rel_path, e)
                self.available = False

    def bars(self, ticker: str):
        if self._df is None or ticker not in self._df.columns:
            return ("missing", None)
        return ("ok", int(self._df[ticker].notna().sum()))


class HkJsonResolver:
    """Per-ticker JSON snapshot under site/hkstockdata/<ticker>.json. Bars = length of the
    chart price array (chart.t / chart.c) when present, else nobars (a snapshot without a
    determinable history is informational, not a failure). Missing file => missing; the dir
    absent entirely => store_unavailable."""

    def __init__(self, root: Path):
        self.dir = root / "site" / "hkstockdata"
        self.store = "site/hkstockdata"
        self.available = self.dir.is_dir() and any(self.dir.glob("*.json"))

    @staticmethod
    def _chart_len(d: dict) -> int | None:
        chart = d.get("chart")
        if isinstance(chart, dict):
            for k in ("t", "c"):
                v = chart.get(k)
                if isinstance(v, list):
                    return len(v)
        return None

    def bars(self, ticker: str):
        p = self.dir / f"{ticker}.json"
        if not p.exists():
            return ("missing", None)
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            return ("missing", f"unreadable: {e}")
        n = self._chart_len(d) if isinstance(d, dict) else None
        return ("ok", n) if n is not None else ("nobars", None)


class MembershipResolver:
    """Theme / basket single-names. Their canonical EXISTENCE is membership in
    data/universe/membership.parquet (the S&P 1500 set the themes are curated from). Their PRICE
    history may live in a committed per-ticker store (data/stocks, data/baskets/ohlcv) OR in the
    breadth close-matrix cache that is deliberately kept OUT of git (see LIMITATIONS.md). So:
      - present in a committed price store           -> ('ok', bars)        [can check >= min_bars]
      - in membership but no committed price parquet -> ('nobars', None)    [expected, NOT a fail]
      - absent from BOTH membership and price stores -> ('missing', None)   [real config typo -> fail]
    store_unavailable only if the membership table itself is absent."""

    def __init__(self, data_dir: Path, price_groups: list[str]):
        self.prices = MultiParquetDirResolver(data_dir, price_groups)
        self.path = data_dir / "universe" / "membership.parquet"
        self.store = "data/universe/membership.parquet"
        self.available = self.path.exists()
        self._members: set[str] = set()
        if self.available:
            try:
                m = pd.read_parquet(self.path, columns=["ticker"])
                self._members = {str(t) for t in m["ticker"].dropna().tolist()}
            except Exception as e:  # corrupt membership table — treat the cohort as unauditable
                log.warning("membership table unreadable: %s", e)
                self.available = False

    def bars(self, ticker: str):
        status, val = self.prices.bars(ticker)
        if status in ("ok", "unreadable"):
            return (status, val)            # a committed price series (or a corrupt one) wins
        if ticker in self._members:         # in the universe but price is in the git-excluded cache
            return ("nobars", None)
        return ("missing", None)            # not even in membership = a real config error


# --- universe ticker lists (from config) ------------------------------------------------

def _dedup(seq) -> list[str]:
    """Sorted unique, preserving only truthy string tickers (stable, deterministic output)."""
    return sorted({t for t in (seq or []) if isinstance(t, str) and t})


def _flatten(d: dict | None) -> list[str]:
    out: list[str] = []
    for v in (d or {}).values():
        if isinstance(v, list):
            out.extend(v)
    return out


def _theme_tickers(conf: dict) -> list[str]:
    out: list[str] = []
    for th in (conf.get("themes") or {}).values():
        if isinstance(th, dict):
            out.extend(th.get("tickers") or [])
    return _dedup(out)


def _etf_union(conf: dict) -> list[str]:
    t = (conf.get("yahoo") or {}).get("tickers") or {}
    keys = ["extras", "style", "factors", "ipo", "credit", "bond_etfs", "intl_etfs"]
    out: list[str] = []
    for k in keys:
        out.extend(t.get(k) or [])
    return _dedup(out)


def _hk_members(conf: dict) -> list[str]:
    out: list[str] = []
    for sec in (conf.get("hk") or {}).get("sectors", {}).values():
        if isinstance(sec, dict):
            out.extend(sec.get("members") or [])
    return _dedup(out)


def _intl_indices(conf: dict) -> list[str]:
    ctr = (conf.get("intl") or {}).get("countries") or {}
    out = [v.get("index") for v in ctr.values() if isinstance(v, dict) and v.get("index")]
    return _dedup(out)


# --- per-universe driver ----------------------------------------------------------------

def _run_universe(name: str, tickers: list[str], resolver, min_bars: int,
                  missing_is_fail: bool = True) -> ac.Universe:
    """Resolve every ticker through one resolver. Store absent -> skipped (no mass-fail).
    short -> fail; unreadable -> fail; nobars -> flag; missing -> fail on a COMPLETE store, or
    flag on a coverage-limited one (missing_is_fail=False)."""
    u = ac.Universe(name)
    if not resolver.available:
        u.skipped = True
        u.note = f"store {resolver.store} unavailable — cohort skipped (not failed)"
        u.n = 0
        log.info("universe %-20s SKIPPED (%s)", name, resolver.store)
        return u

    u.n = len(tickers)
    for t in tickers:
        status, val = resolver.bars(t)
        if status == "ok":
            bars = int(val)
            if bars < min_bars:
                u.fail(t, f"short: {bars} bars < {min_bars}")
        elif status == "unreadable":
            u.fail(t, f"unreadable in {resolver.store}: {val}")
        elif status == "missing":
            if missing_is_fail:
                u.fail(t, f"missing from {resolver.store}")
            else:
                u.flag(t, "missing", f"not in {resolver.store} (coverage-limited store)")
        elif status == "nobars":
            u.flag(t, "nobars", f"present in {resolver.store}, bar-count indeterminate")
        # store_unavailable per-ticker should not occur (we gate on .available up front)
    log.info("universe %-20s n=%d failed=%d flags=%d", name, u.n, u.n_failed, len(u.flags))
    return u


# --- public entrypoint ------------------------------------------------------------------

def run(cfg: dict | None = None, asof: date | None = None,
        out_dir: Path | None = None, data_dir: Path | None = None,
        conf: dict | None = None) -> dict:
    """Build every configured-universe coverage check and write data/quality/universe_audit.json.

    cfg overrides the quality block; conf overrides config.yml; data_dir overrides the data
    root (resolvers honor it via the inline safe-name); asof/out_dir are test seams. Returns
    the audit document; NEVER raises for data issues (they are recorded as fails/flags)."""
    cfg = cfg or ac.quality_cfg()
    conf = conf or config.load()
    data_dir = data_dir or config.data_dir()
    root = data_dir.parent  # site/hkstockdata lives beside data/, under the repo root
    min_bars = int(cfg.get("universe_min_bars", 250))

    universes: list[ac.Universe] = []

    # 1) US sector ETFs -> per-ticker parquet in data/yahoo
    universes.append(_run_universe(
        "us_sectors", _dedup((conf.get("yahoo") or {}).get("tickers", {}).get("sectors")),
        ParquetDirResolver(data_dir, "yahoo"), min_bars))

    # 2) US ETF zoo (extras|style|factors|ipo|credit|bond_etfs|intl_etfs) -> data/yahoo
    universes.append(_run_universe(
        "us_etfs", _etf_union(conf),
        ParquetDirResolver(data_dir, "yahoo"), min_bars))

    # 3) Theme single-names -> membership table (existence) + data/stocks|baskets/ohlcv (bars).
    #    A name absent from membership is a real config typo (fail); a name in membership but
    #    without a committed price parquet is fine (price lives in the git-excluded breadth cache).
    universes.append(_run_universe(
        "us_themes", _theme_tickers(conf),
        MembershipResolver(data_dir, ["stocks", "baskets/ohlcv"]), min_bars))

    # 4) China constituents -> wide column table data/china_search/closes.parquet (coverage-limited:
    #    the search set is capped, so "not a column" is a coverage flag, not a fail; truncated fails).
    universes.append(_run_universe(
        "china_constituents", _dedup(_flatten((conf.get("china") or {}).get("constituents"))),
        WideParquetResolver(data_dir, "china_search/closes.parquet"), min_bars, missing_is_fail=False))

    # 5) Canada constituents -> wide column table data/canada_search/closes.parquet (coverage-limited)
    universes.append(_run_universe(
        "canada_constituents", _dedup(_flatten((conf.get("canada") or {}).get("constituents"))),
        WideParquetResolver(data_dir, "canada_search/closes.parquet"), min_bars, missing_is_fail=False))

    # 6) HK sector members -> per-ticker JSON snapshots site/hkstockdata/<ticker>.json (coverage-limited:
    #    only the charted names are stored, so "no json" is a coverage flag, not a fail).
    universes.append(_run_universe(
        "hk_sectors", _hk_members(conf),
        HkJsonResolver(root), min_bars, missing_is_fail=False))

    # 7) Intl headline indices -> priority parquet stores yahoo > intl_prices > intl
    universes.append(_run_universe(
        "intl_indices", _intl_indices(conf),
        MultiParquetDirResolver(data_dir, ["yahoo", "intl_prices", "intl"]), min_bars))

    doc = ac.write_audit("universe", "universe", universes, cfg, asof=asof, out_dir=out_dir)
    active = [u for u in universes if not u.skipped]
    log.info("universe audit: %d cohorts (%d active), n=%d failed=%d flags=%d",
             len(universes), len(active), doc["n"], doc["n_failed"], doc["n_flags"])
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Configured-universe coverage audit.")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="override the data root (default: config data_dir)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="override the data/quality output dir")
    ap.add_argument("--asof", type=str, default=None, help="YYYY-MM-DD asof override")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s")

    asof = date.fromisoformat(args.asof) if args.asof else None
    doc = run(asof=asof, out_dir=args.out_dir, data_dir=args.data_dir)

    print(f"universe audit asof={doc['asof']}  n={doc['n']}  "
          f"failed={doc['n_failed']} ({doc['fail_pct']}%)  flags={doc['n_flags']}")
    for u in doc["universes"]:
        tag = "SKIPPED" if u["skipped"] else (
            f"failed={u['n_failed']:>3} flags={u['n_flags']:>3}")
        print(f"  {u['name']:20s} n={u['n']:>3}  {tag}"
              + (f"  [{u['note']}]" if u["skipped"] else ""))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
