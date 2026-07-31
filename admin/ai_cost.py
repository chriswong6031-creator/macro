"""AI / LLM usage + cost panel.

Two layers:
  • estimate()  — DeepSeek-only estimator (call-count × assumed token sizes).
    Preserved 100% backward-compatible so existing tests and UI callers still work.

  • unified()   — ONE normalized cost view across every ledger, for the page.
    Combines lib.ai_costs (per-lobe rollup), the Mastermind bot cost_summary.json,
    and the Codex usage_state.json, with per-source coverage metadata.  All
    sources are fail-soft.
"""
from __future__ import annotations

import json
import logging

from . import config_store
from .flags import secret_present
from .paths import DATA, ROOT, SITE

_log = logging.getLogger(__name__)

# $ per 1M tokens (input, output) — from config.yml comments
PRICING = {
    "deepseek-v4-pro": (0.435, 0.87),
    "deepseek-v4-flash": (0.14, 0.28),
}
# documented per-call token assumptions (input, output)
ASSUMED = {
    "brief_pro": (7000, 2500),     # master_brain reasoning brief over the state JSON
    "translate_flash": (2500, 2500),
    "desk_pro": (4000, 1500),      # one ai_desk analyst / adjudicator call
}
PER_STOCKBRIEF_USD = 0.04          # config: catalyst_stock "~$0.04 each"
BUILD_DAYS_PER_MONTH = 21          # weekday cron ≈ 21 build-days/month


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pin, pout = PRICING.get(model, (0.0, 0.0))
    return in_tok / 1e6 * pin + out_tok / 1e6 * pout


def _assumed_cost(model: str, kind: str) -> float:
    i, o = ASSUMED[kind]
    return _cost(model, i, o)


def _read_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def _count_lines(p) -> int:
    try:
        return sum(1 for _ in p.open())
    except Exception:  # noqa: BLE001
        return 0


def estimate(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else config_store.read_config()
    mb = cfg.get("master_brain", {}) or {}
    ad = cfg.get("ai_desk", {}) or {}
    cs = cfg.get("catalyst_stock", {}) or {}

    key = secret_present("DEEPSEEK_API_KEY")
    lenses = mb.get("lenses") or ["macro", "china", "btc"]
    mb_on = bool(mb.get("enabled")) and key
    mb_interval = int(mb.get("interval_days", 1) or 1)
    translate = bool(mb.get("translate_zh", True))

    ad_on = bool(ad.get("enabled")) and key
    ad_interval = int(ad.get("interval_days", 1) or 1)
    ad_panel = bool((ad.get("panel") or {}).get("enabled", True))
    ad_calls = 5 if ad_panel else 1   # 4 analysts + adjudicator, or single analyst

    cs_on = bool(cs.get("enabled")) and key
    stockbrief_files = len(list((SITE / "stockbrief").glob("*.json"))) if (SITE / "stockbrief").is_dir() else 0

    components = []

    # master brain briefs (one pro call/lens, + a flash translate pass/lens)
    mb_pro = len(lenses) * _assumed_cost("deepseek-v4-pro", "brief_pro")
    mb_tr = (len(lenses) * _assumed_cost("deepseek-v4-flash", "translate_flash")) if translate else 0.0
    components.append({
        "name": "AI Daily Brief (Master Brain)",
        "enabled": mb_on, "model": mb.get("llm_model", "deepseek-v4-pro"),
        "calls_per_build": (len(lenses) + (len(lenses) if translate else 0)) if mb_on else 0,
        "cost_per_build": round(mb_pro + mb_tr, 4) if mb_on else 0.0,
        "interval_days": mb_interval,
        "note": f"{len(lenses)} lenses{' + 中文' if translate else ''}, every {mb_interval}d",
    })

    # ai desk note
    desk_cost = ad_calls * _assumed_cost("deepseek-v4-pro", "desk_pro")
    components.append({
        "name": "AI Desk note",
        "enabled": ad_on, "model": ad.get("llm_model", "deepseek-v4-pro"),
        "calls_per_build": ad_calls if ad_on else 0,
        "cost_per_build": round(desk_cost, 4) if ad_on else 0.0,
        "interval_days": ad_interval,
        "note": f"{'4-analyst panel' if ad_panel else 'single analyst'}, every {ad_interval}d",
    })

    # per-stock briefs (daily; cached per ticker/day; use realized file count as the size)
    cs_cost = stockbrief_files * PER_STOCKBRIEF_USD
    components.append({
        "name": "Per-stock AI briefs",
        "enabled": cs_on, "model": cs.get("llm_model", "deepseek-v4-pro"),
        "calls_per_build": stockbrief_files if cs_on else 0,
        "cost_per_build": round(cs_cost, 4) if cs_on else 0.0,
        "interval_days": 1,
        "note": f"{stockbrief_files} briefs precomputed (~${PER_STOCKBRIEF_USD}/ea, daily)",
    })

    # effective daily = per-build cost amortised by its interval
    eff_daily = sum((c["cost_per_build"] / max(1, c["interval_days"])) for c in components if c["enabled"])
    monthly = eff_daily * BUILD_DAYS_PER_MONTH

    # what changing the brief interval saves (master_brain + ai_desk only)
    base_per_build = sum(c["cost_per_build"] for c in components
                         if c["enabled"] and c["name"] != "Per-stock AI briefs")
    daily_fixed = sum((c["cost_per_build"] / max(1, c["interval_days"]))
                      for c in components if c["enabled"] and c["name"] == "Per-stock AI briefs")
    savings = [{
        "interval": n,
        "monthly_usd": round((base_per_build / n + daily_fixed) * BUILD_DAYS_PER_MONTH, 2),
    } for n in range(1, 8)]

    # realized signals
    last_brief = _read_json(SITE / "master_brief.json") or {}
    theses = _count_lines(DATA / "ai_desk" / "theses.jsonl")

    return {
        "deepseek_key": key,
        "components": components,
        "per_build_usd": round(sum(c["cost_per_build"] for c in components if c["enabled"]), 4),
        "effective_daily_usd": round(eff_daily, 4),
        "monthly_usd": round(monthly, 2),
        "savings_by_interval": savings,
        "realized": {
            "stockbrief_files": stockbrief_files,
            "ai_desk_theses_logged": theses,
            "last_brief_generated_at": last_brief.get("generated_at"),
            "last_brief_model": last_brief.get("model"),
        },
        "assumptions": {
            "pricing_per_1m_tok": PRICING,
            "tokens_per_call": ASSUMED,
            "per_stockbrief_usd": PER_STOCKBRIEF_USD,
            "build_days_per_month": BUILD_DAYS_PER_MONTH,
            "disclaimer": "Estimate only — no token usage is logged; based on call counts × config rates.",
        },
        "unified": unified(),
    }


# ---------------------------------------------------------------------------
# Unified cost model — ONE normalized view across every ledger, for the page
# ---------------------------------------------------------------------------

def _parse_iso(ts):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _age_hours(ts):
    from datetime import datetime, timezone
    dt = _parse_iso(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 1)
    except Exception:  # noqa: BLE001
        return None


def _status_from_age(age_h, stale_h: float = 48.0) -> str:
    if age_h is None:
        return "absent"
    return "live" if age_h <= stale_h else "stale"


def _summarize_ledger():
    """lib.ai_costs.summarize(root=ROOT) via guarded import.  {} on failure."""
    try:
        import importlib as _il
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        return _il.import_module("lib.ai_costs").summarize(root=ROOT) or {}
    except Exception as exc:  # noqa: BLE001
        _log.debug("ai_cost._summarize_ledger: %s", exc)
        return {}


def unified() -> dict | None:
    """Assemble ONE normalized cost model across all ledgers for the AI Cost page.

    Combines the unified usage ledger (lib.ai_costs, rolled up per lobe with
    percentages) with the external ledgers that sync back to the repo — the
    Mastermind bot's cost_summary.json and the Codex usage_state.json — plus
    per-source coverage metadata so the operator can see what is tracked, what
    is stale, and what is missing.  Every source is fail-soft; absent = flagged,
    never fatal.  Never raises.
    """
    try:
        summary = _summarize_ledger()
        d30 = summary.get("d30") or {}
        windows = {
            "today": summary.get("today") or {},
            "d7": summary.get("d7") or {},
            "d30": d30,
        }

        # ── lobes from the unified ledger (already ranked + %-annotated) ──
        lobes: list[dict] = []
        for name, b in (summary.get("by_lobe") or {}).items():
            lobes.append({
                "name": name, "source": "ledger",
                "usd": round(float(b.get("usd", 0.0)), 4),
                "tokens": int(b.get("tokens", 0)),
                "calls": int(b.get("calls", 0)),
                "lanes": b.get("lanes_ranked") or [],
                "no_usd": False,
            })

        # ── Mastermind bot (external VPS cost_summary.json) ──
        mm = _read_json(DATA / "mastermind" / "cost_summary.json")
        bot = None
        if mm and isinstance(mm, dict):
            t30 = mm.get("totals_30d") or {}
            bot_usd = round(float(t30.get("usd", 0.0) or 0.0), 4)
            bot_tok = int(t30.get("input_tokens", 0) or 0) + int(t30.get("output_tokens", 0) or 0)
            # cost_summary by_book/by_seat/by_key are {name: usd_float} maps.
            by_book = t30.get("by_book") or {}
            bot_calls = 0
            for _day in (mm.get("days") or {}).values():
                for _seg in ("autonomous", "heavyweight"):
                    bot_calls += int(((_day or {}).get(_seg) or {}).get("calls", 0) or 0)
            bot = {"as_of": mm.get("as_of"), "totals_30d": t30, "days": mm.get("days")}
            if bot_usd > 0 or bot_tok > 0:
                lobes.append({
                    "name": "Mastermind · bot", "source": "bot",
                    "usd": bot_usd, "tokens": bot_tok, "calls": bot_calls,
                    "lanes": [
                        {"name": k, "usd": round(float(v or 0.0), 4), "tokens": 0, "calls": 0}
                        for k, v in sorted(by_book.items(),
                                           key=lambda kv: float(kv[1] or 0.0),
                                           reverse=True)
                    ],
                    "no_usd": False,
                })

        # ── Codex research lane (usage_state.json — rate-limit only, no USD) ──
        codex_state = _read_json(DATA / "codex_lane" / "usage_state.json")
        codex = None
        if codex_state and isinstance(codex_state, dict):
            tu = codex_state.get("token_usage_last") or {}
            ctok = int(tu.get("total_tokens") or 0) or (
                int(tu.get("input_tokens", 0) or 0) + int(tu.get("output_tokens", 0) or 0))
            codex = {
                "input_tokens": tu.get("input_tokens"),
                "output_tokens": tu.get("output_tokens"),
                "total_tokens": tu.get("total_tokens"),
                "degraded": codex_state.get("degraded"),
                "plan_type": codex_state.get("plan_type"),
                "paused_until": codex_state.get("paused_until"),
                "rate_limits": codex_state.get("rate_limits"),
                "updated_at": codex_state.get("updated_at"),
            }
            lobes.append({
                "name": "Codex", "source": "codex",
                "usd": 0.0, "tokens": ctok,
                "calls": len(codex_state.get("sessions") or []),
                "lanes": [], "no_usd": True,
            })

        # ── combined totals + percentages over the whole picture ──
        tot_usd = round(sum(l["usd"] for l in lobes), 4)
        tot_tok = sum(l["tokens"] for l in lobes)
        tot_calls = sum(l["calls"] for l in lobes)
        for l in lobes:
            l["pct_usd"] = round(100.0 * l["usd"] / tot_usd, 1) if tot_usd else 0.0
            l["pct_tokens"] = round(100.0 * l["tokens"] / tot_tok, 1) if tot_tok else 0.0
        lobes.sort(key=lambda l: (l["usd"], l["tokens"]), reverse=True)

        # ── source coverage (what is tracked / stale / missing) ──
        led_calls = int(d30.get("calls", 0) or 0)
        recent = summary.get("recent") or []
        led_asof = recent[0].get("ts") if recent else None
        sources = [{
            "key": "ledger", "label": "Unified usage ledger + shards",
            "status": "live" if led_calls > 0 else "empty",
            "as_of": led_asof, "age_h": _age_hours(led_asof),
            "usd_30d": round(float(d30.get("usd", 0.0) or 0.0), 4),
            "note": f"{led_calls} calls/30d · data/ai_costs/usage.jsonl(+usage.d)",
        }]
        mm_asof = (mm or {}).get("as_of")
        sources.append({
            "key": "bot", "label": "Mastermind bot (VPS)",
            "status": _status_from_age(_age_hours(mm_asof)) if mm else "absent",
            "as_of": mm_asof, "age_h": _age_hours(mm_asof),
            "usd_30d": round(float(((mm or {}).get("totals_30d") or {}).get("usd", 0.0) or 0.0), 4) if mm else None,
            "note": "external cost_summary.json (per-call rows not synced)",
        })
        cx_asof = (codex_state or {}).get("updated_at")
        sources.append({
            "key": "codex", "label": "Codex research lane",
            "status": _status_from_age(_age_hours(cx_asof)) if codex_state else "absent",
            "as_of": cx_asof, "age_h": _age_hours(cx_asof),
            "usd_30d": None,
            "note": "rate-limit only, no USD" + (" · DEGRADED" if (codex_state or {}).get("degraded") else ""),
        })
        # budget_ledger.json is currently a dead source — flag honestly if absent.
        bl = _read_json(DATA / "metabolism" / "budget_ledger.json")
        sources.append({
            "key": "budget_ledger", "label": "Metabolism budget ledger",
            "status": "live" if bl else "absent", "as_of": (bl or {}).get("as_of"),
            "age_h": _age_hours((bl or {}).get("as_of")) if bl else None,
            "usd_30d": (bl or {}).get("usd_spent") if bl else None,
            "note": "data/metabolism/budget_ledger.json" + ("" if bl else " — not present"),
        })

        # Combined subscription-vs-metered split across ALL sources so the
        # two cards reconcile with the all-sources total.  The Mastermind bot
        # runs on OAuth pool keys → its USD is API-equivalent (subscription).
        cb = summary.get("by_cost_basis") or {}
        sub_led = float((cb.get("subscription") or {}).get("usd", 0.0) or 0.0)
        met_led = float((cb.get("metered") or {}).get("usd", 0.0) or 0.0)
        bot_usd_total = float(((bot or {}).get("totals_30d") or {}).get("usd", 0.0) or 0.0)
        subscription_usd = round(sub_led + bot_usd_total, 4)
        metered_usd = round(met_led, 4)

        return {
            "windows": windows,
            "totals": {
                "usd": tot_usd, "tokens": tot_tok, "calls": tot_calls,
                "subscription_usd": subscription_usd, "metered_usd": metered_usd,
            },
            "lobes": lobes,
            "cost_basis": summary.get("by_cost_basis") or {},
            "providers": summary.get("by_provider_ranked") or [],
            "models": summary.get("by_model_ranked") or [],
            "keys": summary.get("by_key_ranked") or [],
            "sources": sources,
            "bot": bot,
            "codex": codex,
            "recent": recent[:40],
            "lobe_order": summary.get("lobe_order") or [],
        }
    except Exception as exc:  # noqa: BLE001
        _log.warning("ai_cost.unified: %s", exc)
        return None
