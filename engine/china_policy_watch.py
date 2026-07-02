"""China Central Bank & Government Policy Watch — assembler.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS. The China sibling of the US policy_watch page,
but PBoC-and-State-Council-centric. Fans together, with no new scoring:

  * PBoC stance + rate corridor + FX/reserves  (engine/china_pboc_stance.py)
  * NBS latest-prints board                      (china_macro / china_credit stores)
  * Official policy tape                         (filtered china_news_intel PIT bus)
  * Curated intel substrate                      (data/china_policy/intel.json:
      thesis · NPC targets · sector-policy matrix · falsifiable prediction ledger)

Emits the page view-model + a compact data/china_policy/latest.json (the machine-readable
hub contract the intel bus + future China Mastermind read). Never raises.
See research/CHINA_INTEL_POWERHOUSE.md §3.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_policy_watch.v1"

# NBS / macro latest-prints board: (group, series, col, label_en, label_zh, unit)
_NBS_BOARD = [
    ("china_macro", "pmi", "pmi_mfg", "Mfg PMI", "制造业PMI", ""),
    ("china_macro", "pmi", "pmi_nonmfg", "Non-mfg PMI", "非制造业PMI", ""),
    ("china_macro", "cpi", "cpi_yoy", "CPI YoY", "CPI同比", "%"),
    ("china_macro", "ppi", "ppi_yoy", "PPI YoY", "PPI同比", "%"),
    ("china_macro", "money_supply", "m2_yoy", "M2 YoY", "M2同比", "%"),
    ("china_macro", "money_supply", "m1_yoy", "M1 YoY", "M1同比", "%"),
    ("china_macro", "gdp", "gdp_yoy", "GDP YoY", "GDP同比", "%"),
    ("china_macro", "retail", "retail_yoy", "Retail YoY", "社零同比", "%"),
    ("china_macro", "customs", "exports_yoy", "Exports YoY", "出口同比", "%"),
    ("china_credit", "tsf", "tsf_total", "TSF (mo)", "社融(当月)", "¥bn"),
]

_POLICY_THEMES = {"policy", "monetary", "fiscal", "trade", "industrial_policy", "credit"}


def _latest(group: str, name: str, col: str):
    try:
        df = store.read(group, name)
        if df is None or df.empty or col not in df.columns:
            return None, None
        s = df[col].dropna()
        if s.empty:
            return None, None
        return float(s.iloc[-1]), str(s.index.max().date())
    except Exception:  # noqa: BLE001
        return None, None


def _nbs_prints() -> list[dict]:
    rows = []
    for group, name, col, en, zh, unit in _NBS_BOARD:
        v, d = _latest(group, name, col)
        if v is None:
            continue
        rows.append({"label_en": en, "label_zh": zh,
                     "value": round(v, 2), "unit": unit, "asof": d})
    return rows


def _policy_feed(top_n: int = 12) -> list[dict]:
    """Official / policy-themed slice of the china_news_intel PIT bus (tier-1 or policy theme)."""
    try:
        import pandas as pd
        from engine import china_news_intel as ni
        path = ni._events_path()
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        if df.empty:
            return []
        mask = (df["source_tier"] == 1) | (df["theme"].isin(_POLICY_THEMES))
        sub = df[mask].sort_values("first_seen_utc", ascending=False).head(top_n)
        out = []
        for r in sub.itertuples():
            tl = ni.THEME_LABEL.get(r.theme, (r.theme, r.theme))
            out.append({"title": r.title, "url": r.url, "source": r.source,
                        "theme": r.theme, "theme_en": tl[0], "theme_zh": tl[1],
                        "tier": int(r.source_tier), "scheduled_ref": r.scheduled_ref})
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("china policy feed unavailable (%s)", e)
        return []


def _intel() -> dict:
    try:
        p = config.ROOT / "data" / "china_policy" / "intel.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("china policy intel.json unreadable (%s)", e)
    return {}


def _compact(pboc: dict | None, intel: dict) -> dict:
    """The machine-readable latest.json the intel bus + China Mastermind read.

    PBoC corridor mixes vintages — LPR is monthly while FR007/CNY are daily — so each field
    carries its own asof, the top-level asof is the NEWEST constituent (not LPR-anchored),
    and `stale` flags when even the newest is > ~35 days old."""
    corridor = {c["key"]: c["value"] for c in (pboc or {}).get("corridor", [])}
    fx = (pboc or {}).get("fx", {})
    asof_lpr = (pboc or {}).get("asof")
    asof_res = fx.get("asof_reserves")
    asof_cny = fx.get("asof_cny")
    dates = [d for d in (asof_lpr, asof_res, asof_cny) if d]
    newest = max(dates) if dates else str(date.today())
    stale = False
    try:
        stale = (date.today() - date.fromisoformat(newest[:10])).days > 35
    except (ValueError, TypeError):
        pass
    return {
        "schema": SCHEMA, "is_context_only": True,
        "asof": newest, "asof_lpr": asof_lpr, "asof_reserves": asof_res, "asof_cny": asof_cny,
        "stale": stale,
        "stance": (pboc or {}).get("stance"),
        "stance_en": (pboc or {}).get("stance_en"), "stance_zh": (pboc or {}).get("stance_zh"),
        "lpr_1y": corridor.get("lpr_1y"), "lpr_5y": corridor.get("lpr_5y"),
        "rrr": corridor.get("rrr"), "fr007": corridor.get("fr007"),
        "fx_reserves": fx.get("reserves"), "usd_cny": fx.get("usd_cny"),
        "last_moves": [m.get("detail_en") for m in (pboc or {}).get("last_moves", [])],
        "predictions": [p.get("text_en") for p in intel.get("predictions", [])
                        if p.get("status") == "open"],
    }


def snapshot(asof: date | str | None = None) -> dict | None:
    """Full China Policy Watch view-model + the compact latest.json payload. Never raises."""
    try:
        from engine import china_pboc_stance, policy_dates
        pboc = china_pboc_stance.snapshot(asof)
        intel = _intel()
        prints = _nbs_prints()
        feed = _policy_feed()
        if pboc is None and not prints and not intel:
            return None
        # Audit fix: annotate the intel substrate with live date status so the template can
        # surface the intel age and warn when the hand-authored intel.json is stale (>14d).
        intel_dates = policy_dates.annotate(intel)
        return {
            "schema": SCHEMA, "is_context_only": True,
            "asof": (str(asof) if asof else (pboc or {}).get("asof") or str(date.today())),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "pboc": pboc, "nbs_prints": prints, "policy_feed": feed, "intel": intel,
            "intel_dates": intel_dates,
            "latest": _compact(pboc, intel),
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_policy_watch.snapshot failed (%s)", e)
        return None


def write_latest(vm: dict | None) -> None:
    """Persist the compact contract to data/china_policy/latest.json (for the bus)."""
    try:
        if not vm or not vm.get("latest"):
            return
        p = config.ROOT / "data" / "china_policy" / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(vm["latest"], ensure_ascii=False,
                                separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001
        log.error("china_policy_watch.write_latest failed (%s)", e)
