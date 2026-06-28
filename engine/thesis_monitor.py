"""Thesis monitor — the deterministic kill-criteria watcher
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §5).

WHY DETERMINISTIC. The LLM analyst (engine/foresight_analyst) writes a thesis ON the desk's
deterministic CONVERGENCE and logs the HEAT it was built on. This watcher re-reads that
convergence each build and fires THESIS-BROKEN / WEAKENING the moment the alignment decays —
with NO LLM in the loop, so it is fully reproducible and cannot hallucinate a break, and it
fires BEFORE the tape confirms (the convergence is the leading read). It does not parse the
LLM's prose; it watches the hard signal the thesis was justified by.

A thesis BREAKS when the convergence that justified it collapses: the physical correlate is
lost, the surfaces fall below a quorum, or heat drops materially. DISPLAY-ONLY; None when
there are no open theses or no current convergence.
"""
from __future__ import annotations

import json
import logging

from lib import config

log = logging.getLogger(__name__)

BROKEN_DROP = 0.25         # absolute heat fall from open => BROKEN
WEAKEN_DROP = 0.12         # absolute heat fall from open => WEAKENING
MIN_SURFACES = 2           # convergence below this quorum => BROKEN (alignment gone)


def _open_theses() -> dict[str, dict]:
    """Latest open thesis per theme from the analyst ledger."""
    p = config.data_dir() / "foresight" / "analyst_theses.jsonl"
    if not p.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in p.read_text().splitlines():
        try:
            e = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        t = e.get("theme")
        if not t:
            continue
        if t not in latest or str(e.get("asof")) > str(latest[t].get("asof")):
            latest[t] = e
    return latest


def _status(opened: dict, heat_now: float, phys_now: bool, n_now: int) -> str:
    h0 = opened.get("heat_at_open") or 0.0
    drop = h0 - (heat_now or 0.0)
    if (opened.get("physical_at_open") and not phys_now) or n_now < MIN_SURFACES or drop >= BROKEN_DROP:
        return "BROKEN"
    n0 = opened.get("n_surfaces_at_open") or 0
    if drop >= WEAKEN_DROP or (n0 - n_now) >= 1:
        return "WEAKENING"
    return "INTACT"


def compute_thesis_monitor(convergence: dict | None, write_state: bool = True) -> dict | None:
    """Re-evaluate each open analyst thesis against the CURRENT convergence. DISPLAY-ONLY.
    None when there are no open theses or no convergence to check against."""
    opened = _open_theses()
    if not opened or not convergence:
        return None
    current = {it.get("theme"): it for it in (convergence.get("ranked") or [])}
    monitored = []
    for theme, o in opened.items():
        now = current.get(theme) or {}
        heat_now = now.get("heat") or 0.0
        phys_now = bool(now.get("physical_confirmed"))
        n_now = now.get("n_signals") or 0
        status = _status(o, heat_now, phys_now, n_now)
        monitored.append({
            "theme": theme,
            "status": status,
            "heat_at_open": o.get("heat_at_open"),
            "heat_now": round(heat_now, 3),
            "n_surfaces_now": n_now,
            "physical_now": phys_now,
            "opened_asof": o.get("asof"),
            "kill_criteria": o.get("kill_criteria"),
        })
    order = {"BROKEN": 0, "WEAKENING": 1, "INTACT": 2}
    monitored.sort(key=lambda m: order.get(m["status"], 3))
    out = {
        "asof": convergence.get("asof"),
        "n_open": len(monitored),
        "n_broken": sum(1 for m in monitored if m["status"] == "BROKEN"),
        "n_weakening": sum(1 for m in monitored if m["status"] == "WEAKENING"),
        "monitored": monitored,
        "note": ("deterministic (no LLM): each thesis is re-checked against the convergence it "
                 "was built on; it BREAKS when that alignment collapses (physical lost, surfaces "
                 "below quorum, or heat drops materially) — before the tape confirms."),
    }
    if write_state:
        try:
            d = config.data_dir() / "foresight"
            d.mkdir(parents=True, exist_ok=True)
            (d / "thesis_monitor.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001
            log.warning("thesis_monitor state write failed: %s", e)
    return out
