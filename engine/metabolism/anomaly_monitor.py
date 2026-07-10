"""engine.metabolism.anomaly_monitor — Anomaly detection (V2-A §3, R-V2-9).

No LLM.  NEVER-RAISE.  Reads fitness_history + organism_state, applies robust-z
over the last K observations per sensor, and emits insight_bus rows when anomalies
are detected.

ROBUST-Z FORMULA (R-V2-9):
    z = (latest - median) / (1.4826 * MAD)

FIRE CONDITION: |z| >= z_thresh AND n >= n_min
HONEST-NULL:    n < n_min → prints "accruing", NO fire

DETECTORS:
  1. Robust-z anomaly per sensor (vs historical distribution)
  2. Band-break vs contract band (if defined in metabolism_anomaly.yml)
  3. Sustained slope-flip (sign change in rolling slope)
  4. Per-artifact staleness SLA (beyond freshness_sla_hours)
  5. CI-red streak (if a CI-status artifact is configured; else skipped)

All thresholds live in config/metabolism_anomaly.yml (IMMUTABLE).
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.metabolism.insight_bus import build_row, append_row, run_all_emitters  # noqa: F401

log = logging.getLogger(__name__)

_ANOMALY_CONFIG_PATH = Path("config") / "metabolism_anomaly.yml"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _load_anomaly_config(root: Path) -> dict[str, Any]:
    """Load config/metabolism_anomaly.yml.  Returns {} on any failure (fail-open)."""
    p = root / _ANOMALY_CONFIG_PATH
    if not p.exists():
        log.warning("anomaly_monitor: config not found at %s", p)
        return {}
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("anomaly_monitor: cannot load config — %s", exc)
        return {}


# ── Robust statistics ──────────────────────────────────────────────────────────

def _robust_z(values: list[float]) -> tuple[float | None, float | None, float | None]:
    """Compute robust z-score for the LATEST value in `values`.

    Returns: (z, median, mad) or (None, None, None) if degenerate.
    values is expected to be in chronological order; the latest is values[-1].
    """
    if len(values) < 2:
        return None, None, None
    try:
        med = statistics.median(values)
        deviations = [abs(v - med) for v in values]
        mad = statistics.median(deviations)
        if mad == 0.0:
            return None, med, 0.0
        z = (values[-1] - med) / (1.4826 * mad)
        return z, med, mad
    except Exception as exc:  # noqa: BLE001
        log.warning("anomaly_monitor._robust_z: failed — %s", exc)
        return None, None, None


def _sustained_slope_flip(values: list[float], window: int = 5) -> bool:
    """Detect a sustained slope flip: sign of early vs late rolling slope reversed.

    Returns True if the sign of the slope changed AND both halves have magnitude
    above min_slope from the config (default 0.05).
    """
    if len(values) < 2 * window:
        return False
    try:
        early = values[:window]
        late = values[-window:]
        early_slope = (early[-1] - early[0]) / max(1, len(early) - 1)
        late_slope = (late[-1] - late[0]) / max(1, len(late) - 1)
        if early_slope == 0.0 or late_slope == 0.0:
            return False
        # Flip = opposite signs
        return (early_slope > 0) != (late_slope > 0)
    except Exception:  # noqa: BLE001
        return False


# ── Fitness history loading ────────────────────────────────────────────────────

def _load_fitness_history_values(
    root: Path, lobe_id: str, sensor_name: str, K: int
) -> list[float]:
    """Load last K numeric fitness history values for a sensor.

    Tries data/metabolism/fitness_history/{lobe_id}.jsonl first;
    falls back to the fitness card's embedded history.
    Returns a list of float values in chronological order.
    """
    values: list[float] = []

    # Try jsonl fitness history
    hist_path = root / "data" / "metabolism" / "fitness_history" / f"{lobe_id}.jsonl"
    if hist_path.exists():
        try:
            rows: list[dict] = []
            for line in hist_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
            # Extract sensor-specific values
            for row in rows[-K:]:
                sensors = row.get("sensors") or {}
                sensor = sensors.get(sensor_name)
                if isinstance(sensor, dict):
                    v = sensor.get("value")
                else:
                    v = sensor
                if v is not None:
                    try:
                        values.append(float(v))
                    except Exception:  # noqa: BLE001
                        continue
        except Exception as exc:  # noqa: BLE001
            log.warning("anomaly_monitor: hist read failed for %s.%s — %s", lobe_id, sensor_name, exc)

    # If not enough from history, try current fitness card
    if len(values) < 2:
        card_path = root / "data" / "metabolism" / "fitness" / f"{lobe_id}.json"
        card = _read_json(card_path)
        if isinstance(card, dict):
            sensors = card.get("sensors") or {}
            sensor = sensors.get(sensor_name)
            if isinstance(sensor, dict):
                v = sensor.get("value")
                if v is not None:
                    try:
                        values.append(float(v))
                    except Exception:  # noqa: BLE001
                        pass

    return values[-K:]  # return at most K values


# ── Per-sensor anomaly check ───────────────────────────────────────────────────

def check_sensor_anomaly(
    lobe_id: str,
    sensor_name: str,
    values: list[float],
    sensor_cfg: dict,
    global_defaults: dict,
    cycle_id: str | None = None,
) -> list[dict]:
    """Check one sensor for anomalies.  Returns insight bus rows (may be empty).

    NEVER-RAISE.
    """
    try:
        K = sensor_cfg.get("K") or global_defaults.get("K") or 20
        n_min = sensor_cfg.get("n_min") or global_defaults.get("n_min") or 5
        z_thresh = sensor_cfg.get("z_thresh") or global_defaults.get("z_thresh") or 2.5
        contract_band = sensor_cfg.get("contract_band")

        rows: list[dict] = []
        n = len(values)

        if n < n_min:
            # Honest accruing — no fire
            log.debug(
                "anomaly_monitor: %s.%s accruing (%d/%d obs)", lobe_id, sensor_name, n, n_min
            )
            return []

        # 1. Robust-z anomaly
        z, med, mad = _robust_z(values)
        if z is not None and abs(z) >= z_thresh:
            rows.append(build_row(
                emitter="anomaly_monitor.robust_z",
                kind="health_transition",
                severity="high" if abs(z) >= z_thresh * 1.5 else "medium",
                entities=[lobe_id, sensor_name],
                summary=(
                    f"Anomaly in {lobe_id}.{sensor_name}: "
                    f"robust_z={z:.2f} (thresh={z_thresh}, latest={values[-1]:.4f}, "
                    f"median={med:.4f})"
                ),
                evidence_ref=f"data/metabolism/fitness/{lobe_id}.json",
                cycle_id=cycle_id,
            ))

        # 2. Band-break (if contract_band is defined)
        if contract_band and isinstance(contract_band, (list, tuple)) and len(contract_band) == 2:
            lo, hi = float(contract_band[0]), float(contract_band[1])
            latest = values[-1]
            if not (lo <= latest <= hi):
                rows.append(build_row(
                    emitter="anomaly_monitor.band_break",
                    kind="health_transition",
                    severity="high",
                    entities=[lobe_id, sensor_name],
                    summary=(
                        f"Band-break in {lobe_id}.{sensor_name}: "
                        f"latest={latest:.4f} outside [{lo}, {hi}]"
                    ),
                    evidence_ref=f"data/metabolism/fitness/{lobe_id}.json",
                    cycle_id=cycle_id,
                ))

        # 3. Sustained slope-flip
        slope_flip_min = global_defaults.get("slope_flip_min") or 0.05
        if n >= 2 * 5 and _sustained_slope_flip(values):
            rows.append(build_row(
                emitter="anomaly_monitor.slope_flip",
                kind="health_transition",
                severity="medium",
                entities=[lobe_id, sensor_name],
                summary=(
                    f"Slope flip detected in {lobe_id}.{sensor_name} "
                    f"over last {n} observations"
                ),
                evidence_ref=f"data/metabolism/fitness/{lobe_id}.json",
                cycle_id=cycle_id,
            ))

        return rows

    except Exception as exc:  # noqa: BLE001
        log.warning("anomaly_monitor.check_sensor_anomaly: %s.%s — %s", lobe_id, sensor_name, exc)
        return []


# ── Staleness SLA check ────────────────────────────────────────────────────────

def check_staleness_sla(root: Path, config: dict, cycle_id: str | None = None) -> list[dict]:
    """Check all metabolism artifacts for staleness vs their SLA.

    NEVER-RAISE.
    """
    try:
        synapse_path = root / "config" / "synapse.yml"
        if not synapse_path.exists():
            return []
        try:
            import yaml  # noqa: PLC0415
            raw = yaml.safe_load(synapse_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("check_staleness_sla: cannot read synapse.yml — %s", exc)
            return []

        artifacts = raw.get("artifacts") or {}
        default_sla = (config.get("defaults") or {}).get("default_sla_hours") or 48
        now = datetime.now(timezone.utc).timestamp()
        rows: list[dict] = []

        for art_id, art in artifacts.items():
            if not isinstance(art, dict):
                continue
            if "metabolism" not in art.get("owner_program", ""):
                continue
            sla_h = art.get("freshness_sla_hours") or default_sla
            path_rel = art.get("path", "")
            if not path_rel:
                continue
            p = root / path_rel
            if not p.exists():
                continue
            try:
                age_h = (now - p.stat().st_mtime) / 3600.0
                if age_h > float(sla_h):
                    rows.append(build_row(
                        emitter="anomaly_monitor.staleness_sla",
                        kind="freshness_sla_breach",
                        severity="medium",
                        entities=[art_id],
                        summary=f"Artifact {art_id} stale: {age_h:.1f}h > SLA {sla_h}h",
                        evidence_ref=path_rel,
                        cycle_id=cycle_id,
                    ))
            except Exception as exc:  # noqa: BLE001
                log.warning("check_staleness_sla: stat for %s failed — %s", p, exc)
                continue
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("check_staleness_sla: failed — %s", exc)
        return []


# ── Main runner ────────────────────────────────────────────────────────────────

def run_anomaly_monitor(
    root: Path | None = None,
    cycle_id: str | None = None,
) -> list[dict]:
    """Run all anomaly checks and append rows to the insight bus.

    Returns list of newly appended rows.
    NEVER-RAISE.
    """
    try:
        repo = _repo_root(root)
        config = _load_anomaly_config(repo)
        defaults = config.get("defaults") or {}
        sensors_cfg = config.get("sensors") or {}

        new_rows: list[dict] = []

        # 1. Per-sensor robust-z (from fitness cards)
        fitness_dir = repo / "data" / "metabolism" / "fitness"
        if fitness_dir.exists():
            for card_path in sorted(fitness_dir.glob("*.json")):
                lobe_id = card_path.stem
                try:
                    card = _read_json(card_path)
                    if not isinstance(card, dict):
                        continue
                    sensors = card.get("sensors") or {}
                    K = defaults.get("K") or 20
                    for sensor_name in sensors:
                        sensor_key = f"{lobe_id}.{sensor_name}"
                        sensor_cfg = sensors_cfg.get(sensor_key) or {}
                        k_use = sensor_cfg.get("K") or K
                        values = _load_fitness_history_values(repo, lobe_id, sensor_name, k_use)
                        rows = check_sensor_anomaly(
                            lobe_id=lobe_id,
                            sensor_name=sensor_name,
                            values=values,
                            sensor_cfg=sensor_cfg,
                            global_defaults=defaults,
                            cycle_id=cycle_id,
                        )
                        for row in rows:
                            if append_row(row, root=repo):
                                new_rows.append(row)
                except Exception as exc:  # noqa: BLE001
                    log.warning("anomaly_monitor: lobe %s failed — %s", lobe_id, exc)
                    continue

        # 2. Staleness SLA check
        try:
            sla_rows = check_staleness_sla(repo, config, cycle_id=cycle_id)
            for row in sla_rows:
                if append_row(row, root=repo):
                    new_rows.append(row)
        except Exception as exc:  # noqa: BLE001
            log.warning("anomaly_monitor: staleness check failed — %s", exc)

        # 3. CI-red streak (only if configured)
        ci_cfg = config.get("ci_red_streak") or {}
        ci_artifact = ci_cfg.get("ci_status_artifact")
        if ci_artifact:
            try:
                ci_path = repo / ci_artifact
                if ci_path.exists():
                    ci_data = _read_json(ci_path)
                    if isinstance(ci_data, dict):
                        streak = ci_data.get("consecutive_failures") or 0
                        streak_thresh = ci_cfg.get("streak_threshold") or 3
                        if streak >= streak_thresh:
                            row = build_row(
                                emitter="anomaly_monitor.ci_red_streak",
                                kind="health_transition",
                                severity="high",
                                entities=["ci"],
                                summary=f"CI red streak: {streak} consecutive failures",
                                evidence_ref=str(ci_artifact),
                                cycle_id=cycle_id,
                            )
                            if append_row(row, root=repo):
                                new_rows.append(row)
            except Exception as exc:  # noqa: BLE001
                log.warning("anomaly_monitor: ci_red_streak check failed — %s", exc)

        return new_rows

    except Exception as exc:  # noqa: BLE001
        log.warning("anomaly_monitor.run_anomaly_monitor: failed — %s", exc)
        return []
