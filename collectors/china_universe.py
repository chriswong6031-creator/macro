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
  data/china_search/index_cons.parquet  last KNOWN-GOOD CSI constituent list per index
      (symbol/ticker/name_zh/fetched_date). Serves membership on a night CSIndex is
      degraded so a network blip cannot shrink the universe; see _resolve_index_membership.

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
from io import BytesIO

import pandas as pd
import yfinance as yf

from collectors.base import Adapter, is_connection_error
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

    Shanghai (6xxxxx main + 688/689xxx STAR, 900xxx B-shares) → .SS
    Shenzhen (0xxxxx, 3xxxxx ChiNext)                          → .SZ
    Beijing / other                                            → None (no yfinance feed)

    The Shanghai test is `900`-exact, NOT a bare `9` prefix: Beijing has issued 92xxxx
    codes since 2023 (920045, 920807 奔朗新材, 920914 远航精密 — all live in 同花顺
    concept-board data), and a `9` prefix swept them into `.SS` as a NONEXISTENT
    '920045.SS'. That fails QUIETLY, not loudly — yfinance returns an all-NaN column
    and `dropna(axis=1, how='all')` deletes it, so a bad code shrinks the universe with
    no error. Matches `collectors.china_ths_concepts.to_suffixed`, which maps the same
    three segments (4xxxxx / 8xxxxx / 92xxxx) to `.BJ`.
    """
    code = str(code).strip().zfill(6)
    if not code.isdigit() or len(code) != 6:
        return None
    if code[0] == "6" or code.startswith("900"):
        return f"{code}.SS"
    if code[0] in ("0", "3"):
        return f"{code}.SZ"
    return None  # Beijing Stock Exchange (4xxxxx / 8xxxxx / 92xxxx) + B-shares elsewhere — skip


# The official CSIndex constituent table, as an .xls on CSIndex's own OSS bucket. This
# is the exact URL akshare's index_stock_cons_csindex builds — fetched here directly so
# the call carries a TIMEOUT (see _csindex_direct).
_CSINDEX_CONS_URL = ("https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
                     "file/autofile/cons/{symbol}cons.xls")

# Constituent columns are selected by a NAME MARKER, never by a "代码"/"名称" substring
# scan: the same frame carries 指数代码/指数名称 (the INDEX's own code '000852' / name
# '中证1000'), which such a scan matches FIRST — mapping every row to one bogus ticker.
#
# Two header dialects reach this parser and they are NOT the same string:
#   * akshare's reader overwrites all nine headers POSITIONALLY with 成分券代码 …
#     (成分, fen1).
#   * the raw .xls ships BILINGUAL headers using 成份券代码Constituent Code (成份, fen4).
# A single-dialect literal therefore matches one source and silently misses the other,
# so both variants (plus the English half) are markers. The English constituent columns
# are excluded explicitly — '成份券英文名称Constituent Name(Eng)' contains the lowercased
# marker 'constituent name' and would otherwise win the name pick.
_CSINDEX_CODE_COL = "成分券代码"          # akshare's normalized header (kept: pinned by tests)
_CSINDEX_NAME_COL = "成分券名称"
_CONS_CODE_MARKERS = ("成分券代码", "成份券代码", "constituent code")
_CONS_NAME_MARKERS = ("成分券名称", "成份券名称", "constituent name")
_ENGLISH_MARKERS = ("英文", "(eng)")

# Known constituent count per CSI index symbol — the denominator for the shortfall check.
# NOT derivable from the digits: '000852' is 中证1000 and '000905' is 中证500, so the
# symbol number and the member count are unrelated. An unlisted symbol simply gets no
# size check (logged), never a wrong one.
_INDEX_EXPECTED_SIZE = {
    "000016": 50,     # 上证50
    "000300": 300,    # 沪深300
    "000905": 500,    # 中证500
    "000906": 800,    # 中证800
    "000852": 1000,   # 中证1000
    "932000": 2000,   # 中证2000
}

# Re-stamp an unchanged cached membership at most this often, so the committed cache
# does not churn 365 times a year for an index whose members did not move.
_INDEX_CACHE_RESTAMP_DAYS = 7


def _norm_code(v: object) -> str:
    """Constituent code -> zero-padded 6-digit string. ``1`` / ``'1'`` / ``1.0`` -> ``'000001'``.

    The raw CSIndex .xls types the constituent-code column as int64 (平安银行 arrives as
    ``1``, not ``'000001'``), and any NaN in the column promotes it to float, whose
    ``str()`` is ``'1.0'`` — which ``zfill(6)`` turns into ``'0001.0'`` and
    ``_code_to_ticker`` then rejects as non-digit, dropping a real constituent with no
    error. akshare's own reader handles only the int case (``.astype(str).str.zfill(6)``).
    """
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def _pick_cons_col(columns, markers: tuple[str, ...]) -> str | None:
    """First column whose header carries a CONSTITUENT marker (never an index/English one)."""
    for c in columns:
        s = str(c).strip()
        low = s.lower()
        if any(e in low for e in _ENGLISH_MARKERS):
            continue
        if any(m in s or m in low for m in markers):
            return c
    return None


def _cons_pairs(df: pd.DataFrame) -> list[tuple[str, str]]:
    """(code, name_zh) pairs from a CSIndex constituent frame, either header dialect."""
    code_col = _pick_cons_col(df.columns, _CONS_CODE_MARKERS)
    name_col = _pick_cons_col(df.columns, _CONS_NAME_MARKERS)
    if code_col is None:
        raise RuntimeError(f"no constituent-code column in csindex frame: {list(df.columns)}")
    codes = df[code_col]
    if not len(codes):
        raise RuntimeError("empty constituent table")
    names = df[name_col] if name_col is not None else [""] * len(codes)
    return [(_norm_code(c), str(n).strip()) for c, n in zip(codes, names)]


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
        # Last KNOWN-GOOD CSI constituent list per index. Serves membership on a night
        # CSIndex is degraded, so a network blip cannot shrink the universe (_index_rows).
        self.index_cache_path = self.dir / "index_cons.parquet"

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

    # -- CSI index constituents ------------------------------------------------
    def _csindex_direct(self, sym: str) -> list[tuple[str, str]]:
        """Constituents straight from the official CSIndex .xls, with a TIMEOUT.

        akshare's ``index_stock_cons_csindex`` builds this same URL and fetches it with a
        bare ``requests.get(url)`` — no timeout argument at all, so the call inherits
        requests' default of *waiting forever*. A probe from this host on 2026-08-05 hung
        **742 s** before raising ConnectionError, and nothing inside china_universe bounded
        it: the only other limit is the asia-close job cap (165 min), i.e. the whole
        nightly lane is the timeout. ``self.http_get`` carries an explicit per-attempt
        timeout plus the configured retries/backoff, so the same stall now costs at most
        ``retries x index_fetch_timeout_s`` (plus backoff) and then falls through to a
        source that answers.
        """
        r = self.http_get(_CSINDEX_CONS_URL.format(symbol=sym),
                          retries=int(self.ycfg["retries"]),
                          backoff_base=float(self.ycfg["backoff_base_s"]),
                          timeout=int(self.cfg.get("index_fetch_timeout_s", 30)))
        return _cons_pairs(pd.read_excel(BytesIO(r.content)))

    def _index_rows(self, ak, sym: str) -> tuple[list[tuple[str, str]], str]:
        """(code, name_zh) pairs for one CSI index + the source that served them.

        Three rungs, most authoritative first:

        1. ``csindex``           — the official constituent .xls fetched by this adapter,
                                   time-bounded (see ``_csindex_direct``). Works with no
                                   akshare installed at all.
        2. ``csindex-ak``        — akshare's reader for the SAME url. Same authoritative
                                   data, different (positional) header handling, so it can
                                   still win when CSIndex reshuffles its header text. It is
                                   SKIPPED when rung 1 failed because the host is
                                   unreachable: retrying a dead host through a call that
                                   cannot time out is how the 742 s stall happens.
        3. ``index_stock_cons``  — legacy, KNOWN-INCOMPLETE (duplicate codes: 288 unique of
                                   300 rows for CSI 300, 772 of 1000 for CSI 1000, measured
                                   2026-08-04). Last resort, and its use is annotated by
                                   ``_resolve_index_membership`` rather than merely logged.
        """
        try:
            return self._csindex_direct(sym), "csindex"
        except Exception as e:  # noqa: BLE001 — CSIndex down / 404 / shape change
            host_dead = is_connection_error(e)
            log.warning("china_universe: direct csindex fetch for %s failed (%s) — %s",
                        sym, e, "host unreachable, SKIPPING akshare's untimed reader"
                        if host_dead else "retrying via akshare's reader")
        if not host_dead and ak is not None:
            try:
                return _cons_pairs(ak.index_stock_cons_csindex(symbol=sym)), "csindex-ak"
            except Exception as e:  # noqa: BLE001 — endpoint absent (older akshare) / shape change
                log.warning("china_universe: akshare csindex reader for %s failed (%s)", sym, e)
        if ak is None:
            raise RuntimeError("csindex .xls unavailable and akshare is not installed")
        log.warning("china_universe: csindex %s unavailable — falling back to "
                    "index_stock_cons, whose list is KNOWN-INCOMPLETE (duplicate codes; "
                    "772 unique of 1000 rows for CSI 1000, measured 2026-08-04)", sym)
        df = ak.index_stock_cons(symbol=sym)
        # Legacy frame is ['品种代码','品种名称','纳入日期'] — no index-level columns, so the
        # version-tolerant substring scan is safe HERE and only here.
        code_col = next(
            (c for c in df.columns if "代码" in c or c.lower() in ("code", "symbol")),
            df.columns[0] if len(df.columns) else None,
        )
        name_col = next((c for c in df.columns if "名称" in c or c.lower() == "name"), None)
        if code_col is None:
            raise RuntimeError(f"no code column in index_stock_cons: {list(df.columns)}")
        return [(_norm_code(r[code_col]), str(r[name_col]).strip() if name_col else "")
                for _, r in df.iterrows()], "index_stock_cons"

    # -- last-known-good membership cache (one row per ticker per index) -------
    def _read_index_cache(self, sym: str) -> tuple[list[dict], str]:
        """Last known-good membership for one index -> (rows, fetched_date); ([], "") if unusable.

        A cache older than ``index_cache_max_age_days`` is NOT served: holding prior
        membership is meant to ride out a transient blip, and a months-old constituent
        list is a worse answer than a fresh 95%-complete one. Fail-soft throughout — an
        unreadable cache degrades to "no cache", never to a failed run.
        """
        if not self.index_cache_path.exists():
            return [], ""
        try:
            df = pd.read_parquet(self.index_cache_path)
        except Exception as e:  # noqa: BLE001 — a corrupt cache must not kill the night
            log.warning("china_universe: index cache unreadable (%s) — ignored", e)
            return [], ""
        if "symbol" not in df.columns or "ticker" not in df.columns:
            return [], ""
        part = df[df["symbol"].astype(str) == str(sym)]
        if part.empty:
            return [], ""
        stamp = str(part["fetched_date"].iloc[0]) if "fetched_date" in part.columns else ""
        max_age = int(self.cfg.get("index_cache_max_age_days", 30))
        try:
            age = (pd.Timestamp.utcnow().tz_localize(None).normalize()
                   - pd.Timestamp(stamp)).days
        except Exception:  # noqa: BLE001 — unparseable stamp: treat as unusable, not as fresh
            age = max_age + 1
        if age > max_age:
            log.warning("china_universe: cached %s membership is %dd old (> %dd) — NOT served; "
                        "tonight's degraded list stands", sym, age, max_age)
            return [], ""
        names = part["name_zh"] if "name_zh" in part.columns else [""] * len(part)
        return [{"ticker": str(t), "name_zh": str(z)}
                for t, z in zip(part["ticker"], names)], stamp

    def _write_index_cache(self, sym: str, live: list[dict]) -> None:
        """Persist a HEALTHY constituent list as the fallback membership (fail-soft)."""
        today = str(pd.Timestamp.utcnow().tz_localize(None).normalize().date())
        try:
            prev = (pd.read_parquet(self.index_cache_path)
                    if self.index_cache_path.exists()
                    else pd.DataFrame(columns=["symbol", "ticker", "name_zh", "fetched_date"]))
            if "symbol" not in prev.columns:
                prev = pd.DataFrame(columns=["symbol", "ticker", "name_zh", "fetched_date"])
            is_sym = prev["symbol"].astype(str) == str(sym)
            same = prev[is_sym]
            if not same.empty and set(same["ticker"]) == {r["ticker"] for r in live}:
                try:
                    age = (pd.Timestamp(today)
                           - pd.Timestamp(str(same["fetched_date"].iloc[0]))).days
                except Exception:  # noqa: BLE001 — unparseable stamp -> re-stamp it
                    age = _INDEX_CACHE_RESTAMP_DAYS + 1
                if age <= _INDEX_CACHE_RESTAMP_DAYS:
                    return          # unchanged and still fresh: no nightly churn
            fresh = pd.DataFrame([{"symbol": str(sym), "ticker": r["ticker"],
                                   "name_zh": r["name_zh"], "fetched_date": today}
                                  for r in live])
            self.index_cache_path.parent.mkdir(parents=True, exist_ok=True)
            pd.concat([prev[~is_sym], fresh], ignore_index=True).to_parquet(
                self.index_cache_path, index=False)
        except Exception as e:  # noqa: BLE001 — the cache is resilience, never a gate
            log.warning("china_universe: could not persist %s index cache (%s)", sym, e)

    def _resolve_index_membership(self, sym: str, live: list[dict], source: str,
                                  tol: float) -> list[dict]:
        """Choose between tonight's list and the last known-good one — and SAY SO.

        Two ways tonight's list is not fit to define membership:
          * it came off the legacy ``index_stock_cons`` endpoint, whose duplicate codes
            cost ~12 names on CSI 300 and ~228 on CSI 1000;
          * it is short of the index's KNOWN size by more than ``index_shortfall_tol``,
            whatever served it (an authoritative source can be truncated too).

        Either way the old code just ``log.warning``-ed and shipped the short list, so the
        universe silently flickered night to night — and a name dropping out of
        china_search is not free: it freezes that ticker's ``closes`` column and gets
        marked in ``dropped.parquet``. A transient network blip should not buy that. So a
        degraded night serves the cached membership when one is available and larger, and
        the event is emitted as a GitHub annotation, not just a log line.

        The annotation is a BARE ``print`` on purpose. Every builder here logs through a
        prefixing formatter, so ``log.warning("::warning …")`` emits ``WARNING ::warning …``
        and GitHub drops it silently — an alarm that reviews as wired and produces nothing
        (tests/test_gh_annotation_line_start.py).

        Cost of serving the cache: constituents that genuinely LEFT the index linger in the
        search universe until the next healthy fetch. That is a few extra searchable names,
        against a frozen price column and a dropped-marker for every name lost — and it
        self-heals on the next good night.
        """
        expected = _INDEX_EXPECTED_SIZE.get(sym)
        n = len(live)
        lossy = source not in ("csindex", "csindex-ak")
        short = expected is not None and n < expected * (1.0 - tol)
        if not lossy and not short and n:
            self._write_index_cache(sym, live)
            return live
        if expected is None:
            log.info("china_universe: no known size for CSI %s — shortfall check skipped", sym)
        cached, stamp = self._read_index_cache(sym)
        exp_txt = f"{expected} expected" if expected else "expected size unknown"
        if cached and len(cached) > n:
            print(f"::warning title=csindex-fallback::CSI {sym} came back degraded from "
                  f"{source} ({n} unique mappable tickers, {exp_txt}) — serving the cached "
                  f"membership from {stamp} ({len(cached)} tickers) instead, so a transient "
                  f"CSIndex outage cannot shrink the china_search universe", flush=True)
            return cached
        print(f"::warning title=csindex-fallback::CSI {sym} came back degraded from {source} "
              f"({n} unique mappable tickers, {exp_txt}) and no usable cached membership "
              f"exists — the china_search universe is SHORT for this index tonight; every "
              f"name it drops freezes that ticker's closes column and is marked in "
              f"dropped.parquet", flush=True)
        return live

    def _index_constituents(self, symbols: list[str]) -> list[dict]:
        """Fetch constituent lists for named CSI indices (e.g. '000300', '000852').
        Returns a list of {ticker, name_zh} dicts. Best-effort: one failed index is
        logged and skipped, never fatal.

        Source is the official CSIndex constituent table (exactly 300 / 1000 unique
        codes), fetched directly and with a timeout by ``_index_rows``. The legacy
        index_stock_cons endpoint is a last resort only: it returns the right ROW count
        carrying duplicate codes — 772 unique of 1000 for CSI 1000 and 288 of 300 for
        CSI 300 (measured 2026-08-04) — silently dropping 228 real constituents. When a
        night lands on it, or lands short of the index's known size for any other reason,
        ``_resolve_index_membership`` prefers the last known-good membership and raises a
        GitHub annotation."""
        try:
            import akshare as ak  # noqa: PLC0415 — optional dep
        except ImportError:
            ak = None
            log.warning("china_universe: akshare not installed — the official CSIndex .xls "
                        "is the only constituent source this run")
        tol = float(self.cfg.get("index_shortfall_tol", 0.05))
        rows: list[dict] = []
        for sym in symbols:
            try:
                pairs, source = self._index_rows(ak, sym)
            except Exception as e:  # noqa: BLE001 — one bad index must not kill the run
                log.warning("china_universe: CSI index %s failed on every source (%s)", sym, e)
                pairs, source = [], "no source"
            seen: dict[str, str] = {}
            for code, zh in pairs:
                t = _code_to_ticker(code)
                if not t or t in seen:      # dedup per index; Beijing/other codes drop out
                    continue
                seen[t] = zh
            live = [{"ticker": t, "name_zh": zh} for t, zh in seen.items()]
            # Count what was actually UNIONED (unique + ticker-mappable), never len(df):
            # a row-count log reported 1000/1000 while 228 CSI 1000 members were missing.
            log.info("china_universe: CSI index %s → %d constituents from %d %s rows",
                     sym, len(live), len(pairs), source)
            rows.extend(self._resolve_index_membership(sym, live, source, tol))
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
