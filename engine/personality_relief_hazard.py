"""PSS-RH1 prospective synchronized relief-rally hazard accrual.

The historical PSS-SR3 result selected this adverse hypothesis, so no
historical action can count as confirmation.  This lane replays the exact
outcome-blind SR3 construction over a frozen membership and enrolls only action
closes strictly after the frozen 2026-07-24 boundary.

It is deliberately inert with respect to the product.  The ledger is
operator-research evidence only: it cannot enter, rank, size, gate, alert,
display to users, or promote itself.  Nightly is the sole lifecycle advancer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled
from lib import config

log = logging.getLogger(__name__)

PROGRAM_ID = "PSS-RH1"
FAMILY = "pss_rh1_relief_hazard_prospective"
LEDGER_SCHEMA = "personality_relief_hazard.ledger/v1"
STATE_SCHEMA = "personality_relief_hazard.state/v1"
MANIFEST_SCHEMA = "personality_relief_hazard.manifest/v1"
MEMBERSHIP_SCHEMA = "personality_relief_hazard.membership/v1"
CONSTRUCTION_ID = "pss_sr3_exact_v1_as_adverse_hazard"

EXPECTED_MANIFEST_SHA256 = (
    "0b07345178592032570aeb57c1c54c1cb24b6463a5836431bc7daf5d44b0cc6b"
)
EXPECTED_MEMBERSHIP_SHA256 = (
    "f00c9d70e0c554213d6aa9a82fecc1492bcedc49c04ce36d4a14647f85713baf"
)
EXPECTED_CONSTRUCTION_SHA256 = (
    "3f9be23e75af3079105f33eb930541ffb8ab8d9e28fbd2125c2271d098c1e6dc"
)
NOT_BEFORE_SESSION = "2026-07-24"

LOOKBACK = 60
ANCHOR_COOLDOWN = 21
FORMATION_DAYS = 4
ATR_WINDOW = 14
PEER_MIN = 15
BREADTH_MIN = 0.15
BREADTH_Q_WINDOW = 126
BREADTH_Q_MIN = 63
BREADTH_Q = 0.80
PATH_MAX = 30
SUBJECT_PERSISTENCE = 3
SUBJECT_HOLD_ATR = 0.50
SUBJECT_RECOVERY_ATR = 1.00
SUBJECT_MAX_ATR = 1.75
SUBJECT_BREACH_ATR = 0.50
PEER_PERSISTENCE = 3
PEER_RECOVERY_ATR = 0.50
PEER_TREND_LOOKBACK = 5
LEVEL_FLOOR = 0.50
ACTIVE_FLOOR = 0.50
GRADE_HORIZON = 63
PROX_WINDOW = 31
REBOUND_TARGET = 0.08
ANCHOR_SCAN_START = pd.Timestamp("2020-07-01")

SECTORS = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)

AUTHORITY = {
    "research_only": True,
    "may_enter": False,
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "may_alert": False,
    "may_display_to_users": False,
    "may_auto_promote": False,
}


def _data_root(root: Path | None) -> Path:
    return root if root is not None else config.data_dir()


def _base(root: Path | None) -> Path:
    return _data_root(root) / "personality_timing"


def manifest_path(root: Path | None = None) -> Path:
    return _base(root) / "relief_hazard_manifest_v1.json"


def membership_path(root: Path | None = None) -> Path:
    return _base(root) / "relief_hazard_membership_v1.json"


def ledger_path(root: Path | None = None) -> Path:
    return _base(root) / "relief_hazard.jsonl"


def state_path(root: Path | None = None) -> Path:
    return _base(root) / "relief_hazard_state.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_registration(root: Path | None = None) -> dict[str, Any] | None:
    """Load the frozen manifest and membership or make the lane inert."""
    try:
        manifest_file = manifest_path(root)
        membership_file = membership_path(root)
        if _sha256(manifest_file) != EXPECTED_MANIFEST_SHA256:
            raise ValueError("manifest hash mismatch")
        if _sha256(membership_file) != EXPECTED_MEMBERSHIP_SHA256:
            raise ValueError("membership hash mismatch")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        membership = json.loads(membership_file.read_text(encoding="utf-8"))
        if manifest.get("schema") != MANIFEST_SCHEMA:
            raise ValueError("manifest schema mismatch")
        if membership.get("schema") != MEMBERSHIP_SCHEMA:
            raise ValueError("membership schema mismatch")
        if manifest.get("program_id") != PROGRAM_ID:
            raise ValueError("program id mismatch")
        if manifest.get("family") != FAMILY:
            raise ValueError("family mismatch")
        if manifest.get("not_before_session") != NOT_BEFORE_SESSION:
            raise ValueError("prospective boundary mismatch")
        if membership.get("not_before_session") != NOT_BEFORE_SESSION:
            raise ValueError("membership boundary mismatch")
        if manifest.get("construction_sha256") != EXPECTED_CONSTRUCTION_SHA256:
            raise ValueError("construction hash declaration mismatch")
        if _canonical_sha256(manifest.get("construction")) != EXPECTED_CONSTRUCTION_SHA256:
            raise ValueError("construction content mismatch")
        member_spec = manifest.get("membership") or {}
        if member_spec.get("sha256") != EXPECTED_MEMBERSHIP_SHA256:
            raise ValueError("manifest membership binding mismatch")
        members = membership.get("members") or []
        if len(members) != 799 or member_spec.get("ticker_count") != len(members):
            raise ValueError("frozen membership count mismatch")
        if manifest.get("authority") != AUTHORITY:
            raise ValueError("authority fence mismatch")
        return {"manifest": manifest, "membership": membership}
    except Exception as exc:  # noqa: BLE001 — invalid registration must fail inert
        log.warning("personality_relief_hazard: registration rejected (%s)", exc)
        return None


def clean_index(frame: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    frame = frame.copy()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def _load_ohlcv(
    root: Path | None,
    sym: str,
    *,
    through: pd.Timestamp | None = None,
) -> pd.DataFrame | None:
    path = _data_root(root) / "baskets" / "ohlcv" / f"{sym}.parquet"
    try:
        frame = clean_index(pd.read_parquet(path))
        frame = frame[["open", "high", "low", "close"]].astype(float)
        if through is not None:
            frame = frame.loc[frame.index <= through]
        return frame if not frame.empty else None
    except Exception as exc:  # noqa: BLE001 — per-name failure is censused
        log.debug("personality_relief_hazard: %s OHLC unavailable (%s)", sym, exc)
        return None


def atr14_prior(frame: pd.DataFrame) -> pd.Series:
    prior_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prior_close).abs(),
            (frame["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean().shift(1)


def greedy_anchors(candidate: np.ndarray) -> np.ndarray:
    accepted: list[int] = []
    next_allowed = 0
    for index in np.flatnonzero(np.asarray(candidate, dtype=bool)):
        if index >= next_allowed:
            accepted.append(int(index))
            next_allowed = int(index) + ANCHOR_COOLDOWN + 1
    return np.asarray(accepted, dtype=int)


def ex_self_breadth(
    new_low: pd.DataFrame,
    valid: pd.DataFrame,
    sym: str,
) -> tuple[pd.Series, pd.Series]:
    numerator = new_low.sum(axis=1) - new_low[sym].astype(int)
    denominator = valid.sum(axis=1) - valid[sym].astype(int)
    breadth = numerator / denominator.where(denominator > 0)
    return breadth.astype(float), denominator.astype(float)


def first_subject_recovery(
    close: np.ndarray,
    low: np.ndarray,
    anchor: int,
    atr_anchor: float,
    reference_low: float,
) -> int | None:
    """Return the first fully observable three-session held recovery."""
    confirm = anchor + FORMATION_DAYS - 1
    latest = min(len(close) - 1, confirm + PATH_MAX)
    start = confirm + SUBJECT_PERSISTENCE - 1
    for action in range(start, latest + 1):
        window = slice(action - SUBJECT_PERSISTENCE + 1, action + 1)
        closes = close[window]
        lows = low[window]
        if not np.isfinite(closes).all() or not np.isfinite(lows).all():
            continue
        if np.min(closes) < reference_low + SUBJECT_HOLD_ATR * atr_anchor:
            continue
        if np.min(lows) < reference_low - SUBJECT_BREACH_ATR * atr_anchor:
            continue
        depth = (close[action] - reference_low) / atr_anchor
        if SUBJECT_RECOVERY_ATR <= depth <= SUBJECT_MAX_ATR:
            return action
    return None


def peer_recovery_minima(
    close: pd.DataFrame,
    low: pd.DataFrame,
    atr: pd.DataFrame,
    sym: str,
    anchor: int,
    action: int,
) -> tuple[tuple[float, float] | None, str]:
    """Return persistent passive and active ex-self recovery breadth."""
    confirm = anchor + FORMATION_DAYS - 1
    peer_reference = low.iloc[anchor : confirm + 1].min(axis=0)
    peer_atr = atr.iloc[anchor]
    valid_reference = peer_reference.notna() & peer_atr.notna() & peer_atr.gt(0)
    valid_reference.loc[sym] = False
    if int(valid_reference.sum()) < PEER_MIN:
        return None, "peer_reference_count"

    level_values: list[float] = []
    active_values: list[float] = []
    threshold = peer_reference + PEER_RECOVERY_ATR * peer_atr
    for position in range(action - PEER_PERSISTENCE + 1, action + 1):
        level_valid = valid_reference & close.iloc[position].notna()
        if int(level_valid.sum()) < PEER_MIN:
            return None, "peer_action_count"
        level = close.iloc[position].ge(threshold) & level_valid
        level_values.append(float(level.sum() / level_valid.sum()))

        prior_position = position - PEER_TREND_LOOKBACK
        if prior_position < 0:
            return None, "peer_trend_history"
        active_valid = (
            valid_reference
            & close.iloc[position].notna()
            & close.iloc[prior_position].notna()
        )
        if int(active_valid.sum()) < PEER_MIN:
            return None, "peer_action_count"
        active = (
            close.iloc[position].ge(threshold)
            & close.iloc[position].gt(close.iloc[prior_position])
            & active_valid
        )
        active_values.append(float(active.sum() / active_valid.sum()))
    return (float(min(level_values)), float(min(active_values))), "ok"


def severity_band(value: float) -> str:
    if 0.15 <= value < 0.30:
        return "p1"
    if value < 0.50:
        return "p2"
    return "p3"


def delay_band(value: int) -> str:
    if value <= 10:
        return "d1"
    if value <= 20:
        return "d2"
    return "d3"


def distance_band(value: float) -> str:
    if value < 1.25:
        return "x1"
    if value < 1.50:
        return "x2"
    return "x3"


def classify_path(level_min: float, active_min: float) -> str:
    if level_min < LEVEL_FLOOR:
        return "weak_level"
    if active_min >= ACTIVE_FLOOR:
        return "relief_hazard"
    return "level_control"


def _sector_frames(
    root: Path | None,
    names: list[str],
    through: pd.Timestamp,
) -> tuple[pd.DatetimeIndex, dict[str, pd.DataFrame], list[str]]:
    loaded: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for sym in names:
        frame = _load_ohlcv(root, sym, through=through)
        if frame is None:
            missing.append(sym)
        else:
            loaded[sym] = frame
    if not loaded:
        return pd.DatetimeIndex([]), {}, missing
    values: set[pd.Timestamp] = set()
    for frame in loaded.values():
        values.update(frame.index[frame.index >= pd.Timestamp("2018-01-01")])
    index = pd.DatetimeIndex(sorted(values))
    return index, {sym: frame.reindex(index) for sym, frame in loaded.items()}, missing


def _scan_paths(
    registration: dict[str, Any],
    root: Path | None,
    through: pd.Timestamp,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Detect exact SR3 paths using action-close information only."""
    members = registration["membership"]["members"]
    ticker_sector = {
        str(row["sym"]): str(row["sector"])
        for row in members
        if row.get("sector") in SECTORS
    }
    by_sector: dict[str, list[str]] = {}
    for sym, sector in ticker_sector.items():
        by_sector.setdefault(sector, []).append(sym)

    cutoff = pd.Timestamp(NOT_BEFORE_SESSION)
    rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    loaded_count = 0
    anchor_count = 0
    prospective_anchor_count = 0

    for sector in SECTORS:
        names = sorted(by_sector.get(sector, []))
        index, data, missing = _sector_frames(root, names, through)
        reasons["missing_ohlcv"] += len(missing)
        loaded_count += len(data)
        if len(data) <= PEER_MIN:
            reasons["too_few_sector_peers"] += len(data)
            continue

        close = pd.DataFrame(
            {sym: frame["close"] for sym, frame in data.items()},
            index=index,
        )
        low = pd.DataFrame(
            {sym: frame["low"] for sym, frame in data.items()},
            index=index,
        )
        atr = pd.DataFrame(
            {sym: atr14_prior(frame) for sym, frame in data.items()},
            index=index,
        )
        prior_low = close.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).min()
        valid = close.notna() & prior_low.notna()
        new_low = close.le(prior_low) & valid

        for sym in sorted(data):
            breadth, peer_count = ex_self_breadth(new_low, valid, sym)
            threshold = (
                breadth.shift(1)
                .rolling(BREADTH_Q_WINDOW, min_periods=BREADTH_Q_MIN)
                .quantile(BREADTH_Q)
            )
            candidates = (
                close[sym].le(prior_low[sym])
                & breadth.ge(BREADTH_MIN)
                & breadth.ge(threshold)
                & peer_count.ge(PEER_MIN)
                & (index >= ANCHOR_SCAN_START)
            ).fillna(False)
            anchors = greedy_anchors(candidates.to_numpy(dtype=bool))
            anchor_count += len(anchors)

            sym_close = close[sym].to_numpy(dtype=float)
            sym_low = low[sym].to_numpy(dtype=float)
            sym_atr = atr[sym].to_numpy(dtype=float)
            breadth_array = breadth.to_numpy(dtype=float)
            peer_count_array = peer_count.to_numpy(dtype=float)

            for anchor_value in anchors:
                anchor = int(anchor_value)
                confirm = anchor + FORMATION_DAYS - 1
                if confirm >= len(index):
                    reasons["incomplete_formation"] += 1
                    continue
                latest_possible = min(len(index) - 1, confirm + PATH_MAX)
                if index[latest_possible] <= cutoff:
                    continue
                prospective_anchor_count += 1
                formation = slice(anchor, confirm + 1)
                if np.any(peer_count_array[formation] < PEER_MIN):
                    reasons["formation_peer_count"] += 1
                    continue
                values = np.asarray(
                    [
                        sym_atr[anchor],
                        np.nanmin(sym_low[formation]),
                        breadth_array[anchor],
                        np.nanmax(breadth_array[formation]),
                    ],
                    dtype=float,
                )
                if not np.isfinite(values).all() or values[0] <= 0:
                    reasons["invalid_formation"] += 1
                    continue
                atr_anchor, reference_low, anchor_breadth, peer_peak = values
                action = first_subject_recovery(
                    sym_close,
                    sym_low,
                    anchor,
                    float(atr_anchor),
                    float(reference_low),
                )
                if action is None:
                    reasons["no_subject_recovery"] += 1
                    continue
                action_date = index[action]
                if action_date <= cutoff:
                    reasons["pre_cutoff_action"] += 1
                    continue
                minima, reason = peer_recovery_minima(
                    close,
                    low,
                    atr,
                    sym,
                    anchor,
                    action,
                )
                if minima is None:
                    reasons[reason] += 1
                    continue
                level_min, active_min = minima
                close_depth = float(
                    (sym_close[action] - reference_low) / atr_anchor
                )
                rows.append(
                    {
                        "kind": "event",
                        "schema": LEDGER_SCHEMA,
                        "program_id": PROGRAM_ID,
                        "family": FAMILY,
                        "construction_id": CONSTRUCTION_ID,
                        "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
                        "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
                        "authority": dict(AUTHORITY),
                        "sym": sym,
                        "sector": sector,
                        "anchor_date": str(index[anchor].date()),
                        "formation_confirm": str(index[confirm].date()),
                        "action_date": str(action_date.date()),
                        # Preserve the source floats used by the later outcome
                        # ruler; presentation rounding must never move a rebound
                        # target or frozen breach boundary.
                        "action_close": float(sym_close[action]),
                        "atr_anchor": float(atr_anchor),
                        "reference_low": float(reference_low),
                        "anchor_breadth": round(float(anchor_breadth), 10),
                        "formation_peer_peak": round(float(peer_peak), 10),
                        "level_min": round(level_min, 10),
                        "active_min": round(active_min, 10),
                        "group": classify_path(level_min, active_min),
                        "delay_sessions": int(action - confirm),
                        "close_depth_atr": round(close_depth, 10),
                        "severity_band": severity_band(float(peer_peak)),
                        "delay_band": delay_band(int(action - confirm)),
                        "distance_band": distance_band(close_depth),
                        "grade": None,
                        "grade_as_of": None,
                    }
                )

    rows.sort(
        key=lambda row: (
            row["action_date"],
            row["sector"],
            row["sym"],
            row["anchor_date"],
        )
    )
    census = {
        "frozen_members": len(ticker_sector),
        "loaded_members": loaded_count,
        "missing_members": int(reasons["missing_ohlcv"]),
        "anchors": anchor_count,
        "prospective_candidate_anchors": prospective_anchor_count,
        "detected_post_cutoff_paths": len(rows),
        "reasons": dict(sorted(reasons.items())),
    }
    return rows, census


def _exact_pos(index: pd.DatetimeIndex, date_text: str) -> int | None:
    position = int(index.searchsorted(pd.Timestamp(date_text)))
    if position >= len(index) or str(index[position].date()) != str(date_text)[:10]:
        return None
    return position


def _competing_risk(
    close: np.ndarray,
    low: np.ndarray,
    action: int,
    breach_level: float,
) -> dict[str, Any]:
    """Fixed-denominator race; a same-session breach wins."""
    if action + GRADE_HORIZON >= len(close):
        return {
            "rebound8_first": False,
            "breach_first": False,
            "unresolved": True,
            "resolution_day": None,
        }
    target = close[action] * (1.0 + REBOUND_TARGET)
    for day in range(1, GRADE_HORIZON + 1):
        position = action + day
        if not np.isfinite(close[position]) or not np.isfinite(low[position]):
            continue
        if low[position] < breach_level:
            return {
                "rebound8_first": False,
                "breach_first": True,
                "unresolved": False,
                "resolution_day": day,
            }
        if close[position] >= target:
            return {
                "rebound8_first": True,
                "breach_first": False,
                "unresolved": False,
                "resolution_day": day,
            }
    return {
        "rebound8_first": False,
        "breach_first": False,
        "unresolved": True,
        "resolution_day": None,
    }


def _grade_row(frame: pd.DataFrame, row: dict[str, Any]) -> dict[str, Any] | None:
    index = pd.DatetimeIndex(frame.index)
    action = _exact_pos(index, str(row.get("action_date") or ""))
    if action is None or action + GRADE_HORIZON >= len(frame):
        return None
    close = frame["close"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    entry = float(row["action_close"])
    forward = close[action + 1 : action + GRADE_HORIZON + 1]
    if len(forward) != GRADE_HORIZON or not np.isfinite(forward).all():
        return None
    mae63 = (float(np.min(forward)) / entry - 1.0) * 100.0
    prox: float | None = None
    tdt: int | None = None
    w5: bool | None = None
    called: bool | None = None
    if action >= PROX_WINDOW:
        local = close[action - PROX_WINDOW : action + PROX_WINDOW + 1]
        if len(local) == 2 * PROX_WINDOW + 1 and np.isfinite(local).all():
            trough = float(np.min(local))
            prox = (entry / trough - 1.0) * 100.0
            tdt = int(np.argmin(local)) - PROX_WINDOW
            w5 = bool(prox <= 5.0)
            called = bool(-2 <= tdt <= 5)
    risk = _competing_risk(
        close,
        low,
        action,
        float(row["reference_low"])
        - SUBJECT_BREACH_ATR * float(row["atr_anchor"]),
    )
    return {
        "matured_on": str(index[action + GRADE_HORIZON].date()),
        "mae63": round(mae63, 6),
        "tail10": bool(mae63 <= -10.0),
        "prox": round(prox, 6) if prox is not None else None,
        "w5": w5,
        "called": called,
        "tdt": tdt,
        **risk,
    }


def _event_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("construction_id") or ""),
        str(row.get("sym") or ""),
        str(row.get("anchor_date") or ""),
        str(row.get("action_date") or ""),
    )


def _load_events(root: Path | None) -> list[dict[str, Any]]:
    path = ledger_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001 — tolerate one torn line
            continue
        if row.get("kind") == "event" and row.get("schema") == LEDGER_SCHEMA:
            rows.append(row)
    return rows


def _atomic_write(path: Path, text: str, *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=prefix,
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _rewrite_ledger(root: Path | None, events: list[dict[str, Any]]) -> None:
    registration = {
        "kind": "registration",
        "schema": LEDGER_SCHEMA,
        "program_id": PROGRAM_ID,
        "family": FAMILY,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
        "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
        "not_before_session": NOT_BEFORE_SESSION,
        "event_rows_at_launch": 0,
        "authority": dict(AUTHORITY),
    }
    header = (
        f"# PSS-RH1 prospective relief-hazard ledger — schema {LEDGER_SCHEMA}\n"
        "# Event action_date must be strictly after 2026-07-24. No historical backfill.\n"
        "# Nightly is the sole lifecycle advancer. Keep-first rows; one 63-session grade.\n"
        "# OPERATOR RESEARCH ONLY — no entry/rank/size/gate/alert/user-display authority.\n"
    )
    rows = [registration, *events]
    body = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        for row in rows
    )
    _atomic_write(
        ledger_path(root),
        header + body + "\n",
        prefix=".relief_hazard.",
    )


def _write_state(root: Path | None, state: dict[str, Any]) -> None:
    _atomic_write(
        state_path(root),
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        prefix=".relief_hazard_state.",
    )


def _coverage_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    matured = [row for row in events if row.get("grade") is not None]
    primary = [
        row
        for row in matured
        if row.get("group") in {"relief_hazard", "level_control"}
    ]
    action_dates = sorted(str(row.get("action_date")) for row in primary)
    months = sorted({date[:7] for date in action_dates})
    span = (
        int((pd.Timestamp(action_dates[-1]) - pd.Timestamp(action_dates[0])).days)
        if len(action_dates) >= 2
        else 0
    )
    groups = Counter(str(row.get("group")) for row in matured)
    minimums = {
        "matured_primary_rows": len(primary),
        "unique_names": len({str(row.get("sym")) for row in primary}),
        "relief_hazard_rows": groups["relief_hazard"],
        "level_control_rows": groups["level_control"],
        "distinct_action_months": len(months),
        "action_date_span_days": span,
        # Informative strata are intentionally computed only by the future
        # adjudicator; this lane never opens the outcome-bearing inference tape.
        "informative_exact_strata": None,
    }
    required = {
        "matured_primary_rows": 500,
        "unique_names": 250,
        "relief_hazard_rows": 100,
        "level_control_rows": 100,
        "distinct_action_months": 12,
        "action_date_span_days": 365,
        "informative_exact_strata": 30,
    }
    count_ready = all(
        minimums[key] is not None and int(minimums[key]) >= value
        for key, value in required.items()
        if key != "informative_exact_strata"
    )
    return {
        "status": "locked_minimums",
        "sole_read_executed": False,
        "count_and_clock_minimums_met": count_ready,
        "observed": minimums,
        "required": required,
        "note": (
            "No interim effect estimates. Informative strata and outcomes are "
            "opened only by the separately reviewed sole adjudication."
        ),
    }


def update(root: Path | None = None, *, as_of: str | None = None) -> dict | None:
    """Enroll post-cutoff paths and advance exactly-matured grades on nightly."""
    try:
        observed_as_of = as_of or pd.Timestamp.now("UTC").date().isoformat()
        through = pd.Timestamp(observed_as_of)
        gate_open = nightly_advance_enabled()
        registration = load_registration(root)
        existing = _load_events(root)
        appended = 0
        advanced = 0
        rejected_pre_cutoff = 0
        scan_census: dict[str, Any] = {}

        if gate_open and registration is not None:
            detected, scan_census = _scan_paths(registration, root, through)
            seen = {_event_key(row) for row in existing}
            for row in detected:
                # Independent defense against a scanner regression or test double.
                if str(row.get("action_date") or "") <= NOT_BEFORE_SESSION:
                    rejected_pre_cutoff += 1
                    continue
                key = _event_key(row)
                if key in seen:
                    continue
                row["observed_as_of"] = observed_as_of
                row["enrolled_as_of"] = observed_as_of
                row["last_advanced_as_of"] = None
                existing.append(row)
                seen.add(key)
                appended += 1

            for row in existing:
                if row.get("grade") is not None:
                    continue
                frame = _load_ohlcv(
                    root,
                    str(row.get("sym") or ""),
                    through=through,
                )
                if frame is None:
                    continue
                grade = _grade_row(frame, row)
                if grade is None:
                    continue
                row["grade"] = grade
                row["grade_as_of"] = observed_as_of
                row["last_advanced_as_of"] = observed_as_of
                advanced += 1

        if gate_open and registration is not None and (appended or advanced):
            existing.sort(
                key=lambda row: (
                    row.get("action_date") or "",
                    row.get("sector") or "",
                    row.get("sym") or "",
                    row.get("anchor_date") or "",
                )
            )
            _rewrite_ledger(root, existing)

        groups = Counter(str(row.get("group")) for row in existing)
        matured = sum(row.get("grade") is not None for row in existing)
        action_dates = sorted(
            str(row.get("action_date"))
            for row in existing
            if row.get("action_date")
        )
        state = {
            "schema": STATE_SCHEMA,
            "program_id": PROGRAM_ID,
            "family": FAMILY,
            "status": "prospective_accrual_only",
            "authority": dict(AUTHORITY),
            "as_of": observed_as_of,
            "generated_utc": pd.Timestamp.now("UTC").isoformat(),
            "gate_open": gate_open,
            "registration_ok": registration is not None,
            "not_before_session": NOT_BEFORE_SESSION,
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
            "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
            "ledger": {
                "events": len(existing),
                "primary_events": groups["relief_hazard"] + groups["level_control"],
                "relief_hazard": groups["relief_hazard"],
                "level_control": groups["level_control"],
                "weak_level_diagnostic": groups["weak_level"],
                "matured": matured,
                "ungraded": len(existing) - matured,
                "appended_today": appended,
                "advanced_today": advanced,
                "rejected_pre_cutoff_today": rejected_pre_cutoff,
                "earliest_action": action_dates[0] if action_dates else None,
                "latest_action": action_dates[-1] if action_dates else None,
            },
            "scan_census": scan_census,
            "decision_read": _coverage_state(existing),
            "consumers": [],
            "note": (
                "Exact PSS-SR3 construction accruing prospectively as an adverse "
                "relief-rally hypothesis. Historical SR3 rows count as zero. "
                "Operator research only; no entry, rank, size, gate, alert, "
                "user-display, or auto-promotion authority."
            ),
        }
        _write_state(root, state)
        if appended or advanced:
            log.info(
                "personality_relief_hazard: +%d prospective events, +%d grades",
                appended,
                advanced,
            )
        return state
    except Exception as exc:  # noqa: BLE001 — additive research lane never breaks engine
        log.warning("personality_relief_hazard update failed (%s)", exc)
        return None
