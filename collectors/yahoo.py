"""Yahoo Finance collector via yfinance — unofficial API, replaceable by design.

Stores EOD adjusted close (+ volume) per ticker under data/yahoo/. Daily runs
fetch a short overlap window and upsert; backfill fetches max history.

Dual-basis store (W1.3):
- ``close``       — total-return (split+dividend adjusted) = Adj Close from yfinance
                    auto_adjust=False.  Byte-identical to the old auto_adjust=True Close.
- ``close_price`` — split-adjusted, dividend-UNadjusted = Close from yfinance
                    auto_adjust=False.  The correct basis for all structure math
                    (ZigZag, detrended osc, DCL/failed-cycle, drawdown-from-ATH).
For tickers where yfinance supplies no Adj Close (certain FX/index symbols), close_price
is set equal to close (no dividends → no basis difference) and the fact is logged.

Adjustment-basis guard: both stored bases are re-adjusted by Yahoo at every fetch,
so a 1mo window pulled after an ex-div/split disagrees with stored history on every
overlap date. ``store.basis_shifted`` detects that and the name is re-pulled
period='max' instead of spliced (see ``_rebase_shifted``).
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config, delisted_symbols, store
from lib.ticker_aliases import fetch_symbol

log = logging.getLogger(__name__)


def _drop_delisted(tickers: list[str]) -> list[str]:
    """Remove securities that stopped existing from a fetch list.

    A delisted symbol can never return data, so requesting it every night puts a
    permanent entry in `_report_missing_symbols`' warning — the one tripwire that
    exists to catch the NEXT symbol yfinance goes quiet on. A warning that is
    always on is a warning nobody reads, which is how CTRA/TPH sat frozen for
    three months (research/RESOLUTION_20260806_SIDE_STORE_SYMBOLS.md).

    Membership is untouched: the ticker stays in `stock_search.extra_tickers`, its
    store keeps every bar, and its page stays searchable (CSP-R1). Only the
    pointless network request goes away.

    PURE — the disclosure lives in `_report_delisted_exclusions`, called once per
    `fetch()`. This function runs on several lists per run (the ticker union, then
    the re-read extras list for the Stooq fallback); printing here would emit the
    same notice two or three times and read as three separate events."""
    dead = delisted_symbols.tickers()
    if not dead:
        return tickers
    return [t for t in tickers if t not in dead]


def _report_delisted_exclusions(tickers: list[str]) -> list[str]:
    """Name every symbol this run deliberately did NOT request, and why.

    Silence would re-create the exact failure mode #4643 was built to end — a name
    leaving the collector's attention with nothing in the log to say it happened.
    A ::notice rather than a ::warning: this is the system working as designed, not
    a defect. Bare print, never through the logger (a logger-prefixed annotation is
    silently discarded by GitHub Actions). Returns the excluded list so a test can
    assert on the classification without re-parsing the printed line."""
    dead = delisted_symbols.tickers()
    dropped = sorted(t for t in tickers if t in dead)
    if dropped:
        rows = delisted_symbols.ledger()
        detail = ", ".join(f"{t}(last session {rows[t]['last_session']}, "
                           f"{rows[t]['reason']})" for t in dropped)
        print(f"::notice title=yahoo collector delisted::{len(dropped)} symbol(s) not "
              f"requested — the security stopped existing, so no feed can return it; "
              f"store and page kept: {detail}", flush=True)
    return dropped


class YahooAdapter(Adapter):
    name = "yahoo"
    group = "yahoo"

    def __init__(self) -> None:
        self.cfg = config.load()["yahoo"]

    def all_tickers(self) -> list[str]:
        out: list[str] = []
        for grp in self.cfg["tickers"].values():
            out.extend(grp)
        # stock_search.extra_tickers must be collected here or they can never be
        # searched (build_stock_library reads data/yahoo/<t>.parquet for them).
        # Skip ^-prefixed index symbols — they belong in the tickers groups.
        extra = config.load().get("stock_search", {}).get("extra_tickers", []) or []
        out.extend(t for t in extra if not str(t).startswith("^"))
        # W3 — Foresight Desk theme members: derive from config.themes at collect
        # time so future theme-member changes flow automatically (self-maintaining;
        # no separate list to keep in sync). foresight_grader._closes + the tape-
        # extension leg in foresight_score both require data/yahoo/<ticker>.parquet
        # for every theme member — without this, _theme_excess returns None and the
        # grading ledger stays pending forever.
        for theme in (config.load().get("themes") or {}).values():
            # (theme or {}): a bare `some_theme:` YAML key yields None — never crash collect
            for t in ((theme or {}).get("tickers") or []):
                if t and not str(t).startswith("^"):
                    out.append(t)
        # A delisted security is dropped from the FETCH only (config membership and
        # the store are untouched — see _drop_delisted). `maintained_tickers()` is
        # the un-filtered view for the store-tip audit, which must still see those
        # stores; every other caller of all_tickers() wants the fetch list.
        return _drop_delisted(list(dict.fromkeys(out)))

    def maintained_tickers(self) -> list[str]:
        """Every ticker whose data/yahoo store this group owns — the fetch list PLUS
        the delisted names whose stores it still carries.

        `all_tickers()` is what gets requested; this is what gets audited. Feeding
        `audit_store_freshness` the fetch list alone would make a delisted store
        invisible to the one check that reads stores rather than fetch results, and
        an invisible store is how a wrong ledger row (or a ticker reused by a new
        issuer) would never be caught."""
        return list(dict.fromkeys(self.all_tickers() + sorted(delisted_symbols.tickers())))

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tickers = self.all_tickers()
        _report_delisted_exclusions(self.maintained_tickers())
        period = "max" if full_history else "1mo"
        # Keep intraday High/Low for the volatility group (^VIX etc.) — the daily
        # VIX wick (intraday high vs close) is a washout / thin-quote tell that
        # engine/dislocation.py reads. Everything else stays close+volume to avoid
        # churning ~1500 parquets.
        ohlc = set(self.cfg["tickers"].get("vol", []))
        frames: dict[str, pd.DataFrame] = {}
        no_adj_close: list[str] = []
        bs = self.cfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            # Renamed names are REQUESTED under the vendor's symbol and STORED under the
            # config ticker (lib/ticker_aliases) — without this, Marsh (MMC->MRSH, 2026-01-14)
            # 404s every run and never reaches the store.
            df = self._download([fetch_symbol(t) for t in batch], period)
            for t in batch:
                sub_out = self._extract(df, t, ohlc, no_adj_close)
                if sub_out is not None:
                    frames[t] = sub_out
        if no_adj_close:
            log.info("yahoo: %d tickers had no Adj Close (close_price=close, no dividends): %s",
                     len(no_adj_close), no_adj_close)
        deferred: list[str] = []
        if not full_history:
            deferred = self._rebase_shifted(frames, ohlc)
        # Stooq fallback for searchable single stocks Yahoo refused this run.
        # Basis-deferred names are NOT refilled: Stooq is a different source/basis,
        # so a refill would splice exactly what the guard just refused.
        # `_drop_delisted` filtered `tickers`, but this list is re-read from config,
        # where a delisted name deliberately KEEPS its membership (its page must stay
        # searchable) — so it has to be filtered again here, or the Stooq fallback
        # spends a request per night probing a security that stopped existing.
        extras = _drop_delisted(
            config.load().get("stock_search", {}).get("extra_tickers", []) or [])
        self._fill_missing_extras(frames, [t for t in extras if t not in deferred])
        # M3: `deferred` names WERE returned this run (yfinance served real data for
        # them) — they were pulled out of `frames` only because `_rebase_shifted`'s
        # re-pull failed on a basis mismatch (kept out of THIS run so the guard
        # re-flags them next night, never spliced onto a stale basis). Reconciling
        # against `frames` alone would relabel them "returned no data", which is
        # false and would mislead every nightly read of this warning.
        _report_missing_symbols(tickers, set(frames) | set(deferred))
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"yahoo returned only {len(frames)}/{len(tickers)} tickers")
        return frames

    def _extract(self, df: pd.DataFrame, t: str, ohlc: set[str],
                 no_adj_close: list[str]) -> pd.DataFrame | None:
        """Slice one ticker out of a (possibly MultiIndex) yf.download response and
        rename to the store schema; None when yfinance returned nothing for it.

        `t` is the CONFIG ticker throughout (store key, ohlc-group membership, log lines);
        the response is keyed by the vendor symbol, which differs for renamed names."""
        try:
            sym = fetch_symbol(t)
            sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
            # W1.3 dual-basis rename:
            #   Adj Close -> close     (TR, byte-identical to old auto_adjust=True Close)
            #   Close     -> close_price (split-adj, div-UNadj — structure-math basis)
            # Vol/OHLC group also gets High/Low.
            if t in ohlc:
                want = ["High", "Low", "Close", "Adj Close", "Volume"]
            else:
                want = ["Close", "Adj Close", "Volume"]
            available = sub[[c for c in want if c in sub.columns]]
            if "Adj Close" in available.columns:
                renamed = available.rename(columns={
                    "Adj Close": "close",
                    "Close":     "close_price",
                    "Volume":    "volume",
                    "High":      "high",
                    "Low":       "low",
                })
            else:
                # FX / indices that yfinance provides no Adj Close for:
                # Close ≡ Adj Close (no dividends) → set close_price = close.
                no_adj_close.append(t)
                renamed = available.rename(columns={
                    "Close":  "close",
                    "Volume": "volume",
                    "High":   "high",
                    "Low":    "low",
                })
                if "close" in renamed.columns:
                    renamed["close_price"] = renamed["close"]
            sub_out = renamed.dropna(subset=["close"])
            return sub_out if not sub_out.empty else None
        except KeyError:
            log.warning("yahoo: no data for %s", t)
            return None

    def _rebase_shifted(self, frames: dict[str, pd.DataFrame],
                        ohlc: set[str]) -> list[str]:
        """Adjustment-basis guard (the odds-store pattern from scripts/build_odds).

        A name whose 1mo window disagrees with stored closes on the overlap dates
        was re-adjusted by Yahoo (ex-div/split) since the last pull; splicing the
        window would strand every pre-window row on the stale basis (measured on
        SPY: +0.2576% on all rows before 2026-05-18 — one dividend of drift; a
        missed split would be a 10x step). Flagged names are re-pulled
        period='max' so the whole store rebases in one shot. A name whose re-pull
        fails is DROPPED from this run — never spliced — leaving the store
        untouched so the guard re-flags it the next night. Returns the tickers
        dropped without a heal (the caller keeps them away from the Stooq refill)."""
        tol = float(self.cfg.get("upsert_basis_tol", 1e-3))
        shifted = [t for t, f in frames.items()
                   if store.basis_shifted(self.group, t, f, tol=tol)]
        if not shifted:
            return []
        log.info("yahoo: %d name(s) on a re-adjusted basis — refetching period='max': %s",
                 len(shifted), shifted[:12])
        for t in shifted:
            frames.pop(t, None)
        healed: list[str] = []
        scrap: list[str] = []  # no-Adj-Close names were already logged on the window pass
        bs = self.cfg["batch_size"]
        for i in range(0, len(shifted), bs):
            batch = shifted[i:i + bs]
            try:
                df = self._download([fetch_symbol(t) for t in batch], "max")
            except Exception as e:  # noqa: BLE001 — degrade: skip tonight, re-flag next run
                log.warning("yahoo: basis refetch failed for %d name(s) (%s) — kept out "
                            "of this run; the guard retries next night", len(batch), e)
                continue
            for t in batch:
                sub_out = self._extract(df, t, ohlc, scrap)
                if sub_out is not None:
                    frames[t] = sub_out
                    healed.append(t)
        return [t for t in shifted if t not in healed]

    def _fill_missing_extras(self, frames: dict[str, pd.DataFrame],
                             extras: list[str]) -> dict[str, pd.DataFrame]:
        """Best-effort Stooq backfill for extra_tickers Yahoo returned no data for.

        Yahoo intermittently 404s live large-caps (e.g. Marsh MMC, Fiserv FI —
        served only under stale symbols); without a fallback they never reach the
        store and drop out of the library. Bounded to the extra_tickers set (plain
        US symbols Stooq's ``.us`` feed understands, not crypto/futures/indices)
        and never fatal — Stooq is IP-gated, so a block just leaves the name
        missing, no worse than before."""
        missing = [t for t in extras if not str(t).startswith("^") and t not in frames]
        if not missing:
            return frames
        from lib import stooq
        recovered = []
        for t in missing:
            s = stooq.stooq_daily(t)
            if s is not None and not s.empty:
                frames[t] = s
                recovered.append(t)
        if recovered:
            log.info("yahoo: Stooq fallback recovered %d name(s): %s", len(recovered), recovered)
        still = [t for t in missing if t not in frames]
        if still:
            log.warning("yahoo: no data from Yahoo or Stooq for %s", still)
        return frames

    def _download(self, batch: list[str], period: str) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.cfg["retries"]):
            try:
                # W1.3: auto_adjust=False returns BOTH Close (split-adj, div-UNadj)
                # AND Adj Close (split+div adjusted = TR).  The old auto_adjust=True
                # returned only an adjusted Close.  Switching to False + renaming
                # Adj Close→close keeps the stored ``close`` values byte-identical to
                # what was stored before this change (the invariance gate verified this
                # for SPY, EWJ, ^GSPC, and a FX pair with relative error < 1e-6).
                df = yf.download(batch, period=period, auto_adjust=False,
                                 progress=False, group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty yfinance response")
                return df
            except Exception as e:  # noqa: BLE001
                last_exc = e
                wait = self.cfg["backoff_base_s"] * (2 ** attempt)
                log.warning("yfinance batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]


#: The store schema every data/yahoo/<T>.parquet carries, in column order.
#: Pinned here rather than derived, because it is a CONTRACT with readers that
#: never go through this module: engine/trajectory.py:66 and
#: engine/desk_grader.py:124 open the parquet directly and read ``close``.
#: A writer that produces a different frame poisons them silently.
STORE_COLUMNS: tuple[str, ...] = ("close_price", "close", "volume")


def extract_store_frame(sub: pd.DataFrame, ticker: str, *,
                        with_ohlc: bool = False,
                        no_adj_close: list[str] | None = None) -> pd.DataFrame | None:
    """The ONE dual-basis rename seam — shared by the nightly collector and the
    off-render universe backfill (``scripts/backfill_yahoo_universe.py``).

    Exists so there is exactly one implementation of "yfinance response ->
    data/yahoo store frame". A second writer that re-derives the rename is the
    silent-poison shape: ``close`` is total-return (split+dividend) adjusted and
    ``close_price`` is split-only, so a writer that swaps them, drops one, or
    reorders the columns leaves every grader reading the wrong basis with no
    error anywhere (engine/trajectory.py, engine/desk_grader.py and the hub
    ledger all read the parquet directly — see STORE_COLUMNS).

    ``sub`` may be either a full ``yf.download`` response (MultiIndex columns,
    sliced by ``lib.ticker_aliases.fetch_symbol(ticker)`` exactly as ``fetch()``
    does) or a FLAT single-symbol frame the caller already sliced out of a batch
    response. The flat form is what lets the backfill request a vendor symbol the
    alias table does not carry — a US class share is served as ``BRK-B`` while the
    ledger's join key stays ``BRK.B`` — without teaching this module a second
    symbol map.

    ``with_ohlc`` mirrors the collector's vol-group behaviour (keep intraday
    High/Low). ``no_adj_close`` collects the tickers yfinance served no Adj Close
    for (close_price := close, no dividends → no basis difference); pass a list to
    observe them, omit it when you do not care.
    """
    adapter = YahooAdapter()
    return adapter._extract(sub, ticker, {ticker} if with_ohlc else set(),
                            no_adj_close if no_adj_close is not None else [])


def _report_missing_symbols(requested: list[str], frames_keys) -> list[str]:
    """Requested-vs-returned reconciliation for one fetch() run (R4, never-silent
    collectors, research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md).

    `_extract()` already drops a requested-but-unreturned symbol via a log-only
    `except KeyError`, and both `detect_stale_series` (collectors/base) and this
    module's own `check_yahoo_freshness` only inspect frames a fetch DID return —
    a symbol yfinance silently refuses (CTRA/TPH/TCNNF class) was invisible to
    every guard, with only the 70%-of-run aggregate floor as a backstop. This is
    the per-run, per-symbol disclosure that floor doesn't provide. Bare
    ::warning (annotation law — never through the logger); returns the missing
    list so a caller/test can assert on it without re-parsing the printed text."""
    have = set(frames_keys)
    missing = [t for t in requested if t not in have]
    if missing:
        shown = missing[:15]
        more = len(missing) - len(shown)
        print(f"::warning title=yahoo collector missing symbols::{len(missing)} requested "
              f"symbol(s) returned no data: {', '.join(shown)}"
              f"{f', +{more} more' if more > 0 else ''}", flush=True)
    return missing


# ---------------------------------------------------------------------------
# Store-level freshness tripwire (the check_cor_vol_freshness idiom from
# collectors/cboe_indices, VSB W1a). detect_stale_series (collectors/base) only
# inspects frames a fetch RETURNED, so a series NO adapter fetches is invisible
# to it. That is exactly how data/yahoo/_GSPC.parquet froze silently for a month
# (last obs 2026-06-12): ^GSPC was seeded once by a one-shot backtest script
# (scripts/spvector_baseline.py) and never entered any config["yahoo"]["tickers"]
# group, while eight engines kept reading it via store.read("yahoo", "^GSPC").
# The pinned list below is deliberately IN CODE, not derived from the config
# ticker groups — a config-derived expectation goes blind the moment a name
# falls out of the list, which is the failure class this tripwire guards.
# ---------------------------------------------------------------------------
ENGINE_CRITICAL_SERIES: tuple[str, ...] = (
    "^GSPC",   # US price-index benchmark: intl_performance RRG, cycle_proxies,
               # equity_alloc, financial_news, intl_claims, lab, live_overlay, signal_lab
    "SPY",     # master US total-return benchmark — engine.inputs features + many more
    "^VIX",    # vol-regime / dislocation OHLC substrate
)


def check_yahoo_freshness(max_lag_sessions: int = 3, min_rows: int = 1000) -> list[dict]:
    """NYSE-calendar freshness + row-floor check on the engine-critical yahoo names.

    Reads the STORE (not the fetch result) against the exchange calendar, so it
    fires no matter WHY a series stopped accruing: never in the ticker config
    (the ^GSPC failure), dropped from a group, breaker wedged, or upstream
    serving a frozen tail with 200-OK. Warn/alert only — it writes named
    run_status["stale_series"] entries and logs; it NEVER fails the lane."""
    from datetime import timedelta

    from collectors.base import _write_stale_series
    from lib import nyse_calendar

    expected = nyse_calendar.expected_last_session()
    problems: list[dict] = []
    for series in ENGINE_CRITICAL_SERIES:
        df = store.read("yahoo", series)
        rows = 0 if df is None else len(df)
        last = None if (df is None or df.empty) else pd.Timestamp(df.index.max()).date()
        lag = 0
        if last is not None:
            # sessions missing from the store: NYSE sessions in (last, expected]
            d = last + timedelta(days=1)
            while d <= expected and lag <= max_lag_sessions + 1:
                if nyse_calendar.is_session(d):
                    lag += 1
                d += timedelta(days=1)
        reason = None
        if df is None:
            reason = "missing from store"
        elif rows < min_rows:
            reason = f"row floor: {rows} < {min_rows} (stub re-seed)"
        elif lag > max_lag_sessions:
            reason = f"stale: last obs {last} is >{max_lag_sessions} sessions behind {expected}"
        if reason:
            entry = {"group": "yahoo", "series": series, "rows": rows,
                     "last_obs": str(last) if last else None,
                     "cadence_days": 1,
                     "age_days": (expected - last).days if last else None,
                     "reason": reason}
            problems.append(entry)
            log.warning("yahoo freshness: %s — %s", series, reason)
    if problems:
        _write_stale_series(problems)
    else:
        log.info("yahoo freshness: all %d engine-critical series fresh "
                 "(last expected session %s)", len(ENGINE_CRITICAL_SERIES), expected)
    return problems


_STALE_CAL_DAYS = 7  # cross-ref: engine.name_score_grader._MAX_BAR_LAG_DAYS — the SAME
# 7-calendar-day staleness law as the scan/ledger admission gate. Collectors must not
# import engine (layering), so this is a deliberate duplicate of that constant's VALUE,
# not an independently chosen policy — keep the two in sync if the law ever moves.


def audit_store_freshness(tickers: list[str], group: str = "yahoo") -> dict:
    """Store-tip freshness audit across every ticker `group` is asked to maintain —
    NOT just the 3-name ENGINE_CRITICAL_SERIES tuple `check_yahoo_freshness` covers
    (that function and this one are deliberately independent; leave both as-is).
    This is the R4 "store-tip audit covers every name the yahoo group maintains"
    disclosure: CTRA/TPH/RGI/CNH=X froze for weeks as ordinary side-store extras,
    never engine-critical, so the narrow tripwire never saw them.

    Reads each store tip ONCE via lib.store.read (no network — ~740 parquet reads
    for the full yahoo group, acceptable once per nightly collect). Classifies
    against the GROUP's own max tip (self-relative, no wall-clock dependency):
      delisted — the security stopped existing (config/delisted_symbols.yml). A
                 finished tape is not a defect, so these are reported separately
                 and are excluded from `stale`/`stub`; #4616's law, "delisted is
                 not stale", applies to this audit as much as to the page copy.
      stale   — tip present but more than _STALE_CAL_DAYS behind the group's ref tip
      stub    — fewer than 60 rows (a name that never grew past its first backfill)
      missing — no store file, or an empty/unparseable one
    A name may be BOTH stub and stale. Bare ::warning per non-empty category (cap
    15, annotation law — never through the logger); never raises. Returns
    {"ref": <ISO date str | None>, "stale": {ticker: tip}, "stub": {ticker: rows},
    "missing": [ticker, ...], "delisted": {ticker: tip}} so a caller/test can
    assert on the classification."""
    tips: dict[str, pd.Timestamp] = {}
    rows_by: dict[str, int] = {}
    missing: list[str] = []
    for t in tickers:
        df = store.read(group, t)
        if df is None or df.empty:
            missing.append(t)
            continue
        rows_by[t] = len(df)
        try:
            ts = pd.Timestamp(df.index.max())
            if pd.isna(ts):
                raise ValueError
            tips[t] = ts
        except (TypeError, ValueError):
            missing.append(t)
    ref_ts = max(tips.values()) if tips else None
    ref = str(ref_ts.date()) if ref_ts is not None else None
    # Exit rows come out of the defect buckets BEFORE they are computed — a delisted
    # name is permanently behind the group ref and (for a young listing) permanently
    # short of 60 rows, so leaving it in would make both warnings unclearable and
    # cost them the attention the next real freeze needs.
    dead_rows = delisted_symbols.ledger()
    delisted = {t: str(ts.date()) for t, ts in tips.items() if t in dead_rows}
    stale: dict[str, str] = {}
    if ref_ts is not None:
        for t, ts in tips.items():
            if t not in dead_rows and (ref_ts - ts).days > _STALE_CAL_DAYS:
                stale[t] = str(ts.date())
    stub = {t: n for t, n in rows_by.items() if n < 60 and t not in dead_rows}
    if delisted:
        shown = sorted(delisted)[:15]
        more = len(delisted) - len(shown)
        print(f"::notice title={group} store audit delisted::{len(delisted)} name(s) "
              f"hold a finished tape (not scored, store kept): "
              f"{', '.join(f'{t}({delisted[t]})' for t in shown)}"
              f"{f', +{more} more' if more > 0 else ''}", flush=True)
    # A store that advanced PAST its recorded last session contradicts its own exit
    # row: either the resolution was wrong, or the symbol was reused by a different
    # issuer (the ECHO/EchoStar class — a reused ticker refills with the new holder's
    # history and looks born-clean). Loud, because the page is asserting a delisting
    # date that the data no longer supports.
    for t, tip in sorted(delisted.items()):
        recorded = str(dead_rows[t].get("last_session"))
        if tip > recorded:
            print(f"::warning title={group} store audit delisted contradiction::{t} "
                  f"store tip {tip} is AFTER its recorded last session {recorded} — "
                  "the exit row in config/delisted_symbols.yml is wrong, or the "
                  "symbol was reused by another issuer; re-resolve before trusting "
                  "either the page copy or this store", flush=True)
    if stale:
        shown = sorted(stale)[:15]
        more = len(stale) - len(shown)
        print(f"::warning title={group} store audit frozen::{len(stale)} name(s) "
              f">{_STALE_CAL_DAYS}d behind ref {ref}: "
              f"{', '.join(f'{t}({stale[t]})' for t in shown)}"
              f"{f', +{more} more' if more > 0 else ''}", flush=True)
    if stub:
        shown = sorted(stub)[:15]
        more = len(stub) - len(shown)
        print(f"::warning title={group} store audit stub::{len(stub)} name(s) under "
              f"60 rows: {', '.join(f'{t}({stub[t]})' for t in shown)}"
              f"{f', +{more} more' if more > 0 else ''}", flush=True)
    if missing:
        shown = sorted(missing)[:15]
        more = len(missing) - len(shown)
        print(f"::warning title={group} store audit missing::{len(missing)} name(s) "
              f"have no store: {', '.join(shown)}"
              f"{f', +{more} more' if more > 0 else ''}", flush=True)
    # M1: self-relative blindness backstop — every check above is relative to `ref`
    # (this group's own max tip), so a TOTAL freeze (every ticker frozen together)
    # is invisible to them. Disclosure only, against wall-clock now — never a gate.
    if ref_ts is not None:
        _now = pd.Timestamp.utcnow().tz_localize(None)
        _behind_wall = (_now.normalize() - ref_ts.tz_localize(None).normalize()).days \
            if ref_ts.tzinfo is not None else (_now.normalize() - ref_ts.normalize()).days
        if _behind_wall > _STALE_CAL_DAYS:
            print(f"::warning title={group} store audit tip stale::group ref tip {ref} "
                  f"is >{_STALE_CAL_DAYS}d behind today — possible collector outage", flush=True)
    return {"ref": ref, "stale": stale, "stub": stub, "missing": missing,
            "delisted": delisted}
