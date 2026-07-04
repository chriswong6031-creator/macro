"""Mastermind emit — the actionable, ranked alt-data signal feed for the portfolio bot.

Fuses the three layers into ONE machine-readable contract the Mastermind bot consumes via
its `altdata_flow` lens:

  * the DETERMINISTIC weighted convergence (engine.altdata_signals by_ticker),
  * the OPUS brain's conviction / action / direction + falsifiable thesis (engine.altdata_brain),
  * the INFLUENCE graph affiliations (which important actors are connected to the name),

into a per-ticker ``signal_score`` (0-100), an ``action`` (ACCUMULATE / WATCH / AVOID) and a
``direction`` (long / short / neutral). Per the desk's mandate this IS an actionable axis —
but the bot applies its own risk framework on top, and every brain call is graded vs SPY so
the axis stays calibrated. When the brain is absent (no token), the feed degrades to the
deterministic convergence with conviction derived from the weighted score.

Writes site/altdata/mastermind.json (+ a data copy). The schema is documented inline so the
bot can read it cold.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import config
from engine.altdata_brain import _EXTENDED_PP  # shared constant for extension threshold

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ entry badge helpers

def _load_gate_verdicts(root=None) -> dict:
    """Load site/factordata/signal_gate.json → {ticker: verdict}.  Never raises."""
    try:
        p = (Path(root) if root else config.ROOT) / "site" / "factordata" / "signal_gate.json"
        if not p.exists():
            return {}
        d = json.loads(p.read_text())
        return d.get("verdicts") or {}
    except Exception:  # noqa: BLE001
        return {}


def _entry_badge(ticker: str, gate_verdicts: dict, yahoo_closes) -> str | None:
    """Return tier string ('T1'/'T2'/'T3') if the name is buyable, else None.

    For names already in the 1,662-name gate store, reads the cached verdict.
    For names absent from the store, computes on demand from the yahoo close series
    (if available).  Never raises.
    """
    try:
        from engine.signal_gate import is_buyable, gate as sg_gate
        v = gate_verdicts.get(ticker)
        if v is not None:
            return v.get("tier_cascade") if is_buyable(v) else None
        # on-demand compute for names outside the 1662-name store
        if yahoo_closes is not None:
            v2 = sg_gate(ticker, yahoo_closes)
            return v2.get("tier_cascade") if is_buyable(v2) else None
    except Exception:  # noqa: BLE001
        pass
    return None

SCHEMA = "altdata.mastermind.v1"

# deterministic conviction tiers when the brain hasn't weighed in (weighted_score bands)
_W_HIGH, _W_MED = 1.6, 0.9


def _det_conviction(weighted: float, count: int) -> str:
    if weighted >= _W_HIGH or count >= 4:
        return "high"
    if weighted >= _W_MED or count >= 2:
        return "medium"
    return "low"


def _signal_score(weighted: float, conviction: str, action: str, rs, extended: bool,
                  n_actors: int, source: str = "brain") -> int:
    """Composite 0-100 actionable score. Deterministic weight is the spine; the brain's
    conviction + price confirmation adjust it; extension and a bearish action dock it.

    Conviction bonus is ONLY added for brain-sourced theses — on the deterministic path,
    conviction is derived FROM the same weighted_score that drives the base, so adding it
    back would double-count the same signal.
    """
    base = min(60.0, (weighted or 0) * 32.0)
    # Only add conviction bonus when the brain provided it independently; deterministic
    # conviction is a function of weighted/count so it is already embedded in the base.
    if source == "brain":
        base += {"high": 25, "medium": 12, "low": 0}.get(conviction, 0)
    base += {"ACCUMULATE": 8, "WATCH": 0, "AVOID": -30}.get(action, 0)
    if rs is not None:
        base += max(-8.0, min(10.0, rs / 3.0))        # mild confirm; never the whole story
    if extended:
        base -= 15.0                                   # entry already gone
    base += min(10.0, n_actors * 2.0)                  # influential affiliation adds weight
    return int(max(0, min(100, round(base))))


def _direction(lean: str | None, action: str) -> str:
    if lean == "overweight":
        return "long"
    if lean in ("underweight", "avoid") or action == "AVOID":
        return "short"
    return "long" if action == "ACCUMULATE" else "neutral"


def build_mastermind(by_ticker: dict | None, brain: dict | None, influence: dict | None,
                     picks: dict | None, track: dict | None, root=None, top: int = 30) -> dict:
    """Assemble the ranked actionable feed. Pure; never raises into the pipeline.

    T1 (RS truth): RS is computed per-name DIRECTLY from yahoo adjusted-close parquets,
    bypassing the truncated picks list and the breadth cache.  Names with no yahoo
    parquet receive rs=None + no_price_data=True and never carry a fake RS value.

    T2 (rolling_over demotion): names where off_high_252 ≤ −15% AND 20d ret < 0 AND
    below 50dma are demoted to a separate `broken_signals` list and never appear on the
    main conviction board.  They are surfaced in the output for honest display.

    T3 (entry badge): names with a T1/T2/T3 confluence buy verdict (signal_gate) carry
    `entry_tier` so the UI can show a ⚡ prime-entry chip.
    """
    from engine.altdata_picks import _rs_vs_spy as _rs_direct, _trajectory

    bt = (by_ticker or {}).get("tickers", {}) if by_ticker else {}
    brain_by = {t.get("ticker"): t for t in (brain or {}).get("theses", [])}
    affil_by = {w.get("ticker"): w for w in (influence or {}).get("watch", [])}
    # T1: pre-load gate verdicts for O(1) badge lookup; on-demand fallback for unknowns
    gate_verdicts = _load_gate_verdicts(root)

    signals = []
    broken_signals = []   # rolling-over names: shown separately, never on conviction board

    for tk, rec in bt.items():
        count = int(rec.get("convergence_score", 0) or 0)
        weighted = float(rec.get("weighted_score", 0) or 0)
        th = brain_by.get(tk)
        affil = affil_by.get(tk, {})
        n_actors = int(affil.get("n_actors", 0) or 0)
        # only emit names with a real read: >=2 channels, or a brain thesis, or an affiliation
        if count < 2 and not th and n_actors == 0:
            continue

        # T1: RS TRUTH — compute directly from yahoo parquets; ignore picks truncation
        # Brain thesis may carry a pre-computed rs (already using yahoo); if it has one
        # trust it (it was computed by altdata_brain.gather_evidence → _rs_vs_spy which
        # also now goes yahoo-only).  Otherwise compute fresh per-name.
        brain_rs = (th or {}).get("rs_vs_spy_60d")
        rs = brain_rs if brain_rs is not None else _rs_direct(tk, root)
        # no_price_data flag: True when yahoo parquet is absent (rs is definitively None)
        no_price_data = (rs is None)

        # Brain flag OR deterministic: a name already >_EXTENDED_PP above SPY has no entry left.
        extended = bool((th or {}).get("extended")) or (rs is not None and rs > _EXTENDED_PP)

        # T2: TRAJECTORY — rolling_over demotion (yahoo-only; no_price_data → not rolling_over)
        traj = _trajectory(tk, root)
        rolling_over = traj.get("rolling_over", False)

        source = "brain" if th else "deterministic"
        if th:
            conviction, action, lean = (th.get("conviction", "low"),
                                        th.get("action", "WATCH"), th.get("lean"))
        else:
            conviction, action, lean = _det_conviction(weighted, count), "WATCH", None

        # T3: ENTRY BADGE — load yahoo close only if needed for on-demand gate compute
        yahoo_closes = None
        if tk not in gate_verdicts:
            try:
                from engine.altdata_picks import _yahoo_series
                yahoo_closes = _yahoo_series(tk, root)
            except Exception:  # noqa: BLE001
                pass
        entry_tier = _entry_badge(tk, gate_verdicts, yahoo_closes)

        row = {
            "ticker": tk,
            "signal_score": _signal_score(weighted, conviction, action, rs, extended, n_actors,
                                          source=source),
            "conviction": conviction,
            "action": action,
            "direction": _direction(lean, action),
            "source": source,
            "weighted_score": round(weighted, 2),
            "convergence_score": count,
            "channels": rec.get("channels", []),
            "trump_linked": bool(rec.get("trump_linked")),
            "rs_vs_spy_60d": rs,
            "no_price_data": no_price_data,
            "extended": extended,
            "rolling_over": rolling_over,
            "off_high_252": traj.get("off_high_252"),
            "ret_20d": traj.get("ret_20d"),
            "above_50dma": traj.get("above_50dma"),
            "entry_tier": entry_tier,
            "affiliations": [{"actor": a.get("actor"), "rel": a.get("rel"), "kind": a.get("kind")}
                             for a in affil.get("actors", [])][:6],
            "n_affiliated_actors": n_actors,
            "thesis": (th or {}).get("thesis"),
            "second_order": (th or {}).get("second_order", []),
            "falsifier": (th or {}).get("falsifier"),
            "clamped": (th or {}).get("clamped"),
        }
        # T2: rolling_over names go to the broken strip, never the conviction board
        if rolling_over:
            broken_signals.append(row)
        else:
            signals.append(row)

    signals.sort(key=lambda s: s["signal_score"], reverse=True)
    broken_signals.sort(key=lambda s: s["signal_score"], reverse=True)

    cal = track or {}
    out = {
        "schema": SCHEMA,
        "as_of": (by_ticker or {}).get("as_of"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": (
            "Actionable alt-data axis for the Mastermind bot. Each signal: signal_score "
            "0-100 (composite of weighted convergence + brain conviction + price confirm − "
            "extension), action ∈ {ACCUMULATE,WATCH,AVOID}, direction ∈ {long,short,neutral}, "
            "source ∈ {brain,deterministic}. The bot sizes through its OWN risk framework; "
            "this is an input, not an order. Brain calls are graded vs SPY (see calibration). "
            "An extended name is never ACCUMULATE. trump_linked / affiliations flag actor ties. "
            "rolling_over names (off_high≤−15% AND 20d<0 AND below 50dma) appear in "
            "broken_signals only — crowd attention, NOT entries. "
            "entry_tier (T1/T2/T3) = validated confluence buy gate signal."),
        "regime_read": (brain or {}).get("regime_read"),
        "brain_present": bool(brain and brain.get("theses")),
        # brain_usable = present AND not degraded; downstream (template + bot) should de-rate
        # the conviction board when False — scores are deterministic only, not graded vs SPY.
        "brain_usable": bool(brain and brain.get("theses") and not brain.get("degraded_reason")),
        "calibration": {
            "n_scored": cal.get("scored_total"), "hit_rate": (cal.get("overall") or {}).get("hit_rate"),
            "open": cal.get("open"), "note": cal.get("calibration_note"),
        },
        "n_signals": len(signals),
        "n_broken": len(broken_signals),
        "signals": signals[:top],
        "broken_signals": broken_signals[:top],
        "disclaimer": (brain or {}).get("disclaimer"),
    }
    _write(out, root)
    log.info("altdata mastermind emit: %d signals (%d brain-backed, %d broken/rolling-over, top score %d)",
             len(signals), sum(1 for s in signals if s["source"] == "brain"),
             len(broken_signals),
             signals[0]["signal_score"] if signals else 0)
    return out


def _write(out: dict, root=None) -> None:
    base_data = (config.data_dir() if root is None else (root / "data")) / "altdata"
    base_site = (config.ROOT if root is None else root) / "site" / "altdata"
    for base in (base_data, base_site):
        base.mkdir(parents=True, exist_ok=True)
        (base / "mastermind.json").write_text(json.dumps(out, indent=2, default=str))


def load(root=None) -> dict:
    p = (config.data_dir() if root is None else (root / "data")) / "altdata" / "mastermind.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}
