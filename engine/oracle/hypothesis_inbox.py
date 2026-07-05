"""Oracle P9 — Hypothesis Inbox: autonomous hypothesis-collection layer.

DESIGN LAW: machines collect facts; they never author hypothesis text.
  Every row in the inbox is PIT-stamped, keep-first idempotent, bilingual, and
  contains ONLY observable facts. A strong model converts inbox rows to
  mechanism stories in batch, offline — never here.

FOUR COLLECTORS (each independently try-wrapped — one crash never blocks):
  1. ANALOGUE_SURPRISE  — Tier-S episodes whose 21d outcome newly matured and
     falls OUTSIDE the analogue envelope (k=7 kNN, leakage law in memory.py).
  2. DETECTION_MISS     — Tier-S + Tier-M nodes with large rs-change (10-session
     |z| > 2, within their tier) but no active or recent episode.
  3. SCREEN_LIVE_DIVERGENCE — registry compounds where sign(live mean) differs
     from sign(screened effect_63d); deduplicated per calendar month.
  4. SENTINEL_MIRROR    — new sentinel_log.jsonl rows mirrored into the inbox so
     the batch-review pass reads ONE place.

OUTPUT FILE:  data/oracle/hypothesis_inbox.jsonl
STATE FILE:   data/oracle/hypothesis_state.json  (graded episode IDs, line counts)

FLOOD LAW: detection-miss capped at 10 rows per night; truncation count logged.
FIRST-RUN SEEDS SILENTLY: no rows written on the very first run (state absent).
TORN-LINE TOLERANCE: reader skips unparseable lines without crashing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INBOX_FILENAME = "hypothesis_inbox.jsonl"
STATE_FILENAME = "hypothesis_state.json"

# Collector thresholds
_ANALOGUE_OUTCOME_HORIZON_SESSIONS = 21   # sessions to call "matured" for surprise check
_ANALOGUE_K = 7
_DETECTION_Z_THRESH = 2.0                 # cross-sectional |z| threshold for detection miss
_DETECTION_WINDOW_SESSIONS = 10           # 10-session rs-change window
_DETECTION_FLOOD_CAP = 10                 # max detection-miss rows per night
_SCREEN_LIVE_MIN_N = 10                   # minimum live_n to compare signs


# ---------------------------------------------------------------------------
# Helpers: JSONL reader (torn-line tolerant) and idempotent writer
# ---------------------------------------------------------------------------

def _read_inbox_ids(inbox_path: Path) -> set[str]:
    """Return all row IDs already in the inbox (keep-first gate). Torn lines skipped."""
    ids: set[str] = set()
    if not inbox_path.exists():
        return ids
    for line in inbox_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            row_id = row.get("id")
            if row_id:
                ids.add(row_id)
        except (json.JSONDecodeError, Exception):  # noqa: BLE001
            pass
    return ids


def _append_rows(inbox_path: Path, rows: list[dict]) -> None:
    """Append rows to the inbox JSONL file (creates parent dirs if needed)."""
    if not rows:
        return
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    with open(inbox_path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def _pit_stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_state(state_path: Path) -> dict:
    """Load hypothesis_state.json; return empty dict on first run."""
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. ANALOGUE SURPRISE
# ---------------------------------------------------------------------------

def _collect_analogue_surprise(
    data_dir: Path,
    inbox_path: Path,
    state: dict,
    is_first_run: bool,
) -> list[dict]:
    """Collector 1: newly matured Tier-S episode outcomes outside analogue envelope.

    LEAKAGE LAW: delegated to engine.oracle.memory.find_analogues (k=7).
    KEEP-FIRST: graded episode IDs tracked in state["graded_episode_ids"].
    FIRST-RUN SEEDS SILENTLY: no rows appended.

    Returns list of new inbox rows added.
    """
    try:
        eps_path = data_dir / "oracle" / "episodes_s.parquet"
        panel_path = data_dir / "oracle" / "panel_s.parquet"
        if not eps_path.exists() or not panel_path.exists():
            log.info("analogue_surprise: episodes_s or panel_s not found — skip")
            return []

        episodes = pd.read_parquet(eps_path)
        panel = pd.read_parquet(panel_path)

        # Only Tier-S episodes — keep all; no tier column (all rows in episodes_s are Tier-S)
        # Filter: 21d outcome NEWLY matured (i.e., outcome_mature_21d is True)
        if "outcome_mature_21d" not in episodes.columns or "outcome_rs_21d" not in episodes.columns:
            log.info("analogue_surprise: outcome columns absent — skip")
            return []

        matured = episodes[episodes["outcome_mature_21d"] == True].copy()
        # Only episodes with onset_date AFTER 2026-07-04 as per task spec
        matured["onset_date"] = pd.to_datetime(matured["onset_date"])
        matured = matured[matured["onset_date"] > pd.Timestamp("2026-07-04")]

        if matured.empty:
            log.info("analogue_surprise: no post-2026-07-04 matured episodes — skip")
            return []

        # State: which episode_ids have already been graded
        graded_ids: set[str] = set(state.get("graded_episode_ids", []))
        existing_inbox_ids = _read_inbox_ids(inbox_path)

        from engine.oracle.memory import find_analogues

        new_rows: list[dict] = []
        newly_graded: list[str] = []

        for _, ep in matured.iterrows():
            ep_id = str(ep.get("episode_id", ""))
            if ep_id in graded_ids:
                continue  # already processed

            # Mark as graded regardless (keep-prior pattern)
            newly_graded.append(ep_id)

            if is_first_run:
                # First run: seed silently — do NOT write rows
                continue

            direction = str(ep["direction"])
            realized_da = float(ep["outcome_rs_21d"]) * (-1.0 if direction == "out" else 1.0)

            # Build query dict for find_analogues
            query = {
                "episode_id": ep_id,
                "onset_date": str(ep["onset_date"])[:10],
                "direction": direction,
                "node": str(ep.get("node", "")),
                "peak_accel_z": float(ep.get("peak_accel_z", np.nan)) if not pd.isna(ep.get("peak_accel_z", np.nan)) else np.nan,
                "cohesion_at_onset": ep.get("cohesion_at_onset"),
                "breadth_at_onset": ep.get("breadth_at_onset"),
                "regime_vix_pctile": ep.get("regime_vix_pctile"),
                "regime_spy_above_200d": ep.get("regime_spy_above_200d"),
            }

            result = find_analogues(query, episodes, panel=panel, k=_ANALOGUE_K)
            analogues = result.get("analogues", [])

            # Build envelope from matured analogue 21d DA outcomes
            analogue_outcomes_21d = [
                a["outcomes"].get("da_21d")
                for a in analogues
                if a["outcomes"].get("mature_21d", False) and a["outcomes"].get("da_21d") is not None
            ]
            if len(analogue_outcomes_21d) < 2:
                # Not enough matured analogues to form an envelope
                continue

            env_lo = float(min(analogue_outcomes_21d))
            env_hi = float(max(analogue_outcomes_21d))

            # Outside envelope?
            if realized_da < env_lo or realized_da > env_hi:
                node = str(ep.get("node", ""))
                onset_date = str(ep["onset_date"])[:10]
                row_id = f"analogue_surprise::{ep_id}"
                if row_id in existing_inbox_ids:
                    continue

                # Collect onset regime tags
                regime_tags: dict[str, Any] = {
                    "vix_pctile": _safe_float(ep.get("regime_vix_pctile")),
                    "spy_above_200d": _safe_float(ep.get("regime_spy_above_200d")),
                    "two_sided": bool(ep.get("two_sided", False)),
                }

                row = {
                    "id": row_id,
                    "type": "analogue_surprise",
                    "pit_stamp": _pit_stamp(),
                    "node": node,
                    "episode_id": ep_id,
                    "realized_da_21d": float(realized_da),
                    "envelope_lo": env_lo,
                    "envelope_hi": env_hi,
                    "k": len(analogues),
                    "n_matured_analogues": len(analogue_outcomes_21d),
                    "onset_date": onset_date,
                    "direction": direction,
                    "onset_regime_tags": regime_tags,
                    "converted": None,
                    "detail_en": (
                        f"Node {node} episode {ep_id}: realized 21d direction-adjusted outcome "
                        f"{realized_da:.4f} is outside analogue envelope "
                        f"[{env_lo:.4f}, {env_hi:.4f}] (k={len(analogues)}, "
                        f"n_matured={len(analogue_outcomes_21d)}). "
                        f"Onset {onset_date}, direction={direction}."
                    ),
                    "detail_zh": (
                        f"节点 {node} 事件 {ep_id}：21日方向调整后实际结果 "
                        f"{realized_da:.4f} 超出类比事件包络 "
                        f"[{env_lo:.4f}, {env_hi:.4f}]（k={len(analogues)}，"
                        f"已成熟={len(analogue_outcomes_21d)}）。"
                        f"起始日 {onset_date}，方向={direction}。"
                    ),
                }
                new_rows.append(row)

        # Update graded_ids in state
        state["graded_episode_ids"] = list(graded_ids | set(newly_graded))

        return new_rows

    except Exception as e:  # noqa: BLE001
        log.error("analogue_surprise: FAILED: %s", e)
        return []


# ---------------------------------------------------------------------------
# 2. DETECTION MISS
# ---------------------------------------------------------------------------

def _collect_detection_miss(
    data_dir: Path,
    inbox_path: Path,
    is_first_run: bool,
) -> list[dict]:
    """Collector 2: nodes with large rs-change but no active/recent episode.

    Cross-sectional z computed WITHIN each tier's own node pool.
    Cap: top 10 by |z| per night (flood law).
    FIRST-RUN SEEDS SILENTLY.

    Returns list of new inbox rows added.
    """
    try:
        if is_first_run:
            return []

        existing_inbox_ids = _read_inbox_ids(inbox_path)

        candidates: list[dict] = []

        for tier_label, panel_file, eps_file in [
            ("s", "panel_s.parquet", "episodes_s.parquet"),
            ("m", "panel_m.parquet", "episodes_m.parquet"),
        ]:
            panel_path = data_dir / "oracle" / panel_file
            eps_path = data_dir / "oracle" / eps_file
            if not panel_path.exists():
                continue

            panel = pd.read_parquet(panel_path)
            if panel.empty:
                continue

            episodes = None
            if eps_path.exists():
                episodes = pd.read_parquet(eps_path)

            # Latest panel date
            all_dates = panel.index.get_level_values("date").unique().sort_values()
            if len(all_dates) < _DETECTION_WINDOW_SESSIONS + 1:
                continue

            latest_date = all_dates[-1]
            window_start_date = all_dates[-_DETECTION_WINDOW_SESSIONS - 1]

            # Compute 10-session rs change per node
            if "rs" not in panel.columns:
                continue

            node_level = panel.index.get_level_values("node").unique()
            rs_changes: dict[str, float] = {}
            panel_context_at_start: dict[str, dict] = {}

            for node in node_level:
                try:
                    np_ = panel.xs(node, level="node")
                except KeyError:
                    continue

                rs_series = np_["rs"].sort_index()
                if latest_date not in rs_series.index or window_start_date not in rs_series.index:
                    continue

                rs_end = float(rs_series.loc[latest_date])
                rs_start = float(rs_series.loc[window_start_date])
                if np.isnan(rs_end) or np.isnan(rs_start):
                    continue

                rs_changes[node] = rs_end - rs_start

                # Panel context at window start date
                ctx: dict[str, Any] = {}
                for col in ["accel_z", "cohesion", "breadth_50", "washout_w"]:
                    if col in np_.columns and window_start_date in np_.index:
                        v = np_.loc[window_start_date, col]
                        ctx[col] = float(v) if not pd.isna(v) else None
                panel_context_at_start[node] = ctx

            if len(rs_changes) < 3:
                continue

            # Cross-sectional z within this tier
            changes_arr = np.array(list(rs_changes.values()))
            mean_chg = float(np.nanmean(changes_arr))
            std_chg = float(np.nanstd(changes_arr))
            if std_chg < 1e-10:
                continue

            for node, chg in rs_changes.items():
                z = (chg - mean_chg) / std_chg
                if abs(z) <= _DETECTION_Z_THRESH:
                    continue

                # Is there an active or recent episode (within 10 sessions)?
                has_episode = False
                if episodes is not None and not episodes.empty:
                    eps_for_node = episodes[episodes["node"] == node].copy()
                    eps_for_node["onset_date"] = pd.to_datetime(eps_for_node["onset_date"])

                    # Check: any episode active (onset within last 10 sessions, not exhausted before window start)
                    window_start_ts = pd.Timestamp(window_start_date)
                    latest_ts = pd.Timestamp(latest_date)

                    active_eps = eps_for_node[
                        (eps_for_node["onset_date"] >= window_start_ts)
                        | (
                            (eps_for_node["onset_date"] < window_start_ts) &
                            (
                                eps_for_node["exhausted_date"].isna() |
                                (pd.to_datetime(eps_for_node["exhausted_date"]) >= window_start_ts)
                            )
                        )
                    ]
                    has_episode = len(active_eps) > 0

                if has_episode:
                    continue

                # Build inbox row id: one per node per day (deduplicated)
                latest_date_str = str(latest_date)[:10]
                row_id = f"detection_miss::{tier_label}::{node}::{latest_date_str}"
                if row_id in existing_inbox_ids:
                    continue

                candidates.append({
                    "id": row_id,
                    "type": "detection_miss",
                    "pit_stamp": _pit_stamp(),
                    "node": node,
                    "tier": tier_label,
                    "move_z": float(z),
                    "rs_chg_10s": float(chg),
                    "panel_date": latest_date_str,
                    "panel_context_at_move_start": panel_context_at_start.get(node, {}),
                    "converted": None,
                    "detail_en": (
                        f"Node {node} (tier={tier_label}): 10-session rs-change {chg:.4f} "
                        f"has cross-sectional z={z:.2f} (threshold={_DETECTION_Z_THRESH}) "
                        f"but no episode active or onset in the window ending {latest_date_str}."
                    ),
                    "detail_zh": (
                        f"节点 {node}（层={tier_label}）：10日RS变化 {chg:.4f} "
                        f"的横截面z值={z:.2f}（阈值={_DETECTION_Z_THRESH}），"
                        f"但在截至 {latest_date_str} 的窗口内无活跃或起始事件。"
                    ),
                })

        # Flood cap: top 10 by |z|
        candidates.sort(key=lambda r: abs(r["move_z"]), reverse=True)
        truncated = len(candidates) - _DETECTION_FLOOD_CAP
        if truncated > 0:
            log.warning(
                "detection_miss: flood cap hit — %d candidates, keeping top %d, "
                "truncated %d",
                len(candidates), _DETECTION_FLOOD_CAP, truncated,
            )
        new_rows = candidates[:_DETECTION_FLOOD_CAP]
        return new_rows

    except Exception as e:  # noqa: BLE001
        log.error("detection_miss: FAILED: %s", e)
        return []


# ---------------------------------------------------------------------------
# 3. SCREEN-LIVE DIVERGENCE
# ---------------------------------------------------------------------------

def _collect_screen_live_divergence(
    data_dir: Path,
    inbox_path: Path,
    is_first_run: bool,
) -> list[dict]:
    """Collector 3: registry compounds where sign(live mean) != sign(screened effect_63d).

    Dedup: one row per compound per calendar month.
    live_n >= 10 required.
    FIRST-RUN SEEDS SILENTLY.

    Returns list of new inbox rows added.
    """
    try:
        if is_first_run:
            return []

        compounds_dir = data_dir / "oracle" / "compounds"
        registry_path = compounds_dir / "registry.jsonl"
        live_ledger_path = compounds_dir / "live_ledger.jsonl"

        if not registry_path.exists():
            log.info("screen_live_divergence: registry.jsonl not found — skip")
            return []

        # Load registry
        registry: list[dict] = []
        for line in registry_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                registry.append(json.loads(line))
            except (json.JSONDecodeError, Exception):  # noqa: BLE001
                pass

        if not registry:
            return []

        # Load live ledger to compute per-compound live mean effect
        live_by_compound: dict[str, list[float]] = {}
        if live_ledger_path.exists():
            for line in live_ledger_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except (json.JSONDecodeError, Exception):  # noqa: BLE001
                    continue
                cid = r.get("compound_id", "")
                if not cid:
                    continue
                if r.get("outcome_mature") is True:
                    ex = r.get("excess_63d")
                    if ex is not None:
                        live_by_compound.setdefault(cid, []).append(float(ex))

        existing_inbox_ids = _read_inbox_ids(inbox_path)
        today_str = date.today().strftime("%Y-%m")  # YYYY-MM for monthly dedup

        new_rows: list[dict] = []

        for compound in registry:
            cid = compound.get("id", "")
            if not cid:
                continue

            live_vals = live_by_compound.get(cid, [])
            live_n = len(live_vals)
            if live_n < _SCREEN_LIVE_MIN_N:
                continue

            screened = compound.get("effect_63d") or compound.get("screened_effect_63d")
            if screened is None:
                continue

            live_mean = float(np.mean(live_vals))

            # Sign divergence check
            if np.sign(live_mean) == np.sign(float(screened)):
                continue

            # Monthly dedup: one row per compound per calendar month
            row_id = f"screen_live_divergence::{cid}::{today_str}"
            if row_id in existing_inbox_ids:
                continue

            new_rows.append({
                "id": row_id,
                "type": "screen_live_divergence",
                "pit_stamp": _pit_stamp(),
                "compound_id": cid,
                "screened_effect_63d": float(screened),
                "live_mean_effect_63d": live_mean,
                "n_live": live_n,
                "converted": None,
                "detail_en": (
                    f"Compound {cid}: live mean excess 63d ({live_mean:.4f}, n={live_n}) "
                    f"sign-diverges from screened effect ({screened:.4f}). "
                    f"Warrants Fable review."
                ),
                "detail_zh": (
                    f"化合物 {cid}：实时平均超额收益63日（{live_mean:.4f}，n={live_n}）"
                    f"符号与筛选效应（{screened:.4f}）相反。"
                    f"需要Fable审核。"
                ),
            })

        return new_rows

    except Exception as e:  # noqa: BLE001
        log.error("screen_live_divergence: FAILED: %s", e)
        return []


# ---------------------------------------------------------------------------
# 4. SENTINEL MIRROR
# ---------------------------------------------------------------------------

def _collect_sentinel_mirror(
    data_dir: Path,
    inbox_path: Path,
    state: dict,
    is_first_run: bool,
) -> list[dict]:
    """Collector 4: new sentinel_log.jsonl rows mirrored into the inbox.

    Tracks prior line count in state["sentinel_log_line_count"].
    FIRST-RUN SEEDS SILENTLY (only seeds the line count).

    Returns list of new inbox rows added.
    """
    try:
        sentinel_log_path = data_dir / "oracle" / "sentinel_log.jsonl"
        if not sentinel_log_path.exists():
            return []

        lines = sentinel_log_path.read_text(encoding="utf-8").splitlines()
        prior_count = int(state.get("sentinel_log_line_count", -1))

        # Update state regardless
        state["sentinel_log_line_count"] = len(lines)

        if is_first_run or prior_count < 0:
            # First run: seed the line count silently
            return []

        new_lines = lines[prior_count:]
        if not new_lines:
            return []

        existing_inbox_ids = _read_inbox_ids(inbox_path)
        new_rows: list[dict] = []

        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                sentinel_row = json.loads(line)
            except (json.JSONDecodeError, Exception):  # noqa: BLE001
                continue

            # Build unique ID from sentinel fields
            ts = sentinel_row.get("ts", "")
            check = sentinel_row.get("check", "")
            level = sentinel_row.get("level", "")
            row_id = f"sentinel::{check}::{ts}"

            if row_id in existing_inbox_ids:
                continue

            inbox_row: dict[str, Any] = {
                "id": row_id,
                "type": "sentinel",
                "pit_stamp": _pit_stamp(),
                "converted": None,
                "detail_en": sentinel_row.get("detail_en", ""),
                "detail_zh": sentinel_row.get("detail_zh", ""),
            }
            # Copy all sentinel fields through
            inbox_row.update({
                k: v for k, v in sentinel_row.items()
                if k not in ("detail_en", "detail_zh")
            })
            new_rows.append(inbox_row)

        return new_rows

    except Exception as e:  # noqa: BLE001
        log.error("sentinel_mirror: FAILED: %s", e)
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_hypothesis_inbox(data_dir: Path, dry_run: bool = False) -> dict[str, int]:
    """Run all four collectors and append results to hypothesis_inbox.jsonl.

    Returns counts by type: {"analogue_surprise": n, "detection_miss": n,
    "screen_live_divergence": n, "sentinel": n, "total": n}.
    """
    oracle_dir = data_dir / "oracle"
    inbox_path = oracle_dir / INBOX_FILENAME
    state_path = oracle_dir / STATE_FILENAME

    state = _load_state(state_path)
    is_first_run = not state  # empty dict = first run

    if is_first_run:
        log.info("hypothesis_inbox: first run detected — seeding silently")
        # Initialize state with sentinel keys so _save_state writes non-empty JSON
        state["graded_episode_ids"] = []
        state["sentinel_log_line_count"] = 0

    counts: dict[str, int] = {
        "analogue_surprise": 0,
        "detection_miss": 0,
        "screen_live_divergence": 0,
        "sentinel": 0,
        "total": 0,
    }

    # --- Collector 1: Analogue Surprise ---
    # Each collector is wrapped in an independent try/except so a crash in one
    # does not block any subsequent collector (flood law § design law).
    try:
        rows_1 = _collect_analogue_surprise(data_dir, inbox_path, state, is_first_run)
    except Exception as e:  # noqa: BLE001
        log.error("analogue_surprise: collector raised: %s", e)
        rows_1 = []
    if rows_1 and not dry_run:
        _append_rows(inbox_path, rows_1)
    counts["analogue_surprise"] = len(rows_1)

    # --- Collector 2: Detection Miss ---
    try:
        rows_2 = _collect_detection_miss(data_dir, inbox_path, is_first_run)
    except Exception as e:  # noqa: BLE001
        log.error("detection_miss: collector raised: %s", e)
        rows_2 = []
    if rows_2 and not dry_run:
        _append_rows(inbox_path, rows_2)
    counts["detection_miss"] = len(rows_2)

    # --- Collector 3: Screen-Live Divergence ---
    try:
        rows_3 = _collect_screen_live_divergence(data_dir, inbox_path, is_first_run)
    except Exception as e:  # noqa: BLE001
        log.error("screen_live_divergence: collector raised: %s", e)
        rows_3 = []
    if rows_3 and not dry_run:
        _append_rows(inbox_path, rows_3)
    counts["screen_live_divergence"] = len(rows_3)

    # --- Collector 4: Sentinel Mirror ---
    try:
        rows_4 = _collect_sentinel_mirror(data_dir, inbox_path, state, is_first_run)
    except Exception as e:  # noqa: BLE001
        log.error("sentinel_mirror: collector raised: %s", e)
        rows_4 = []
    if rows_4 and not dry_run:
        _append_rows(inbox_path, rows_4)
    counts["sentinel"] = len(rows_4)

    counts["total"] = sum(v for k, v in counts.items() if k != "total")

    # Persist updated state
    if not dry_run:
        _save_state(state_path, state)

    log.info(
        "hypothesis_inbox: total=%d (analogue_surprise=%d, detection_miss=%d, "
        "screen_live_divergence=%d, sentinel=%d)%s",
        counts["total"],
        counts["analogue_surprise"],
        counts["detection_miss"],
        counts["screen_live_divergence"],
        counts["sentinel"],
        " [dry-run]" if dry_run else "",
    )

    return counts


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_float(v) -> float | None:
    """Convert to float, None if None or NaN."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None
