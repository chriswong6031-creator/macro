"""Build site/rr_banner.json — the Risk-Radar EXTREME alert tape payload.

Sibling of the White House alert (scripts/build_whitehouse.py → site/wh_banner.json).
The SAME client script (templates/wh_banner.js) hosts both channels: it fetches
wh_banner.json AND rr_banner.json and, when both are live, alternates the one 42px
top bar between them.

This alert is deliberately RARE. It fires only when the Risk Radar reaches its
worst, gate-confirmed band — the "if you're still in, you gotta get out" moment —
NOT every time the radar is merely elevated. Concretely: the GATED state (the one
the card displays) must reach ``risk-off``. That gate matters: engine/risk_radar.py
caps the displayed state at ``caution`` until price action confirms (SPY < 200-day
or breadth weak), so a raw score in the risk-off zone that the market hasn't yet
confirmed does NOT shout. Reading the ungated state here would cry wolf.

Payload is display-derived from the same fields the Risk Radar card shows, so the
banner never originates a signal — it only re-flashes what the calibrated engine
already published (house law: LLMs/builders may de-escalate, never originate).

Degrade-silent: no radar snapshot, or state below the threshold → alert:null (the
client renders nothing). Never raises; a failure just skips the artifact.

Run standalone:  python -m scripts.build_rr_banner
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("build_rr_banner")

# The gated state at/above which the extreme alert fires. risk_radar.py bands:
# calm<55, watch 55, caution 68, elevated 78, risk-off 88 — "risk-off" is the top.
# This is intentionally STRICTER than the engine's own loud alert (which fires from
# "elevated"): this banner is the get-out-now tier, not the general warning tier.
RR_ALERT_FROM = "risk-off"

# Plain-English names for raw radar firing-leg codes — ported VERBATIM from the
# rr_leg() macro in templates/_risk_radar_card.html.j2 so the banner evidence reads
# identically to the card. (en, zh).
_LEG_NAMES: dict[str, tuple[str, str]] = {
    "credit_oas_roc":    ("HY credit spreads widening", "高收益利差走阔"),
    "credit_hyg_tlt":    ("HY bonds lagging Treasuries", "高收益债跑输国债"),
    "rates_move":        ("Bond-market volatility (MOVE)", "债市波动率（MOVE）"),
    "rates_realrate":    ("Real yields jumping", "实际利率跳升"),
    "bubble_ext":        ("S&P stretched vs 200-day", "标普超买（>200日线）"),
    "bubble_leadership": ("Narrow leadership (semis)", "领涨过窄（半导体）"),
    "growth_defensives": ("Defensives outperforming", "防御股跑赢"),
    "growth_cyc_def":    ("Cyclicals fading vs defensives", "周期股弱于防御"),
    "vol_term":          ("VIX term-structure stress", "VIX 期限结构紧张"),
    "vol_putcall":       ("Put/call skew", "认沽/认购偏斜"),
    "vol_gex":           ("Dealer gamma (GEX)", "做市商 Gamma"),
    "global_breadth":    ("Global breadth < 200-day (C3)", "全球广度跌破200日（C3）"),
    "us_rate_2y":        ("US 2-year yield jump", "美债2年利率跳升"),
    "us_rate_10y":       ("US 10-year yield jump", "美债10年利率跳升"),
    "us_real_rate":      ("US real yield jump", "美债实际利率跳升"),
    "us_cn_diff":        ("US–China yield gap widening", "中美利差走阔"),
    "usd_cnh":           ("Yuan depreciation (USD/CNH)", "人民币贬值"),
    "usd_strength":      ("US dollar strength", "美元走强"),
    "cn_breadth":        ("A-share breadth < 200-day", "A股广度跌破200日"),
    "ca_breadth":        ("TSX breadth < 200-day", "多指广度跌破200日"),
}


def _pct(x, default=None):
    """0..1 probability → integer percent (None-safe)."""
    try:
        return round(float(x) * 100)
    except (TypeError, ValueError):
        return default


def _round1(x):
    try:
        return round(float(x), 1)
    except (TypeError, ValueError):
        return None


def build_alert(rr: dict) -> dict | None:
    """Return the alert record for rr_banner.json, or None when the radar is below
    the extreme threshold / the snapshot is unusable."""
    if not isinstance(rr, dict):
        return None
    if rr.get("state") != RR_ALERT_FROM:  # gated state — see module docstring
        return None

    scares = [s for s in (rr.get("scares") or []) if isinstance(s, dict)]
    dom_label = rr.get("dominant_label_en")
    dom = next((s for s in scares if s.get("label_en") == dom_label), None)

    # WHY it's amplified (1): the dominant scare's leading firing legs, plain-English.
    reasons = []
    for leg in ((dom or {}).get("firing_legs") or [])[:3]:
        code = leg.get("leg")
        en, zh = _LEG_NAMES.get(code, (code, code))
        reasons.append({
            "en": en, "zh": zh,
            "pctile": _pct(leg.get("pctile")),
            "confirmed": bool(leg.get("confirmed")),
        })

    # WHY it's amplified (2): OTHER scares also firing hot (elevated/risk-off band) —
    # the co-firing threats that turned a single scare into a broad get-out signal.
    amplifiers = [
        {"en": s.get("label_en"), "zh": s.get("label_zh") or s.get("label_en"),
         "score": round(s["score"]) if s.get("score") is not None else None}
        for s in scares
        if s.get("label_en") != dom_label
        and s.get("band") in ("elevated", "risk-off")
        and s.get("score") is not None
    ]

    dp = rr.get("drawdown_prob") or {}
    ramp = [
        {"h_en": "5d", "h_zh": "5日", "pct": _pct(dp.get("h5"))},
        {"h_en": "10d", "h_zh": "10日", "pct": _pct(dp.get("h10"))},
        {"h_en": "21d", "h_zh": "21日", "pct": _pct(dp.get("h21"))},
    ]
    ramp = [r for r in ramp if r["pct"] is not None]

    # conjunction_n = how many scares fired together (the engine's own amplification
    # count); fall back to the co-firing tally so the "N threats" chip is honest.
    conj_n = dp.get("conjunction_n")
    if not isinstance(conj_n, int):
        conj_n = 1 + len(amplifiers)

    score = rr.get("top_score")
    dom_en = rr.get("dominant_label_en") or "broad risk-off"
    dom_zh = rr.get("dominant_label_zh") or "全面风险规避"
    # Lead the headline with the get-out framing, then the dominant scare, so the tape
    # reads "EXTREME RISK-OFF · <driver>" rather than a bare engine label.
    return {
        # dismissal signature: re-opens the bar only when the state OR the day changes
        "id": f"rr-{rr.get('asof', '')}-{rr.get('state')}",
        "state": rr.get("state"),
        "score": round(score) if score is not None else None,
        "href": "macro.html",
        "headline_en": f"EXTREME RISK-OFF · {dom_en}",
        "headline_zh": f"极端风险规避 · {dom_zh}",
        # "how much the market is projected to fall" — the radar measures the
        # probability of a >=5% SPY pullback; >=5% is the fixed threshold it scores
        # (engine drawdown_prob.measure), so we flash >=5% as the magnitude.
        "odds_pct": _pct(dp.get("h21")),
        "lift": _round1(dp.get("lift_h21")),
        "base_pct": _pct(dp.get("base_h21")),
        "ramp": ramp,
        "reasons": reasons,
        "amplifiers": amplifiers,
        "conjunction_n": conj_n,
    }


def build(site_dir: Path | None = None) -> Path:
    """Read the live radar snapshot and (re)write site/rr_banner.json. Returns the
    path written. Never raises — on any failure it writes an inert alert:null so a
    stale extreme banner can never linger."""
    if site_dir is None:
        site_dir = config.ROOT / config.load()["storage"]["site_dir"]
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    out = site_dir / "rr_banner.json"

    alert = None
    asof = None
    try:
        latest = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        rr = latest.get("risk_radar")
        if isinstance(rr, dict):
            asof = rr.get("asof")
            alert = build_alert(rr)
    except Exception as e:  # noqa: BLE001
        log.warning("rr_banner: could not read radar snapshot (%s) — writing inert", e)

    payload = {
        "schema": "rr_banner.v1",
        "asof": asof,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alert": alert,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    log.info("rr_banner.json written (alert=%s)", "yes" if alert else "none")
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
