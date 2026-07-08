"""HK Narrative / Attention-Shock engine — DISPLAY-ONLY context organ (W1 data-plane).

Surfaces news-volume spikes and tone shifts for HK platform-tech bellwethers
via GDELT DOC 2.0 article-count and tone time-series.

DISPLAY-ONLY. No signal. No edge claim. No LLM-originated score.
Ships display-tier immediately; forward ledger accrues for future context use.

CONTEXT TIER CAVEAT
-------------------
GDELT measures English-language news volume and sentiment — a noisy, imprecise
proxy for market-relevant narrative. Entity resolution is imperfect: queries
match any article naming the company string, not disambiguated company events.
This is the WEAKEST-falsifiability organ in the HK dashboard. It is displayed
as context only, labelled explicitly on-page as "weakest evidence tier."

METRICS
-------
Per-entity (deterministic, no LLM):
  attention_shock_z   : z-score of today's vol_intensity vs trailing baseline
                        (mean + std over the baseline window; positive = spike)
  tone_pctile         : today's avg_tone as a percentile vs own history (0-100)
  narrative_state     : descriptive label (quiet / attention_spike /
                        tone_positive_shift / tone_negative_shift)

Young-series exclusion: entities with < MIN_BASELINE_OBS observations in the
baseline window are excluded from any state assignment (state = None) and
returned with a young=True flag — identical to fear_greed young_tiles logic.

FRESHNESS
---------
Delegates to engine/hk_freshness for freshness gate (same pattern as other HK
organs). Missing or stale store degrades to no-data per entity (fail-open).

OUTPUT
------
snapshot() returns a dict:
  {
    "display_only": True,
    "as_of": "YYYY-MM-DD",
    "freshness": "ok" | "degraded" | "stale" | "missing",
    "entities": [
      {
        "slug": str,
        "ticker": str,
        "name_en": str,
        "name_zh": str,
        "attention_shock_z": float | None,
        "tone_pctile": float | None,
        "narrative_state": str | None,   # None when young/no-data
        "young": bool,                   # True when < MIN_BASELINE_OBS obs
        "n_obs": int | None,
        "as_of_date": str | None,
        "no_data_reason": str | None,
      },
      ...
    ],
    "note": "context, not a signal / 舆情参考，非买卖信号",
    "caveat_en": str,
    "caveat_zh": str,
  }
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import json
import numpy as np
import pandas as pd

from collectors.hk_gdelt import ENTITIES, load_store
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Min-history gate (mirrors fear_greed DAILY_MIN logic)
# ---------------------------------------------------------------------------

MIN_BASELINE_OBS = 20   # need ≥20 points in trailing window to assign a state
BASELINE_WINDOW  = 90   # days of history used for z-score / percentile

# Narrative-state thresholds (descriptive only)
_SPIKE_Z_THRESH    = 2.0   # |z| >= this → attention_spike
_TONE_HIGH_PCTILE  = 70.0  # tone_pctile >= this → tone_positive_shift
_TONE_LOW_PCTILE   = 30.0  # tone_pctile <= this → tone_negative_shift

# Forward ledger
_LEDGER_DIR  = "hk_impulse"
_LEDGER_FILE = "narrative_ledger.jsonl"
_ORGAN_ID    = "hk_narrative"


def _ledger_advance_enabled() -> bool:
    """True only when running in the asia-close nightly lane (CN_LANE=asia)."""
    return os.environ.get("CN_LANE", "").lower() == "asia"


# ---------------------------------------------------------------------------
# Core per-entity computation
# ---------------------------------------------------------------------------

def _compute_entity(slug: str, data_root: Path) -> dict:
    """Compute narrative metrics for one entity.
    Returns a per-entity dict with all required keys. Never raises.
    """
    from collectors.hk_gdelt import ENTITIES as _ENTITIES
    entity = next((e for e in _ENTITIES if e.slug == slug), None)
    if entity is None:
        return {
            "slug": slug, "ticker": None, "name_en": slug, "name_zh": slug,
            "attention_shock_z": None, "tone_pctile": None,
            "narrative_state": None, "young": True,
            "n_obs": 0, "as_of_date": None,
            "no_data_reason": "unknown entity slug",
        }

    base = {
        "slug":     entity.slug,
        "ticker":   entity.ticker,
        "name_en":  entity.name_en,
        "name_zh":  entity.name_zh,
    }

    df = load_store(slug, data_root)
    if df is None or df.empty:
        return {**base,
                "attention_shock_z": None, "tone_pctile": None,
                "narrative_state": None, "young": True,
                "n_obs": 0, "as_of_date": None,
                "no_data_reason": "store missing or empty"}

    # Drop NaN vol rows; need at least MIN_BASELINE_OBS non-NaN vol points
    vol_s   = df["vol_intensity"].dropna()
    tone_s  = df["avg_tone"].dropna()

    n_obs = len(vol_s)
    as_of_date = vol_s.index.max().date().isoformat() if n_obs else None

    if n_obs < MIN_BASELINE_OBS:
        return {**base,
                "attention_shock_z": None, "tone_pctile": None,
                "narrative_state": None, "young": True,
                "n_obs": n_obs, "as_of_date": as_of_date,
                "no_data_reason": f"young series: {n_obs} < {MIN_BASELINE_OBS} obs"}

    # Baseline = all observations except the most recent one (trailing N-1 days)
    baseline_vol  = vol_s.iloc[:-1]
    latest_vol    = float(vol_s.iloc[-1])

    if len(baseline_vol) < 2:
        return {**base,
                "attention_shock_z": None, "tone_pctile": None,
                "narrative_state": None, "young": True,
                "n_obs": n_obs, "as_of_date": as_of_date,
                "no_data_reason": "insufficient baseline for z-score"}

    mu  = float(baseline_vol.mean())
    std = float(baseline_vol.std(ddof=1))
    if std < 1e-10:
        # Near-zero std → can't z-score; not a crash
        attention_z = None
    else:
        attention_z = round((latest_vol - mu) / std, 3)

    # Tone percentile vs own history
    tone_pctile: float | None = None
    if not tone_s.empty and len(tone_s) >= 2:
        try:
            # percentile_rank: fraction of history that is below today's tone
            latest_tone = float(tone_s.iloc[-1])
            baseline_tone = tone_s.iloc[:-1]
            tone_pctile = round(
                float((baseline_tone < latest_tone).mean()) * 100.0, 1
            )
        except Exception as e:  # noqa: BLE001
            log.debug("hk_narrative: tone percentile failed for %s: %s", slug, e)

    # Narrative state (descriptive)
    narrative_state: str | None = None
    if attention_z is not None:
        if abs(attention_z) >= _SPIKE_Z_THRESH:
            narrative_state = "attention_spike"
        elif tone_pctile is not None and tone_pctile >= _TONE_HIGH_PCTILE:
            narrative_state = "tone_positive_shift"
        elif tone_pctile is not None and tone_pctile <= _TONE_LOW_PCTILE:
            narrative_state = "tone_negative_shift"
        else:
            narrative_state = "quiet"

    return {**base,
            "attention_shock_z": attention_z,
            "tone_pctile":       tone_pctile,
            "narrative_state":   narrative_state,
            "young":             False,
            "n_obs":             n_obs,
            "as_of_date":        as_of_date,
            "no_data_reason":    None}


# ---------------------------------------------------------------------------
# Freshness helper
# ---------------------------------------------------------------------------

def _freshness_verdict(data_root: Path) -> str:
    """Simple freshness check against coverage.json."""
    try:
        from collectors.hk_gdelt import load_coverage
        cov = load_coverage(data_root)
        if not cov:
            return "missing"
        today = date.today().isoformat()
        n_fresh = sum(1 for e in ENTITIES
                      if cov.get(e.slug, {}).get("date") == today
                      and cov.get(e.slug, {}).get("status") == "ok")
        if n_fresh == 0:
            return "stale"
        if n_fresh < len(ENTITIES) // 2:
            return "degraded"
        return "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("hk_narrative: freshness check failed: %s", e)
        return "missing"


# ---------------------------------------------------------------------------
# Public API: snapshot
# ---------------------------------------------------------------------------

def snapshot(data_root: Path | None = None) -> dict:
    """Compute the narrative pulse snapshot for all bellwether entities.

    Returns a serialisable dict. Never raises.
    """
    if data_root is None:
        data_root = config.data_dir()

    try:
        freshness = _freshness_verdict(data_root)
        entities_out = []
        for entity in ENTITIES:
            try:
                row = _compute_entity(entity.slug, data_root)
                entities_out.append(row)
            except Exception as e:  # noqa: BLE001
                log.warning("hk_narrative: compute failed for %s: %s", entity.slug, e)
                entities_out.append({
                    "slug": entity.slug, "ticker": entity.ticker,
                    "name_en": entity.name_en, "name_zh": entity.name_zh,
                    "attention_shock_z": None, "tone_pctile": None,
                    "narrative_state": None, "young": True,
                    "n_obs": None, "as_of_date": None,
                    "no_data_reason": f"compute error: {e}",
                })

        return {
            "display_only": True,
            "organ": _ORGAN_ID,
            "as_of": date.today().isoformat(),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "freshness": freshness,
            "entities": entities_out,
            "note": "context, not a signal / 舆情参考，非买卖信号",
            "caveat_en": (
                "Narrative/attention context — weakest evidence tier, not a signal. "
                "GDELT measures English-language news volume; entity resolution is imprecise. "
                "Accruing display-only context."
            ),
            "caveat_zh": (
                "舆情/关注度参考 — 最弱证据层，非交易信号。"
                "GDELT 仅统计英文媒体报道量，实体识别精度有限。"
                "仅供参考，持续积累。"
            ),
        }
    except Exception as e:  # noqa: BLE001
        log.error("hk_narrative.snapshot crashed: %s", e)
        return {
            "display_only": True,
            "organ": _ORGAN_ID,
            "as_of": date.today().isoformat(),
            "freshness": "missing",
            "entities": [],
            "error": str(e),
            "note": "context, not a signal / 舆情参考，非买卖信号",
            "caveat_en": "Narrative context unavailable.",
            "caveat_zh": "舆情参考暂不可用。",
        }


# ---------------------------------------------------------------------------
# Forward ledger
# ---------------------------------------------------------------------------

def _ledger_path(data_root: Path | None = None) -> Path:
    if data_root is None:
        data_root = config.data_dir()
    return data_root / _LEDGER_DIR / _LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all ledger rows. Returns [] if file missing or corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Atomic write via temp-file + os.replace."""
    import os
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else "")
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".narrative_ledger_tmp_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stamp(snap: dict, data_root: Path | None = None) -> int:
    """Append one row per (date, ticker) to the forward ledger.
    Idempotent on (ticker, date). Only executes when CN_LANE=asia.
    Returns number of rows appended. Never raises.
    """
    if not _ledger_advance_enabled():
        log.debug("hk_narrative.stamp: ledger advance skipped (CN_LANE != asia)")
        return 0
    try:
        today = snap.get("as_of", date.today().isoformat())
        rows = load_ledger(data_root)
        existing_keys = {(r.get("date"), r.get("ticker")) for r in rows}

        appended = 0
        for ent in snap.get("entities", []):
            ticker = ent.get("ticker")
            if not ticker:
                continue
            key = (today, ticker)
            if key in existing_keys:
                continue  # idempotent

            # Only stamp if we have at least one metric value
            if ent.get("attention_shock_z") is None and ent.get("tone_pctile") is None:
                continue

            row = {
                "date":               today,
                "ticker":             ticker,
                "slug":               ent.get("slug"),
                "name_en":            ent.get("name_en"),
                "attention_shock_z":  ent.get("attention_shock_z"),
                "tone_pctile":        ent.get("tone_pctile"),
                "narrative_state":    ent.get("narrative_state"),
                "asof_freshness":     snap.get("freshness"),
                "organ":              _ORGAN_ID,
            }
            rows.append(row)
            existing_keys.add(key)
            appended += 1

        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("hk_narrative.stamp failed: %s", e)
        return 0


def run(data_root: Path | None = None) -> dict:
    """One-shot: compute snapshot + stamp ledger. Returns snapshot. Never raises."""
    try:
        snap = snapshot(data_root=data_root)
        stamp(snap, data_root=data_root)
        return snap
    except Exception as e:  # noqa: BLE001
        log.error("hk_narrative.run crashed: %s", e)
        return {
            "display_only": True,
            "organ":        _ORGAN_ID,
            "freshness":    "missing",
            "entities":     [],
            "error":        str(e),
            "note":         "context, not a signal / 舆情参考，非买卖信号",
            "caveat_en":    "Narrative context unavailable.",
            "caveat_zh":    "舆情参考暂不可用。",
        }
