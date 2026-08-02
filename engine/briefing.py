"""DAILY BRIEFING — the brain-facing transmission layer over the intelligence bundle.

The intelligence bundle (engine/intelligence.py → site/intelligence/by_ticker.json) is
the per-ticker FACTS store: four facets per name, side by side. That is the right shape
for "tell me everything about ticker X", but the wrong shape for "what should I look at
today" — the Mastermind brain (Claude Opus) should not have to scan every ticker and
re-derive priority on each pull.

This module reduces the bundle to a RANKED, NARRATIVE-READY briefing optimized for an LLM
reader:

  • priority_queue — the top names by transmission priority (confidence × strength), each
    with a one-line deterministic situation, the directional lean, the concrete evidence,
    the active source mix, and the falsifier. No prose is invented here; the situation line
    is the same FACTS-derived read the intelligence layer already computed.
  • divergences — the subset where demand (the tape) and supply (smart-money / radar) point
    OPPOSITE ways. These are the highest-information items — an LLM should spend its depth
    budget here, not on names where everything already agrees.
  • macro_context — regime label, tape tone, and the next scheduled catalysts, so the brain
    frames every name against the backdrop instead of in a vacuum.

PURE + DEGRADE-NEVER-RAISE + CONTEXT-ONLY. Nothing here scores or sizes; it republishes and
ranks already-built artifacts so one cheap pull gives the brain a triaged worklist.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "intelligence.briefing.v1"

DEFAULT_TOP = 25

DISCLAIMER = (
    "Context only. A ranked triage of the per-ticker intelligence bundle for the reasoning "
    "brain — priority = facet agreement × signal strength, never a position size. The "
    "divergence block (tape vs smart-money) is where the edge lives; spend depth there. The "
    "brain sizes through its own risk framework; nothing here sizes alone."
)

HOW_TO_USE = (
    "Read macro_context first to frame the day. Triage priority_queue top-down: high "
    "confidence + high strength = act-worthy; low confidence = watch. The divergences list "
    "is the subset worth deep research — demand and supply disagree, so the consensus is "
    "incomplete. Pull the full 4-facet record for any name via the by_ticker bundle. Every "
    "item carries its change-this-read condition — track it; a thesis you cannot kill is "
    "not a thesis."
)

# read labels where demand-tape and supply/ smart-money point opposite ways
_DIVERGENT_LABELS = {"early_edge", "crowded_top"}


def _facts(v: dict) -> dict:
    """Flatten the four facets into a compact evidence block for the brain."""
    radar = v.get("radar") or {}
    alt = v.get("alt") or {}
    news = v.get("news") or {}
    standout = v.get("standout") or {}
    return {
        "radar_state": radar.get("state"),
        "radar_edge": radar.get("edge_score"),
        "alt_score": alt.get("signal_score"),
        "alt_action": alt.get("action"),
        "alt_channels": alt.get("channels"),
        "news_lean": news.get("sentiment_lean"),
        "news_n_recent": news.get("n_recent"),
        "standout_label": standout.get("label") or standout.get("state"),
        "standout_conviction": standout.get("conviction"),
    }


def _item(v: dict) -> dict:
    """One priority_queue / divergence entry — the brain-ready view of a ticker."""
    brain = v.get("brain") or {}
    read = v.get("read") or {}
    return {
        "ticker": v.get("ticker"),
        "priority": brain.get("priority", 0.0),
        "confidence": brain.get("confidence", 0.0),
        "strength": brain.get("strength", 0.0),
        "lean": brain.get("lean", 0),
        "read": read.get("label"),
        "situation": read.get("read"),
        "n_facets": brain.get("n_facets", 0),
        "source_mix": brain.get("source_mix", []),
        "evidence": brain.get("evidence", ""),
        "falsifier": brain.get("falsifier"),
        "facts": _facts(v),
    }


def _is_divergent(v: dict) -> bool:
    read = v.get("read") or {}
    if read.get("label") in _DIVERGENT_LABELS:
        return True
    nd, sd = read.get("news_dir"), read.get("supply_dir")
    return nd is not None and sd is not None and nd != 0 and sd != 0 and (nd * sd) < 0


def build(bundle: dict | None, macro_context: dict | None = None,
          today: date | None = None, top: int = DEFAULT_TOP) -> dict:
    """Reduce the intelligence bundle to a ranked, brain-optimized briefing. PURE.

    bundle         — engine.intelligence.build() output (or load_and_build()).
    macro_context  — {regime, tape_tone, catalysts:[...]} assembled by the build script.
    """
    tickers = (bundle or {}).get("tickers") or {}
    items = [_item(v) for v in tickers.values()]
    # rank by transmission priority, tie-break on confidence then strength — all desc
    items.sort(key=lambda x: (x["priority"], x["confidence"], x["strength"]), reverse=True)

    priority_queue = items[:max(0, top)]
    divergences = [_item(v) for v in tickers.values() if _is_divergent(v)]
    divergences.sort(key=lambda x: (x["confidence"], x["strength"]), reverse=True)

    today = today or date.today()
    n_actionable = sum(1 for x in priority_queue
                       if x["confidence"] >= 0.6 and x["strength"] >= 0.5)
    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "macro_context": macro_context or {},
        "n_universe": len(items),
        "n_priority": len(priority_queue),
        "n_actionable": n_actionable,
        "n_divergences": len(divergences),
        "priority_queue": priority_queue,
        "divergences": divergences,
        "how_to_use": HOW_TO_USE,
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------- #
# macro-context assembly (impure — reads published artifacts; degrades to {})
# --------------------------------------------------------------------------- #
def _read(rel: str):
    p = config.ROOT / rel
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.warning("briefing: read %s failed (%s)", rel, e)
        return None


def macro_context(today: date | None = None) -> dict:
    """Assemble the regime / tape / catalyst frame the brain reads before the queue.
    The daily regime artifact (data/regime/latest.json) is the rich frame — quadrant,
    cycle, liquidity, Fed stance, and the plain-English posture. Best-effort: every
    source is optional and degrades to a missing key.

    Migration (W1 PR2): reads world_state first for the regime/radar sub-blocks;
    falls back to the legacy direct read of data/regime/latest.json on any failure
    or staleness.  risk_radar_raw is carried verbatim in world_state (same shape
    as latest.json['risk_radar']), so the radar passthrough is behavior-preserving.
    Fields that live only in latest.json (fed_stance, playbook, catalyst_tone) are
    read from the raw file in both paths — they are not in world_state.
    """
    ctx: dict = {}

    # --- W1 PR2 migration: try world_state first ---
    ws_used = False
    try:
        from engine.neuralweb.read import load_world_state
        ws = load_world_state()
        if ws is not None:
            reg_block = ws.get("regime") or {}
            quad_name = reg_block.get("quad_name")
            label = reg_block.get("label")
            if quad_name or label:
                ctx["regime"] = quad_name or label
                for src, dst in (("label", "quad"), ("cycle_tag", "cycle"),
                                 ("liquidity_overlay", "liquidity"),
                                 ("transition_state", "transition")):
                    val = reg_block.get(src)
                    if val is not None:
                        ctx[dst] = val
                ws_used = True
    except Exception as e:  # noqa: BLE001 — context-only, never break the briefing
        log.debug("briefing: world_state read failed (%s)", e)

    # For fields NOT in world_state (fed_stance, playbook, catalyst_tone) and as
    # fallback when world_state is absent — read latest.json directly.
    reg = _read("data/regime/latest.json") or _read("site/regime/latest.json")
    if isinstance(reg, dict):
        if not ws_used:
            # Full legacy path: populate regime fields from raw file
            ctx["regime"] = reg.get("quad_name") or reg.get("label") or reg.get("regime")
            for src, dst in (("label", "quad"), ("cycle_tag", "cycle"),
                             ("liquidity_overlay", "liquidity"),
                             ("transition_state", "transition")):
                if reg.get(src) is not None:
                    ctx[dst] = reg.get(src)

        # fed_stance, playbook, catalyst_tone are NOT in world_state — always from raw file.
        fed = reg.get("fed_stance")
        if isinstance(fed, dict) and (fed.get("label_en") or fed.get("stance")):
            ctx["fed_stance"] = fed.get("label_en") or fed.get("stance")
        play = reg.get("playbook")
        if isinstance(play, dict) and play.get("headline"):
            ctx["posture"] = play.get("headline")           # plain-English tape/posture frame
        tone = reg.get("catalyst_tone")
        if isinstance(tone, dict) and tone.get("tone_score") is not None:
            ctx["last_catalyst_tone"] = {"kind": tone.get("kind"),
                                         "tone_score": tone.get("tone_score")}

    # next scheduled macro catalysts — compute best-effort (cheap, deterministic schedule)
    try:
        from engine import macro_news
        cats = macro_news.upcoming_catalysts(today) or []
        if cats:
            ctx["catalysts"] = [
                {"label": c.get("label") or c.get("type"), "date": c.get("date"),
                 "time_et": c.get("time_et")}
                for c in cats[:5] if isinstance(c, dict)
            ]
    except Exception as e:  # noqa: BLE001 — context-only, never break the briefing
        log.debug("briefing: upcoming_catalysts failed (%s)", e)

    if today:
        ctx["as_of"] = today.isoformat()
    return ctx


def load_and_build(today: date | None = None, top: int = DEFAULT_TOP) -> dict:
    """Read the published intelligence bundle + macro frame and emit the briefing.
    Never raises; absent inputs degrade to an empty queue."""
    from engine import intelligence  # local import to avoid an import cycle at module load

    bundle = intelligence.load_and_build(today)
    return build(bundle, macro_context(today), today, top)
