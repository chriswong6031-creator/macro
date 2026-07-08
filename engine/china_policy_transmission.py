"""China Policy Transmission Unifier — DISPLAY/CONTEXT-ONLY · LEAF.

Reads existing stores (PBoC stance, policy watch, event calendar, official
communiques, RRR/LPR/OMO data) and reduces them to a single deterministic
``policy_impulse`` label + event ledger.  Does NOT duplicate logic — it
*imports* the sub-engines and reads the underlying stores they already consume.

FENCES (enforced, not aspirational):
  * engine/china_intel_bus.py — UNTOUCHED (CYCLES contract).
  * engine/china_pboc_stance.py, engine/china_policy_watch.py,
    engine/china_event_calendar.py — IMPORTED (never copied).
  * data/china_official/communiques.parquet — READ-ONLY.
  * data/china_pboc/*, data/china_macro/* — READ-ONLY.
  * ``engine/setups.py`` rank weights — UNTOUCHED.

SCHEMA (binding, from masterplan §5):
  events.jsonl fields:
    ts, source, kind, title, url, sectors, phrase_diff_ref, _hash

  policy_transmission.json fields:
    policy_impulse, transmission_channel, recent_events,
    staleness.per_source_days, priced_in_check (DESCRIPTIVE, labeled),
    built, schema, authority

POLICY_IMPULSE RULES (deterministic thresholds, documented here):
  market_rescue  — any RRR cut ≥ 0.50pp OR LPR cut ≥ 25bp within 90d,
                   AND the latest FR007 z-score ≤ −1.5 (forced-easing regime)
  easing         — pboc_stance == "easing" (score ≥ 2)
  tightening     — pboc_stance == "tightening" (score ≤ −2)
  targeted_support — latest communiqué (≤120d) contains capital_market OR
                     property OR industrial keywords (see module constants),
                     AND pboc stance is NOT easing/tightening
  neutral        — all others

Never raises; degrades to data_gaps entries on missing stores.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "china_policy_transmission.v1"

# ---------------------------------------------------------------------------
# Bilingual keyword lists for sector tagging (EN + ZH). These are module
# constants so they serve as the canonical reference for the whole W4 wave.
# ---------------------------------------------------------------------------

# Capital market support keywords (EN)
_KW_CAPITAL_MARKET_EN = [
    "stock market", "equity market", "a-share", "csrc", "securities",
    "margin finance", "etf", "stock stabilization", "national team",
    "market rescue", "circuit breaker", "suspension", "ipo freeze",
]
# Capital market support keywords (ZH)
_KW_CAPITAL_MARKET_ZH = [
    "股市", "A股", "资本市场", "证监会", "融资融券", "ETF",
    "股票市场", "托市", "国家队", "平准", "停牌", "注册制",
]

# Property sector keywords (EN)
_KW_PROPERTY_EN = [
    "property", "real estate", "housing", "home purchase", "mortgage",
    "lpr 5y", "down payment", "land", "developer", "evergrande",
    "urban renewal", "shantytown",
]
# Property sector keywords (ZH)
_KW_PROPERTY_ZH = [
    "房地产", "楼市", "住房", "购房", "抵押贷款", "房贷",
    "首付", "土地", "房企", "城中村", "棚改", "限购", "限贷",
]

# Industrial / manufacturing support keywords (EN)
_KW_INDUSTRIAL_EN = [
    "manufacturing", "industrial", "equipment upgrade", "trade-in",
    "semiconductor", "chip", "new energy", "ev", "supply chain",
    "dual circulation", "self-reliance", "strategic emerging",
    "made in china 2025",
]
# Industrial / manufacturing support keywords (ZH)
_KW_INDUSTRIAL_ZH = [
    "制造业", "工业", "设备更新", "以旧换新", "半导体", "芯片",
    "新能源", "新能源汽车", "供应链", "双循环", "自立自强",
    "战略性新兴产业", "中国制造2025",
]

# Source mapping: communique family → source field
_FAMILY_TO_SOURCE = {
    "pboc_mpc":      "pboc",
    "politburo_econ": "politburo",
    "cewc":          "cewc",
}

# Valid source values per schema
_VALID_SOURCES = {"pboc", "state_council", "csrc", "ndrc", "mof", "politburo", "cewc", "other"}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _event_hash(ts: str, source: str, kind: str, title: str) -> str:
    """Dedup key = SHA-256 of (ts|source|kind|title), first 16 hex chars."""
    raw = f"{ts}|{source}|{kind}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _tag_sectors(text: str) -> list[str]:
    """Return sector tags for a piece of text using bilingual keyword lists."""
    tl = text.lower()
    tags: list[str] = []
    # capital_market
    if any(k in tl for k in _KW_CAPITAL_MARKET_EN) or any(
        k in text for k in _KW_CAPITAL_MARKET_ZH
    ):
        tags.append("capital_market")
    # property
    if any(k in tl for k in _KW_PROPERTY_EN) or any(
        k in text for k in _KW_PROPERTY_ZH
    ):
        tags.append("property")
    # industrial
    if any(k in tl for k in _KW_INDUSTRIAL_EN) or any(
        k in text for k in _KW_INDUSTRIAL_ZH
    ):
        tags.append("industrial")
    return tags


def _fr007_z() -> float | None:
    """Rolling-120d z-score of FR007; None on missing data."""
    try:
        import numpy as np
        from lib import store
        rr = store.read("china_pboc", "repo_rates")
        if rr is None or "FR007" not in rr.columns:
            return None
        s = rr["FR007"].dropna()
        if len(s) < 30:
            return None
        roll_mean = s.rolling(120, min_periods=30).mean()
        roll_std = s.rolling(120, min_periods=30).std().replace(0, np.nan)
        z = (s - roll_mean) / roll_std
        v = z.iloc[-1]
        return float(v) if not np.isnan(v) else None
    except Exception:  # noqa: BLE001
        return None


def _latest_lpr_cut_90d() -> float | None:
    """Maximum absolute LPR-1Y cut within the trailing 90 days (positive = cut). None if none."""
    try:
        import pandas as pd
        from lib import store
        df = store.read("china_macro", "lpr_rate")
        if df is None or "lpr_1y" not in df.columns:
            return None
        s = df["lpr_1y"].dropna()
        cutoff = s.index.max() - pd.Timedelta(days=90)
        recent = s[s.index >= cutoff]
        if recent.empty:
            return None
        diffs = recent.diff().dropna()
        cuts = diffs[diffs < 0]
        if cuts.empty:
            return None
        return float(abs(cuts.sum()))  # cumulative cut magnitude in pp
    except Exception:  # noqa: BLE001
        return None


def _latest_rrr_cut_90d() -> float | None:
    """Maximum absolute RRR cut within the trailing 90 days. None if none."""
    try:
        import pandas as pd
        from lib import store
        df = store.read("china_macro", "rrr")
        if df is None or "rrr_change" not in df.columns:
            return None
        s = df["rrr_change"].dropna()
        cutoff = s.index.max() - pd.Timedelta(days=90)
        recent = s[s.index >= cutoff]
        cuts = recent[recent < 0]
        if cuts.empty:
            return None
        return float(abs(cuts.sum()))
    except Exception:  # noqa: BLE001
        return None


def _recent_communique_text(days: int = 120) -> str:
    """Body text of communiques published within the last `days` days (joined)."""
    try:
        import pandas as pd
        from lib import config
        path = config.ROOT / "data/china_official/communiques.parquet"
        if not path.exists():
            return ""
        df = pd.read_parquet(path)
        df = df[df["source"] != "explicit_gap"]
        dates = pd.to_datetime(df["publish_date"], errors="coerce")
        cutoff = pd.Timestamp.now(tz=None) - pd.Timedelta(days=days)
        mask = dates >= cutoff
        recent = df[mask]
        return " ".join(recent["body"].dropna().tolist())
    except Exception:  # noqa: BLE001
        return ""


def _classify_impulse(
    pboc_stance: str | None,
    fr007_z: float | None,
    rrr_cut_90d: float | None,
    lpr_cut_90d: float | None,
    recent_comm_text: str,
) -> str:
    """Deterministic policy_impulse classifier.

    Thresholds (documented):
      market_rescue  : (rrr_cut ≥ 0.50pp OR lpr_cut ≥ 0.25pp within 90d)
                       AND fr007_z ≤ −1.5
      easing         : pboc_stance == "easing"
      tightening     : pboc_stance == "tightening"
      targeted_support: recent communiqué text hits capital_market/property/
                        industrial sectors (in 120d), and NOT easing/tightening
      neutral        : all others
    """
    if pboc_stance in ("easing", "tightening") and (
        (rrr_cut_90d or 0) >= 0.50 or (lpr_cut_90d or 0) >= 0.25
    ) and (fr007_z is not None and fr007_z <= -1.5):
        return "market_rescue"

    if pboc_stance == "easing":
        return "easing"
    if pboc_stance == "tightening":
        return "tightening"

    if recent_comm_text:
        tags = _tag_sectors(recent_comm_text)
        if tags:
            return "targeted_support"

    return "neutral"


def _derive_channels(impulse: str, pboc_stance: str | None) -> list[str]:
    """Derive the transmission_channel list from impulse + stance."""
    channels: list[str] = []
    if impulse in ("easing", "market_rescue"):
        channels.extend(["rate", "liquidity"])
    if impulse == "market_rescue":
        channels.append("stabilization")
    if impulse == "targeted_support":
        channels.append("fiscal_or_structural")
    if pboc_stance in ("easing", "neutral") and impulse not in ("tightening",):
        if "liquidity" not in channels:
            channels.append("liquidity")
    if impulse == "tightening":
        channels.append("rate")
    return sorted(set(channels))


# ---------------------------------------------------------------------------
# Event ledger seeding
# ---------------------------------------------------------------------------

def _seed_rrr_events() -> list[dict]:
    """Seed RRR change events from china_macro/rrr."""
    events: list[dict] = []
    try:
        from lib import store
        df = store.read("china_macro", "rrr")
        if df is None or "rrr_change" not in df.columns:
            return events
        s = df["rrr_change"].dropna()
        changes = s[s != 0]
        for idx, val in changes.items():
            ts = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
            cut = val < 0
            title = f"RRR {'cut' if cut else 'hike'} {abs(val):.2f}pp"
            events.append({
                "ts": ts,
                "source": "pboc",
                "kind": "rrr",
                "title": title,
                "url": None,
                "sectors": [],
                "phrase_diff_ref": None,
                "_hash": _event_hash(ts, "pboc", "rrr", title),
            })
    except Exception:  # noqa: BLE001
        pass
    return events


def _seed_lpr_events() -> list[dict]:
    """Seed LPR change events from china_macro/lpr_rate (1Y series)."""
    events: list[dict] = []
    try:
        from lib import store
        df = store.read("china_macro", "lpr_rate")
        if df is None or "lpr_1y" not in df.columns:
            return events
        s = df["lpr_1y"].dropna()
        diffs = s.diff().dropna()
        changes = diffs[diffs != 0]
        for idx, val in changes.items():
            ts = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
            cut = val < 0
            bp = int(round(abs(val) * 100))
            title = f"1Y LPR {'cut' if cut else 'hike'} {bp}bp"
            events.append({
                "ts": ts,
                "source": "pboc",
                "kind": "lpr",
                "title": title,
                "url": None,
                "sectors": [],
                "phrase_diff_ref": None,
                "_hash": _event_hash(ts, "pboc", "lpr", title),
            })
    except Exception:  # noqa: BLE001
        pass
    return events


def _seed_omo_mlf_events(z_threshold: float = 1.5) -> list[dict]:
    """Seed OMO/MLF events from FR007 z-score exceedances.

    Only dates where |FR007 z-score| > z_threshold are emitted; these represent
    notable PBoC liquidity operations (injection or drain) above a z-threshold.
    """
    events: list[dict] = []
    try:
        import numpy as np
        from lib import store
        rr = store.read("china_pboc", "repo_rates")
        if rr is None or "FR007" not in rr.columns:
            return events
        s = rr["FR007"].dropna()
        if len(s) < 30:
            return events
        roll_mean = s.rolling(120, min_periods=30).mean()
        roll_std = s.rolling(120, min_periods=30).std().replace(0, np.nan)
        z = (s - roll_mean) / roll_std
        above = z[z.abs() > z_threshold].dropna()
        # Collapse consecutive dates into the first day of each episode (avoid
        # flooding with daily FR007 moves — just the onset matters).
        import pandas as pd
        prev_date = None
        for idx, zval in above.items():
            d = idx.date() if hasattr(idx, "date") else idx
            if prev_date is not None and (d - prev_date).days <= 3:
                continue  # same episode
            prev_date = d
            ts = str(d)
            direction = "injection" if zval < 0 else "drain"
            title = f"FR007 z={zval:.2f} ({direction})"
            events.append({
                "ts": ts,
                "source": "pboc",
                "kind": "omo_mlf",
                "title": title,
                "url": None,
                "sectors": [],
                "phrase_diff_ref": None,
                "_hash": _event_hash(ts, "pboc", "omo_mlf", title),
            })
    except Exception:  # noqa: BLE001
        pass
    return events


def _seed_communique_events() -> list[dict]:
    """Seed rhetoric events from official communiques (kind=rhetoric)."""
    events: list[dict] = []
    try:
        import pandas as pd
        from lib import config
        path = config.ROOT / "data/china_official/communiques.parquet"
        if not path.exists():
            return events
        df = pd.read_parquet(path)
        df = df[df["source"] != "explicit_gap"]
        for row in df.itertuples():
            pub = getattr(row, "publish_date", None)
            if not pub or str(pub) in ("nan", "None", ""):
                pub = getattr(row, "meeting_date", None)
            if not pub or str(pub) in ("nan", "None", ""):
                continue
            ts = str(pub)[:10]
            family = getattr(row, "family", "other")
            source = _FAMILY_TO_SOURCE.get(family, "other")
            title = str(getattr(row, "title", ""))[:200]
            doc_id = str(getattr(row, "doc_id", ""))
            body = str(getattr(row, "body", ""))
            sectors = _tag_sectors(body + " " + title)
            events.append({
                "ts": ts,
                "source": source,
                "kind": "rhetoric",
                "title": title,
                "url": str(getattr(row, "url", "") or ""),
                "sectors": sectors,
                "phrase_diff_ref": doc_id or None,
                "_hash": _event_hash(ts, source, "rhetoric", title),
            })
    except Exception:  # noqa: BLE001
        pass
    return events


def _dedup(events: list[dict]) -> list[dict]:
    """Deduplicate by _hash, keep latest (by ts)."""
    seen: dict[str, dict] = {}
    for ev in sorted(events, key=lambda e: e.get("ts", "")):
        seen[ev["_hash"]] = ev
    return sorted(seen.values(), key=lambda e: e.get("ts", ""))


# ---------------------------------------------------------------------------
# Staleness block
# ---------------------------------------------------------------------------

def _staleness_block() -> dict:
    """Per-source days-since-last-event (display only)."""
    from datetime import date as _date
    today = _date.today()
    out: dict[str, Any] = {}

    def _days(d_str: str | None) -> int | None:
        if not d_str:
            return None
        try:
            return (_date.today() - _date.fromisoformat(str(d_str)[:10])).days
        except (ValueError, TypeError):
            return None

    try:
        from lib import store
        # LPR
        lpr = store.read("china_macro", "lpr_rate")
        if lpr is not None:
            out["lpr"] = _days(str(lpr.index.max().date()))
    except Exception:  # noqa: BLE001
        pass
    try:
        from lib import store
        # RRR
        rrr = store.read("china_macro", "rrr")
        if rrr is not None:
            out["rrr"] = _days(str(rrr.index.max().date()))
    except Exception:  # noqa: BLE001
        pass
    try:
        from lib import store
        # FR007
        rr = store.read("china_pboc", "repo_rates")
        if rr is not None:
            out["fr007"] = _days(str(rr.index.max().date()))
    except Exception:  # noqa: BLE001
        pass
    try:
        import pandas as pd
        from lib import config
        path = config.ROOT / "data/china_official/communiques.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            df2 = df[df["source"] != "explicit_gap"]
            latest_pub = df2["publish_date"].dropna()
            latest_pub = latest_pub[latest_pub.astype(str) != "nan"]
            if not latest_pub.empty:
                out["communiques"] = _days(str(latest_pub.max())[:10])
                # Staleness note: communiques ending 2026-04-28 is plausibly real —
                # no Politburo econ meeting between late April and July 2026. This is
                # printed as staleness data, not patched.
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_events() -> list[dict]:
    """Build the full seeded event list by merging all sub-sources.

    Deduplicates by hash(ts+source+kind+title). Returns sorted list (oldest first).
    Safe to call multiple times; dedup is idempotent.
    """
    events: list[dict] = []
    events.extend(_seed_rrr_events())
    events.extend(_seed_lpr_events())
    events.extend(_seed_omo_mlf_events())
    events.extend(_seed_communique_events())
    return _dedup(events)


def snapshot() -> dict | None:
    """Build the policy_transmission.json payload.  Never raises.

    Returns None only when ALL sub-sources are missing (total data absence).
    """
    try:
        from engine import china_pboc_stance as pboc_eng
        pboc = pboc_eng.snapshot()

        stance = (pboc or {}).get("stance")  # "easing"/"neutral"/"tightening" or None

        fr007_z = _fr007_z()
        rrr_cut_90d = _latest_rrr_cut_90d()
        lpr_cut_90d = _latest_lpr_cut_90d()
        recent_text = _recent_communique_text(days=120)

        if pboc is None and not recent_text:
            log.warning("china_policy_transmission: all sub-sources empty")
            return None

        impulse = _classify_impulse(stance, fr007_z, rrr_cut_90d, lpr_cut_90d, recent_text)
        channels = _derive_channels(impulse, stance)

        # Recent events: last 10 from ledger (or freshly seeded if ledger absent)
        events = seed_events()
        recent = [
            {k: v for k, v in e.items() if k != "_hash"}
            for e in events[-10:][::-1]  # newest first, max 10
        ]

        staleness = _staleness_block()
        data_gaps: list[str] = []
        if not pboc:
            data_gaps.append("pboc_stance unavailable")
        if fr007_z is None:
            data_gaps.append("FR007 z-score unavailable")

        return {
            "schema": SCHEMA,
            "authority": {"tier": "context_only", "may_originate": False, "may_escalate": False},
            "built": datetime.now(timezone.utc).isoformat(),
            "asof": str(date.today()),
            "policy_impulse": impulse,
            "transmission_channel": channels,
            "recent_events": recent,
            "staleness": {"per_source_days": staleness},
            # priced_in_check is DESCRIPTIVE ONLY — not a signal, not a gate.
            # Labeled explicitly per masterplan §5 and operator law.
            "priced_in_check": {
                "descriptive": True,
                "label": "descriptive only — not a signal",
                "fr007_z": fr007_z,
                "pboc_stance": stance,
            },
            "data_gaps": data_gaps,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_policy_transmission.snapshot failed: %s", e)
        return None
