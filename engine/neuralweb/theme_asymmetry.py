"""engine.neuralweb.theme_asymmetry — TIL W3 Per-Leg Asymmetry Panel.

Display/context tier only. Authority block: is_context_only=True, all promotion
flags False. Never raises; missing input → honest null leg + stale_legs entry.

Seven INDEPENDENT legs, each:
  {value: float|null, band: low|med|high|null,
   inputs: [artifact:field...], stale: bool, note_en: str, note_zh: str}

NO composite / master / rank / score / total at theme level (WA-R1 / R-TIL-3).
The panel IS the product.

Public API
----------
run_stage(root: Path) -> None
    Entry point auto-discovered by scripts/build_thematic_state.py.
    Writes data/neuralweb/theme_asymmetry.json + site projection.

compose_asymmetry(root: Path) -> dict
    Returns the schema neuralweb.theme_asymmetry.v1 dict. Never raises.

Leg sources
-----------
a. bottleneck_tightness — foresight_cascade.json bottleneck_band +
   radar.json flags observable.accel (theme-activity acceleration).
b. stale_consensus_gap — foresight_cascade revision_level/revision_breadth
   (analyst revision trajectory/breadth) crossed against demand_band
   (activity direction). Finnhub recommendation.parquet gives per-member
   revision dispersion when available; absent → honest null for dispersion.
c. cyclical_dislocation — theme_intel textures.bull_age.drawdown_from_peak
   vs accel_z (RS trend divergence).
d. entry_cleanliness — theme_intel textures.clean_entry + textures.overbought
   + narrative_emergence hype.stretched_share.
e. crowding_hazard — theme_intel components.crowding + divergence_log
   quadrant (hype-risk = crowding flag). HAZARD framing only (NEXTL-U13).
f. falsifier_clarity — data/neuralweb/theme_thesis_ledger.jsonl (W1;
   absent → null leg + stale note "thesis ledger pending W1").
g. orthogonality — covariance_spine dispersion.avg_corr (universe level) +
   theme_intel perf.60d.rel (basket's 60-day alpha vs SPY).
"""
from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema / authority constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.theme_asymmetry.v1"

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "display",
    "forbidden_uses": [
        "ranking",
        "sizing",
        "alert_escalation",
        "board_ordering",
        "mastermind_arming",
        "scored_path",
        "composite_score",
    ],
}

HARD_CAVEAT = (
    "not a buy score; no behavior-changing consumer"
)

# ---------------------------------------------------------------------------
# Source paths (relative to repo root)
# ---------------------------------------------------------------------------

_CROSSWALK_PATH = "config/theme_crosswalk.yml"
_FORESIGHT_PATH = "site/basketdata/foresight_cascade.json"
_BASKETS_PATH = "site/basketdata/baskets.json"
_RADAR_PATH = "site/basketdata/radar.json"
_NARRATIVE_PATH = "site/basketdata/narrative_emergence.json"
_DIVERGENCE_LOG_PATH = "data/foresight/divergence_log.jsonl"
_COVARIANCE_PATH = "site/neuralwebdata/covariance_spine.json"
_THESIS_LEDGER_PATH = "data/neuralweb/theme_thesis_ledger.jsonl"
_FINNHUB_RECS_PATH = "data/finnhub/recommendation.parquet"

# Output paths
_DATA_OUT = "data/neuralweb/theme_asymmetry.json"
_SITE_OUT = "site/neuralwebdata/theme_asymmetry.json"

_STALE_DAYS = 5  # calendar days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _asof_today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _now_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_stale(val: Any) -> bool:
    if val is None:
        return True
    try:
        s = str(val).strip()[:10]
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - dt).days >= _STALE_DAYS
    except Exception:  # noqa: BLE001
        return True


def _load_json(path: Path, label: str) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, f"{label}: not found"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: parse error — {exc}"


def _load_yaml(path: Path, label: str) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, f"{label}: not found"
    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: parse error — {exc}"


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".tmp_{path.name}_", suffix=".json", delete=False,
    ) as tf:
        tf.write(text)
        tmp = Path(tf.name)
    tmp.replace(path)


def _null_leg(
    inputs: list[str],
    stale: bool = True,
    note_en: str = "source absent or unreadable",
    note_zh: str = "数据源缺失或不可读",
) -> dict:
    return {
        "value": None,
        "band": None,
        "inputs": inputs,
        "stale": stale,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _band_from_value(value: float, lo: float, hi: float) -> str:
    """Map a value to low/med/high given thresholds."""
    if value <= lo:
        return "low"
    if value >= hi:
        return "high"
    return "med"


# ---------------------------------------------------------------------------
# Source loaders
# ---------------------------------------------------------------------------

def _load_foresight(root: Path) -> tuple[dict, list[str]]:
    """Returns ({theme_id: rec}, stale_legs)."""
    data, err = _load_json(root / _FORESIGHT_PATH, "foresight_cascade")
    if err or data is None:
        return {}, [err or "foresight_cascade: empty"]
    stale: list[str] = []
    if _is_stale(data.get("asof")):
        stale.append(f"foresight_cascade: stale (as_of={data.get('asof')})")
    by_id = {t["theme"]: t for t in data.get("themes", []) if isinstance(t, dict) and "theme" in t}
    return by_id, stale


def _load_baskets_intel(root: Path) -> tuple[dict, list[str]]:
    """Returns ({basket_id: intel_rec}, stale_legs)."""
    data, err = _load_json(root / _BASKETS_PATH, "baskets")
    if err or data is None:
        return {}, [err or "baskets: empty"]
    stale: list[str] = []
    asof = data.get("as_of") or (data.get("theme_intel") or {}).get("as_of")
    if _is_stale(asof):
        stale.append(f"baskets: stale (as_of={asof})")
    ti_themes = (data.get("theme_intel") or {}).get("themes", [])
    by_id = {t["id"]: t for t in ti_themes if isinstance(t, dict) and "id" in t}
    return by_id, stale


def _load_radar_flags(root: Path) -> tuple[dict, list[str]]:
    """Returns ({basket_id: flag_rec}, stale_legs)."""
    data, err = _load_json(root / _RADAR_PATH, "radar")
    if err or data is None:
        return {}, [err or "radar: empty"]
    stale: list[str] = []
    if _is_stale(data.get("as_of")):
        stale.append(f"radar: stale (as_of={data.get('as_of')})")
    by_id: dict = {}
    for flag in data.get("flags", []):
        if isinstance(flag, dict) and flag.get("basket"):
            by_id[flag["basket"]] = flag
    return by_id, stale


def _load_narrative(root: Path) -> tuple[dict, list[str]]:
    """Returns hype info keyed by basket member overlap.
    Returns ({basket_id_or_tag: hype_rec}, stale_legs).
    We aggregate hype.stretched_share across all narratives with basket_overlap > 0.
    """
    data, err = _load_json(root / _NARRATIVE_PATH, "narrative_emergence")
    if err or data is None:
        return {}, [err or "narrative_emergence: empty"]
    stale: list[str] = []
    if _is_stale(data.get("as_of")):
        stale.append(f"narrative_emergence: stale (as_of={data.get('as_of')})")
    # Collect max stretched_share across all narratives as a universe-level hype signal
    narratives = data.get("narratives", [])
    max_stretched: float = 0.0
    ipo_wave = False
    for n in narratives:
        if isinstance(n, dict):
            hype = n.get("hype") or {}
            stretched_share = hype.get("stretched_share") or 0.0
            if isinstance(stretched_share, (int, float)):
                max_stretched = max(max_stretched, float(stretched_share))
            if hype.get("ipo_wave"):
                ipo_wave = True
    return {"_universe": {"max_stretched_share": max_stretched, "ipo_wave": ipo_wave}}, stale


def _load_divergence_log(root: Path) -> tuple[dict, list[str]]:
    """Returns ({theme_id: latest_row}, stale_legs).
    Reads ALL quadrant rows (not just hidden-opportunity).
    """
    path = root / _DIVERGENCE_LOG_PATH
    if not path.exists():
        return {}, [f"divergence_log: not found"]
    latest: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            theme = row.get("theme")
            asof = row.get("asof")
            if not theme or not asof:
                continue
            existing = latest.get(theme)
            if existing is None or asof > existing.get("asof", ""):
                latest[theme] = row
    except Exception as exc:  # noqa: BLE001
        return {}, [f"divergence_log: read error — {exc}"]
    stale: list[str] = []
    for theme, row in latest.items():
        if _is_stale(row.get("asof")):
            stale.append(f"divergence_log[{theme}]: stale (as_of={row.get('asof')})")
    return latest, stale


def _load_covariance(root: Path) -> tuple[dict, list[str]]:
    """Returns covariance_spine dict, stale_legs."""
    data, err = _load_json(root / _COVARIANCE_PATH, "covariance_spine")
    if err or data is None:
        return {}, [err or "covariance_spine: empty"]
    stale: list[str] = []
    if _is_stale(data.get("as_of")):
        stale.append(f"covariance_spine: stale (as_of={data.get('as_of')})")
    return data, stale


def _load_thesis_ledger(root: Path) -> tuple[list[dict], list[str]]:
    """Returns (rows, stale_legs). Absent file → empty rows + stale note."""
    path = root / _THESIS_LEDGER_PATH
    if not path.exists():
        return [], ["thesis_ledger: pending W1 build (theme_thesis.py not yet present)"]
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        return [], [f"thesis_ledger: read error — {exc}"]
    return rows, []


def _load_finnhub_revisions(root: Path) -> tuple[dict, list[str]]:
    """Returns ({ticker: revision_info}, stale_legs). Absent parquet → empty."""
    path = root / _FINNHUB_RECS_PATH
    if not path.exists():
        return {}, ["finnhub_recs: parquet absent — per-member revision dispersion unavailable"]
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        need = {"ticker", "period", "strongBuy", "buy", "sell", "strongSell"}
        if not need <= set(df.columns):
            return {}, ["finnhub_recs: missing required columns"]
        from engine.analyst_revisions import revision_map
        return revision_map(df), []
    except Exception as exc:  # noqa: BLE001
        return {}, [f"finnhub_recs: error — {exc}"]


# ---------------------------------------------------------------------------
# Band thresholds (constants — inspect-based, display tier)
# ---------------------------------------------------------------------------

# Bottleneck tightness: accel >= 1.0 means activity is accelerating (YoY > 1x)
_ACCEL_HIGH = 1.2   # accel >= 1.2 → strong activity acceleration
_ACCEL_MED = 0.8    # accel >= 0.8 → moderate

# Stale consensus gap: revision_breadth >= 0.5 → majority upgrading
_REV_BREADTH_HIGH = 0.5
_REV_BREADTH_MED = 0.1
_REV_BREADTH_LOW = -0.1   # any negative → downgrading

# Cyclical dislocation: drawdown_from_peak as abs magnitude
_DRAWDOWN_HIGH = 0.25   # >25% from peak
_DRAWDOWN_MED = 0.10

# Entry cleanliness: clean_entry.quality 0-1; overbought.value 0-1
# High cleanliness = high quality + low overbought + low stretched_share
_CLEAN_HI = 0.65
_CLEAN_MED = 0.35

# Crowding: 0-1 from components.crowding
_CROWD_HIGH = 0.70
_CROWD_MED = 0.40

# Orthogonality: 60d relative return vs SPY
# High positive rel → theme is moving independently (orthogonal to market)
_ORTH_HIGH = 0.20    # +20% excess → high orthogonality
_ORTH_MED = -0.10    # < -10% → same direction as market or worse

# Falsifier clarity: share of falsifiers that are machine-checkable
_FALS_HIGH = 0.60
_FALS_MED = 0.30


# ---------------------------------------------------------------------------
# Per-leg computation functions (each takes pre-indexed dicts, returns leg dict)
# ---------------------------------------------------------------------------

def _leg_bottleneck_tightness(
    foresight_rec: dict | None,
    radar_flags_by_basket: dict,
    basket_ids: list[str],
    theme_id: str,
) -> dict:
    """Leg a: bottleneck_tightness.
    Sources: foresight_cascade.bottleneck_band (T1 FRED tightness) +
             radar.flags[basket].observable.accel (theme-activity acceleration).
    """
    inputs = [
        "foresight_cascade:bottleneck_band",
        "foresight_cascade:tightness",
        "radar:flags.observable.accel",
    ]

    if foresight_rec is None:
        return _null_leg(
            inputs, stale=True,
            note_en="foresight_cascade absent — bottleneck tightness unavailable",
            note_zh="未能读取 foresight_cascade — 瓶颈紧张度不可用",
        )

    bb = foresight_rec.get("bottleneck_band")  # e.g. "TIGHT (text)", "TIGHTENING (fingerprint)", None
    tightness_raw = foresight_rec.get("tightness")  # 0-1 float or None

    # Map bottleneck_band to a numeric 0-1 tightness score
    bb_score: float | None = None
    if bb is not None:
        bb_lower = bb.lower()
        if "tight" in bb_lower and "loosening" not in bb_lower:
            bb_score = tightness_raw if tightness_raw is not None else 0.7
        elif "tightening" in bb_lower:
            bb_score = tightness_raw if tightness_raw is not None else 0.6
        elif "loosening" in bb_lower:
            bb_score = tightness_raw if tightness_raw is not None else 0.2
        elif "neutral" in bb_lower or "watch" in bb_lower:
            bb_score = tightness_raw if tightness_raw is not None else 0.3

    # Activity acceleration from radar flags (max accel across theme's baskets)
    accels: list[float] = []
    for bid in basket_ids:
        flag = radar_flags_by_basket.get(bid)
        if flag:
            accel = (flag.get("observable") or {}).get("accel")
            if accel is not None and isinstance(accel, (int, float)):
                accels.append(float(accel))

    accel_max: float | None = max(accels) if accels else None

    # Combine: if both available average them (both 0-1 scaled)
    accel_norm: float | None = None
    if accel_max is not None:
        # accel is 0-2+ (YoY multiple); normalize to 0-1 by capping at 2.0
        accel_norm = min(1.0, accel_max / 2.0)

    if bb_score is None and accel_norm is None:
        return _null_leg(
            inputs, stale=True,
            note_en="no bottleneck band or activity data for this theme",
            note_zh="该主题无瓶颈波段或活动数据",
        )

    parts = [v for v in [bb_score, accel_norm] if v is not None]
    value = sum(parts) / len(parts)

    band: str
    if value >= 0.65:
        band = "high"
    elif value >= 0.35:
        band = "med"
    else:
        band = "low"

    bb_note = f"band={bb}" if bb else "band=null"
    accel_note = f"accel={accel_max:.2f}" if accel_max is not None else "accel=null"
    note_en = f"bottleneck_band={bb_note}, {accel_note} → tightness={value:.2f}"
    note_zh = f"瓶颈波段={bb_note}，活动加速={accel_note}，综合紧张度={value:.2f}"

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": False,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _leg_stale_consensus_gap(
    foresight_rec: dict | None,
    basket_ids: list[str],
    revision_map: dict,
    membership_by_basket: dict,
) -> dict:
    """Leg b: stale_consensus_gap — 'secular at cyclical prices'.
    Fires HIGH when activity has turned up but revisions are still flat/falling.
    Sources: foresight_cascade.demand_band (activity direction),
             foresight_cascade.revision_level/revision_breadth (analyst trajectory),
             finnhub recommendation.parquet (per-member revision dispersion).
    """
    inputs = [
        "foresight_cascade:demand_band",
        "foresight_cascade:broadening_state",
        "foresight_cascade:revision_level",
        "foresight_cascade:revision_breadth",
        "finnhub_recs:revision_direction",
    ]

    if foresight_rec is None:
        return _null_leg(
            inputs, stale=True,
            note_en="foresight_cascade absent",
            note_zh="foresight_cascade 缺失",
        )

    # Activity direction: demand_band + broadening_state
    demand_band = foresight_rec.get("demand_band")   # "ACCELERATING", "DECELERATING", None
    broadening = foresight_rec.get("broadening_state")  # "RISING", "ROLLING", "MIXED", None
    activity_up = False
    if demand_band in ("ACCELERATING",):
        activity_up = True
    elif broadening in ("RISING",):
        activity_up = True

    # Analyst revision trajectory
    rev_level = foresight_rec.get("revision_level")   # "POSITIVE", "NEGATIVE", None
    rev_breadth = foresight_rec.get("revision_breadth")  # float -1..+1 or None
    est_drift_90d = foresight_rec.get("est_drift_90d")   # float % or None

    revisions_lagging = False
    if rev_level == "NEGATIVE":
        revisions_lagging = True
    elif rev_breadth is not None and rev_breadth < _REV_BREADTH_MED:
        revisions_lagging = True
    elif est_drift_90d is not None and est_drift_90d < 0:
        revisions_lagging = True

    # Per-member revision dispersion from Finnhub (optional)
    member_tickers: list[str] = []
    for bid in basket_ids:
        member_tickers.extend(membership_by_basket.get(bid, []))
    member_tickers = list(set(member_tickers))

    dispersion_note = "no_dispersion_data"
    if revision_map and member_tickers:
        member_revs = [revision_map[tk] for tk in member_tickers if tk in revision_map]
        if member_revs:
            dirs = [r.get("direction", "stable") for r in member_revs]
            n_downgrading = sum(1 for d in dirs if d == "downgrading")
            n_upgrading = sum(1 for d in dirs if d == "upgrading")
            dispersion_note = (
                f"{n_downgrading}/{len(dirs)} downgrading, "
                f"{n_upgrading}/{len(dirs)} upgrading"
            )
            if n_downgrading > n_upgrading:
                revisions_lagging = True

    # Gap fires HIGH when activity turned up but revisions still flat/negative
    if activity_up is None and not revisions_lagging:
        return _null_leg(
            inputs, stale=True,
            note_en="insufficient data for consensus gap assessment",
            note_zh="数据不足，无法评估共识差距",
        )

    # Score: 1.0 = classic setup (activity up + revisions lagging)
    if activity_up and revisions_lagging:
        value = 0.85
        band = "high"
        note_en = (
            f"activity accelerating ({demand_band or broadening}) "
            f"but revisions lagging (level={rev_level}, breadth={rev_breadth}); "
            f"member dispersion: {dispersion_note}"
        )
        note_zh = (
            f"活动加速（{demand_band or broadening}）但分析师修正滞后"
            f"（水平={rev_level}，广度={rev_breadth}）；成员分散：{dispersion_note}"
        )
    elif activity_up and not revisions_lagging:
        value = 0.35
        band = "med"
        note_en = (
            f"activity accelerating ({demand_band or broadening}) "
            f"and revisions following (level={rev_level}, breadth={rev_breadth}); "
            f"gap narrowing. {dispersion_note}"
        )
        note_zh = (
            f"活动加速（{demand_band or broadening}）且修正跟进"
            f"（水平={rev_level}，广度={rev_breadth}）；差距收窄。{dispersion_note}"
        )
    elif not activity_up and revisions_lagging:
        value = 0.20
        band = "low"
        note_en = (
            f"activity not accelerating ({demand_band or broadening}) "
            f"and revisions lagging — aligned weakness. {dispersion_note}"
        )
        note_zh = (
            f"活动未加速（{demand_band or broadening}）且修正滞后——一致疲软。{dispersion_note}"
        )
    else:
        value = 0.15
        band = "low"
        note_en = (
            f"activity not accelerating ({demand_band or broadening}), "
            f"revisions positive (level={rev_level}, breadth={rev_breadth}); "
            f"no gap. {dispersion_note}"
        )
        note_zh = (
            f"活动未加速（{demand_band or broadening}），修正正面"
            f"（水平={rev_level}，广度={rev_breadth}）；无差距。{dispersion_note}"
        )

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": False,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _leg_cyclical_dislocation(
    ti_recs: list[dict],
    basket_ids: list[str],
) -> dict:
    """Leg c: cyclical_dislocation — drawdown from high vs RS trend divergence.
    Sources: theme_intel textures.bull_age.drawdown_from_peak,
             theme_intel textures.overbought.value,
             theme_intel accel_z.
    High = deep drawdown while RS trend is positive (price pulled back into strength).
    """
    inputs = [
        "baskets:theme_intel.textures.bull_age.drawdown_from_peak",
        "baskets:theme_intel.accel_z",
        "baskets:theme_intel.rs_pctile",
    ]

    if not ti_recs:
        return _null_leg(
            inputs, stale=True,
            note_en="no theme_intel records for this theme's baskets",
            note_zh="该主题篮子无 theme_intel 记录",
        )

    # Aggregate across baskets: worst drawdown + average RS
    drawdowns: list[float] = []
    accel_zs: list[float] = []
    rs_pctiles: list[float] = []

    for rec in ti_recs:
        textures = rec.get("textures") or {}
        bull_age = textures.get("bull_age") or {}
        dd = bull_age.get("drawdown_from_peak")
        if dd is not None and isinstance(dd, (int, float)):
            drawdowns.append(abs(float(dd)))   # store as positive magnitude

        az = rec.get("accel_z")
        if az is not None and isinstance(az, (int, float)):
            accel_zs.append(float(az))

        rs = rec.get("rs_pctile")
        if rs is not None and isinstance(rs, (int, float)):
            rs_pctiles.append(float(rs))

    if not drawdowns:
        return _null_leg(
            inputs, stale=True,
            note_en="drawdown_from_peak unavailable in theme_intel",
            note_zh="theme_intel 中无法获取回撤数据",
        )

    max_dd = max(drawdowns)          # worst drawdown from peak (magnitude)
    avg_accel_z = sum(accel_zs) / len(accel_zs) if accel_zs else None
    avg_rs = sum(rs_pctiles) / len(rs_pctiles) if rs_pctiles else None

    # Dislocation = deep drawdown (price pulled back) while RS trend is still positive
    # Normalize drawdown to 0-1 (cap at 50%)
    dd_norm = min(1.0, max_dd / 0.50)

    # Adjust: higher RS percentile + drawdown = more dislocation opportunity
    rs_factor = float(avg_rs) if avg_rs is not None else 0.5
    accel_sign = 1 if (avg_accel_z is not None and avg_accel_z > 0) else 0

    # Combined: drawdown gives the "price pulled back" component;
    # RS > 0.5 + accel > 0 gives "but relative strength intact" (true dislocation)
    if rs_factor >= 0.5 and accel_sign:
        # Classic cyclical dislocation setup
        value = 0.4 + 0.6 * dd_norm
    elif rs_factor >= 0.5:
        value = 0.2 + 0.5 * dd_norm
    else:
        # Drawdown + weak RS → deterioration, not dislocation
        value = 0.1 + 0.2 * dd_norm

    if value >= 0.65:
        band = "high"
    elif value >= 0.35:
        band = "med"
    else:
        band = "low"

    rs_str = f"{avg_rs:.2f}" if avg_rs is not None else "null"
    accel_str = f"{avg_accel_z:.2f}" if avg_accel_z is not None else "null"
    note_en = (
        f"max_drawdown_from_peak={max_dd:.1%}, "
        f"avg_rs_pctile={rs_str}, "
        f"avg_accel_z={accel_str} "
        f"→ dislocation={value:.2f}"
    )
    note_zh = (
        f"最大回撤={max_dd:.1%}，平均RS百分位={rs_str}，"
        f"平均加速z值={accel_str} "
        f"→ 错位={value:.2f}"
    )

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": False,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _leg_entry_cleanliness(
    ti_recs: list[dict],
    narrative_data: dict,
) -> dict:
    """Leg d: entry_cleanliness — inverse extension.
    Sources: theme_intel textures.clean_entry + textures.overbought,
             narrative_emergence hype.stretched_share.
    High = clean, not extended, not parabolic.
    """
    inputs = [
        "baskets:theme_intel.textures.clean_entry",
        "baskets:theme_intel.textures.overbought",
        "baskets:theme_intel.ext_abs",
        "narrative_emergence:hype.stretched_share",
    ]

    if not ti_recs:
        return _null_leg(
            inputs, stale=True,
            note_en="no theme_intel records for this theme's baskets",
            note_zh="该主题篮子无 theme_intel 记录",
        )

    # Aggregate clean entry quality across baskets (average)
    clean_qualities: list[float] = []
    overbought_values: list[float] = []
    ext_abs_values: list[float] = []

    for rec in ti_recs:
        textures = rec.get("textures") or {}
        ce = textures.get("clean_entry") or {}
        quality = ce.get("quality")
        if quality is not None and isinstance(quality, (int, float)):
            clean_qualities.append(float(quality))

        ob = textures.get("overbought") or {}
        ob_val = ob.get("value")
        if ob_val is not None and isinstance(ob_val, (int, float)):
            overbought_values.append(float(ob_val))

        ea = rec.get("ext_abs")
        if ea is not None and isinstance(ea, (int, float)):
            ext_abs_values.append(float(ea))

    # Universe-level hype (narrative hype stretched share)
    universe = narrative_data.get("_universe", {})
    max_stretched = universe.get("max_stretched_share", 0.0)
    ipo_wave = universe.get("ipo_wave", False)

    if not clean_qualities and not overbought_values:
        return _null_leg(
            inputs, stale=True,
            note_en="clean_entry and overbought data unavailable",
            note_zh="无法获取入场质量和超买数据",
        )

    avg_quality = sum(clean_qualities) / len(clean_qualities) if clean_qualities else 0.5
    avg_overbought = sum(overbought_values) / len(overbought_values) if overbought_values else 0.5
    avg_ext_abs = sum(ext_abs_values) / len(ext_abs_values) if ext_abs_values else 0.0

    # ext_abs z: normalize by capping at 3σ → 0 is clean, 3σ = very extended
    ext_penalty = min(1.0, avg_ext_abs / 3.0) if ext_abs_values else 0.0
    hype_penalty = float(max_stretched) * 0.3
    ipo_penalty = 0.2 if ipo_wave else 0.0

    # Cleanliness = clean_quality - overbought penalty - extension penalty - hype penalty
    value = (avg_quality
             - 0.3 * avg_overbought
             - 0.3 * ext_penalty
             - hype_penalty
             - ipo_penalty)
    value = max(0.0, min(1.0, value))

    band = _band_from_value(value, _CLEAN_MED, _CLEAN_HI)

    note_en = (
        f"avg_clean_quality={avg_quality:.2f}, "
        f"avg_overbought={avg_overbought:.2f}, "
        f"ext_abs={avg_ext_abs:.2f}, "
        f"hype_stretched={max_stretched:.2f} "
        f"→ cleanliness={value:.2f}"
    )
    note_zh = (
        f"平均入场质量={avg_quality:.2f}，"
        f"平均超买={avg_overbought:.2f}，"
        f"延伸绝对值={avg_ext_abs:.2f}，"
        f"炒作拉伸={max_stretched:.2f} "
        f"→ 入场整洁度={value:.2f}"
    )

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": False,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _leg_crowding_hazard(
    ti_recs: list[dict],
    divergence_log_rec: dict | None,
) -> dict:
    """Leg e: crowding_hazard — HAZARD framing only (NEXTL-U13).
    Sources: theme_intel components.crowding,
             divergence_log quadrant (hype-risk = high crowding signal).
    High = elevated crowding hazard.
    """
    inputs = [
        "baskets:theme_intel.components.crowding",
        "divergence_log:quadrant",
        "divergence_log:money_pct",
    ]

    if not ti_recs:
        return _null_leg(
            inputs, stale=True,
            note_en="no theme_intel records for this theme's baskets",
            note_zh="该主题篮子无 theme_intel 记录",
        )

    # Average crowding penalty across baskets
    crowding_vals: list[float] = []
    for rec in ti_recs:
        c = (rec.get("components") or {}).get("crowding")
        if c is not None and isinstance(c, (int, float)):
            crowding_vals.append(float(c))

    avg_crowding = sum(crowding_vals) / len(crowding_vals) if crowding_vals else None

    # Divergence log hazard signal: hype-risk quadrant or very high money_pct
    div_hazard_boost = 0.0
    div_note = "no_div_log_entry"
    if divergence_log_rec is not None:
        quadrant = divergence_log_rec.get("quadrant")
        money_pct = divergence_log_rec.get("money_pct")
        if quadrant == "hype-risk":
            div_hazard_boost = 0.25
            div_note = "hype-risk quadrant"
        elif money_pct is not None and float(money_pct) >= 0.8:
            div_hazard_boost = 0.10
            div_note = f"money_pct={money_pct:.2f} (elevated)"
        else:
            div_note = f"quadrant={quadrant}"

    if avg_crowding is None:
        return _null_leg(
            inputs, stale=True,
            note_en="crowding data unavailable",
            note_zh="拥挤数据不可用",
        )

    value = min(1.0, avg_crowding + div_hazard_boost)
    band = _band_from_value(value, _CROWD_MED, _CROWD_HIGH)

    note_en = (
        f"avg_crowding={avg_crowding:.2f}, "
        f"div_log={div_note} "
        f"→ crowding_hazard={value:.2f}. "
        "HAZARD framing only; not a directional read."
    )
    note_zh = (
        f"平均拥挤={avg_crowding:.2f}，"
        f"背离日志={div_note} "
        f"→ 拥挤风险={value:.2f}。"
        "仅为风险识别，非方向性判断。"
    )

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": False,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _leg_falsifier_clarity(
    thesis_rows: list[dict],
    thesis_stale: list[str],
    theme_id: str,
) -> dict:
    """Leg f: falsifier_clarity.
    Sources: data/neuralweb/theme_thesis_ledger.jsonl (W1 output).
    Absent file → null leg + stale note "thesis ledger pending W1".
    High = many machine-checkable falsifiers currently ARMED.
    """
    inputs = ["theme_thesis_ledger:falsifiers.machine_checkable",
              "theme_thesis_ledger:falsifiers.status"]

    if thesis_stale and not thesis_rows:
        return _null_leg(
            inputs, stale=True,
            note_en="thesis ledger pending W1 build",
            note_zh="假证伪器清单等待 W1 构建",
        )

    # Filter to this theme's rows
    theme_rows = [r for r in thesis_rows if r.get("theme_id") == theme_id]
    if not theme_rows:
        return _null_leg(
            inputs, stale=True,
            note_en=f"no thesis ledger entries for theme {theme_id}",
            note_zh=f"主题 {theme_id} 无假证伪器条目",
        )

    # Collect all falsifiers across thesis rows
    all_falsifiers: list[dict] = []
    for row in theme_rows:
        falsifiers = row.get("falsifiers") or []
        if isinstance(falsifiers, list):
            all_falsifiers.extend(f for f in falsifiers if isinstance(f, dict))

    if not all_falsifiers:
        return _null_leg(
            inputs, stale=True,
            note_en=f"no falsifier records in thesis entries for {theme_id}",
            note_zh=f"主题 {theme_id} 假证伪器条目无内容",
        )

    n_total = len(all_falsifiers)
    n_machine_checkable = sum(
        1 for f in all_falsifiers
        if f.get("machine_checkable") is True or f.get("check") is not None
    )
    # ARMED = not FIRED, not DATA_MISSING
    n_armed = sum(
        1 for f in all_falsifiers
        if f.get("status") not in ("FIRED", "DATA_MISSING", "EXPIRED")
        and f.get("machine_checkable") is True
    )

    share_checkable = n_machine_checkable / n_total if n_total > 0 else 0.0
    share_armed = n_armed / n_machine_checkable if n_machine_checkable > 0 else 0.0

    # Clarity = weighted combination: checkability (0.6) + armedness (0.4)
    value = 0.6 * share_checkable + 0.4 * share_armed

    band = _band_from_value(value, _FALS_MED, _FALS_HIGH)

    note_en = (
        f"n_falsifiers={n_total}, "
        f"machine_checkable={n_machine_checkable} ({share_checkable:.0%}), "
        f"armed={n_armed} ({share_armed:.0%}) "
        f"→ clarity={value:.2f}"
    )
    note_zh = (
        f"假证伪器总数={n_total}，"
        f"机器可验证={n_machine_checkable}（{share_checkable:.0%}），"
        f"已激活={n_armed}（{share_armed:.0%}）"
        f"→ 清晰度={value:.2f}"
    )

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": False,
        "note_en": note_en,
        "note_zh": note_zh,
    }


def _leg_orthogonality(
    ti_recs: list[dict],
    cov_data: dict,
) -> dict:
    """Leg g: orthogonality — is this theme its own trade?
    Sources: site/neuralwebdata/covariance_spine.json dispersion.avg_corr
             (universe-level; per-basket-to-megacap correlation not in spine),
             theme_intel perf.60d.rel (basket's 60-day alpha vs SPY as proxy).
    High orthogonality = theme moves independently of market/megacap complex.
    """
    inputs = [
        "covariance_spine:blocks.dispersion.avg_corr",
        "baskets:theme_intel.perf.60d.rel",
        "baskets:theme_intel.accel_z",
    ]

    # Universe avg_corr from covariance spine (how correlated universe is overall)
    dispersion = (cov_data.get("blocks") or {}).get("dispersion") or {}
    universe_avg_corr = dispersion.get("avg_corr")  # 0-1; low = dispersed (more orthogonal)

    if not ti_recs and universe_avg_corr is None:
        return _null_leg(
            inputs, stale=True,
            note_en="covariance spine and theme_intel both unavailable",
            note_zh="协方差骨干和 theme_intel 均不可用",
        )

    # Per-basket 60d relative return vs SPY as orthogonality proxy
    # Positive rel = theme is diverging from market (orthogonal)
    rel_60d_vals: list[float] = []
    accel_z_vals: list[float] = []
    for rec in ti_recs:
        perf = rec.get("perf") or {}
        rel_60d = (perf.get("60d") or {}).get("rel")
        if rel_60d is not None and isinstance(rel_60d, (int, float)):
            rel_60d_vals.append(float(rel_60d))
        az = rec.get("accel_z")
        if az is not None and isinstance(az, (int, float)):
            accel_z_vals.append(float(az))

    avg_rel_60d: float | None = (
        sum(rel_60d_vals) / len(rel_60d_vals) if rel_60d_vals else None
    )
    avg_accel_z: float | None = (
        sum(accel_z_vals) / len(accel_z_vals) if accel_z_vals else None
    )

    if avg_rel_60d is None:
        # Fall back to universe-level dispersion only
        if universe_avg_corr is None:
            return _null_leg(
                inputs, stale=True,
                note_en="per-basket correlation not available in covariance spine; "
                        "no theme_intel relative return data",
                note_zh="协方差骨干中无逐篮子相关数据；theme_intel 中亦无相对收益数据",
            )
        # Only universe-level: low avg_corr → universe is dispersed → themes are orthogonal
        orth_from_corr = 1.0 - float(universe_avg_corr)
        value = orth_from_corr
        note_en = (
            f"universe avg_corr={universe_avg_corr:.2f} → "
            f"orthogonality (universe proxy)={value:.2f}. "
            "Per-basket-to-megacap correlation not in spine; universe dispersion used as proxy."
        )
        note_zh = (
            f"全局平均相关性={universe_avg_corr:.2f} → "
            f"正交性（全局代理）={value:.2f}。"
            "骨干中无逐篮子与大盘相关数据；以全局分散度代理。"
        )
        stale_flag = False
    else:
        # Use 60d relative performance as primary orthogonality proxy
        # High positive rel → theme diverging from market → high orthogonality
        # Map rel_60d to 0-1 with 0% = 0.5, +30% = 1.0, -30% = 0.0
        rel_norm = max(0.0, min(1.0, (float(avg_rel_60d) + 0.30) / 0.60))

        # Universe avg_corr modifier (optional): low corr → up-weight orthogonality
        if universe_avg_corr is not None:
            # Low universe corr means conditions are better for idio performance
            corr_mod = (1.0 - float(universe_avg_corr)) * 0.1
        else:
            corr_mod = 0.0

        value = min(1.0, rel_norm + corr_mod)

        note_en = (
            f"avg_60d_rel={avg_rel_60d:.1%}, "
            f"universe_avg_corr={universe_avg_corr if universe_avg_corr is not None else 'null'} "
            f"→ orthogonality={value:.2f}. "
            "Per-basket-to-megacap corr not in spine; 60d relative return used as proxy."
        )
        note_zh = (
            f"平均60日相对收益={avg_rel_60d:.1%}，"
            f"全局平均相关性={universe_avg_corr if universe_avg_corr is not None else '无'} "
            f"→ 正交性={value:.2f}。"
            "骨干中无逐篮子与大盘相关数据；以60日相对收益代理。"
        )
        stale_flag = False

    if value >= 0.65:
        band = "high"
    elif value >= 0.35:
        band = "med"
    else:
        band = "low"

    return {
        "value": round(value, 3),
        "band": band,
        "inputs": inputs,
        "stale": stale_flag,
        "note_en": note_en,
        "note_zh": note_zh,
    }


# ---------------------------------------------------------------------------
# Per-theme composition
# ---------------------------------------------------------------------------

def _compose_theme(
    theme_cfg: dict,
    foresight_by_id: dict,
    baskets_by_id: dict,
    radar_flags_by_basket: dict,
    narrative_data: dict,
    divergence_log: dict,
    cov_data: dict,
    thesis_rows: list[dict],
    thesis_stale: list[str],
    revision_map: dict,
    membership_by_basket: dict,
) -> dict:
    """Build a single theme asymmetry panel (7 independent legs). Never raises."""
    tid = theme_cfg["id"]
    foresight_id = theme_cfg.get("foresight_id")
    basket_ids: list[str] = theme_cfg.get("basket_ids", [])

    foresight_rec = foresight_by_id.get(foresight_id) if foresight_id else None

    # Collect theme_intel records for this theme's baskets
    ti_recs = [baskets_by_id[bid] for bid in basket_ids if bid in baskets_by_id]

    # Divergence log entry for this theme
    div_rec = divergence_log.get(tid)

    try:
        leg_a = _leg_bottleneck_tightness(
            foresight_rec, radar_flags_by_basket, basket_ids, tid
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_a error: %s", tid, exc)
        leg_a = _null_leg(["foresight_cascade:bottleneck_band", "radar:flags.observable.accel"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    try:
        leg_b = _leg_stale_consensus_gap(
            foresight_rec, basket_ids, revision_map, membership_by_basket
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_b error: %s", tid, exc)
        leg_b = _null_leg(["foresight_cascade:revision_level"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    try:
        leg_c = _leg_cyclical_dislocation(ti_recs, basket_ids)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_c error: %s", tid, exc)
        leg_c = _null_leg(["baskets:theme_intel.textures"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    try:
        leg_d = _leg_entry_cleanliness(ti_recs, narrative_data)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_d error: %s", tid, exc)
        leg_d = _null_leg(["baskets:theme_intel.textures.clean_entry"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    try:
        leg_e = _leg_crowding_hazard(ti_recs, div_rec)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_e error: %s", tid, exc)
        leg_e = _null_leg(["baskets:theme_intel.components.crowding"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    try:
        leg_f = _leg_falsifier_clarity(thesis_rows, thesis_stale, tid)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_f error: %s", tid, exc)
        leg_f = _null_leg(["theme_thesis_ledger:falsifiers"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    try:
        leg_g = _leg_orthogonality(ti_recs, cov_data)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme %s leg_g error: %s", tid, exc)
        leg_g = _null_leg(["covariance_spine:blocks.dispersion"],
                           note_en=f"compute error: {exc}", note_zh=f"计算错误: {exc}")

    return {
        "theme_id": tid,
        "name_en": theme_cfg["name_en"],
        "name_zh": theme_cfg["name_zh"],
        "basket_ids": basket_ids,
        "legs": {
            "bottleneck_tightness": leg_a,
            "stale_consensus_gap": leg_b,
            "cyclical_dislocation": leg_c,
            "entry_cleanliness": leg_d,
            "crowding_hazard": leg_e,
            "falsifier_clarity": leg_f,
            "orthogonality": leg_g,
        },
    }


# ---------------------------------------------------------------------------
# Basket membership lookup helper
# ---------------------------------------------------------------------------

def _load_membership(root: Path) -> dict:
    """Returns {basket_id: [ticker, ...]} tolerantly."""
    path = root / "data/baskets/membership.json"
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        out: dict = {}
        for bid, bdata in d.get("baskets", {}).items():
            out[bid] = bdata.get("tickers", []) if isinstance(bdata, dict) else []
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("membership.json read failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Main composition
# ---------------------------------------------------------------------------

def compose_asymmetry(root: Path | None = None) -> dict:
    """Compose the theme_asymmetry artifact. Never raises; returns a valid dict."""
    if root is None:
        root = _repo_root()
    root = Path(root)

    now = _now_str()
    as_of = _asof_today()
    all_stale_legs: list[str] = []

    # Load crosswalk
    xwalk_data, xwalk_err = _load_yaml(root / _CROSSWALK_PATH, "theme_crosswalk")
    if xwalk_err or xwalk_data is None:
        log.error("theme_crosswalk unavailable: %s", xwalk_err)
        return {
            "schema": SCHEMA,
            "as_of": as_of,
            "generated_at": now,
            "hard_caveat": HARD_CAVEAT,
            "authority": AUTHORITY_BLOCK,
            "themes": [],
            "stale_legs": [f"theme_crosswalk: {xwalk_err}"],
            "error": "crosswalk unavailable — no theme blocks composed",
        }

    theme_cfgs = xwalk_data.get("themes", [])

    # Load all sources (each tolerant)
    foresight_by_id, sl1 = _load_foresight(root)
    all_stale_legs.extend(sl1)

    baskets_by_id, sl2 = _load_baskets_intel(root)
    all_stale_legs.extend(sl2)

    radar_flags_by_basket, sl3 = _load_radar_flags(root)
    all_stale_legs.extend(sl3)

    narrative_data, sl4 = _load_narrative(root)
    all_stale_legs.extend(sl4)

    divergence_log, sl5 = _load_divergence_log(root)
    all_stale_legs.extend(sl5)

    cov_data, sl6 = _load_covariance(root)
    all_stale_legs.extend(sl6)

    thesis_rows, thesis_stale = _load_thesis_ledger(root)
    all_stale_legs.extend(thesis_stale)

    revision_map_data, sl8 = _load_finnhub_revisions(root)
    all_stale_legs.extend(sl8)

    membership_by_basket = _load_membership(root)

    # Compose per-theme
    theme_blocks: list[dict] = []
    for cfg in theme_cfgs:
        try:
            block = _compose_theme(
                theme_cfg=cfg,
                foresight_by_id=foresight_by_id,
                baskets_by_id=baskets_by_id,
                radar_flags_by_basket=radar_flags_by_basket,
                narrative_data=narrative_data,
                divergence_log=divergence_log,
                cov_data=cov_data,
                thesis_rows=thesis_rows,
                thesis_stale=thesis_stale,
                revision_map=revision_map_data,
                membership_by_basket=membership_by_basket,
            )
            theme_blocks.append(block)
        except Exception as exc:  # noqa: BLE001
            log.error("theme %s compose failed (skipped): %s", cfg.get("id"), exc)
            all_stale_legs.append(f"theme.{cfg.get('id')}: compose error — {exc}")

    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "generated_at": now,
        "hard_caveat": HARD_CAVEAT,
        "authority": AUTHORITY_BLOCK,
        "n_themes": len(theme_blocks),
        "themes": theme_blocks,
        "stale_legs": all_stale_legs,
    }


# ---------------------------------------------------------------------------
# run_stage — auto-discovered by scripts/build_thematic_state.py
# ---------------------------------------------------------------------------

def run_stage(root: Path) -> None:
    """TIL W3 entry point. Writes data + site artifacts. Never raises fatally."""
    import time
    t0 = time.perf_counter()
    root = Path(root)

    try:
        artifact = compose_asymmetry(root)
    except Exception as exc:  # noqa: BLE001
        log.error("compose_asymmetry() failed: %s", exc)
        artifact = {
            "schema": SCHEMA,
            "as_of": _asof_today(),
            "generated_at": _now_str(),
            "hard_caveat": HARD_CAVEAT,
            "authority": AUTHORITY_BLOCK,
            "themes": [],
            "stale_legs": [f"compose exception: {exc}"],
        }

    # Stamp with envelope
    try:
        from engine.neuralweb.envelope import stamp
        artifact = stamp(artifact, artifact_id="theme-asymmetry")
    except Exception as exc:  # noqa: BLE001
        log.warning("envelope stamp failed (non-fatal): %s", exc)

    # Write data artifact
    data_path = root / _DATA_OUT
    try:
        _atomic_write(data_path, artifact)
        log.info("wrote %s", data_path)
    except Exception as exc:  # noqa: BLE001
        log.error("data write failed: %s", exc)

    # Write site mirror
    site_path = root / _SITE_OUT
    try:
        _atomic_write(site_path, artifact)
        log.info("wrote %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.error("site write failed: %s", exc)

    elapsed = time.perf_counter() - t0
    n_themes = len(artifact.get("themes", []))
    n_stale = len(artifact.get("stale_legs", []))
    log.info(
        "theme_asymmetry done in %.2fs — themes=%d stale_legs=%d",
        elapsed, n_themes, n_stale,
    )
    print(
        f"[theme_asymmetry] done {elapsed:.2f}s — themes={n_themes} stale_legs={n_stale}",
        flush=True,
    )
