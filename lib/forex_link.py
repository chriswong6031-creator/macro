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


def _read_latest() -> dict:
    """Return full forex/latest.json as a dict ({} if absent/unreadable)."""
    p = config.data_dir() / "forex" / "latest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def stance() -> dict:
    """Return the latest.json `stance` block, or {} if absent.

    B3 spec item 1: consumers (commodities, bonds, etc.) surface the plain-word
    dollar stance produced by build_forex. Degrades to {} when the key is absent
    (first nightly before build_forex lands the key, or stale store). Never raises.
    """
    try:
        return _read_latest().get("stance") or {}
    except Exception:  # noqa: BLE001
        return {}


def dollar_day() -> dict | None:
    """Return the latest.json `dollar_day` block {z, flag, dir}, or None if absent.

    B3 spec item 1: consumers read this for the daily dollar-move context chip.
    Degrades to None when the key is absent. Never raises.
    """
    try:
        raw = _read_latest().get("dollar_day")
        if not isinstance(raw, dict):
            return None
        return raw
    except Exception:  # noqa: BLE001
        return None


def transmission_asset(key: str) -> dict | None:
    """Return the per-asset transmission block from latest.json `transmission.assets[key]`.

    Returns {corr_fast, corr_slow, effect, stability} or None if absent.
    B3 spec item 2/3: consumers read effect/stability for plain-word display chips.
    """
    try:
        raw = _read_latest()
        assets = (raw.get("transmission") or {}).get("assets") or {}
        val = assets.get(key)
        return val if isinstance(val, dict) else None
    except Exception:  # noqa: BLE001
        return None
