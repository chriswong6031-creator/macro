"""China A-share SEARCH universe — the broad name set behind the A-Share Analyzer
search box (site/chinastockdata/).

DECOUPLED from collectors/china_breadth.py on purpose. china_breadth is the curated
~80-name large-cap CSI300-style BREADTH/calibration gauge and must stay stable (the
regime engine is tuned on it). This collector instead imports the top-N mainland
A-shares by market cap so "not all Chinese stocks can be searched" stops being true,
WITHOUT perturbing the calibrated engine — exactly how the US side keeps breadth
(S&P 500) separate from its larger search caches (S&P 400/600).

Data planes (both free, verified 2026-06-13):
  * Universe + Chinese names + market-cap ranking : Sina market-center JSON
      (Market_Center.getHQNodeData, node=hs_a, sort=mktcap). One request/page.
  * Close history (5y, for the cycle/ladder engine)  : yfinance (.SS/.SZ), batched.
  * English name + sector (for English search/labels): yfinance get_info, enriched
      once per ticker and CACHED in members.parquet (bounded lookups/run).

Outputs (committed — small; gives the engine CI job the data via git pull, no
fragile cross-job actions/cache):
  data/china_search/closes.parquet   wide [date x ticker] adjusted closes (APPEND-ONLY with
      BOUNDED retention — names leaving the top-N keep their frozen history columns for
      ~2y (frozen_retention_days) then age out, so the file stays small; see below)
  data/china_search/members.parquet  index=ticker; name / name_zh / name_en / sector / mktcap_yi
  data/china_search/dropped.parquet  ticker → dropped_date marker for names that left the live
      top-N (append-only; cleared if a name re-enters). Lets consumers tell "current" from "frozen".
  data/china_search/coverage.parquet 1-row daily time series (n_stocks) for run_status

build_china_library.universe() reads these FIRST so real names win over the
ticker-as-name fallback from the breadth cache.

SURVIVORSHIP NOTE: before the append-only fix (masterplan §W6-CN), this collector
retroactively DELETED a dropped name's entire history column every run — worse than
snapshot survivorship, because it erased the deep-decliner failure cases the reversal
signal specifically buys. Every china_search-derived backtest statistic produced from
the pre-fix committed history (e.g. the 0.58 reversal Sharpe) is therefore an UPPER
BOUND until the panel is re-accrued append-only.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from collectors.breadth import repair_seams
from lib import config

log = logging.getLogger(__name__)


def _overwrite_overlap(fresh: pd.DataFrame, prev: pd.DataFrame) -> pd.DataFrame:
    """Merge a fresh wide-closes pull over a prior one WITHOUT a combine_first seam.

    For dividend/split-ADJUSTED (auto_adjust=True) closes the fresh pull's window is the
    corrected truth for every bar it covers, so it fully overwrites its own date span
    [fresh.min, fresh.max]; only prior rows strictly OLDER than the fresh window (deep
    history the short refresh did not reach) are carried forward. Columns present only in
    ``prev`` are preserved whole (append-only history). NaN-only fresh columns fall back to
    prev so a name the fresh pull failed to return keeps its history.
    """
    if prev is None or prev.empty:
        return fresh.sort_index()
    if fresh is None or fresh.empty:
        return prev.sort_index()
    # defensive: a duplicated column label makes df[col] return a DataFrame → later boolean
    # checks would raise 'truth value of a Series is ambiguous'. Dedup keeps the last.
    fresh = fresh.loc[:, ~fresh.columns.duplicated(keep="last")]
    prev = prev.loc[:, ~prev.columns.duplicated(keep="last")]
    lo = fresh.index.min()
    full_index = prev.index.union(fresh.index)
    out = pd.DataFrame(index=full_index)
    for col in dict.fromkeys(list(prev.columns) + list(fresh.columns)):
        pcol = prev[col].reindex(full_index) if col in prev.columns else pd.Series(index=full_index, dtype="float64")
        if col in fresh.columns and fresh[col].notna().sum() > 0:
            # fresh OWNS its whole date span [lo, fresh.max] — every bar there is on the
            # NEW re-adjusted basis. prev only fills rows STRICTLY OLDER than lo (deep history
            # the refresh did not reach). A trading day the fresh pull skipped inside its own
            # window is LEFT NaN, NOT backfilled from prev: a stale un-re-adjusted prev value
            # on the new basis would recreate the exact seam this function exists to erase
            # (and the signal engines tolerate a NaN gap far better than a wrong level).
            # This matches lib.store.upsert(overwrite_overlap=True), which also drops prev
            # inside the fresh window — the two seam-free merges stay consistent.
            fcol = fresh[col].reindex(full_index)
            out[col] = fcol.where(full_index >= lo, pcol)
        else:
            # prev-only column (dropped name) or fresh-miss → carry the WHOLE prev history
            # forward untouched (append-only, no retroactive deletion).
            out[col] = pcol
    return out.sort_index()


def _to_ticker(sina_symbol: str) -> str | None:
    """sh600519 -> 600519.SS ; sz000001 -> 000001.SZ ; bj/others -> None."""
    s = (sina_symbol or "").strip().lower()
    if len(s) < 8:
        return None
    mkt, code = s[:2], s[2:]
    if not code.isdigit():
        return None
    if mkt == "sh":
        return f"{code}.SS"
    if mkt == "sz":
        return f"{code}.SZ"
    return None  # Beijing (bj) etc. — yfinance has no clean feed


def _code_to_ticker(code: str) -> str | None:
    """Convert a bare 6-digit A-share code to a Yahoo Finance ticker.

    Shanghai (6xxxxx, 9xxxxx, 688xxx STAR) → .SS
    Shenzhen (0xxxxx, 3xxxxx ChiNext)       → .SZ
    Beijing / other                          → None (no yfinance feed)
    """
    code = str(code).strip().zfill(6)
    if not code.isdigit() or len(code) != 6:
        return None
    if code[0] in ("6", "9") or code.startswith("688"):
        return f"{code}.SS"
    if code[0] in ("0", "3"):
        return f"{code}.SZ"
    return None  # 8xxxxx / 4xxxxx = Beijing Stock Exchange — skip


class ChinaUniverseAdapter(Adapter):
    name = "china_universe"
    group = "china_search"
    stale_after_days = 7

    def __init__(self) -> None:
        cn = config.load()["china"]
        self.cfg = cn["search_universe"]
        # Manually-added individual names (config extra_tickers/extra_names): kept
        # searchable even though they sit below the Sina/CSI cutoff. See fetch()/_enrich().
        self.extra_tickers = list(self.cfg.get("extra_tickers", []) or [])
        self.extra_names = dict(self.cfg.get("extra_names", {}) or {})
        self.ycfg = cn["yahoo"]                 # batch_size / retries / backoff_base_s
        self.dir = config.data_dir() / "china_search"
        self.closes_path = self.dir / "closes.parquet"
        self.members_path = self.dir / "members.parquet"
        self.dropped_path = self.dir / "dropped.parquet"   # append-only frozen-history marker table

    # -- universe (Sina) -------------------------------------------------------
    def _sina_universe(self) -> pd.DataFrame:
        """Top-N A-shares by market cap: DataFrame[ticker, name_zh, mktcap_yi]."""
        scfg = self.cfg["sina"]
        size, page_size = int(self.cfg["size"]), int(scfg["page_size"])
        floor_wan = float(self.cfg.get("min_mktcap_yi", 0)) * 1e4   # 亿 -> 万 (Sina mktcap unit)
        pages = (size + page_size - 1) // page_size + 2             # a little headroom for dropped bj/dupes
        rows: list[dict] = []
        seen: set[str] = set()
        for page in range(1, pages + 1):
            params = {"page": page, "num": page_size, "sort": "mktcap", "asc": 0,
                      "node": scfg["node"], "symbol": "", "_s_r_a": "page"}
            r = self.http_get(scfg["url"], retries=self.ycfg["retries"],
                              backoff_base=self.ycfg["backoff_base_s"], timeout=30,
                              params=params, headers={"Referer": scfg["referer"]})
            try:
                data = r.json()
            except Exception:  # noqa: BLE001 — Sina sometimes returns null/garbage on overrun
                data = None
            if not data:
                break
            for d in data:
                t = _to_ticker(str(d.get("symbol", "")))
                if not t or t in seen:
                    continue
                mktcap_wan = float(d.get("mktcap") or 0)
                if mktcap_wan < floor_wan:
                    continue
                seen.add(t)
                rows.append({"ticker": t, "name_zh": str(d.get("name", "")).strip(),
                             "mktcap_yi": round(mktcap_wan / 1e4, 1)})
            if len(rows) >= size:
                break
            time.sleep(0.4)
        out = pd.DataFrame(rows).head(size)
        if len(out) < min(200, size // 2):
            raise RuntimeError(f"sina universe too small: {len(out)} rows (expected ~{size})")
        log.info("china_universe: Sina returned %d ranked A-shares", len(out))
        return out.set_index("ticker")

    # -- closes (yfinance) -----------------------------------------------------
    def _download_closes(self, tickers: list[str], period: str) -> pd.DataFrame:
        bs = int(self.ycfg["batch_size"])
        parts: list[pd.DataFrame] = []
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            for attempt in range(self.ycfg["retries"]):
                try:
                    df = yf.download(batch, period=period, auto_adjust=True,
                                     progress=False, group_by="column", threads=True)
                    if df is None or df.empty:
                        break
                    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
                    parts.append(closes)
                    break
                except Exception as e:  # noqa: BLE001
                    wait = self.ycfg["backoff_base_s"] * (2 ** attempt)
                    log.warning("china_universe closes batch %d failed (%s); retry in %.0fs",
                                i // bs, e, wait)
                    time.sleep(wait)
            time.sleep(1)
        if not parts:
            raise RuntimeError("china_universe: no closes downloaded")
        wide = pd.concat(parts, axis=1)
        wide = wide.loc[:, ~wide.columns.duplicated()]
        return wide.sort_index()

    def _merge_refreshed(self, fresh: pd.DataFrame, prev: pd.DataFrame) -> pd.DataFrame:
        """``_overwrite_overlap`` + split-seam repair (2026-07-10 KLAC class).

        _overwrite_overlap makes the fresh pull own its OWN date span, which
        erases the dividend-edge seam — but prev rows OLDER than the fresh
        window are carried forward unchanged, so a split/bonus issue (10送10)
        since the last refresh still leaves the pre-window history on the old
        basis: a permanent fake step exactly at the fresh window's lower edge.
        Flagged tickers are re-pulled over the full window and replaced
        wholesale; never fatal (see collectors.breadth.repair_seams)."""
        merged = _overwrite_overlap(fresh, prev)
        merged, _ = repair_seams(merged, fresh, prev, self._download_closes,
                                 name=self.name)
        return merged

    # -- English name + sector (yfinance get_info, cached + bounded) ----------
    def _enrich(self, members: pd.DataFrame, prev: pd.DataFrame | None,
                seed: dict | None = None) -> pd.DataFrame:
        """Fill name_en / sector from a cached prior members table; look up at most
        enrich_per_run NEW tickers via yfinance get_info so nightly stays fast.

        `seed` (config extra_names) curates name_en / name_zh / sector for the
        manually-added small caps BEFORE the yfinance pass and only when still empty,
        so a mislabeled get_info can't override the hand-picked sector — and so the
        seeded names drop out of the lookup queue entirely (no wasted lookup)."""
        members = members.copy()
        members["name_en"] = ""
        members["sector"] = ""
        if prev is not None:
            for col in ("name_en", "sector"):
                if col in prev.columns:
                    members[col] = members.index.map(prev[col]).fillna("")
        for t, meta in (seed or {}).items():
            if t not in members.index or not isinstance(meta, dict):
                continue
            for col in ("name_en", "sector", "name_zh"):
                val = str(meta.get(col, "") or "").strip()
                if val and not str(members.at[t, col]).strip():
                    members.at[t, col] = val
        missing = [t for t in members.index
                   if not str(members.at[t, "name_en"]).strip()
                   or not str(members.at[t, "sector"]).strip()]
        budget = int(self.cfg.get("enrich_per_run", 0))
        looked, ok = 0, 0
        for t in missing:
            if looked >= budget:
                break
            looked += 1
            try:
                info = yf.Ticker(t).get_info() or {}
            except Exception:  # noqa: BLE001 — unofficial; degrade to zh-only name
                continue
            en = (info.get("longName") or info.get("shortName") or "").strip()
            sec = (info.get("sector") or "").strip()
            if en:
                members.at[t, "name_en"] = en
            if sec:
                members.at[t, "sector"] = sec
            if en or sec:
                ok += 1
            time.sleep(0.15)
        if missing:
            log.info("china_universe: enriched %d/%d new names (%d still pending, capped at %d/run)",
                     ok, looked, max(0, len(missing) - looked), budget)
        # combined display name -> "English / 中文" (both searchable); zh-only fallback
        def _disp(row: pd.Series) -> str:
            en, zh = str(row["name_en"]).strip(), str(row["name_zh"]).strip()
            return f"{en} / {zh}" if en and zh else (en or zh or row.name)
        members["name"] = members.apply(_disp, axis=1)
        members["sector"] = members["sector"].replace("", "A-share")
        return members

    # -- CSI index constituents (akshare) -------------------------------------
    def _index_constituents(self, symbols: list[str]) -> list[dict]:
        """Fetch constituent lists for named CSI indices (e.g. '000300', '000852')
        via akshare. Returns a list of {ticker, name_zh} dicts. Best-effort: one
        failed index is logged and skipped, never fatal."""
        try:
            import akshare as ak  # noqa: PLC0415 — optional dep
        except ImportError:
            log.warning("china_universe: akshare not installed — CSI index fetch skipped")
            return []
        rows: list[dict] = []
        for sym in symbols:
            try:
                df = ak.index_stock_cons(symbol=sym)
                # akshare column names vary by version — try common patterns
                code_col = next(
                    (c for c in df.columns if "代码" in c or c.lower() in ("code", "symbol")),
                    df.columns[0] if len(df.columns) else None,
                )
                name_col = next(
                    (c for c in df.columns if "名称" in c or c.lower() == "name"),
                    None,
                )
                if code_col is None:
                    log.warning("china_universe: index %s — no code column found (%s)", sym, list(df.columns))
                    continue
                for _, row in df.iterrows():
                    t = _code_to_ticker(str(row[code_col]))
                    if t:
                        zh = str(row[name_col]).strip() if name_col else ""
                        rows.append({"ticker": t, "name_zh": zh})
                log.info("china_universe: CSI index %s → %d constituents", sym, len(df))
            except Exception as e:  # noqa: BLE001 — one bad index must not kill the run
                log.warning("china_universe: akshare index %s failed (%s) — skipped", sym, e)
        return rows

    # -- main ------------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("china_universe disabled in config")
        self.dir.mkdir(parents=True, exist_ok=True)

        uni = self._sina_universe()

        # Union with CSI index constituents (CSI 300 + CSI 1000 by default).
        # Stocks already ranked by Sina are kept with their real mktcap; extras
        # get a conservative 30亿 placeholder (all CSI index members exceed the floor).
        idx_symbols = self.cfg.get("index_constituents", [])
        if idx_symbols:
            idx_rows = self._index_constituents(idx_symbols)
            extra = [r for r in idx_rows if r["ticker"] not in uni.index]
            if extra:
                extra_df = pd.DataFrame(
                    [{"ticker": r["ticker"], "name_zh": r["name_zh"], "mktcap_yi": 30.0}
                     for r in extra]
                ).set_index("ticker")
                # deduplicate within the extras list (same ticker from multiple indices)
                extra_df = extra_df[~extra_df.index.duplicated(keep="first")]
                uni = pd.concat([uni, extra_df])
                log.info("china_universe: +%d CSI index extras (total %d)", len(extra_df), len(uni))

        # Manually-added individual names (config extra_tickers): unioned last so a
        # name below the Sina top-800 / CSI cutoff stays searchable. Real mktcap from
        # extra_names when provided, else the same 30亿 placeholder as the CSI extras.
        extra_t = [t for t in self.extra_tickers if t not in uni.index]
        if extra_t:
            rows = [{"ticker": t,
                     "name_zh": str((self.extra_names.get(t) or {}).get("name_zh", "") or "").strip(),
                     "mktcap_yi": float((self.extra_names.get(t) or {}).get("mktcap_yi", 30.0) or 30.0)}
                    for t in extra_t]
            cfg_df = pd.DataFrame(rows).set_index("ticker")
            cfg_df = cfg_df[~cfg_df.index.duplicated(keep="first")]
            uni = pd.concat([uni, cfg_df])
            log.info("china_universe: +%d config extra_tickers (total %d)", len(cfg_df), len(uni))

        tickers = uni.index.tolist()

        prev_closes = pd.read_parquet(self.closes_path) if self.closes_path.exists() else None
        period = self.cfg.get("history_period", "5y")
        if full_history:
            closes = self._download_closes(tickers, "max")
        elif prev_closes is not None and not prev_closes.empty:
            age = (pd.Timestamp.utcnow().tz_localize(None) - prev_closes.index.max()).days
            new = [t for t in tickers if t not in prev_closes.columns]
            fresh = self._download_closes(tickers, "1mo" if age <= 21 else period)
            # SEAM-FREE merge for auto_adjust=True closes: a re-adjusted history is a coherent
            # whole, so the fresh pull must FULLY OVERWRITE its own date window (not combine_first,
            # which keeps stale un-re-adjusted prev values at the refresh edge → a permanent basis
            # step that biases rev_z and can fabricate crosses). Only prev rows OLDER than the fresh
            # window are carried forward. See lib.store.upsert / masterplan §W6-CN fix 2.
            # _merge_refreshed adds the split-seam repair on top: those carried-forward pre-window
            # rows are exactly what a split re-bases out from under (#2120 KLAC class).
            closes = self._merge_refreshed(fresh, prev_closes)
            if new:                                       # backfill deep history for new entrants
                deep = self._download_closes(new, period)
                closes = _overwrite_overlap(deep, closes)
        else:
            closes = self._download_closes(tickers, period)
        closes = closes.dropna(axis=1, how="all")

        # APPEND-ONLY history (do NOT retroactively trim to the current top-N — that
        # physically deleted dropped names' history every run, erasing exactly the
        # deep-decliner failure cases the reversal signal buys, so china_search-based
        # stats were an upper bound). Names that leave the current universe keep their
        # frozen columns; a dropped-date marker table records when each left the live set
        # so downstream consumers can distinguish "current" from "frozen" without a
        # retroactive-deletion survivorship leak. See research/ENGINE_FIX_MASTERPLAN.md §W6-CN.
        current = set(tickers)
        prev_cols = set(prev_closes.columns) if prev_closes is not None else set()

        # Record names that were in the universe last run but dropped out of the current
        # top-N (append-only; a name re-entering the top-N is un-marked so the marker is a
        # point-in-time record of the *latest* transition, never a hard delete).
        today_ts = pd.Timestamp.utcnow().tz_localize(None).normalize()
        today = str(today_ts.date())
        newly_dropped = sorted(prev_cols - current)
        prev_dropped = (pd.read_parquet(self.dropped_path)
                        if self.dropped_path.exists() else pd.DataFrame(columns=["ticker", "dropped_date"]))
        drop_map = dict(zip(prev_dropped.get("ticker", []), prev_dropped.get("dropped_date", [])))
        for t in newly_dropped:
            drop_map.setdefault(t, today)                            # keep the FIRST-seen drop date
        for t in current:
            drop_map.pop(t, None)                                    # re-entrant: clear the marker

        # BOUNDED retention: keep a dropped name's frozen history for frozen_retention_days
        # (default ~2y) — long enough that no live reversal window (63d) or forward grader
        # (≤21d) references it, but bounding the committed file so append-only does not grow
        # without limit (the docstring's "committed — small" contract). A column is pruned only
        # AFTER its retention window; the reversal-failure cases the signal buys are preserved
        # for the whole backtest-relevant lookback.
        retention_days = int(self.cfg.get("frozen_retention_days", 730))
        aged_out = {t for t, d in drop_map.items()
                    if t not in current
                    and (today_ts - pd.Timestamp(d)).days > retention_days}
        if aged_out:
            closes = closes[[c for c in closes.columns if c not in aged_out]]
            for t in aged_out:
                drop_map.pop(t, None)
            log.info("china_universe: pruned %d frozen columns aged out past %dd retention",
                     len(aged_out), retention_days)
        dropped_df = pd.DataFrame(
            [{"ticker": t, "dropped_date": d} for t, d in sorted(drop_map.items())]
        )

        cover_cols = [t for t in closes.columns if t in current]     # coverage counted on the LIVE set
        live = len(cover_cols)
        log.info("china_universe coverage: %d/%d live names have closes (%.0f%%); "
                 "closes file carries %d columns (incl. %d frozen-history names)",
                 live, len(tickers), 100 * live / max(1, len(tickers)),
                 closes.shape[1], len(dropped_df))
        if live < len(tickers) * 0.6:
            raise RuntimeError(f"china_universe closes too sparse: {live}/{len(tickers)}")

        prev_members = pd.read_parquet(self.members_path) if self.members_path.exists() else None
        members = self._enrich(uni, prev_members, seed=self.extra_names)
        members = members.loc[[t for t in members.index if t in closes.columns]]

        if not full_history:
            closes.to_parquet(self.closes_path)
            if not dropped_df.empty:
                dropped_df.to_parquet(self.dropped_path, index=False)
        members[["name", "name_zh", "name_en", "sector", "mktcap_yi"]].to_parquet(self.members_path)

        cov = pd.DataFrame({"n_stocks": [len(members)], "n_columns": [closes.shape[1]],
                            "n_dropped": [len(dropped_df)]},
                           index=pd.DatetimeIndex([closes.index.max()], name="date"))
        return {"coverage": cov}
