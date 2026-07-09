"""Build the Policy-Lever ARMED/QUIET card artifact.

Writes site/policy_lever.json — consumed by scripts/build_site.py
for the US market-state surface (dashboard.html.j2, mode=stocks).

Artifact schema (Policy-Shock W2-F, masterplan §4):

    policy_lever = {
      "schema": "policy_lever.v1",
      "as_of": "YYYY-MM-DD",
      "favored_complex": {
        "basket": ["SMH", "SOXX"],
        "drawdown_pct": float,     # trailing-120d peak drawdown %
        "drawdown_z": float | None,
        "note": str,               # unsigned EN display copy
        "note_zh": str,
      },
      "jawboning": {
        "n_7d": int | None,
        "n_30d": int | None,
        "last_alert_ts": str | None,
        "last_alert_summary": str | None,   # ~140 chars
      },
      "calendar": {
        "days_to_midterm": int,
        "context_note": str,
        "context_note_zh": str,
      },
      "levers": [
        {
          "name": str,
          "name_zh": str,
          "asset": str | None,
          "arming": dict | None,   # technical_arming block from engine/commodity_signals.py
          "watch": str,            # unsigned qualitative EN
          "watch_zh": str,
        }
      ],
      "state": "QUIET" | "ELEVATED" | "ARMED",
      "framing": str,
      "framing_zh": str,
    }

ARMED rule (frozen v1, PS-R9):
  favored_complex.drawdown_pct <= -15%  AND  any lever.arming.armed  → ARMED
  exactly ONE of the two conditions                                   → ELEVATED
  neither                                                             → QUIET

PS-R1: The word "intent" must not appear in card copy.
PS-R4: No probabilities anywhere.
PS-R7: Site artifact only (site/policy_lever.json). No data/ ledger.

Usage:
    python -m scripts.build_policy_lever
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_policy_lever")

# ---------------------------------------------------------------------------
# Constants (frozen v1 per PS-R9)
# ---------------------------------------------------------------------------
_MIDTERM_DATE = datetime(2026, 11, 3, tzinfo=timezone.utc)
_DRAWDOWN_THRESHOLD = -0.15          # -15% triggers the drawdown leg
_DRAWDOWN_WINDOW_D = 120             # trailing days for peak-to-current
_DRAWDOWN_ZSCORE_WINDOW_D = 252      # history for z-score normalisation
_JAWBONE_7D_WINDOW = 7
_JAWBONE_30D_WINDOW = 30
_LAST_ALERT_SUMMARY_LEN = 140


# ---------------------------------------------------------------------------
# Framing copy (PS-R1: no "intent"; PS-R4: no probabilities)
# ---------------------------------------------------------------------------
_FRAMING_EN = (
    "Conditions under which violent reversals are more likely — not intent, not timing."
)
_FRAMING_ZH = (
    "衡量剧烈反转更可能发生的条件——不是意图，也不是时点。"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_price(ticker: str) -> pd.DataFrame | None:
    """Load daily close from the committed yahoo store (same path as commodity_inputs).

    Synthesises open/high/low from close so the commodity_signals functions work.
    Returns None (never raises) if the store is absent.
    """
    try:
        df = store.read("yahoo", ticker)
        if df is None or df.empty:
            log.warning("price store absent for %s", ticker)
            return None
        px = df.rename(columns=str.lower).copy()
        px.index = pd.to_datetime(px.index).normalize()
        px = px[~px.index.duplicated(keep="last")].sort_index().dropna(subset=["close"])
        for c in ("open", "high", "low"):
            if c not in px.columns:
                px[c] = px["close"]
        keep = ["open", "high", "low", "close"] + (["volume"] if "volume" in px.columns else [])
        return px[keep]
    except Exception as e:  # noqa: BLE001
        log.warning("load_price(%s) failed: %s", ticker, e)
        return None


def _compute_drawdown(tickers: list[str]) -> dict:
    """Equal-weight composite drawdown (trailing-120d peak) for a basket of tickers.

    Returns a dict with keys: drawdown_pct (float), drawdown_z (float | None),
    as_of (str), note (EN), note_zh (ZH).
    """
    series: list[pd.Series] = []
    for t in tickers:
        px = _load_price(t)
        if px is not None and not px.empty:
            series.append(px["close"].rename(t))

    if not series:
        return {
            "basket": tickers,
            "drawdown_pct": None,
            "drawdown_z": None,
            "as_of": None,
            "note": "Price data unavailable — drawdown not computed.",
            "note_zh": "价格数据不可用，回撤未计算。",
        }

    # align, fill forward, equal-weight composite
    aligned = pd.concat(series, axis=1).sort_index().ffill().dropna(how="all")
    composite = aligned.mean(axis=1)

    # trailing-120d drawdown
    trail_120 = composite.tail(_DRAWDOWN_WINDOW_D + 1)  # +1 for safety
    if len(trail_120) < 10:
        return {
            "basket": tickers,
            "drawdown_pct": None,
            "drawdown_z": None,
            "as_of": str(composite.index[-1].date()) if len(composite) else None,
            "note": "Insufficient price history for drawdown.",
            "note_zh": "价格历史数据不足，无法计算回撤。",
        }

    peak = float(trail_120.max())
    current = float(composite.iloc[-1])
    dd_pct = round((current / peak - 1) * 100, 2) if peak != 0 else None
    as_of = str(composite.index[-1].date())

    # z-score vs trailing 252d distribution of same rolling window
    dd_z: float | None = None
    try:
        hist_close = composite.tail(_DRAWDOWN_ZSCORE_WINDOW_D + _DRAWDOWN_WINDOW_D)
        rolling_peak = hist_close.rolling(_DRAWDOWN_WINDOW_D, min_periods=60).max()
        dd_series = (hist_close / rolling_peak - 1).dropna()
        if len(dd_series) >= 20:
            mean = float(dd_series.mean())
            std = float(dd_series.std())
            dd_current = float(dd_series.iloc[-1])
            dd_z = round((dd_current - mean) / std, 2) if std > 0 else None
    except Exception:  # noqa: BLE001
        pass

    # display note (unsigned, no probabilities, no "intent")
    dd_str = f"{dd_pct:+.1f}%" if dd_pct is not None else "N/A"
    note = (
        f"Semis complex (SMH/SOXX equal-weight) is {dd_str} from the "
        f"trailing-120-day peak. Depth of the drawdown is the structural "
        f"context for rotation-reversal conditions."
    )
    note_zh = (
        f"半导体组合（SMH/SOXX等权）距过去120日高点{dd_str}。"
        f"回撤深度是轮动反转条件的结构性背景。"
    )

    return {
        "basket": tickers,
        "drawdown_pct": dd_pct,
        "drawdown_z": dd_z,
        "as_of": as_of,
        "note": note,
        "note_zh": note_zh,
    }


def _compute_oil_arming() -> dict | None:
    """Run technical_arming on CL=F (crude oil futures) via the SAME engine path
    that build_commodities.py uses — do not reimplement.

    Returns None if price data or config is unavailable.
    """
    try:
        from engine import commodity_signals
        cfg = config.load()["commodities"]
        px = _load_price("CL=F")
        if px is None or px.empty:
            return None
        return commodity_signals.technical_arming(px, cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("oil arming computation failed: %s", e)
        return None


def _compute_jawboning(alerts_path: Path) -> dict:
    """Read data/whitehouse/alerts.jsonl (READ-ONLY — sentinel is the single writer).

    Returns jawboning counts for 7d/30d windows plus the most recent alert summary.
    Degrades gracefully to nulls when the file is absent or corrupted.
    """
    null_result = {
        "n_7d": None,
        "n_30d": None,
        "last_alert_ts": None,
        "last_alert_summary": None,
        "_note": "whitehouse/alerts.jsonl absent — jawboning unavailable",
    }

    if not alerts_path.exists():
        log.info("whitehouse alerts file absent — jawboning nulls")
        return null_result

    try:
        lines = alerts_path.read_text(encoding="utf-8").splitlines()
        alerts = [json.loads(l) for l in lines if l.strip()]
    except Exception as e:  # noqa: BLE001
        log.warning("whitehouse alerts parse failed: %s", e)
        return {**null_result, "_note": f"parse error: {e}"}

    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=_JAWBONE_7D_WINDOW)
    cutoff_30d = now - timedelta(days=_JAWBONE_30D_WINDOW)

    n_7d = 0
    n_30d = 0
    last_alert = None
    last_ts: datetime | None = None

    for a in alerts:
        raw_pub = a.get("published") or a.get("generated_at", "")
        if not raw_pub:
            continue
        try:
            pub = datetime.fromisoformat(raw_pub)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if pub >= cutoff_7d:
            n_7d += 1
        if pub >= cutoff_30d:
            n_30d += 1

        if last_ts is None or pub > last_ts:
            last_ts = pub
            last_alert = a

    last_alert_ts: str | None = None
    last_alert_summary: str | None = None
    if last_alert is not None:
        last_alert_ts = last_alert.get("published") or last_alert.get("generated_at")
        # Prefer the short banner_title; fall back to summary[:140]
        raw_summary = last_alert.get("banner_title") or last_alert.get("summary") or ""
        last_alert_summary = raw_summary[:_LAST_ALERT_SUMMARY_LEN] if raw_summary else None

    return {
        "n_7d": n_7d,
        "n_30d": n_30d,
        "last_alert_ts": last_alert_ts,
        "last_alert_summary": last_alert_summary,
    }


def _compute_calendar() -> dict:
    """Days to 2026-11-03 midterms + unsigned display context (no signal language)."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days = max(0, (_MIDTERM_DATE - today).days)
    context_note = (
        f"US midterm elections: {days} days (2026-11-03). "
        f"Policy cycle context only — no directional read."
    )
    context_note_zh = (
        f"美国中期选举：{days}天（2026年11月3日）。"
        f"仅作政策周期背景参考，不作方向性判断。"
    )
    return {
        "days_to_midterm": days,
        "context_note": context_note,
        "context_note_zh": context_note_zh,
    }


def _build_levers(oil_arming: dict | None) -> list[dict]:
    """Build the levers array.

    Lever 1: Iran / oil (CL=F) — uses the W1-B arming block.
    Lever 2: China / tariffs — no technical asset; qualitative only.

    watch copy: unsigned factual text (PS-R1 no "intent"; PS-R4 no probabilities).
    """
    return [
        {
            "name": "Iran / oil",
            "name_zh": "伊朗/石油",
            "asset": "CL=F",
            "arming": oil_arming,
            "watch": (
                "Re-escalation risk restated by 2026-07-08 strike developments; "
                "oil is the transmission lever to rate-cut repricing. "
                "A rapid CL=F spike would widen breakevens and reprice fed-funds futures, "
                "reversing the conditions that have supported the semis recovery."
            ),
            "watch_zh": (
                "2026年7月8日打击事件重申了再升级风险；"
                "石油是向降息重定价传导的核心杠杆。"
                "CL=F快速飙升将扩大盈亏平衡通胀预期并重定价联邦基金期货，"
                "逆转支撑半导体复苏的现有条件。"
            ),
        },
        {
            "name": "China / tariffs",
            "name_zh": "中国/关税",
            "asset": None,
            "arming": None,
            "watch": (
                "Tariff truce fragility: any rollback of the 90-day pause or "
                "re-escalation in export controls would directly compress the "
                "semis supply chain margins that are priced into the current recovery."
            ),
            "watch_zh": (
                "关税休战的脆弱性：90天暂停期内任何回退"
                "或出口管制再升级，将直接压缩已计入当前复苏预期的"
                "半导体供应链利润率。"
            ),
        },
    ]


def _compute_state(drawdown_pct: float | None, levers: list[dict]) -> str:
    """ARMED rule (frozen v1, PS-R9).

    favored_complex.drawdown_pct <= -15%  AND  any lever.arming.armed  → ARMED
    exactly ONE of the two conditions                                   → ELEVATED
    neither                                                             → QUIET
    """
    dd_armed = (drawdown_pct is not None) and (drawdown_pct <= _DRAWDOWN_THRESHOLD * 100)
    lever_armed = any(
        (lv.get("arming") or {}).get("armed", False) for lv in levers
    )
    if dd_armed and lever_armed:
        return "ARMED"
    if dd_armed or lever_armed:
        return "ELEVATED"
    return "QUIET"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build() -> dict:
    """Assemble the full policy_lever artifact. Returns the dict."""
    root = config.ROOT
    alerts_path = root / "data" / "whitehouse" / "alerts.jsonl"

    # 1. favored complex drawdown
    log.info("computing favored-complex drawdown (SMH/SOXX)…")
    fc = _compute_drawdown(["SMH", "SOXX"])

    # 2. oil arming (W1-B engine path — same config as build_commodities)
    log.info("computing oil arming (CL=F technical_arming)…")
    oil_arming = _compute_oil_arming()

    # 3. jawboning
    log.info("reading whitehouse alerts (read-only)…")
    jawboning = _compute_jawboning(alerts_path)

    # 4. calendar
    calendar = _compute_calendar()

    # 5. levers
    levers = _build_levers(oil_arming)

    # 6. state
    state = _compute_state(fc.get("drawdown_pct"), levers)

    as_of = fc.get("as_of") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    artifact = {
        "schema": "policy_lever.v1",
        "as_of": as_of,
        "favored_complex": fc,
        "jawboning": jawboning,
        "calendar": calendar,
        "levers": levers,
        "state": state,
        "framing": _FRAMING_EN,
        "framing_zh": _FRAMING_ZH,
    }
    return artifact


def main() -> int:
    """Build and write site/policy_lever.json. Returns 0 on success, 0 on non-fatal failure."""
    try:
        artifact = build()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("build_policy_lever failed (%s) — skipping site artifact", e)
        return 0

    # Write to site/policy_lever.json (atomic via temp file)
    root = config.ROOT
    cfg = config.load()
    site_dir_name = cfg.get("storage", {}).get("site_dir", "site")
    site_dir = root / site_dir_name
    site_dir.mkdir(parents=True, exist_ok=True)
    out = site_dir / "policy_lever.json"

    try:
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
        tmp.replace(out)
        log.info("wrote %s  (state=%s)", out, artifact.get("state"))
    except Exception as e:  # noqa: BLE001
        log.error("failed to write %s: %s", out, e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
