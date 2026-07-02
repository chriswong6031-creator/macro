"""engine/missing_tape_attention.py — Missing-Tape Leg C: Attention-Collapse Anomaly.

Spec: research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md D8 §4 W4.

A THEME or ENTITY whose Chinese-language qbus volume (cn_count) collapses
abnormally while offshore English-language volume (en_count) does NOT collapse
is flagged as "possibly suppressed."

Logic:
1. From qbus items, compute daily CN-lane and EN-lane item counts per theme/entity
   over a trailing 30-day window.
2. For each subject, compute a COLLAPSE Z:
       cn_z = (today_cn − trailing_cn_mean) / trailing_cn_std
       en_z = (today_en − trailing_en_mean) / trailing_en_std
   A collapse candidate has cn_z ≤ -1.5 (CN volume dropped) AND en_z > -0.5
   (EN volume did not similarly drop).
3. Confidence tier (corroboration across Missing-Tape legs):
       HIGH   — cn_z ≤ -2.5, en_z ≥ +0.5, AND recrawl_log has ≥1 "gone/edited" for
                a TIER1 item tagged with the same theme in the last 14d.
       MED    — cn_z ≤ -1.5, en_z > -0.5 (no recrawl corroboration).
       LOW    — cn_z ≤ -1.0, en_z > -0.75 (borderline; flagged for awareness only).

Semantics: RISK FLAG only — "attention-collapse" marks a series "possibly suppressed,"
NOT "demand fell."  direction=0 throughout; never a positive signal (spec D8).

PURE module — LEAF in the dependency graph.  No network; consumes qbus.read_items()
and the recrawl_log parquet.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from pathlib import Path

LOG = logging.getLogger("missing_tape_attention")

ROOT = Path(__file__).resolve().parent.parent


# Module-level import so callers (and tests) can monkeypatch this reference.
# Wrapped in try/except so the module imports cleanly even in isolated test envs.
try:
    from engine.qbus import read_items  # noqa: F401  (re-exported for monkeypatching)
except Exception:  # noqa: BLE001
    def read_items():  # type: ignore[misc]
        return None

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
_WINDOW_DAYS: int = 30
_CN_COLLAPSE_Z_HIGH: float = -2.5
_CN_COLLAPSE_Z_MED: float = -1.5
_CN_COLLAPSE_Z_LOW: float = -1.0
_EN_STABLE_Z_HIGH: float = 0.5   # EN actually rising
_EN_STABLE_Z_MED: float = -0.5   # EN not collapsing
_EN_STABLE_Z_LOW: float = -0.75  # EN borderline stable

# Minimum daily count observations in the trailing window before flagging.
_MIN_OBS: int = 5

# Recrawl corroboration look-back (days).
_RECRAWL_LOOKBACK: int = 14


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _data_root() -> Path:
    try:
        from lib import config
        return config.data_dir()
    except Exception:
        return ROOT / "data"


def _mean_std(vals: list[float]) -> tuple[float, float]:
    """Sample mean and std of a list.  Returns (0, 1) on empty/unit lists."""
    if not vals:
        return 0.0, 1.0
    n = len(vals)
    mu = sum(vals) / n
    if n < 2:
        return mu, 1.0
    var = sum((v - mu) ** 2 for v in vals) / (n - 1)
    return mu, math.sqrt(var) if var > 0 else 1.0


def _safe_z(today_val: float, history: list[float]) -> float:
    """Z-score of today_val vs history.  NaN when history too short."""
    if len(history) < _MIN_OBS:
        return float("nan")
    mu, sigma = _mean_std(history)
    return (today_val - mu) / sigma


# --------------------------------------------------------------------------- #
# qbus volume extraction
# --------------------------------------------------------------------------- #
def _daily_counts_by_subject(asof: date, window_days: int = _WINDOW_DAYS):
    """
    Returns two dicts:
        cn_counts[subject][date_str] = int
        en_counts[subject][date_str] = int

    Subjects are ALL unique theme and entity tokens found in qbus items over the
    window.  CN lane = lang=="zh"; EN lane = lang=="en".
    """
    try:
        import pandas as pd
    except Exception as exc:
        LOG.warning("pandas import failed: %s", exc)
        return {}, {}

    try:
        df = read_items()
    except Exception as exc:
        LOG.warning("qbus read failed: %s", exc)
        return {}, {}

    if df is None or df.empty:
        return {}, {}

    # Date filter
    start = asof - timedelta(days=window_days + 1)
    day_col = pd.to_datetime(df["seendate"], errors="coerce", utc=True)
    fallback = pd.to_datetime(df["_crawled_at"], errors="coerce", utc=True)
    day_col = day_col.fillna(fallback)
    df = df[
        (day_col >= pd.Timestamp(start.isoformat(), tz="UTC"))
        & (day_col <= pd.Timestamp(asof.isoformat(), tz="UTC"))
    ].copy()
    df["_day"] = day_col[df.index].dt.date.astype(str)

    cn_counts: dict[str, dict[str, int]] = {}
    en_counts: dict[str, dict[str, int]] = {}

    for _, row in df.iterrows():
        lang = str(row.get("lang", "en"))
        day = str(row.get("_day", ""))
        bucket = cn_counts if lang == "zh" else en_counts

        for field in ("themes", "entities"):
            raw = str(row.get(field, ""))
            for subj in raw.split(","):
                subj = subj.strip()
                if not subj:
                    continue
                if subj not in bucket:
                    bucket[subj] = {}
                bucket[subj][day] = bucket[subj].get(day, 0) + 1

    return cn_counts, en_counts


# --------------------------------------------------------------------------- #
# recrawl corroboration
# --------------------------------------------------------------------------- #
def _recrawl_hit_subjects(data_root: Path, asof: date) -> set[str]:
    """Return the set of qbus theme tokens associated with gone/edited recrawl rows
    in the last _RECRAWL_LOOKBACK days.  Used for HIGH-tier corroboration."""
    try:
        import pandas as pd
    except Exception:
        return set()

    log_path = data_root / "missing_tape" / "recrawl_log.parquet"
    if not log_path.exists():
        return set()

    try:
        log_df = pd.read_parquet(log_path)
    except Exception:
        return set()

    cutoff = (asof - timedelta(days=_RECRAWL_LOOKBACK)).isoformat()
    hits = log_df[
        (log_df["status"].isin(["gone", "edited"]))
        & (log_df["recrawl_at"] >= cutoff)
    ]
    if hits.empty:
        return set()

    # Look up the themes of those item_ids in qbus
    bus = read_items()
    if bus is None or bus.empty:
        return set()

    hit_ids = set(hits["item_id"].astype(str))
    matched = bus[bus["item_id"].isin(hit_ids)]
    subjects: set[str] = set()
    for raw in matched["themes"].fillna(""):
        for t in str(raw).split(","):
            t = t.strip()
            if t:
                subjects.add(t)
    return subjects


# --------------------------------------------------------------------------- #
# main: detect collapse flags
# --------------------------------------------------------------------------- #
def detect_flags(
    *,
    asof: date | None = None,
    window_days: int = _WINDOW_DAYS,
    data_root: Path | None = None,
) -> list[dict]:
    """
    Detect attention-collapse anomalies.

    Returns a list of flag dicts:
        {
          "subject":    str,
          "cn_z":       float,
          "en_z":       float,
          "confidence": "HIGH" | "MED" | "LOW",
          "today_cn":   int,
          "today_en":   int,
          "asof":       str,
        }

    Only subjects with ≥ _MIN_OBS days of history are flagged.
    """
    asof = asof or date.today()
    data_root = data_root or _data_root()

    cn_counts, en_counts = _daily_counts_by_subject(asof, window_days)
    recrawl_subjects = _recrawl_hit_subjects(data_root, asof)

    today_str = asof.isoformat()
    all_subjects = set(cn_counts) | set(en_counts)

    flags: list[dict] = []

    for subject in sorted(all_subjects):
        cn_by_day = cn_counts.get(subject, {})
        en_by_day = en_counts.get(subject, {})

        # today's counts
        today_cn = cn_by_day.get(today_str, 0)
        today_en = en_by_day.get(today_str, 0)

        # trailing history (exclude today)
        cn_hist = [cn_by_day[d] for d in sorted(cn_by_day) if d < today_str]
        en_hist = [en_by_day[d] for d in sorted(en_by_day) if d < today_str]

        cn_z = _safe_z(float(today_cn), cn_hist)
        en_z = _safe_z(float(today_en), en_hist)

        if math.isnan(cn_z) or math.isnan(en_z):
            continue

        # Apply collapse thresholds
        if cn_z > _CN_COLLAPSE_Z_LOW:
            continue  # no collapse
        if en_z < _EN_STABLE_Z_LOW:
            continue  # EN also collapsed — consistent global drop, not suppression

        # Determine confidence tier
        if (
            cn_z <= _CN_COLLAPSE_Z_HIGH
            and en_z >= _EN_STABLE_Z_HIGH
            and subject in recrawl_subjects
        ):
            confidence = "HIGH"
        elif cn_z <= _CN_COLLAPSE_Z_MED and en_z > _EN_STABLE_Z_MED:
            confidence = "MED"
        else:
            confidence = "LOW"

        flags.append({
            "subject": subject,
            "cn_z": round(cn_z, 3),
            "en_z": round(en_z, 3),
            "confidence": confidence,
            "today_cn": int(today_cn),
            "today_en": int(today_en),
            "asof": today_str,
        })

    flags.sort(key=lambda f: f["cn_z"])  # most-collapsed first
    LOG.info("attention_collapse: %d flags detected on %s", len(flags), today_str)
    return flags
