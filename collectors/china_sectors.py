"""China Shenwan (申万) L1 industry indices — the authoritative domestic sector
index family and the free analogue of the Bloomberg GS China sector baskets
(GSXACHBA banks / GSXACCON consumption / GSXACNRE real estate / GSXACNAU auto).

Mainland institutional desks watch the Shenwan L1 indices the way an offshore desk
watches the GS baskets. They are *real* sector indices (not ETF proxies), with deep
history — most L1 industries print from 1999-12-31, the 2014-reindexed ones (banks,
auto, non-bank financials …) from 2014-02-21 — which is what makes a tops/bottoms
study and a cycle calibration possible (the sector ETFs only go back ~5y).

Source: akshare, keyless.
  • `index_hist_sw(symbol=code, period="day")` — daily index OHLC + volume + amount,
    full history every call (so store.upsert is idempotent).
  • `sw_index_first_info()` — current static-PE / TTM-PE / PB / dividend-yield per L1
    industry, appended one row/day so the engine can percentile-rank a sector's
    valuation against its own accruing history.
  • `index_component_sw(symbol=code)` — CURRENT constituent membership per L1 code
    (ticker/name/weight/inclusion-date), keyless (Flow Observatory W4 spike, PASSED
    2026-09-03: `www.swsresearch.com` JSON endpoint, no key/token). No historical
    membership is exposed — see `collect_sw_membership()`.

Stored under group `china_sectors`: one parquet per L1 code (e.g. `801780.parquet` =
银行/Banks) with close/open/high/low/volume/amount, plus `valuation.parquet` (wide,
one row/day: `<code>_pe_ttm` / `<code>_pb` / `<code>_div`), plus `membership.parquet`
(W4 — an INTERVAL table, not a date-indexed price series, so it is read/diffed/written
directly rather than through `lib.store.upsert`'s datetime-index merge; see
`collect_sw_membership()`).

Akshare segfaults under threads → registered as a SERIAL collector in scripts/collect.py
(deliberately NOT in `_CONCURRENT_HOSTS`). Per-code isolation: one dead industry logs a
gap and the rest of the board still updates.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from pathlib import Path

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

# Shenwan L1 industry universe (31 codes, stable). code -> (cn, en). Hardcoded so a
# flaky `sw_index_first_info` never strands the price collection; the valuation pass
# refreshes display PE/PB/div on top. engine/china_sectors.py maps dashboard sectors
# (and the GS consumption composite) onto these codes via config.china.shenwan.
SW_L1: dict[str, tuple[str, str]] = {
    "801010": ("农林牧渔", "Agriculture"),
    "801030": ("基础化工", "Chemicals"),
    "801040": ("钢铁", "Steel"),
    "801050": ("有色金属", "Nonferrous Metals"),
    "801080": ("电子", "Electronics"),
    "801110": ("家用电器", "Home Appliances"),
    "801120": ("食品饮料", "Food & Beverage"),
    "801130": ("纺织服饰", "Textiles & Apparel"),
    "801140": ("轻工制造", "Light Manufacturing"),
    "801150": ("医药生物", "Pharma & Biotech"),
    "801160": ("公用事业", "Utilities"),
    "801170": ("交通运输", "Transportation"),
    "801180": ("房地产", "Real Estate"),
    "801200": ("商贸零售", "Retail & Commerce"),
    "801210": ("社会服务", "Consumer Services"),
    "801230": ("综合", "Conglomerates"),
    "801710": ("建筑材料", "Building Materials"),
    "801720": ("建筑装饰", "Construction"),
    "801730": ("电力设备", "Power Equipment"),
    "801740": ("国防军工", "Defense & Military"),
    "801750": ("计算机", "Computers"),
    "801760": ("传媒", "Media"),
    "801770": ("通信", "Telecoms"),
    "801780": ("银行", "Banks"),
    "801790": ("非银金融", "Non-bank Financials"),
    "801880": ("汽车", "Automobiles"),
    "801890": ("机械设备", "Machinery"),
    "801950": ("煤炭", "Coal"),
    "801960": ("石油石化", "Oil & Petrochem"),
    "801970": ("环保", "Environmental"),
    "801980": ("美容护理", "Beauty & Care"),
}

# index_hist_sw column (Chinese) -> stored column
_HIST_COLS = {
    "收盘": "close", "开盘": "open", "最高": "high",
    "最低": "low", "成交量": "volume", "成交额": "amount",
}


MEMBERSHIP_COLUMNS = ["ticker", "l1_code", "l1_name", "start_date", "end_date", "collected_at"]


def normalize_cn_ticker(raw: str) -> str:
    """``'002142'`` -> ``'002142.SZ'``; ``'600000'`` -> ``'600000.SS'`` — the same
    ``.SS``/``.SZ`` suffix convention every other collector/basket store in this repo
    already uses. SSE (Shanghai) main-board/STAR codes start with 6 (B-shares with 9
    are legacy/illiquid but map the same way); everything else (SZSE: 000/001/002/003
    main board, 300/301 ChiNext) is Shenzhen — EXCEPT the Beijing Stock Exchange
    (N3, W4 repair): 8xxxxx (83/87/88-series NEEQ-select carryovers) and the two-digit
    43xxxx/92xxxx prefixes are BSE, ``.BJ``, checked BEFORE the 6/9 branch so a 92xxxx
    code is never misrouted to the legacy-B-share ``.SS`` fallback. A ``.BJ`` ticker is
    honest, not silently dropped: it still counts in a sector's ``n_members`` (real
    membership), and lands in ``excluded(missing)`` (spec §3) until the Tushare
    large-order panel this desk reads from covers the BSE."""
    code = str(raw).strip()
    if "." in code:  # already suffixed (defensive; akshare never emits this today)
        return code.upper()
    if code[:1] == "8" or code[:2] in ("43", "92"):
        return f"{code}.BJ"
    return f"{code}.SS" if code[:1] in ("6", "9") else f"{code}.SZ"


def _membership_path():
    from lib import config
    return config.data_dir() / "china_sectors" / "membership.parquet"


def overlapping_intervals(df: pd.DataFrame) -> list[dict]:
    """Store invariant (B2/W4 repair): every ``(ticker, l1_code)`` pair's rows, sorted
    by ``start_date``, must form a sequence of NON-overlapping ``[start_date,
    end_date)`` intervals — a name cannot re-enter an industry before its own prior
    stint there closed, and two simultaneously-open rows for the same pair is a
    storage-level contradiction. Returns one violation dict per offending pair (empty
    == clean); never raises — callers log/annotate on a non-empty result so a real
    anomaly is visible without ever blocking a build."""
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for (ticker, code), g in df.groupby(["ticker", "l1_code"]):
        g = g.sort_values("start_date", na_position="first")
        open_rows = int(g["end_date"].isna().sum())
        if open_rows > 1:
            out.append({"ticker": ticker, "l1_code": code, "reason": "multiple_open_intervals",
                       "n_open": open_rows})
        prev_end = None
        for _, r in g.iterrows():
            start = r.get("start_date")
            if prev_end is not None and start is not None and str(start) < str(prev_end):
                out.append({"ticker": ticker, "l1_code": code, "reason": "overlap",
                           "prev_end": prev_end, "next_start": start})
            prev_end = r.get("end_date") if pd.notna(r.get("end_date")) else prev_end
    return out


def _fetch_sw_snapshot() -> tuple[pd.DataFrame, set[str]]:
    """One ``index_component_sw`` call per SW L1 code -> a flat CURRENT-snapshot frame
    (ticker/l1_code/l1_name/start_date) PLUS the set of codes this run actually
    OBSERVED (a successful call that returned real rows) — B2/W4 repair: the diff step
    in ``collect_sw_membership`` needs to know which codes it may safely close
    intervals for, never inferring "not in the snapshot" as "membership vanished" for
    a code whose fetch simply failed. Per-code isolation, same discipline as the price
    fetch above: one dead index logs a gap, the rest of the snapshot still builds."""
    import akshare as ak  # lazy: heavy import, only needed at collect time

    rows: list[dict] = []
    observed: set[str] = set()
    for code, (cn, en) in SW_L1.items():
        try:
            df = ak.index_component_sw(symbol=code)
        except Exception as e:  # noqa: BLE001 — per-code isolation
            log.warning("china_sectors membership %s (%s) failed: %s", code, en, e)
            continue
        if df is None or df.empty or "证券代码" not in df.columns:
            log.warning("china_sectors membership %s (%s): empty/unexpected payload", code, en)
            continue
        observed.add(code)
        for _, r in df.iterrows():
            ticker = normalize_cn_ticker(r["证券代码"])
            incl = r.get("计入日期")
            start = str(incl) if pd.notna(incl) else None
            rows.append({"ticker": ticker, "l1_code": code, "l1_name": en, "start_date": start})
    return pd.DataFrame(rows, columns=["ticker", "l1_code", "l1_name", "start_date"]), observed


def collect_sw_membership(today: str | None = None, snapshot: pd.DataFrame | None = None,
                          observed_codes: set[str] | None = None,
                          path=None) -> pd.DataFrame:
    """Shenwan L1 constituent membership — an INTERVAL store (ticker · l1_code ·
    l1_name · start_date · end_date[null=current] · collected_at), the official
    (non-overlapping) sector lens' membership source (W4 spec §2A).

    Seeded from the CURRENT snapshot on the first run: every row's ``start_date`` is
    SW's OWN reported inclusion date (``计入日期``, falling back to ``today`` when SW
    omits it) — a fact about the SOURCE, often years before we ever ran this
    collector — while ``collected_at`` is the date OUR pipeline first observed the
    row, i.e. ``today`` on a seed run. That distinction is load-bearing: the "no
    historical replay before real accrual" refusal (spec §2A,
    ``engine.flow_observatory.groups.aggregate_lens``) keys off ``collected_at``,
    never ``start_date`` — using SW's own inclusion date would let a request for
    "official-sector flow in 2022" through even though THIS pipeline has zero
    accrued observations before today.

    Every LATER run diffs the fresh snapshot against the stored table: a (ticker,
    l1_code) pair that dropped out of the snapshot closes that row's OPEN interval
    (``end_date = today``, ``collected_at`` unchanged — it is a first-OBSERVED
    stamp, not a last-touched one); a pair with no OPEN row in the store opens a new
    row with ``collected_at = today``. No historical membership is ever fabricated —
    the file only ever knows what a run has actually observed (masterplan §5 "no
    lawful keyless source before real accrual").

    A ticker holding an OPEN row in more than one ``l1_code`` at once is a storage-
    level contradiction the source itself should never produce (a name lives in
    exactly one Shenwan L1 industry at a time); this function does not resolve that
    ambiguity — it is left for the AGGREGATION layer
    (``engine.flow_observatory.groups.resolve_active_membership``) to detect and
    EXCLUDE, so the same "excluded/missing, never silently double-counted" surface
    (spec §2A/§3) also covers a real source anomaly, not just an unscored member.

    B2/W4 repair — collector safety, three rules:

    1. **Refuse to diff an EMPTY fetched snapshot.** A total akshare outage (every
       code's call failed) used to read as "every sector's membership vanished
       today" — every open interval in the store closed in one run (measured: 5,211
       rows would have closed from a single empty fetch against the real seeded
       store). An empty ``snap`` is now a pure no-op: the existing store is returned
       untouched (not even re-written), and the gap is logged, never silently
       swallowed into a mass-departure diff.
    2. **Close intervals ONLY for l1_codes this run actually OBSERVED.** A partial
       outage (some codes failed, others succeeded) used to close the FAILED codes'
       intervals too, because "not in `snap`" was read identically whether a code's
       fetch failed or its true membership emptied out. ``observed_codes`` (from
       :func:`_fetch_sw_snapshot`, or derived from ``snapshot`` when injected)
       scopes the closure diff to codes this run genuinely saw; every other code's
       open rows are left exactly as they were, with the gap logged by name.
    3. **A re-entry never mints an overlapping interval.** A (ticker, l1_code) pair
       whose prior row is CLOSED (not open) is a re-entry, not a fresh arrival — SW's
       own reported inclusion date can predate that closure (or predate today by
       years), so trusting it verbatim could open a new interval that overlaps the
       one just closed. A re-entry's ``start_date`` is pinned to ``today`` whenever
       the source's own date would not clear the prior close;
       :func:`overlapping_intervals` re-checks the whole merged store as a store
       invariant before every write and logs (never raises on) any violation found.

    ``snapshot``/``observed_codes``/``path`` are injectable (tests / callers that
    already fetched); ``today`` is the collection run's date (ISO string),
    defaulting to the real wall-clock date. Returns the merged frame — the same
    frame written to disk, except on the empty-snapshot no-op above.
    """
    today = today or str(_date.today())
    if snapshot is None:
        snap, observed_codes = _fetch_sw_snapshot()
    else:
        snap = snapshot.copy()
        if observed_codes is None:
            observed_codes = set(snap["l1_code"].unique()) if not snap.empty else set()

    path = Path(path) if path is not None else _membership_path()
    old = None
    if path.exists():
        try:
            old = pd.read_parquet(path)
        except Exception as e:  # noqa: BLE001
            log.warning("china_sectors membership: existing store unreadable (%s)", e)
            old = None

    # (1) refuse to diff an empty snapshot — never a mass-closure inference.
    if snap.empty:
        log.warning("china_sectors membership: fetched snapshot is EMPTY (akshare outage or "
                   "no code returned rows) — refusing to diff/close any interval this run; "
                   "the existing store is left untouched.")
        if old is not None and not old.empty:
            return old.reindex(columns=MEMBERSHIP_COLUMNS)
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)

    if old is None or old.empty:
        merged = snap.copy()
        merged["end_date"] = None
        merged["collected_at"] = today
        merged = merged.reindex(columns=MEMBERSHIP_COLUMNS)
    else:
        old = old.reindex(columns=MEMBERSHIP_COLUMNS).copy()
        open_old = old[old["end_date"].isna()]
        old_keys = set(zip(open_old["ticker"], open_old["l1_code"]))
        # the most recent CLOSED end_date per (ticker, l1_code), for the re-entry
        # start_date guard below (3).
        closed_old = old[old["end_date"].notna()]
        prior_close = (closed_old.sort_values("end_date")
                       .groupby(["ticker", "l1_code"])["end_date"].max()
                       if not closed_old.empty else pd.Series(dtype=object))
        new_keys = set(zip(snap["ticker"], snap["l1_code"]))

        # (2) close intervals ONLY for codes this run observed.
        closed = old.copy()
        is_open = closed["end_date"].isna()
        observed_mask = closed["l1_code"].isin(observed_codes)
        still_present = closed.apply(lambda r: (r["ticker"], r["l1_code"]) in new_keys, axis=1)
        closed.loc[is_open & observed_mask & ~still_present, "end_date"] = today
        skipped = sorted(set(closed.loc[is_open, "l1_code"]) - set(observed_codes))
        if skipped:
            log.warning("china_sectors membership: %d l1_code(s) not observed this run "
                       "(fetch failed/empty) — their open intervals are left untouched: %s",
                       len(skipped), ", ".join(skipped))

        is_new = ~snap.apply(lambda r: (r["ticker"], r["l1_code"]) in old_keys, axis=1)
        arrivals = snap[is_new].copy()
        arrivals["end_date"] = None
        arrivals["collected_at"] = today
        if len(arrivals):
            def _arrival_start(r):
                # (3) a re-entry's start_date may never precede its own prior close.
                prior_end = prior_close.get((r["ticker"], r["l1_code"])) \
                    if len(prior_close) else None
                if prior_end is not None and (not r["start_date"] or str(r["start_date"]) <= str(prior_end)):
                    return today
                return r["start_date"]
            arrivals["start_date"] = arrivals.apply(_arrival_start, axis=1)
        merged = pd.concat([closed, arrivals.reindex(columns=MEMBERSHIP_COLUMNS)], ignore_index=True)

    merged = merged.sort_values(["l1_code", "ticker", "start_date"], na_position="first").reset_index(drop=True)
    violations = overlapping_intervals(merged)
    if violations:
        log.error("china_sectors membership: %d overlapping-interval store invariant "
                 "violation(s) post-merge — %s", len(violations), violations[:5])
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path, index=False)
    return merged


class ChinaSectorsAdapter(Adapter):
    name = "china_sectors"
    group = "china_sectors"
    stale_after_days = 6   # daily index; allow a long weekend / holiday

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        import akshare as ak  # lazy: heavy import, only needed at collect time

        out: dict[str, pd.DataFrame] = {}
        for code, (cn, en) in SW_L1.items():
            try:
                raw = ak.index_hist_sw(symbol=code, period="day")
            except Exception as e:  # noqa: BLE001 — per-code isolation
                log.warning("china_sectors %s (%s) history failed: %s", code, en, e)
                continue
            if raw is None or raw.empty or "日期" not in raw.columns:
                log.warning("china_sectors %s (%s): empty/unexpected payload", code, en)
                continue
            df = pd.DataFrame(index=pd.to_datetime(raw["日期"]))
            for src, dst in _HIST_COLS.items():
                if src in raw.columns:
                    df[dst] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
            df = df.dropna(subset=["close"])
            if not df.empty:
                out[code] = df.sort_index()

        if not out:
            raise RuntimeError("china_sectors: no Shenwan industry returned data")

        # -- valuation snapshot (append one row/day -> accruing own-history) ---------
        try:
            info = ak.sw_index_first_info()
            row: dict[str, float] = {}
            for _, r in info.iterrows():
                code = str(r.get("行业代码", "")).split(".")[0]
                if code not in SW_L1:
                    continue
                row[f"{code}_pe_ttm"] = pd.to_numeric(r.get("TTM(滚动)市盈率"), errors="coerce")
                row[f"{code}_pb"] = pd.to_numeric(r.get("市净率"), errors="coerce")
                row[f"{code}_div"] = pd.to_numeric(r.get("静态股息率"), errors="coerce")
            if row:
                asof = pd.Timestamp.now().normalize()
                out["valuation"] = pd.DataFrame([row], index=pd.DatetimeIndex([asof]))
        except Exception as e:  # noqa: BLE001 — valuation is additive context
            log.warning("china_sectors valuation snapshot failed: %s", e)

        # -- W4: SW L1 constituent membership (interval store, own read/diff/write —
        # not a date-indexed series, so it bypasses the out{} -> store.upsert path) --
        try:
            collect_sw_membership()
        except Exception as e:  # noqa: BLE001 — membership is additive context
            log.warning("china_sectors membership snapshot failed: %s", e)

        return out
