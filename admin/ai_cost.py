"""AI / LLM usage + cost panel.

Two layers:
  • estimate()  — DeepSeek-only estimator (call-count × assumed token sizes).
    Preserved 100% backward-compatible so existing tests and UI callers still work.
    A new "measured" key is added with measured/ledger data from lib.ai_costs,
    data/metabolism/budget_ledger.json, data/mastermind/cost_summary.json, and
    data/codex_lane/usage_state.json.  All measured sources are fail-soft.

  • _measured()  — internal helper that assembles the "measured" block.
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


def estimate() -> dict:
    cfg = config_store.read_config()
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
        "measured": _measured(),
    }


# ---------------------------------------------------------------------------
# Measured data block — all sources fail-soft, absent = None
# ---------------------------------------------------------------------------

def _measured() -> dict | None:
    """Assemble measured cost data from ledger + external sources.

    Returns None when the core ledger is absent or the lib import fails
    (mirrors metabolism_panel's guarded-import idiom).  Never raises.
    """
    try:
        # --- lib.ai_costs summarize (guarded import) ---
        try:
            import sys as _sys
            import importlib as _il
            import pathlib as _pl
            # Ensure repo root is on sys.path so lib.ai_costs imports cleanly.
            _repo = str(ROOT)
            if _repo not in _sys.path:
                _sys.path.insert(0, _repo)
            _ai_mod = _il.import_module("lib.ai_costs")
            summary = _ai_mod.summarize(root=ROOT)
        except Exception as exc:  # noqa: BLE001
            _log.debug("ai_cost._measured: lib.ai_costs unavailable (%s)", exc)
            summary = None

        # --- budget_ledger.json (fail-soft) ---
        budget_ledger = _read_json(DATA / "metabolism" / "budget_ledger.json")
        budget_summary: dict | None = None
        if budget_ledger and isinstance(budget_ledger, dict):
            budget_summary = {
                "usd_spent": budget_ledger.get("usd_spent"),
                "token_spent": budget_ledger.get("token_spent"),
                "as_of": budget_ledger.get("as_of") or budget_ledger.get("ts"),
            }

        # --- mastermind cost_summary.json (fail-soft) ---
        mm_summary = _read_json(DATA / "mastermind" / "cost_summary.json")
        mastermind: dict | None = None
        if mm_summary and isinstance(mm_summary, dict):
            if mm_summary.get("schema") == "mastermind.cost_summary.v1":
                mastermind = {
                    "as_of": mm_summary.get("as_of"),
                    "totals_30d": mm_summary.get("totals_30d"),
                    "days": mm_summary.get("days"),
                }

        # --- codex usage_state.json (fail-soft) ---
        codex_state = _read_json(DATA / "codex_lane" / "usage_state.json")
        codex: dict | None = None
        if codex_state and isinstance(codex_state, dict):
            tu = codex_state.get("token_usage_last") or {}
            codex = {
                "input_tokens": tu.get("input_tokens"),
                "output_tokens": tu.get("output_tokens"),
                "total_tokens": tu.get("total_tokens"),
            }

        # --- per-cycle achievements join (fail-soft) ---
        cycle_rows: list[dict] = []
        if summary and isinstance(summary.get("recent"), list):
            seen_cycles: dict[str, dict] = {}
            for row in summary["recent"]:
                cid = row.get("cycle_id") or ""
                if not cid or cid in seen_cycles:
                    continue
                seen_cycles[cid] = {
                    "cycle_id": cid,
                    "ts": row.get("ts"),
                    "lane": row.get("lane"),
                    "est_cost_usd": row.get("est_cost_usd"),
                    "input_tokens": row.get("input_tokens", 0),
                    "output_tokens": row.get("output_tokens", 0),
                    "achievement": None,
                }
                if len(seen_cycles) >= 10:
                    break
            # Try to enrich with achievements titles/decisions (guarded).
            if seen_cycles:
                try:
                    from admin import metabolism_achievements as _ma  # noqa: PLC0415
                    ach = _ma.achievements(limit_cycles=20, root=ROOT)
                    ach_by_base: dict[str, str] = {}
                    import re as _re  # noqa: PLC0415
                    _BASE_RE = _re.compile(r"^(cycle-\d{4}-\d{2}-\d{2}-[0-9a-fA-F]{4})")
                    for cy in (ach.get("cycles") or []):
                        cid = cy.get("cycle_id") or ""
                        m = _BASE_RE.match(cid)
                        key = m.group(1) if m else cid
                        ach_by_base[key] = (cy.get("headline_plain")
                                            or cy.get("cycle_id") or "")
                    for cid_key, entry in seen_cycles.items():
                        m = _BASE_RE.match(cid_key)
                        base = m.group(1) if m else cid_key
                        if base in ach_by_base:
                            entry["achievement"] = ach_by_base[base]
                except Exception as exc:  # noqa: BLE001
                    _log.debug("ai_cost._measured: achievements join failed (%s)", exc)
            cycle_rows = list(seen_cycles.values())

        return {
            "summary": summary,
            "budget_ledger": budget_summary,
            "mastermind": mastermind,
            "codex": codex,
            "recent_cycles": cycle_rows,
        }
    except Exception as exc:  # noqa: BLE001
        _log.warning("ai_cost._measured: outer error (%s)", exc)
        return None
