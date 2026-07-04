"""Oracle alert engine — fires when an oracle detection crosses a tier boundary.

MIRRORS engine.subsector_rotation_alerts EXACTLY:
  state-diff across runs, idempotent ids (type:node:bucket), FIRST-run silent seed,
  jsonl + KEEP_DAYS, recent().

Event types (R4-bound — see ORACLE_GAUNTLET_P3_ADJUDICATION.md):
  oracle_onset      — node newly enters an episode at onset tier.
                      Severity: minor.
                      MUST embed the false-start rate in the detail text (R4 mandate).
  oracle_confirmed  — onset episode advances to confirmed tier.
                      Severity: minor.
  oracle_rollover   — a leader (active_out episode at confirmed/undeniable tier) node
                      newly exhausts / rolls over. THIS IS THE LOUDEST EXIT SURFACE.
                      Severity: high.
  oracle_two_sided  — a two-sided rotation is confirmed (both legs active).
                      Severity: high.
  oracle_regime     — breadth aggregate crosses the ORACLE_CFG floor.
                      Severity: high.

All bilingual: headline/detail + _zh variants.
FIRST-RUN SILENT SEED: when no prior state exists, write state without emitting events.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
REGION = "us"

# Breadth floor for oracle_regime event
REGIME_BREADTH_FLOOR = 0.65

# Prior-state keys
_STATE_KEYS = ("tier", "direction", "two_sided", "exhausted")


def _dir() -> Path:
    return config.data_dir() / "oracle"


def _state_path() -> Path:
    return _dir() / "alerts_state.json"


def _path() -> Path:
    return _dir() / "oracle_alerts.jsonl"


def load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def write_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def _ev(
    node: str, ts: str, type_: str, severity: str,
    headline: str, detail: str, context: dict,
    headline_zh: str = "", detail_zh: str = "",
) -> dict:
    """Build an idempotent event dict.  id = type:node:bucket."""
    ts_obj = pd.Timestamp(ts)
    bucket = ts_obj.strftime("%Y-%m-%d")
    return {
        "id": f"oracle:{REGION}:{type_}:{node}:{bucket}",
        "ts": ts_obj.isoformat(),
        "source": "oracle",
        "asset": node,
        "type": type_,
        "severity": severity,
        "headline": headline,
        "detail": detail,
        "headline_zh": headline_zh or headline,
        "detail_zh": detail_zh or detail,
        "context": context,
        "anchor": "#rotation-app",
    }


def _fmt_rate(r: float | None) -> str:
    if r is None:
        return "N/A"
    return f"{r:.0%}"


def compute_events(oracle_state: dict, prior: dict | None) -> list[dict]:
    """Diff the new oracle_state against prior to emit events.

    Seeds silently on the first run (no prior state).

    Parameters
    ----------
    oracle_state : dict
        The payload from engine.oracle.live.build_oracle_state().
    prior : dict | None
        The persisted prior state (load_state()).
    """
    prior = prior or {}
    if not prior:
        # First run — seed silently, never storm.
        return []

    ts = oracle_state.get("asof") or pd.Timestamp.utcnow().isoformat()
    error_rates = (oracle_state.get("disclaimers") or {}).get("error_rates") or {}
    fsr = error_rates.get("false_start_rate")
    otc = error_rates.get("onset_to_confirmed_conversion")
    fsr_str = _fmt_rate(fsr)
    otc_str = _fmt_rate(otc)

    out: list[dict] = []

    # --- Per-episode events ---
    cur_ep_map: dict[str, dict] = {}
    for ep in (oracle_state.get("active_episodes") or []):
        key = f"{ep.get('node','')}__{ep.get('direction','')}"
        # Keep the most-advanced tier per (node, direction)
        _tier_rank = {"undeniable": 3, "confirmed": 2, "onset": 1}
        existing = cur_ep_map.get(key)
        if (existing is None or
                _tier_rank.get(ep.get("tier","onset"), 0) >
                _tier_rank.get(existing.get("tier","onset"), 0)):
            cur_ep_map[key] = ep

    for key, ep in cur_ep_map.items():
        node = ep.get("node", "")
        direction = ep.get("direction", "")
        tier = ep.get("tier", "onset")
        two_sided = ep.get("two_sided", False)
        surv = ep.get("survivorship_flagged", False)
        surv_note = " (survivorship-flagged)" if surv else ""
        surv_note_zh = "（存续性偏差标注）" if surv else ""

        was = prior.get(key) or {}
        was_tier = was.get("tier")

        # --- oracle_onset: newly entered onset tier ---
        if was_tier is None and tier == "onset":
            dir_word = "outflow" if direction == "out" else "inflow"
            dir_word_zh = "流出" if direction == "out" else "流入"
            hl = f"Oracle: {node} onset detected — {dir_word} signal"
            hl_zh = f"Oracle: {node} 启动检测 — {dir_word_zh}信号"
            det = (
                f"Oracle state-machine detected an early rotation {dir_word} episode on {node}"
                f"{surv_note}. Onset tier: earliest, least-certain detection. "
                f"Historical false-start rate {fsr_str} — early signal, not a forecast. "
                f"Onset-to-confirmed conversion: {otc_str}. Context only."
            )
            det_zh = (
                f"Oracle 状态机在 {node} 上检测到早期轮{dir_word_zh}事件{surv_note_zh}。"
                f"启动层级：最早、不确定性最高。历史虚假启动率 {fsr_str} — 早期信号，非预测。"
                f"启动至确认转化率：{otc_str}。仅作参考。"
            )
            out.append(_ev(
                node, ts, "oracle_onset", "minor", hl, det,
                {"tier": tier, "direction": direction, "two_sided": two_sided,
                 "false_start_rate": fsr, "onset_to_confirmed_conversion": otc},
                hl_zh, det_zh,
            ))

        # --- oracle_confirmed: advanced from onset to confirmed ---
        elif was_tier == "onset" and tier in ("confirmed", "undeniable"):
            dir_word = "outflow" if direction == "out" else "inflow"
            dir_word_zh = "流出" if direction == "out" else "流入"
            hl = f"Oracle: {node} rotation {direction} confirmed"
            hl_zh = f"Oracle: {node} 轮动{dir_word_zh}确认"
            det = (
                f"Oracle rotation episode for {node} advanced to confirmed tier"
                f"{surv_note}. A sustained directional RS move has met the hysteresis "
                f"confirmation bar. Onset-to-confirmed conversion: {otc_str}. "
                f"Descriptive read — not a directional forecast."
            )
            det_zh = (
                f"Oracle {node} 轮动{dir_word_zh}已晋升至确认层级{surv_note_zh}。"
                f"相对强度的持续定向运动已满足迟滞确认阈值。"
                f"启动至确认转化率：{otc_str}。描述性读数 — 非方向性预测。"
            )
            out.append(_ev(
                node, ts, "oracle_confirmed", "minor", hl, det,
                {"tier": tier, "direction": direction, "two_sided": two_sided},
                hl_zh, det_zh,
            ))

        # --- oracle_rollover: OUT episode at confirmed/undeniable that was just exhausted ---
        # Exhaustion is detected by absence from active_episodes with prior confirmed/undeniable tier.

        # --- oracle_two_sided: newly two-sided (both legs active at confirmed+) ---
        if two_sided and not was.get("two_sided") and tier in ("confirmed", "undeniable"):
            pair = ep.get("pair") or "counterpart"
            hl = f"Oracle: {node} two-sided rotation confirmed"
            hl_zh = f"Oracle: {node} 双向轮动确认"
            det = (
                f"Oracle detected a two-sided rotation — {node} outflow paired with an "
                f"inflow complex ({pair}). Both legs at confirmed tier{surv_note}. "
                f"Descriptive read — sector outflow and inflow are visible on the tape simultaneously."
            )
            det_zh = (
                f"Oracle 检测到双向轮动 — {node} 流出与流入复合体（{pair}）配对。"
                f"两条腿均处于确认层级{surv_note_zh}。"
                f"描述性读数 — 买卖盘轮动同时可见于行情。"
            )
            out.append(_ev(
                node, ts, "oracle_two_sided", "high", hl, det,
                {"tier": tier, "direction": direction, "pair": pair},
                hl_zh, det_zh,
            ))

    # --- oracle_rollover: prior confirmed/undeniable OUT episodes that are now absent ---
    for key, was in prior.items():
        if was.get("direction") != "out":
            continue
        if was.get("tier") not in ("confirmed", "undeniable"):
            continue
        if key not in cur_ep_map:
            # Was a confirmed leader outflow, now exhausted → ROLLOVER (loudest exit)
            node = key.split("__")[0]
            hl = f"Oracle: {node} leader rollover — outflow episode exhausted"
            hl_zh = f"Oracle: {node} 龙头轮出 — 流出事件已结束"
            det = (
                f"Oracle: the {node} outflow episode that was at {was.get('tier')} tier "
                f"has now exhausted. This is the exit signal the system exists for — "
                f"the loudest output. Context only; not a directional buy signal for the other side."
            )
            det_zh = (
                f"Oracle：{node} 曾处于 {was.get('tier')} 层级的流出事件已结束。"
                f"这是本系统最响亮的退出信号。仅作参考；非另一侧的方向性买入信号。"
            )
            out.append(_ev(
                node, ts, "oracle_rollover", "high", hl, det,
                {"was_tier": was.get("tier"), "direction": "out"},
                hl_zh, det_zh,
            ))

    # --- oracle_regime: breadth crossing the floor ---
    regime = oracle_state.get("regime") or {}
    breadth = regime.get("breadth")
    prior_breadth = prior.get("__regime__", {}).get("breadth")
    if (breadth is not None and
            float(breadth) >= REGIME_BREADTH_FLOOR and
            (prior_breadth is None or float(prior_breadth) < REGIME_BREADTH_FLOOR)):
        n_active = regime.get("n_active_complexes", 0)
        hl = f"Oracle: broad rotation signal — {n_active} active complexes, breadth {breadth:.0%}"
        hl_zh = f"Oracle: 广泛轮动信号 — {n_active} 个活跃复合体，宽度 {breadth:.0%}"
        det = (
            f"Oracle breadth aggregate crossed the {REGIME_BREADTH_FLOOR:.0%} floor with "
            f"{n_active} active rotation complexes. Descriptive — a broad rotation is "
            f"underway based on the confirmed-tier state. Not a directional forecast."
        )
        det_zh = (
            f"Oracle 宽度聚合指标穿越 {REGIME_BREADTH_FLOOR:.0%} 阈值，"
            f"{n_active} 个轮动复合体活跃。描述性读数 — 基于确认层级状态的广泛轮动。非方向性预测。"
        )
        out.append(_ev(
            "regime", ts, "oracle_regime", "high", hl, det,
            {"breadth": breadth, "n_active_complexes": n_active,
             "floor": REGIME_BREADTH_FLOOR},
            hl_zh, det_zh,
        ))

    return out


def _snapshot(oracle_state: dict) -> dict:
    """Build the state dict to persist for the next run's diff."""
    snap: dict = {}
    for ep in (oracle_state.get("active_episodes") or []):
        key = f"{ep.get('node','')}__{ep.get('direction','')}"
        _tier_rank = {"undeniable": 3, "confirmed": 2, "onset": 1}
        existing = snap.get(key)
        if (existing is None or
                _tier_rank.get(ep.get("tier","onset"), 0) >
                _tier_rank.get(existing.get("tier","onset"), 0)):
            snap[key] = {
                "tier": ep.get("tier"),
                "direction": ep.get("direction"),
                "two_sided": ep.get("two_sided", False),
            }
    # Persist regime for breadth-crossing event
    regime = oracle_state.get("regime") or {}
    snap["__regime__"] = {
        "breadth": regime.get("breadth"),
        "n_active_complexes": regime.get("n_active_complexes"),
    }
    return snap


def load_events() -> list[dict]:
    p = _path()
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


def write_events(events: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def recent(days: int = 30, as_of: str | None = None) -> list[dict]:
    evs = load_events()
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def rebuild(oracle_state: dict) -> list[dict]:
    """Diff vs prior state, append+dedup new events, persist state.

    Returns events fired THIS run (empty on the seed run).
    """
    if not oracle_state:
        return []
    prior = load_state()
    new_events = compute_events(oracle_state, prior)

    # Idempotent merge: setdefault keeps FIRST occurrence
    by_id = {e["id"]: e for e in load_events()}
    for e in new_events:
        by_id.setdefault(e["id"], e)
    merged = list(by_id.values())
    if merged:
        ref = max(pd.Timestamp(e["ts"]) for e in merged)
        cutoff = ref - pd.Timedelta(days=KEEP_DAYS)
        merged = [e for e in merged if pd.Timestamp(e["ts"]) >= cutoff]
        merged.sort(key=lambda e: e["ts"])
    write_events(merged)
    write_state(_snapshot(oracle_state))
    return new_events
