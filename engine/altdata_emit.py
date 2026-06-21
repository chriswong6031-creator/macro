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

from lib import config

log = logging.getLogger(__name__)

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
                  n_actors: int) -> int:
    """Composite 0-100 actionable score. Deterministic weight is the spine; the brain's
    conviction + price confirmation adjust it; extension and a bearish action dock it."""
    base = min(60.0, (weighted or 0) * 32.0)
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
    """Assemble the ranked actionable feed. Pure; never raises into the pipeline."""
    bt = (by_ticker or {}).get("tickers", {}) if by_ticker else {}
    brain_by = {t.get("ticker"): t for t in (brain or {}).get("theses", [])}
    affil_by = {w.get("ticker"): w for w in (influence or {}).get("watch", [])}
    rs_by = {p.get("ticker"): p.get("rs_vs_spy_60d") for p in (picks or {}).get("picks", [])}

    signals = []
    for tk, rec in bt.items():
        count = int(rec.get("convergence_score", 0) or 0)
        weighted = float(rec.get("weighted_score", 0) or 0)
        th = brain_by.get(tk)
        affil = affil_by.get(tk, {})
        n_actors = int(affil.get("n_actors", 0) or 0)
        # only emit names with a real read: >=2 channels, or a brain thesis, or an affiliation
        if count < 2 and not th and n_actors == 0:
            continue
        rs = (th or {}).get("rs_vs_spy_60d", rs_by.get(tk))
        extended = bool((th or {}).get("extended"))
        if th:
            conviction, action, lean = th.get("conviction", "low"), th.get("action", "WATCH"), th.get("lean")
        else:
            conviction, action, lean = _det_conviction(weighted, count), "WATCH", None
        signals.append({
            "ticker": tk,
            "signal_score": _signal_score(weighted, conviction, action, rs, extended, n_actors),
            "conviction": conviction,
            "action": action,
            "direction": _direction(lean, action),
            "source": "brain" if th else "deterministic",
            "weighted_score": round(weighted, 2),
            "convergence_score": count,
            "channels": rec.get("channels", []),
            "trump_linked": bool(rec.get("trump_linked")),
            "rs_vs_spy_60d": rs,
            "extended": extended,
            "affiliations": [{"actor": a.get("actor"), "rel": a.get("rel"), "kind": a.get("kind")}
                             for a in affil.get("actors", [])][:6],
            "n_affiliated_actors": n_actors,
            "thesis": (th or {}).get("thesis"),
            "second_order": (th or {}).get("second_order", []),
            "falsifier": (th or {}).get("falsifier"),
            "clamped": (th or {}).get("clamped"),
        })
    signals.sort(key=lambda s: s["signal_score"], reverse=True)

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
            "An extended name is never ACCUMULATE. trump_linked / affiliations flag actor ties."),
        "regime_read": (brain or {}).get("regime_read"),
        "brain_present": bool(brain and brain.get("theses")),
        "calibration": {
            "n_scored": cal.get("scored_total"), "hit_rate": (cal.get("overall") or {}).get("hit_rate"),
            "open": cal.get("open"), "note": cal.get("calibration_note"),
        },
        "n_signals": len(signals),
        "signals": signals[:top],
        "disclaimer": (brain or {}).get("disclaimer"),
    }
    _write(out, root)
    log.info("altdata mastermind emit: %d signals (%d brain-backed, top score %d)",
             len(signals), sum(1 for s in signals if s["source"] == "brain"),
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
