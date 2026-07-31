"""AI-brief panel data: current schedule/flags + each brief's last-generated state."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config_store
from .flags import secret_present
from .paths import SITE

_LENS_FILES = {
    "macro": "master_brief.json",
    "china": "china_brief.json",
    "btc": "btc_brief.json",
}


def _read_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def _age_days(ts) -> float | None:
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 86400.0, 2)
    except Exception:  # noqa: BLE001
        return None


def panel(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else config_store.read_config()
    mb = cfg.get("master_brain", {}) or {}
    ad = cfg.get("ai_desk", {}) or {}
    key = secret_present("DEEPSEEK_API_KEY")
    lenses = mb.get("lenses") or ["macro", "china", "btc"]

    items = []
    for lens in lenses:
        fn = _LENS_FILES.get(lens)
        d = _read_json(SITE / fn) if fn else None
        gen = (d or {}).get("generated_at")
        items.append({
            "lens": lens,
            "file": fn,
            "generated_at": gen,
            "age_days": _age_days(gen),
            "model": (d or {}).get("model"),
            "degraded_reason": (d or {}).get("degraded_reason"),
        })

    desk = _read_json(SITE / "ai_desk.json")
    desk_gen = (desk or {}).get("generated_at")

    return {
        "deepseek_key": key,
        "master_brain": {
            "enabled": bool(mb.get("enabled")),
            "interval_days": int(mb.get("interval_days", 1) or 1),
            "translate_zh": bool(mb.get("translate_zh", True)),
            "lenses": lenses,
            "model": mb.get("llm_model"),
            "items": items,
        },
        "ai_desk": {
            "enabled": bool(ad.get("enabled")),
            "interval_days": int(ad.get("interval_days", 1) or 1),
            "panel_enabled": bool((ad.get("panel") or {}).get("enabled", True)),
            "generated_at": desk_gen,
            "age_days": _age_days(desk_gen),
            "theses": (desk or {}).get("theses") and len(desk["theses"]) or 0,
        },
    }
