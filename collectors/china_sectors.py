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
    main board, 300/301 ChiNext) is Shenzhen."""
    code = str(raw).strip()
    if "." in code:  # already suffixed (defensive; akshare never emits this today)
        return code.upper()
    return f"{code}.SS" if code[:1] in ("6", "9") else f"{code}.SZ"


def _membership_path():
    from lib import config
    return config.data_dir() / "china_sectors" / "membership.parquet"


def _fetch_sw_snapshot() -> pd.DataFrame:
    """One ``index_component_sw`` call per SW L1 code -> a flat CURRENT-snapshot frame
    (ticker/l1_code/l1_name/start_date). Per-code isolation, same discipline as the
    price fetch above: one dead index logs a gap, the rest of the snapshot still
    builds."""
    import akshare as ak  # lazy: heavy import, only needed at collect time

    rows: list[dict] = []
    for code, (cn, en) in SW_L1.items():
        try:
            df = ak.index_component_sw(symbol=code)
        except Exception as e:  # noqa: BLE001 — per-code isolation
            log.warning("china_sectors membership %s (%s) failed: %s", code, en, e)
            continue
        if df is None or df.empty or "证券代码" not in df.columns:
            log.warning("china_sectors membership %s (%s): empty/unexpected payload", code, en)
            continue
        for _, r in df.iterrows():
            ticker = normalize_cn_ticker(r["证券代码"])
            incl = r.get("计入日期")
            start = str(incl) if pd.notna(incl) else None
            rows.append({"ticker": ticker, "l1_code": code, "l1_name": en, "start_date": start})
    return pd.DataFrame(rows, columns=["ticker", "l1_code", "l1_name", "start_date"])


def collect_sw_membership(today: str | None = None, snapshot: pd.DataFrame | None = None) -> pd.DataFrame:
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

    ``snapshot`` is injectable (tests / callers that already fetched); ``today`` is
    the collection run's date (ISO string), defaulting to the real wall-clock date.
    Returns the merged frame that was written to disk.
    """
    today = today or str(_date.today())
    snap = _fetch_sw_snapshot() if snapshot is None else snapshot.copy()
    path = _membership_path()
    old = None
    if path.exists():
        try:
            old = pd.read_parquet(path)
        except Exception as e:  # noqa: BLE001
            log.warning("china_sectors membership: existing store unreadable (%s)", e)
            old = None

    if old is None or old.empty:
        merged = snap.copy()
        merged["end_date"] = None
        merged["collected_at"] = today
        merged = merged.reindex(columns=MEMBERSHIP_COLUMNS)
    else:
        old = old.reindex(columns=MEMBERSHIP_COLUMNS).copy()
        open_old = old[old["end_date"].isna()]
        old_keys = set(zip(open_old["ticker"], open_old["l1_code"]))
        new_keys = set(zip(snap["ticker"], snap["l1_code"]))

        closed = old.copy()
        is_open = closed["end_date"].isna()
        still_present = closed.apply(lambda r: (r["ticker"], r["l1_code"]) in new_keys, axis=1)
        closed.loc[is_open & ~still_present, "end_date"] = today

        is_new = ~snap.apply(lambda r: (r["ticker"], r["l1_code"]) in old_keys, axis=1)
        arrivals = snap[is_new].copy()
        arrivals["end_date"] = None
        arrivals["collected_at"] = today
        merged = pd.concat([closed, arrivals.reindex(columns=MEMBERSHIP_COLUMNS)], ignore_index=True)

    merged = merged.sort_values(["l1_code", "ticker", "start_date"], na_position="first").reset_index(drop=True)
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
