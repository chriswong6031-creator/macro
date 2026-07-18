"""Read the forex Dollar Desk's cross-asset transmission for OTHER pages.

The dollar is the master price, so commodity / bond / cross-asset pages surface its
contemporaneous 63-day correlation to each asset as a small DISPLAY-ONLY "USD
sensitivity" annotation. Written by scripts.build_forex (which runs first in daily.yml)
to data/forex/latest.json. Degrades to {} / None if the file or the transmission block
is absent, so a consumer page never breaks on build order.

CONTEXT, not a forecast: these correlations are contemporaneous, regime-dependent and
unstable — the full panel (with stability + calm/stress splits) lives on forex.html.
"""
from __future__ import annotations

import json

from lib import config

# config transmission key -> friendly (en, zh) label for the consuming page
ASSET_LABEL = {
    "SPY": ("S&P 500", "标普500"), "EEM": ("EM equity", "新兴股票"),
    "GC=F": ("Gold", "黄金"), "CL=F": ("Oil", "原油"), "HG=F": ("Copper", "铜"),
    "UST10": ("10y Treasury", "10年期国债"), "BTC": ("Bitcoin", "比特币"),
}
# the labels engine.forex_transmission emits into `unstable` (must match for the flag)
_TLABEL = {"SPY": "US equities", "EEM": "EM equities", "GC=F": "Gold", "CL=F": "Oil (WTI)",
           "HG=F": "Copper", "UST10": "10y Treasury", "BTC": "Bitcoin"}


def transmission() -> dict:
    """The whole transmission block ({} if absent)."""
    p = config.data_dir() / "forex" / "latest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()).get("transmission") or {}
    except Exception:  # noqa: BLE001
        return {}


def asset_corr(key: str, tr: dict | None = None) -> dict | None:
    """USD-sensitivity annotation for one transmission key, or None if unavailable.
    {corr, stable, usd_dir, label, label_zh}. `tr` lets a caller reuse one read."""
    tr = transmission() if tr is None else tr
    corr = (tr.get("corr") or {}).get(key)
    if corr is None:
        return None
    en, zh = ASSET_LABEL.get(key, (key, key))
    return {"corr": corr, "stable": _TLABEL.get(key, key) not in (tr.get("unstable") or []),
            "usd_dir": tr.get("usd_dir"), "label": en, "label_zh": zh}


def _latest() -> dict:
    """Parse data/forex/latest.json once; return {} on any error."""
    p = config.data_dir() / "forex" / "latest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def dollar_lean(fx: dict | None = None) -> dict | None:
    """Return the dollar_desk block from latest.json, or None if absent.

    Keys consumed by callers: lean, lean_zh, lean_net, usd_dir (from transmission),
    triple_red, trend, liquidity_dir, fed_path_lean.  Fail-open: returns None when
    the file is missing, unreadable, or the block is absent.
    `fx` lets a caller reuse one _latest() read."""
    fx = _latest() if fx is None else fx
    desk = fx.get("dollar_desk")
    if not desk:
        return None
    # merge usd_dir from transmission so callers have a single dict
    usd_dir = (fx.get("transmission") or {}).get("usd_dir")
    return {**desk, "usd_dir": usd_dir}


def state_changes(fx: dict | None = None) -> dict | None:
    """Return the state_changes block from latest.json, or None if absent.

    Added by MSX-1 (producer lane); absent until the first post-merge nightly.
    Each key: {current, prev, changed_on, days_in_state}.  Null-tolerant."""
    fx = _latest() if fx is None else fx
    return fx.get("state_changes") or None


def stress_radar(fx: dict | None = None) -> dict | None:
    """Return the regime_radar block (including scenarios list) from latest.json.

    Pre-MSX-1 shape: {as_of, dominant, active, intensity}.
    Post-MSX-1 shape adds: scenarios list per §2.1.  Both shapes returned as-is;
    callers must use .get() on every key."""
    fx = _latest() if fx is None else fx
    return fx.get("regime_radar") or None


def attach_fx_context(radar: dict, page_asof: str | None) -> None:
    """Attach fx_context to a market-state radar dict in-place (fail-open).

    Encapsulates the MSX-1 FX context attach logic shared by build_china.py and
    build_hk.py.  Reads data/forex/latest.json via _latest(); attaches only when
    at least one of dollar_desk / USDCNH pair / usd_dir is present.  Sets
    stale=True (+ built_date) when forex asof < page_asof.  No-op on any missing
    or malformed data — never raises, never modifies radar when data is absent.

    Payload keys: {cnh_basis_bps, cnh_basis_state, usd_dir, as_of, stale
    [, built_date when stale]}.

    Args:
        radar:     The radar dict (e.g. vm["market_state"]["radar"]); mutated
                   in-place by adding "fx_context".
        page_asof: The page's as-of date string (YYYY-MM-DD or similar ISO
                   prefix); used for staleness compare.  May be None / "".
    """
    try:
        fx = _latest()
        desk = fx.get("dollar_desk") or {}
        cnh_pair = (fx.get("pairs") or {}).get("USDCNH") or {}
        usd_dir = (fx.get("transmission") or {}).get("usd_dir")
        if not fx or not (desk or cnh_pair or usd_dir):
            return
        blk: dict = {
            "cnh_basis_bps": cnh_pair.get("cnh_basis_bps"),
            "cnh_basis_state": cnh_pair.get("cnh_basis_state"),
            "usd_dir": usd_dir,
            "as_of": fx.get("asof"),
            "stale": False,
        }
        # Staleness: compare only when both asof strings are non-empty/non-None.
        # str(None)[:10] == "None" which would produce spurious lexicographic
        # failures, so we guard explicitly.
        fx_asof = (fx.get("asof") or "") or ""
        pg_asof = (page_asof or "") or ""
        fx_asof = fx_asof[:10].strip()
        pg_asof = pg_asof[:10].strip()
        if fx_asof and pg_asof and fx_asof < pg_asof:
            blk["stale"] = True
            blk["built_date"] = fx_asof
        radar["fx_context"] = blk
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
