"""scripts/build_subsector_membership.py — author the Nasdaq-100 / Russell-2000 subsector
memberships the index confluence desks + amalgamation cycle families render over.

Inputs (already on disk):
  data/finviz_screener/idx_ndx.json          NDX universe → {ticker, industry, sector, market_cap_b}
                                             (merged with NDX_SUPPLEMENT for QQQ-only names)
  data/finviz_screener/idx_rut.json          Russell-2000 universe (1889 names), same shape
  data/baskets/ohlcv/<T>.parquet             deep OHLCV (engine/basket_index preferred store)

Outputs:
  data/baskets_nasdaq/membership.json        {subsectors{}, amalgamations{}, benchmark, ...}
  data/baskets_russell/membership.json

Design (per the project brief):
  * SUBSECTOR = a Finviz sub-industry, as an equal-weight synthetic index. Only groups with
    >= MIN_PRICED priced members (>= MIN_BARS daily bars) survive — a thin/illiquid group is
    not a chartable index.
  * NDX is CURATED: the index is a TECH index, so non-technical single-name sub-industries are
    dropped from the subsector board (they survive only inside the "Defensives & Ex-Tech"
    amalgamation, which is the whole point — watching whether money rotates OUT of tech). A few
    thin TECH sub-industries are BULKED OUT with close non-NDX peers, kept only when their daily
    returns actually track the existing basket (corr >= MIN_BULK_CORR) — "matches in price action".
  * RUSSELL is ALGORITHMIC: 2000 names spread across ~140 sub-industries — keep every sub-industry
    with enough priced members; amalgamate by the 11 Finviz sectors (the natural rotation buckets).
  * AMALGAMATION = a higher-level complex (union of member tickers) whose internal rotation is
    what keeps an index grinding up without leadership bleeding to ex-index names. These feed the
    `sectors` rollup on the board AND the cycle-page families.

Re-runnable + deterministic. Run AFTER scripts.fetch_finviz_screener + scripts.fetch_basket_ohlcv.
    python -m scripts.build_subsector_membership            # both
    python -m scripts.build_subsector_membership --only nasdaq
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine import basket_index
from lib import config

log = logging.getLogger(__name__)

MIN_BARS = 220          # the confluence cascade needs >= 220 daily bars (== engine score_group)
MIN_PRICED = 3          # a chartable EW index needs a few priced members (== engine MIN_MEMBERS)
MIN_PRICED_RUT = 5      # Russell small-caps are noisier — demand a few more for a stable index
MIN_BULK_CORR = 0.50    # a bulk-out peer must track the core basket's daily returns this closely
BULK_CORR_WINDOW = 378  # ~18 months of daily bars for the correlation read

# ----------------------------------------------------------------- price helpers ----

_CLOSE: dict[str, pd.Series] = {}


def _close(ticker: str) -> pd.Series | None:
    if ticker not in _CLOSE:
        df = basket_index._load_member_ohlcv(ticker)
        _CLOSE[ticker] = (df["close"].dropna() if df is not None and "close" in df else None)
    return _CLOSE[ticker]


def _n_bars(ticker: str) -> int:
    c = _close(ticker)
    return 0 if c is None else len(c)


def _priced(tickers: list[str]) -> list[str]:
    """Members with enough history to gate, de-duped, order-preserved."""
    out, seen = [], set()
    for t in tickers:
        if t and t not in seen and _n_bars(t) >= MIN_BARS:
            seen.add(t)
            out.append(t)
    return out


def _ew_returns(tickers: list[str]) -> pd.Series | None:
    """Equal-weight daily-return series of a basket (mean of member pct-changes on the union calendar)."""
    cols = {t: _close(t) for t in tickers if _close(t) is not None}
    if not cols:
        return None
    px = pd.DataFrame(cols).sort_index()
    rets = px.pct_change()
    return rets.mean(axis=1, skipna=True).dropna()


def _bulk_keep(core: list[str], comps: list[str]) -> tuple[list[str], list[tuple[str, float]]]:
    """Keep comps whose daily returns track the CORE basket (corr >= MIN_BULK_CORR) over the recent
    window. Returns (kept, [(comp, corr)...]) — the audit trail of the price-action match."""
    base = _ew_returns(core)
    kept, audit = [], []
    if base is None:
        return kept, audit
    base = base.iloc[-BULK_CORR_WINDOW:]
    for c in comps:
        if _n_bars(c) < MIN_BARS:
            audit.append((c, float("nan")))
            continue
        cr = _close(c).pct_change().dropna()
        j = pd.concat([base, cr], axis=1, join="inner").dropna()
        corr = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) >= 60 else float("nan")
        audit.append((c, round(corr, 3) if corr == corr else corr))
        if corr == corr and corr >= MIN_BULK_CORR:
            kept.append(c)
    return kept, audit


# ----------------------------------------------------------------- shared assembly ----

def _members(tickers: list[str], names: dict[str, str]) -> list[dict]:
    return [{"ticker": t, "name": names.get(t, t)} for t in tickers]


def _amalgamate(amalg_cfg: dict, subsectors: dict, names: dict, extra_namer) -> dict:
    """Build amalgamation groups: union the member tickers of referenced subsector keys plus any
    explicit `extra` tickers; keep only priced members."""
    out = {}
    for key, cfg in amalg_cfg.items():
        bag: list[str] = []
        for sk in cfg.get("subsectors", []):
            if sk in subsectors:
                bag += [m["ticker"] for m in subsectors[sk]["members"]]
        bag += cfg.get("extra", [])
        members = _priced(bag)
        if len(members) < MIN_PRICED:
            log.warning("amalgamation %s: only %d priced members — skipped", key, len(members))
            continue
        for t in members:
            names.setdefault(t, extra_namer(t))
        out[key] = {"name": cfg["name"], "name_zh": cfg.get("name_zh"),
                    "members": _members(members, names)}
    return out


# =================================================================== NASDAQ-100 ====

# Sub-industries KEPT verbatim as subsector cards (the technical/chartable core of the index).
NDX_KEEP = [
    "Semiconductors", "Software - Application", "Software - Infrastructure",
    "Semiconductor Equipment & Materials", "Internet Retail", "Internet Content & Information",
    "Biotechnology", "Specialty Business Services", "Telecom Services",
]

# Curated subsectors that MERGE / BULK-OUT thin tech groups with close non-NDX peers. `base` =
# the in-index seed (by Finviz industry name, or explicit tickers); `comps` = peer candidates
# (kept only if they track the basket in price action). `sector` = the amalgamation/home label.
# NOTE: single-name mega-cap industries whose price action has no coherent peer basket (AAPL /
# Consumer Electronics, TSLA / Auto, APP / Advertising, NFLX+WBD / Entertainment, EA+TTWO / Gaming)
# are NOT forced into a subsector — the correlation gate rightly rejects their would-be peers. They
# are tracked instead inside the amalgamation rollups + cycle families (see *_ANCHORS extras below).
NDX_CURATED = {
    "computer-hardware": {
        "name": "Computer Hardware & Storage", "sector": "Semis & Silicon",
        "industries": ["Computer Hardware"],                           # SNDK, WDC, STX
        "comps": ["DELL", "SMCI", "NTAP", "PSTG", "HPE", "ANET"],
    },
    "communication-equipment": {
        "name": "Communication Equipment", "sector": "Semis & Silicon",
        "industries": ["Communication Equipment"],                     # CSCO, LITE
        "comps": ["ANET", "JNPR", "CIEN", "MSI", "COMM", "EXTR", "CALX", "AAOI", "INFN"],
    },
    "space-defense-tech": {
        "name": "Space & Defense Tech", "sector": "Software & Cloud",
        "industries": ["Aerospace & Defense"],                         # RKLB, AXON
        "comps": ["KTOS", "AVAV", "LUNR", "RDW", "ASTS"],
    },
}

# Orphaned single-name mega-caps, routed to their natural amalgamation so they stay tracked.
_PLATFORM_ANCHORS = ["APP", "NFLX", "WBD", "EA", "TTWO"]      # ad-tech / streaming / gaming singles
_MOBILITY_ANCHORS = ["TSLA", "RIVN", "LCID"]                  # EV / auto

# Amalgamations (the cycle families + rollup). `subsectors` reference kept/curated subsector keys;
# `extra` adds raw tickers (e.g. ex-tech names that are NOT their own subsector card).
NDX_AMALGAMATIONS = {
    "semis-silicon": {"name": "Semis & Silicon", "name_zh": "半导体与硅",
                      "subsectors": ["semiconductors", "semiconductor-equipment-materials",
                                     "communication-equipment", "computer-hardware"]},
    "software-cloud": {"name": "Software & Cloud", "name_zh": "软件与云",
                       "subsectors": ["software-infrastructure", "software-application",
                                      "specialty-business-services", "space-defense-tech"],
                       "extra": ["CTSH", "VRSK"]},
    "internet-platforms": {"name": "Internet & Platforms", "name_zh": "互联网与平台",
                           "subsectors": ["internet-content-information", "internet-retail",
                                          "telecom-services"],
                           "extra": _PLATFORM_ANCHORS},
    "ai-power-neoclouds": {"name": "AI Power & Neoclouds", "name_zh": "AI 电力与新云",
                           "subsectors": [], "extra": ["CEG", "NBIS", "CRWV", "VRT"]},
    "megacap-anchors": {"name": "Mega-cap Anchors", "name_zh": "超大盘锚",
                        "subsectors": [],
                        "extra": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO"]},
    "consumer-mobility": {"name": "Consumer & Mobility", "name_zh": "消费与出行",
                          "subsectors": [],
                          "extra": _MOBILITY_ANCHORS + ["BKNG", "ABNB", "SBUX", "MAR", "ORLY",
                                                        "ROST", "PDD"]},
    "healthcare-biotech": {"name": "Healthcare & Biotech", "name_zh": "医疗与生物科技",
                           "subsectors": ["biotechnology"],
                           "extra": ["AMGN", "GILD", "ISRG", "DXCM", "GEHC", "IDXX"]},
    "defensives-extech": {"name": "Defensives & Ex-Tech", "name_zh": "防御与非科技",
                          "subsectors": [],
                          "extra": ["PEP", "MNST", "KDP", "CCEP", "COST", "MDLZ", "KHC",
                                    "AEP", "XEL", "EXC", "FANG", "LIN", "CSX", "PCAR", "FAST",
                                    "ODFL", "HON", "PYPL"]},
}


# NDX-100 names that QQQ holds but Finviz's idx_ndx screener omits at the margin (index timing).
# Their Finviz industry is stable, so we bake them in so the build is self-contained (no reliance
# on an inline-merged file). Re-confirm if the index reconstitutes materially.
NDX_SUPPLEMENT = [
    {"ticker": "CHTR", "company": "Charter Communications Inc", "industry": "Telecom Services"},
    {"ticker": "CTSH", "company": "Cognizant Technology Solutions", "industry": "Information Technology Services"},
    {"ticker": "INSM", "company": "Insmed Inc", "industry": "Biotechnology"},
    {"ticker": "VRSK", "company": "Verisk Analytics Inc", "industry": "Consulting Services"},
    {"ticker": "ZS", "company": "Zscaler Inc", "industry": "Software - Infrastructure"},
]


def _industry_groups(rows: list[dict]) -> dict[str, list[str]]:
    g: dict[str, list[str]] = defaultdict(list)
    for r in sorted(rows, key=lambda x: -(x.get("market_cap_b") or 0)):
        g[r["industry"]].append(r["ticker"])
    return g


def _ndx_rows() -> list[dict]:
    """The Finviz idx_ndx pull merged with the QQQ-only supplement (de-duped, finviz wins)."""
    rows = json.loads((config.data_dir() / "finviz_screener" / "idx_ndx.json").read_text())["rows"]
    have = {r["ticker"] for r in rows}
    for s in NDX_SUPPLEMENT:
        if s["ticker"] not in have:
            rows.append({**s, "sector": "", "country": "USA", "market_cap_b": None})
    return rows


def build_nasdaq() -> dict:
    rows = _ndx_rows()
    names = {r["ticker"]: r["company"] for r in rows}
    by_ind = _industry_groups(rows)
    subsectors: dict[str, dict] = {}

    # 1) verbatim-kept Finviz sub-industries
    for ind in NDX_KEEP:
        members = _priced(by_ind.get(ind, []))
        if len(members) < MIN_PRICED:
            log.info("NDX keep %s: %d priced (<%d) — dropped", ind, len(members), MIN_PRICED)
            continue
        key = _slug(ind)
        sector = _home_amalgam(key)
        subsectors[key] = {"name": ind, "sector": sector, "members": _members(members, names)}

    # 2) curated merge / bulk-out subsectors
    for key, cfg in NDX_CURATED.items():
        core = _priced([t for ind in cfg["industries"] for t in by_ind.get(ind, [])])
        kept, audit = _bulk_keep(core, cfg.get("comps", []))
        members = _priced(core + kept)
        log.info("NDX curated %-22s core=%d +bulk=%d  corr=%s", key, len(core), len(kept),
                 [(c, v) for c, v in audit])
        if len(members) < MIN_PRICED:
            log.warning("NDX curated %s: only %d priced — dropped", key, len(members))
            continue
        subsectors[key] = {"name": cfg["name"], "sector": cfg["sector"],
                           "members": _members(members, names)}

    amalgamations = _amalgamate(NDX_AMALGAMATIONS, subsectors, names, lambda t: names.get(t, t))
    return {
        "version": 1, "region": "nasdaq", "index": "Nasdaq-100",
        "benchmark": "QQQ", "benchmark_label": "Nasdaq-100 (QQQ)",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "finviz idx_ndx + QQQ holdings; curated tech subsectors + amalgamations",
        "subsectors": subsectors, "amalgamations": amalgamations,
    }


# Map a kept-subsector key → its home amalgamation label (for the card's sector chip).
def _home_amalgam(subkey: str) -> str:
    for amk, cfg in NDX_AMALGAMATIONS.items():
        if subkey in cfg.get("subsectors", []):
            return cfg["name"]
    return "Nasdaq-100"


def _slug(s: str) -> str:
    import re
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-") or "x"


# =================================================================== RUSSELL-2000 ====

# Russell amalgamations = the 11 Finviz sectors (the natural small-cap rotation buckets).
RUT_SECTOR_ZH = {
    "Technology": "科技", "Healthcare": "医疗", "Financial": "金融", "Industrials": "工业",
    "Consumer Cyclical": "消费周期", "Consumer Defensive": "消费防御", "Energy": "能源",
    "Basic Materials": "基础材料", "Real Estate": "房地产", "Utilities": "公用事业",
    "Communication Services": "通信服务", "Other": "其他",
}


def build_russell() -> dict:
    rows = json.loads((config.data_dir() / "finviz_screener" / "idx_rut.json").read_text())["rows"]
    names = {r["ticker"]: r["company"] for r in rows}
    ind_sector = {r["industry"]: r["sector"] for r in rows}
    by_ind = _industry_groups(rows)

    subsectors: dict[str, dict] = {}
    for ind, tks in sorted(by_ind.items()):
        members = _priced(tks)
        if len(members) < MIN_PRICED_RUT:
            continue
        key = _slug(ind)
        subsectors[key] = {"name": ind, "sector": ind_sector.get(ind, "Other"),
                           "members": _members(members, names)}

    # amalgamate by Finviz sector
    sector_bag: dict[str, list[str]] = defaultdict(list)
    for r in sorted(rows, key=lambda x: -(x.get("market_cap_b") or 0)):
        sector_bag[r["sector"]].append(r["ticker"])
    amalgamations: dict[str, dict] = {}
    for sector, tks in sorted(sector_bag.items()):
        members = _priced(tks)
        if len(members) < MIN_PRICED:
            continue
        amalgamations[_slug(sector)] = {
            "name": sector, "name_zh": RUT_SECTOR_ZH.get(sector),
            "members": _members(members, names)}

    return {
        "version": 1, "region": "russell", "index": "Russell-2000",
        "benchmark": "IWM", "benchmark_label": "Russell-2000 (IWM)",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "finviz idx_rut (1889 names); sub-industry subsectors + sector amalgamations",
        "subsectors": subsectors, "amalgamations": amalgamations,
    }


# ----------------------------------------------------------------- main ----

def _write(region: str, payload: dict) -> None:
    out = config.data_dir() / f"baskets_{region}" / "membership.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Preserve hand-curated keys that the algorithmic builder does not emit.
    # Currently: 'archetype_groups' on the nasdaq membership (added by operator,
    # clobbered each rebuild because build_nasdaq() only emits subsectors+amalgamations).
    if out.exists() and "archetype_groups" not in payload:
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and "archetype_groups" in existing:
                payload["archetype_groups"] = existing["archetype_groups"]
                log.info("%s: re-injected archetype_groups from existing membership.json", region)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: could not read existing membership.json to preserve archetype_groups: %s", region, exc)

    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    n_sub = len(payload["subsectors"])
    n_amg = len(payload["amalgamations"])
    n_names = len({m["ticker"] for g in payload["subsectors"].values() for m in g["members"]})
    log.info("%s: %d subsectors, %d amalgamations, %d distinct priced names → %s",
             region, n_sub, n_amg, n_names, out)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["nasdaq", "russell"], help="build just one")
    args = ap.parse_args(argv)
    if args.only != "russell":
        _write("nasdaq", build_nasdaq())
    if args.only != "nasdaq":
        _write("russell", build_russell())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
