"""China funding-curve context — keyless native rate plumbing that accrues forward
(archived via store.upsert). Masterplan W2, research/china_native_data/
CHINA_HK_NATIVE_DATA_MASTERPLAN_BY_FABLE.md §W2. DISPLAY-TIER CONTEXT ONLY: three
series are collected and accrued here, none is scored, ranked, or gated on.

  repo_fixings  CFETS repo fixing rates (回购定盘利率): FR001/FR007/FR014 (whole
                interbank market, any collateral) plus FDR001/FDR007/FDR014
                (depository institutions, rates-only collateral). The FR−FDR gap is
                the collateral/credit-tier funding premium, and FR007 against the 7d
                OMO rate is the "liquidity temperature" every PBOC-watcher actually
                trades. Dated by the UPSTREAM fixing date. Nightly = one 14-day
                window (idempotent re-pull); --full-history walks month windows from
                2015 (the server rejects a window longer than one month).
  shibor        full-tenor SHIBOR (O/N, 1W, 2W, 1M, 3M, 6M, 9M, 1Y) from the keyless
                Jin10 CDN mirror — the entire 2015-05-08→present history arrives in
                ONE small payload, so this store IS the deep SHIBOR reference and is
                rebuilt whole on every run (upsert is idempotent, so --full-history
                and nightly do exactly the same thing).
                data/china_macro/rates.parquet holds only a ~44-session SHIBOR window
                and is PREREG-FROZEN (CHINA_POLICY_EVENTS_PREREG): it is never read,
                written, or retired here. This store supersedes it as the DEPTH
                reference and leaves the frozen artifact byte-for-byte alone.
  cgb_mm        CFETS bond market-maker quote temperature (债券做市报价): every dealer's
                two-way YIELD quote on CGBs (国债) and policy-bank bonds (国开/农发/进出),
                reduced to median bid/ask/mid plus a median bid-ask spread in bp — how
                tight the street is willing to make markets today. The payload carries
                NO data date (it is a live snapshot), so this leg is dated by the
                COLLECTION date in Asia/Shanghai and is SKIPPED ENTIRELY on Sat/Sun
                rather than stamping a weekend row onto a stale Friday quote.

Every leg degrades independently (same isolation shape as collectors/china_flows.py):
a blocked source just leaves its parquet to grow from the next good day — never a
zero-fill, never a silent gap.

Pacing: ≤1 request/second per host, and the nightly path is 3 HTTP calls (one per
leg, 4-5 if a documented fallback fires). The month-window deep pull runs only under
--full-history, off the render path by construction.
"""
from __future__ import annotations

import io
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from collectors.base import Adapter

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# -- endpoints (all VERIFIED live 2026-07-25/26; see SOURCE_CATALOG_MARKET.md) ------
_CM_HOST = "https://www.chinamoney.com.cn"
_CM_REFERER = _CM_HOST + "/chinese/"
_FRRHIS = _CM_HOST + "/ags/ms/cm-u-bk-currency/FrrHis"
_FRR_CSV = _CM_HOST + "/r/cms/www/chinamoney/data/currency/frr-chrt.csv"
# NOTE: the sibling fdr-chrt.csv is FROZEN upstream (verified stale at 2025-07-24), so
# it is never fetched — FDR tenors come from FrrHis or not at all.
_CBMM = _CM_HOST + "/ags/ms/cm-u-md-bond/CbMktMakQuot"
_JIN10_IL1 = "https://cdn.jin10.com/data_center/reports/il_1.json"
_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"

_HOST_PACE_S = 1.0          # ≤1 req/s per host — house law for every China source
_FR_NIGHTLY_DAYS = 14       # idempotent re-pull window (holidays/late fixings heal)
_FRR_INCEPTION = date(2015, 1, 1)   # deep-pull floor; pre-inception windows come back empty

_FR_COLS = ("FR001", "FR007", "FR014", "FDR001", "FDR007", "FDR014")
# The CSV fallback carries the FR set only; FDR columns stay ABSENT in that mode.
_FR_CSV_COLS = ("FR001", "FR007", "FR014")

# il_1.json tenor key -> store column
_SHIBOR_TENORS = (("O/N", "on"), ("1W", "w1"), ("2W", "w2"), ("1M", "m1"),
                  ("3M", "m3"), ("6M", "m6"), ("9M", "m9"), ("1Y", "y1"))
_EM_FALLBACK_ROWS = 30      # EastMoney fallback depth (O/N tenor only)

_CGB_KW = ("国债",)                      # 国债 = central government bond
_POLICY_KW = ("国开", "农发", "进出")     # CDB / ADBC / EximBank policy-bank paper


def _num(x) -> float:
    """Coerce one upstream scalar to float. '--', '---', '', None -> NaN.

    Never raises: an unparseable cell is a gap, and a gap is stored as NaN (no
    zero-fill). Pure.
    """
    try:
        v = pd.to_numeric(x, errors="coerce")
    except (TypeError, ValueError):
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _med(xs: list[float]) -> float:
    """Median of a non-empty list, NaN for an empty one (never a fabricated 0.0)."""
    return float(pd.Series(xs).median()) if xs else float("nan")


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into calendar-month windows (FrrHis rejects longer spans).

    Pure. Each window is (first_day_covered, last_day_covered) and never straddles a
    month boundary.
    """
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        nxt_month = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((cur, min(end, nxt_month - timedelta(days=1))))
        cur = nxt_month
    return out


def parse_frr_records(records: list[dict]) -> pd.DataFrame:
    """FrrHis records[] -> frame indexed by the UPSTREAM fixing date.

    Each record carries frValueMap = {"date": "YYYY-MM-DD", "FR001": "1.4000", ...}.
    Unparseable rates become NaN; a record with no usable date is dropped. Pure.
    """
    rows: dict[pd.Timestamp, dict] = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        vm = rec.get("frValueMap")
        if not isinstance(vm, dict):
            continue
        idx = pd.to_datetime(str(vm.get("date") or ""), errors="coerce")
        if pd.isna(idx):
            continue
        rows[idx] = {c: _num(vm.get(c)) for c in _FR_COLS}
    if not rows:
        return pd.DataFrame(columns=list(_FR_COLS))
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=list(_FR_COLS))
    return df[~df.index.duplicated(keep="last")].sort_index()


def parse_frr_csv(text: str) -> pd.DataFrame:
    """frr-chrt.csv -> frame with the FR tenors only (documented CNH-R2 fallback).

    Shape: headerless rows of date + the three FR fixings. A shape drift raises
    loudly instead of silently mis-mapping a column onto the wrong tenor. Pure.
    """
    raw = pd.read_csv(io.StringIO(text), header=None).dropna(axis=1)
    if raw.shape[1] != 1 + len(_FR_CSV_COLS):
        raise ValueError(
            f"repo_fixings csv: expected {1 + len(_FR_CSV_COLS)} populated columns "
            f"(date + {', '.join(_FR_CSV_COLS)}), got shape {raw.shape}"
        )
    raw.columns = ["date", *_FR_CSV_COLS]
    # format="mixed" keeps a per-element parse (the CSV has occasionally carried a header
    # row, which coerces to NaT and is dropped below) without the inference warning.
    idx = pd.to_datetime(raw["date"], errors="coerce", format="mixed")
    out = pd.DataFrame({c: pd.to_numeric(raw[c], errors="coerce") for c in _FR_CSV_COLS})
    out.index = idx
    out = out[out.index.notna()]
    if out.empty:
        raise ValueError("repo_fixings csv: no rows with a parseable date")
    return out[~out.index.duplicated(keep="last")].sort_index()


def parse_shibor_values(values: dict) -> pd.DataFrame:
    """il_1.json values{} -> full-tenor SHIBOR frame indexed by fixing date.

    values = {"YYYY-MM-DD": {"O/N": ["1.3812", "1.62"], ...}} where element [0] is the
    fixing in % and [1] the change in bp (dropped — it is a redundant first difference).
    "--" / None -> NaN. Pure.
    """
    cols = [c for _, c in _SHIBOR_TENORS]
    rows: dict[pd.Timestamp, dict] = {}
    for d, tenors in (values or {}).items():
        if not isinstance(tenors, dict):
            continue
        idx = pd.to_datetime(str(d), errors="coerce")
        if pd.isna(idx):
            continue
        row = {}
        for src, col in _SHIBOR_TENORS:
            v = tenors.get(src)
            fixing = v[0] if isinstance(v, (list, tuple)) and v else v
            row[col] = _num(fixing)
        rows[idx] = row
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=cols)
    return df[~df.index.duplicated(keep="last")].sort_index()


def split_contra_rate(raw) -> tuple[float, float] | None:
    """'1.5400 / 1.4500' -> (bid_yield, ask_yield) in %.

    Returns None for '---', a one-sided quote, or a non-numeric side so the row is
    SKIPPED rather than guessed. Pure.
    """
    s = str(raw or "").strip()
    if "/" not in s:
        return None
    parts = [p.strip() for p in s.split("/")]
    if len(parts) != 2:
        return None
    bid, ask = _num(parts[0]), _num(parts[1])
    if pd.isna(bid) or pd.isna(ask):
        return None
    return float(bid), float(ask)


def aggregate_mm_quotes(records: list[dict]) -> dict:
    """CbMktMakQuot records[] -> one snapshot row of quote-temperature aggregates.

    Columns: n_quotes / n_bonds (distinct bond short names) / bid_yield_med /
    ask_yield_med / spread_bp_med (median |bid−ask| in bp) / cgb_n + cgb_mid_med /
    policy_n + policy_mid_med, where mid = (bid+ask)/2.

    cgb_n and policy_n count QUOTES on that family (not distinct bonds) — dealer
    attention is the point, and n_bonds already carries the distinct-name count.
    Malformed rows are skipped; ZERO parseable quotes raises (a thin fabricated
    aggregate would be worse than a logged gap). Pure — no I/O, no clock.
    """
    bids: list[float] = []
    asks: list[float] = []
    spreads_bp: list[float] = []
    names: list[str] = []
    cgb_mids: list[float] = []
    policy_mids: list[float] = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        pair = split_contra_rate(rec.get("contraRate"))
        if pair is None:
            continue
        bid, ask = pair
        name = str(rec.get("abdAssetEncdShrtDesc") or "").strip()
        mid = (bid + ask) / 2.0
        bids.append(bid)
        asks.append(ask)
        spreads_bp.append(abs(bid - ask) * 100.0)
        names.append(name)
        if any(k in name for k in _CGB_KW):
            cgb_mids.append(mid)
        if any(k in name for k in _POLICY_KW):
            policy_mids.append(mid)
    if not bids:
        raise ValueError("cgb_mm: no parseable two-way quotes in the payload")
    return {
        "n_quotes": float(len(bids)),
        "n_bonds": float(len({n for n in names if n})),
        "bid_yield_med": _med(bids),
        "ask_yield_med": _med(asks),
        "spread_bp_med": _med(spreads_bp),
        "cgb_n": float(len(cgb_mids)),
        "cgb_mid_med": _med(cgb_mids),
        "policy_n": float(len(policy_mids)),
        "policy_mid_med": _med(policy_mids),
    }


class ChinaFundingAdapter(Adapter):
    name = "china_funding"
    group = "china_funding"   # 'china_' prefix auto-routes to the asia lane
    stale_after_days = 6

    def _h(self, referer: str) -> dict:
        return {"User-Agent": _UA, "Referer": referer}

    # -- shared HTTP helper (base only ships http_get) --------------------------
    def _post(self, url: str, retries: int = 2, backoff_base: float = 3.0,
              timeout: int = 20, **kwargs) -> requests.Response:
        """POST with the same retry/backoff shape as base.http_get."""
        headers = kwargs.pop("headers", None) or self._h(_CM_REFERER)
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                r = requests.post(url, timeout=timeout, headers=headers, **kwargs)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001 — retried, then surfaced to the leg
                last_exc = e
                wait = backoff_base * (2 ** attempt)
                log.warning("%s POST %s attempt %d/%d failed (%s); retry in %.0fs",
                            self.name, url.split("?")[0], attempt + 1, retries, e, wait)
                if attempt < retries - 1:
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _today_cn(self) -> date:
        """Collection date on the market's own calendar (Asia/Shanghai).

        Overridable in tests so the weekend guard is exercisable without freezing
        the process clock.
        """
        return datetime.now(ZoneInfo("Asia/Shanghai")).date()

    # -- repo fixings (FR/FDR) -------------------------------------------------
    def _frrhis_window(self, start: date, end: date) -> list[dict]:
        params = {"lang": "CN", "startDate": start.isoformat(), "endDate": end.isoformat()}
        r = self._post(_FRRHIS, params=params, headers=self._h(_CM_REFERER))
        recs = (r.json() or {}).get("records") or []
        return [rec for rec in recs if isinstance(rec, dict)]

    def _repo_fixings(self, full_history: bool) -> pd.DataFrame:
        try:
            if full_history:
                return self._repo_fixings_deep()
            today = self._today_cn()
            df = parse_frr_records(self._frrhis_window(
                today - timedelta(days=_FR_NIGHTLY_DAYS), today))
            if df.empty:
                raise ValueError("repo_fixings: FrrHis window returned no fixings")
            return df
        except Exception as e:  # noqa: BLE001 — documented CNH-R2 fallback
            log.warning(
                "china_funding repo_fixings: FrrHis failed (%s); falling back to "
                "frr-chrt.csv — FDR001/FDR007/FDR014 are ABSENT in fallback mode "
                "because that CSV carries the FR set only (its fdr-chrt.csv sibling is "
                "frozen upstream, verified stale at 2025-07-24, so it is never fetched)",
                e)
            r = self.http_get(_FRR_CSV, retries=2, headers=self._h(_CM_REFERER),
                              timeout=20)
            return parse_frr_csv(r.text)

    def _repo_fixings_deep(self) -> pd.DataFrame:
        """Month-windowed backfill from _FRR_INCEPTION. --full-history only.

        Single-shot (not resume-friendly): empty windows (pre-inception, holiday
        months) and a failed window are tolerated and logged; only an entirely empty
        pull raises so the CSV fallback can take over.
        """
        windows = month_windows(_FRR_INCEPTION, self._today_cn())
        frames: list[pd.DataFrame] = []
        skipped = 0
        for i, (start, end) in enumerate(windows):
            if i:
                time.sleep(_HOST_PACE_S)   # ≤1 req/s on chinamoney.com.cn
            try:
                df = parse_frr_records(self._frrhis_window(start, end))
            except Exception as e:  # noqa: BLE001 — one bad window must not sink the pull
                skipped += 1
                log.info("china_funding repo_fixings deep window %s..%s failed: %s",
                         start, end, e)
                continue
            if df.empty:
                skipped += 1
                continue
            frames.append(df)
        if not frames:
            raise ValueError(
                f"repo_fixings: deep pull produced no fixings ({len(windows)} windows, "
                f"{skipped} empty/failed)")
        out = pd.concat(frames)
        out = out[~out.index.duplicated(keep="last")].sort_index()
        log.info("china_funding repo_fixings deep pull: %d rows %s..%s "
                 "(%d/%d windows empty or failed)", len(out), out.index.min().date(),
                 out.index.max().date(), skipped, len(windows))
        return out

    # -- SHIBOR (deep reference) -----------------------------------------------
    def _shibor(self, full_history: bool) -> pd.DataFrame:
        # full_history == nightly on purpose: one payload IS the whole history and
        # upsert is idempotent, so there is nothing deeper to ask for.
        try:
            r = self.http_get(_JIN10_IL1, params={"_": int(time.time() * 1000)},
                              retries=2, headers={"User-Agent": _UA}, timeout=25)
            df = parse_shibor_values((r.json() or {}).get("values") or {})
            if df.empty:
                raise ValueError("shibor: il_1.json carried no parseable dates")
            return df
        except Exception as e:  # noqa: BLE001 — documented CNH-R2 fallback
            log.warning(
                "china_funding shibor: Jin10 CDN failed (%s); EastMoney fallback "
                "NARROWS this run to the 'on' tenor over the last ~%d fixings — the "
                "other 7 tenors are absent today and heal on the next good CDN run",
                e, _EM_FALLBACK_ROWS)
            return self._shibor_em_fallback()

    def _shibor_em_fallback(self) -> pd.DataFrame:
        """EastMoney RPT_IMP_INTRESTRATEN — O/N tenor only, last ~30 fixings.

        Filter vocabulary read off the local akshare source
        (akshare/interest_rate/interbank_rate_em.py): MARKET_CODE 001 =
        上海银行间同业拆借市场, CURRENCY_CODE CNY, INDICATOR_ID 001 = 隔夜 (O/N).
        """
        params = {
            "reportName": "RPT_IMP_INTRESTRATEN",
            "columns": ("REPORT_DATE,REPORT_PERIOD,IR_RATE,CHANGE_RATE,INDICATOR_ID,"
                        "LATEST_RECORD,MARKET,MARKET_CODE,CURRENCY,CURRENCY_CODE"),
            "filter": '(MARKET_CODE="001")(CURRENCY_CODE="CNY")(INDICATOR_ID="001")',
            "pageNumber": 1, "pageSize": _EM_FALLBACK_ROWS,
            "sortColumns": "REPORT_DATE", "sortTypes": -1,
            "source": "WEB", "client": "WEB",
        }
        r = self.http_get(_DC, params=params, retries=2,
                          headers=self._h("https://data.eastmoney.com/"), timeout=25)
        data = ((r.json() or {}).get("result") or {}).get("data") or []
        rows: dict[pd.Timestamp, dict] = {}
        for d in data:
            if not isinstance(d, dict):
                continue
            idx = pd.to_datetime(str(d.get("REPORT_DATE") or ""), errors="coerce")
            if pd.isna(idx):
                continue
            rows[idx.normalize()] = {"on": _num(d.get("IR_RATE"))}
        if not rows:
            raise ValueError("shibor: EastMoney fallback returned no rows either")
        df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
        log.warning("china_funding shibor: fallback frame is %d rows x 1 tenor ('on')",
                    len(df))
        return df

    # -- CGB / policy-bank market-maker quote temperature ----------------------
    def _cgb_mm(self, full_history: bool) -> pd.DataFrame | None:
        today = self._today_cn()
        if today.weekday() >= 5:
            # Live snapshot with no upstream date: a weekend row would stamp Friday's
            # stale quote onto Saturday. Skip the series instead (not an error).
            log.info("china_funding cgb_mm: %s is a weekend in Asia/Shanghai — "
                     "snapshot leg skipped (no frame, no stale row)", today)
            return None
        time.sleep(_HOST_PACE_S)   # second chinamoney.com.cn call of the run
        # No session/cookie dance is needed for this call — akshare's elaborate
        # handshake code is not required in practice (verified 2026-07-25).
        r = self._post(_CBMM, data={"flag": "1", "lang": "cn"},
                       headers=self._h(_CM_REFERER))
        records = (r.json() or {}).get("records") or []
        agg = aggregate_mm_quotes(records)
        return pd.DataFrame(agg, index=[pd.Timestamp(today)])

    # -- fetch -----------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        skipped: list[str] = []
        for key, fn in (("repo_fixings", self._repo_fixings),
                        ("shibor", self._shibor),
                        ("cgb_mm", self._cgb_mm)):
            try:
                df = fn(full_history)
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_funding %s failed: %s", key, e)
                continue
            if df is None or df.empty:
                skipped.append(key)   # deliberate skip (weekend snapshot), not a failure
                continue
            frames[key] = df
        if not frames:
            raise RuntimeError("china_funding: no series produced — "
                               + " | ".join(errors + [f"{k}: skipped" for k in skipped]))
        if errors or skipped:
            log.info("china_funding: %d/%d series ok (failed: %s; skipped: %s)",
                     len(frames), len(frames) + len(errors) + len(skipped),
                     "; ".join(errors) or "none", "; ".join(skipped) or "none")
        return frames
