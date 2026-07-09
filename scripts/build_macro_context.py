"""Build the Macro Weather Station page -> site/macro_context.html.

Reads (all fail-open with graceful empty states):
  data/neuralweb/world_state.json      — rates_transmission, fx_dollar, contradictions,
                                         intelligence lobes (PR-B)
  data/macro_snapshots/latest.json     — ~24 v1 labels grouped by domain
  data/macro_snapshots/transitions.jsonl — label-flip history (last 30 rows)

Writes:
  site/macro_context.html              — bilingual Macro Weather Station page
  data/macro_context/latest.json       — hub contract consumed downstream

Display/context tier only.  No scores, no signals, no Article-2 surfaces.
Usage: python -m scripts.build_macro_context
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_macro_context")

# Shared palette (same as bonds / forex for product consistency)
C = {
    "blue": "#285FFF", "indigo": "#4559DC", "ink": "#0B1733", "text": "#344054",
    "muted": "#6F6F6F", "faint": "#A0A0A0", "red": "#D30B0B", "redfill": "#FEB5B5",
    "amber": "#F5AD42", "green": "#1a7f43", "grid": "#EAECF0", "card": "#FFFFFF",
    "bg": "#F7F8FA", "gold": "#C8A53B", "teal": "#1F8A70",
}

# How many days stale triggers each badge class
_STALE_WARN_DAYS = 2
_STALE_OLD_DAYS = 5

# Domain order for the weather board
DOMAIN_ORDER = [
    "us", "market", "transmission", "fx", "bonds",
    "commodity", "china", "hk", "canada", "dispersion",
]

# Domain display labels: (en, zh)
DOMAIN_LABELS: dict[str, tuple[str, str]] = {
    "us":           ("US Regime",            "美国周期"),
    "market":       ("Market State",         "市场状态"),
    "transmission": ("Rates Transmission",   "利率传导"),
    "fx":           ("FX / Dollar",          "外汇 / 美元"),
    "bonds":        ("Bonds & Credit",       "债券与信用"),
    "commodity":    ("Commodities",          "大宗商品"),
    "china":        ("China",                "中国"),
    "hk":           ("Hong Kong",            "香港"),
    "canada":       ("Canada",               "加拿大"),
    "dispersion":   ("Dispersion",           "离散度"),
}

# Field-level labels: (en, zh) for fields not in the LEX
FIELD_LABELS: dict[str, tuple[str, str]] = {
    "us_quad":              ("Quadrant",           "象限"),
    "us_transition_state":  ("Transition",         "转换状态"),
    "us_fused_risk":        ("Fused Risk",         "融合风险"),
    "us_vol_regime":        ("Vol Regime",         "波动率周期"),
    "us_risk_radar":        ("Risk Radar",         "风险雷达"),
    "us_rate_pressure":     ("Rate Pressure",      "利率压力"),
    "cross_asset_verdict":  ("Cross-Asset",        "跨资产"),
    "market_state_verdict": ("Verdict",            "判定"),
    "yield_curve_regime":   ("Curve Regime",       "曲线周期"),
    "recession_risk":       ("Recession Risk",     "衰退风险"),
    "usd_trend":            ("USD Trend",          "美元趋势"),
    "usd_regime":           ("USD Regime",         "美元周期"),
    "fx_risk":              ("FX Risk",            "外汇风险"),
    "real_rate_regime":     ("Real Rates",         "实际利率"),
    "fx_liquidity_dir":     ("Liquidity",          "流动性"),
    "bond_health_label":    ("Bond Health",        "债券健康"),
    "bond_cycle_phase":     ("Cycle Phase",        "周期阶段"),
    "commodity_regime":     ("Regime",             "周期"),
    "commodity_favored":    ("Favored",            "偏好"),
    "china_quad":           ("Quadrant",           "象限"),
    "hk_quad":              ("Quadrant",           "象限"),
    "hk_risk_state":        ("Risk State",         "风险状态"),
    "canada_quad":          ("Quadrant",           "象限"),
    "dispersion_state":     ("State",              "状态"),
}

# Verdict chip colors for common verdict values
_CHIP_COLOR: dict[str, str] = {
    # quads
    "Q1": C["green"], "Q2": C["amber"], "Q3": C["red"], "Q4": C["indigo"],
    # risk states
    "risk-on": C["green"], "risk-off": C["red"], "Risk-on": C["green"], "Risk-off": C["red"],
    "RISK_OFF": C["red"], "RISK_ON": C["green"],
    # curves
    "bull_flattener": C["teal"], "bull_steepener": C["green"],
    "bear_steepener": C["amber"], "bear_flattener": C["red"],
    # recession risk
    "low": C["green"], "mid": C["amber"], "high": C["red"],
    # bond health
    "healthy": C["green"], "mixed": C["amber"], "stressed": C["red"],
    # transmission states
    "headwind": C["red"], "tailwind": C["green"], "neutral": C["muted"],
    "diverge": C["amber"],
    # trends
    "up": C["green"], "down": C["red"], "flat": C["muted"],
    # dispersion
    "lean_in": C["green"], "diversified": C["blue"], "concentrated": C["amber"],
    # general
    "caution": C["amber"], "normalizing": C["teal"],
    "Restrictive real yields": C["red"],
    "Goldilocks": C["green"],
    "US growth premium": C["blue"],
    "Reflation": C["amber"],
    "soft": C["teal"],
}


def _chip_color(val: str | None) -> str:
    if val is None:
        return C["faint"]
    return _CHIP_COLOR.get(str(val), C["blue"])


def _stale_class(source_asof: str | None, today: str) -> str:
    """Return CSS class for staleness badge based on days-old."""
    if not source_asof:
        return "stale-warn"
    try:
        delta = (date.fromisoformat(today) - date.fromisoformat(source_asof)).days
    except Exception:
        return "stale-warn"
    if delta <= _STALE_WARN_DAYS:
        return "stale-ok"
    if delta <= _STALE_OLD_DAYS:
        return "stale-warn"
    return "stale-old"


def _load_json(path: Path) -> dict | None:
    """Load JSON fail-open; returns None on any error."""
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s: %s", path, exc)
        return None


def _load_transitions(path: Path, n: int = 30) -> list[dict]:
    """Load last n rows of transitions.jsonl, newest first.  Fail-open."""
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        lines = path.read_text().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
            if len(rows) >= n:
                break
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read transitions.jsonl: %s", exc)
    return rows


def _build_weather_board(snapshot: dict | None, today: str) -> list[dict]:
    """Build domain-grouped chip rows for the weather board."""
    if not snapshot:
        return []
    labels = snapshot.get("labels", {})
    sources = snapshot.get("sources", {})

    # Build a domain -> source_asof map from sources keys
    _domain_asof: dict[str, str] = {}
    for src_path, src_asof in sources.items():
        # map source path fragments to domains
        for domain, fragments in {
            "us": ["regime/latest"],
            "market": ["market_state"],
            "transmission": ["transmission"],
            "fx": ["forex"],
            "bonds": ["bond_health"],
            "commodity": ["commodity"],
            "china": ["china_regime"],
            "hk": ["hk_regime"],
            "canada": ["canada_regime"],
            "dispersion": ["dispersion"],
        }.items():
            if any(f in src_path for f in fragments):
                if domain not in _domain_asof or (src_asof or "") > _domain_asof.get(domain, ""):
                    _domain_asof[domain] = src_asof or ""

    board: list[dict] = []
    for domain in DOMAIN_ORDER:
        domain_labels = labels.get(domain, {})
        if not domain_labels:
            continue
        domain_en, domain_zh = DOMAIN_LABELS.get(domain, (domain.upper(), domain.upper()))
        src_asof = _domain_asof.get(domain)
        stale_cls = _stale_class(src_asof, today)
        chips: list[dict] = []
        for field, val in domain_labels.items():
            field_en, field_zh = FIELD_LABELS.get(field, (field, field))
            val_str = str(val) if val is not None else "—"
            # Render list values (e.g. commodity_favored) as comma-joined string
            if isinstance(val, list):
                val_str = ", ".join(str(v) for v in val)
            chips.append({
                "field": field,
                "field_en": field_en,
                "field_zh": field_zh,
                "val": val_str,
                "color": _chip_color(val_str if not isinstance(val, list) else None),
                "null": val is None,
            })
        board.append({
            "domain": domain,
            "domain_en": domain_en,
            "domain_zh": domain_zh,
            "asof": src_asof or "",
            "stale_cls": stale_cls,
            "chips": chips,
        })
    return board


def _build_headwind_tailwind(world_state: dict | None) -> dict:
    """Extract headwind/tailwind matrix from world_state lobes."""
    rt = (world_state or {}).get("rates_transmission", {})
    fx = (world_state or {}).get("fx_dollar", {})
    return {
        "rates": {
            "headwinds": rt.get("headwinds", []),
            "tailwinds": rt.get("tailwinds", []),
            "asof": rt.get("asof"),
            "state": rt.get("state", {}),
        },
        "fx": {
            "headwind_for": (fx.get("transmission") or {}).get("headwind_for", []),
            "tailwind_for": (fx.get("transmission") or {}).get("tailwind_for", []),
            "asof": fx.get("asof"),
            "trend": (fx.get("dollar_desk") or {}).get("trend"),
        },
    }


def _build_contradiction_census(world_state: dict | None) -> dict:
    """Contradiction census from world_state contradictions + intelligence lobes."""
    contradictions = (world_state or {}).get("contradictions", {})
    intelligence = (world_state or {}).get("intelligence", {})
    ca_lobe = (world_state or {}).get("rates_transmission", {})
    # cross_asset_verdict from snapshot-level world state
    ca_verdict_raw = (world_state or {}).get("verdict", {})
    ca_verdict = ca_verdict_raw.get("cross_asset", {}).get("verdict") if isinstance(ca_verdict_raw, dict) else None
    return {
        "n_contradictions": contradictions.get("n", 0),
        "top_pairs": contradictions.get("top_pair_ids", []),
        "n_divergences": intelligence.get("n_divergences"),
        "cross_asset_verdict": ca_verdict,
    }


def _build_view_model(
    snapshot: dict | None,
    world_state: dict | None,
    transitions: list[dict],
    today: str,
) -> dict:
    """Build the complete view-model for the template."""
    macro_context_id = (snapshot or {}).get("macro_context_id", "")
    asof = (snapshot or {}).get("asof", today)
    n_transitions_14d = 0
    if transitions:
        cutoff = ""
        try:
            from datetime import timedelta
            cutoff = (date.fromisoformat(today) - timedelta(days=14)).isoformat()
        except Exception:
            pass
        n_transitions_14d = sum(
            1 for t in transitions if t.get("asof", "") >= cutoff
        )

    weather_board = _build_weather_board(snapshot, today)
    headwind_tailwind = _build_headwind_tailwind(world_state)
    contradiction_census = _build_contradiction_census(world_state)

    # Derive a simple headline from dominant labels
    labels = (snapshot or {}).get("labels", {})
    us_quad = labels.get("us", {}).get("us_quad", "")
    usd_trend = labels.get("fx", {}).get("usd_trend", "")
    bond_health = labels.get("bonds", {}).get("bond_health_label", "")
    headline_en = (
        f"US {us_quad} · USD {usd_trend} · Bonds {bond_health}"
        if (us_quad or usd_trend or bond_health) else "Macro context loading"
    )
    # LEX has canonical Chinese for trend/health words; quads (Q1..Q4) stay as-is.
    from engine.i18n import tr as _tr  # noqa: PLC0415

    _zh_trend = {"up": "上行", "down": "下行", "flat": "走平"}.get(str(usd_trend)) or _tr(str(usd_trend)) or usd_trend
    _zh_health = {"healthy": "健康", "stressed": "承压", "deteriorating": "恶化"}.get(str(bond_health)) or _tr(
        str(bond_health)
    ) or bond_health
    headline_zh = (
        f"美国{us_quad} · 美元{_zh_trend} · 债券{_zh_health}"
        if (us_quad or usd_trend or bond_health) else "宏观背景加载中"
    )

    return {
        "asof": asof,
        "today": today,
        "macro_context_id": macro_context_id,
        "n_transitions_14d": n_transitions_14d,
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "weather_board": weather_board,
        "headwind_tailwind": headwind_tailwind,
        "transitions": transitions,
        "contradiction_census": contradiction_census,
        "snapshot_present": snapshot is not None,
        "world_state_present": world_state is not None,
    }


def main() -> int:
    root = config.ROOT
    data_dir = config.data_dir()
    today = date.today().isoformat()
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- load sources (all fail-open) ---
    snapshot = _load_json(data_dir / "macro_snapshots" / "latest.json")
    world_state = _load_json(data_dir / "neuralweb" / "world_state.json")
    transitions = _load_transitions(data_dir / "macro_snapshots" / "transitions.jsonl", n=30)

    if snapshot is None:
        log.warning("macro_snapshots/latest.json missing — rendering empty-state page")
    if world_state is None:
        log.warning("neuralweb/world_state.json missing — headwind/tailwind matrix will be empty")

    vm = _build_view_model(snapshot, world_state, transitions, today)

    # --- render template ---
    from engine.i18n import tr, td  # noqa: E402
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")), autoescape=True
    )
    env.globals.update(tr=tr, td=td)
    html = env.get_template("macro_context.html.j2").render(
        C=C,
        vm=vm,
        built=built,
        today=today,
    )

    site = root / config.load()["storage"]["site_dir"]
    write_page(site / "macro_context.html", html)
    log.info("wrote %s/macro_context.html (%d KB)", site, len(html) // 1024)

    # --- hub contract ---
    hub_dir = data_dir / "macro_context"
    hub_dir.mkdir(parents=True, exist_ok=True)
    hub = {
        "asof": vm["asof"],
        "macro_context_id": vm["macro_context_id"],
        "n_transitions_14d": vm["n_transitions_14d"],
        "headline_en": vm["headline_en"],
        "headline_zh": vm["headline_zh"],
    }
    (hub_dir / "latest.json").write_text(
        json.dumps(hub, indent=2, ensure_ascii=False)
    )
    log.info("wrote data/macro_context/latest.json — id=%s", vm["macro_context_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
