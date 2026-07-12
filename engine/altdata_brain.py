"""Alt-Data Brain — Claude-Opus convergence analyst (GATED · OAuth · falsifiable).

The deep-reasoning half of the Signal Intelligence desk. It reads the DETERMINISTIC
substrate (weighted convergence by_ticker + the influence graph + bill catalysts) as an
EVIDENCE PACK and asks Claude Opus the judgement a transparent score cannot make:

  * WHY do these independent data points align on this name (or not)?
  * what are the SECOND / THIRD-ORDER beneficiaries of the affiliation/flow?
  * a DIRECTIONAL lean + CONVICTION + an ACTION (ACCUMULATE / WATCH / AVOID), each with a
    machine-checkable FALSIFIER scored vs SPY.

EXTRACTOR + JUDGE, NOT ORACLE. Reason only from the evidence pack; cite the channel/actor
behind each call. Output is FALSIFIABLE and logged to a ledger (data/altdata/
brain_theses.jsonl), graded vs SPY by the EXACT engine.ai_desk_scorer evaluators, and the
track record is fed back into the next prompt to calibrate conviction.

DE-ESCALATION-ONLY LAW (_reconcile): the LLM output is CLAMPED so it can only move DOWN
the action/conviction/lean ladders, never up. A DETERMINISTIC BASELINE is computed from
the cluster's own deterministic fields (weighted_score, extended, rs_vs_spy_60d, channels)
— NEVER from any LLM-proposed field (t.*):
  - Directional witness (deterministic):
      (a) If rs_vs_spy_60d is present: rs >= 0 → deterministic overweight; rs < 0 →
          deterministic underweight (price trend is the witness).
      (b) If rs_vs_spy_60d is None: look for a bullish channel witness in the cluster's
          channels list (_BULLISH_WITNESS_CHANNELS). If at least one is present →
          deterministic overweight.
      (c) If rs_vs_spy_60d is None AND no bullish channel witness → ceiling = WATCH,
          conviction ceiling = "low"; the LLM's lean is preserved as a display lean but
          ACTION and CONVICTION cannot exceed that ceiling.
  - Action ceiling: ACCUMULATE only when deterministic lean == "overweight" AND
    weighted_score >= min_weighted AND NOT extended; otherwise WATCH (overweight) or
    AVOID (non-overweight).
  - Conviction ceiling: "medium" when deterministic lean == "overweight" AND
    weighted_score >= min_weighted; "low" otherwise.

  INVARIANT: the ACTION and CONVICTION ceilings are a function of deterministic fields
  ONLY (rs_vs_spy_60d, channels, weighted_score, extended) — NEVER of any LLM-proposed
  field (t.lean, t.action, t.conviction).

The LLM may de-escalate further (e.g. lower conviction to "low", demote to WATCH) but
may NEVER raise above the deterministic ceiling. The existing hard blocks (ACCUMULATE on
extended → WATCH; ACCUMULATE on bearish lean → AVOID) remain as additional guardrails.

This desk EMITS an actionable scored axis (per the desk's mandate) that the Mastermind bot
consumes — but the bot still applies its own risk framework on top; the ledger keeps the
axis honest. AUTH: Claude via the user's Claude-Code OAuth token (Bearer + oauth beta
header), ANTHROPIC_API_KEY fallback. No token → graceful no-op (degraded artifact).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from lib import config
from engine.catalyst_tone import _extract_json
from engine import ai_desk as _desk
from engine import ai_desk_scorer as _scorer
from engine.regime_label import quad_label          # regime stamp → by_regime track record
from engine import altdata_picks
from engine.neuralweb.constitution import grant_authority, GrantResult, AuthorityLevel
from engine.neuralweb.governance import append_event

log = logging.getLogger(__name__)

OAUTH_BETA = "oauth-2025-04-20"
SCHEMA = "altdata_brain.v1"
BENCH = "SPY"
_LEDGER = ("data", "altdata", "brain_theses.jsonl")
_SCORED = ("data", "altdata", "brain_scored.jsonl")
_TRACK = ("data", "altdata", "brain_track_record.json")
_TRACK_SCHEMA = "altdata_brain_track_record.v1"

_LEANS = {"overweight", "underweight", "avoid"}
_ACTIONS = {"ACCUMULATE", "WATCH", "AVOID"}
_CONV = {"low", "medium", "high"}
_EXTENDED_PP = 35.0          # rs_vs_spy_60d above this = already extended → never ACCUMULATE

# Channels that are unambiguously directionally BULLISH (buying / positive-flow).
# These serve as directional witnesses when rs_vs_spy_60d is unavailable (price series
# absent — routine for split-affected names).  Direction-agnostic channels (material_8k,
# unusual_options, darkpool_accum, trump, activist_13d, affiliation, special_situation,
# patent_cluster, app_demand, etc.) are deliberately EXCLUDED: they document activity
# without asserting direction.
_BULLISH_WITNESS_CHANNELS = frozenset({
    "insider_cluster",    # >=3 open-market insider buyers — highest-weight tell
    "insider_buy",        # single open-market insider buy
    "congress_cluster",   # >=3 congressional members net-buying
    "congress_buy",       # single congressional member net-buying
    "smart_money_13f",    # marquee 13F fund initiated / added
    "gov_contract_accel", # federal contract $ accelerating >=2x off a real base
    "gov_grant_accel",    # federal grant/loan $ accelerating >=2x off a real base
})

_DEFAULTS = {
    "enabled": False,
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "api_key_env": "ANTHROPIC_API_KEY",
    # model ids: prefer config["llm_models"]["reasoning"] (version-pinned); these are
    # the emergency fallback when the llm_models block is absent (W5 migration).
    "models": {"reasoning": "claude-opus-4-8", "tagging": "claude-haiku-4-5-20251001"},
    "max_clusters": 12,
    "max_tokens": 8000,
    "horizon_d": 63,
    "rel_threshold": 0.05,
    "interval_days": 1,
    "min_weighted": 0.9,
}


def _reasoning_model(cfg: dict) -> str:
    """Return the version-pinned reasoning model id.

    Resolution order (W5 migration — P5 R5):
    1. config['llm_models']['reasoning']   (version-pinned, authoritative)
    2. cfg['models']['reasoning']          (per-section override / legacy)
    3. hardcoded default                   (emergency fallback only)

    A missing llm_models block logs a warning but does NOT raise — altdata_brain
    predates the W5 requirement and must keep working during the transition.
    """
    llm_models = config.load().get("llm_models") or {}
    if llm_models.get("reasoning"):
        return str(llm_models["reasoning"])
    from_cfg = (cfg.get("models") or {}).get("reasoning")
    if from_cfg:
        return str(from_cfg)
    log.warning("altdata_brain: llm_models.reasoning missing from config; using hardcoded default")
    return "claude-opus-4-8"

DISCLAIMER = (
    "An AI reading of the desk's own deterministic convergence — accountable and falsifiable, "
    "not a guarantee. Every call cites the channels/actors it is based on, is graded vs SPY "
    "over the horizon, and can be wrong or overconfident. The Mastermind sizes it through its "
    "own risk framework; treat as odds, not a forecast."
)

_SYSTEM = (
    "You are the lead analyst of an ALTERNATIVE-DATA desk for a medium/long-horizon equity "
    "investor. You are handed an EVIDENCE PACK of the desk's OWN deterministic signals: a "
    "per-ticker WEIGHTED CONVERGENCE of independent channels (congressional & insider buying, "
    "federal-contract acceleration, lobbying spikes, dark-pool accumulation, smart-money 13F, "
    "app-store demand, patent clusters), an INFLUENCE GRAPH of important actors (politicians, "
    "founders, fund managers, influencers) and the names they control / hold / talk about / "
    "endorse / partner with, plus pending-legislation catalysts and the desk's own track "
    "record.\n\n"
    "Your job: judge WHERE independent data points genuinely ALIGN into an actionable read, "
    "and name the SECOND/THIRD-ORDER beneficiaries the obvious name points to.\n\n"
    "EXTRACTOR + JUDGE, NOT ORACLE:\n"
    "- Reason ONLY from the evidence pack + well-known market structure. NEVER fabricate a "
    "number, level, or event. Cite the channel/actor behind every claim (e.g. [gov_contract_"
    "accel], [actor:Pelosi]). Where the evidence is thin, say so and lower conviction.\n"
    "- Convergence is UNUSUAL ACTIVITY, not proven edge. A single channel is not a thesis.\n"
    "- NEVER tell the investor to ACCUMULATE a name that is already EXTENDED (rs_vs_spy_60d "
    "above ~+35pp, or flagged extended): the entry is gone — WATCH or AVOID instead.\n"
    "- If a track_record is present, CALIBRATE: if past high-conviction calls missed, default "
    "lower. Be honest about tiny samples.\n\n"
    "For each name worth an actionable read, return a thesis. Omit names where the evidence "
    "does not cohere (honesty over content).\n\n"
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  regime_read: string — one or two sentences on what the convergence picture shows today.\n"
    "  regime_read_zh: string — the same in 简体中文.\n"
    "  theses: array of 0..N objects, each:\n"
    "     ticker: string — the primary investable ticker from the pack.\n"
    "     lean: one of \"overweight\",\"underweight\",\"avoid\".\n"
    "     conviction: one of \"low\",\"medium\",\"high\" (be modest; default low).\n"
    "     action: one of \"ACCUMULATE\",\"WATCH\",\"AVOID\" (ACCUMULATE only for a NON-extended "
    "overweight; never for an extended name).\n"
    "     horizon_d: integer trading days, 20..90.\n"
    "     thesis: string — WHY the data points align, naming the channels/actors.\n"
    "     thesis_zh: string — the same in 简体中文.\n"
    "     second_order: array of strings — the 2nd/3rd-order beneficiaries (tickers/themes) "
    "the primary name implies, each with a one-clause reason.\n"
    "     evidence: array of strings — the specific channels/actors cited.\n"
    "     dissent: string — the single strongest contrary case.\n"
    "     falsifier_text: string — one concrete condition that would prove this wrong.\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)


# --------------------------------------------------------------------------- config + client
def _cfg() -> dict:
    try:
        return {**_DEFAULTS, **(config.load().get("altdata_brain") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _make_call(cfg: dict):
    """Return call(system, user) -> (text|None, degraded|None). Opus reasoning model; caches
    the stable system block. None when no provider is available.

    W5 ITEM 1 — 401-fallback: uses engine.llm_auth.make_call() so an expired OAuth
    token triggers a fallback to ANTHROPIC_API_KEY, with degraded_reason
    "auth_invalid:<provider>" distinguishing auth failures from LLM content errors.
    """
    from engine import llm_auth

    providers = llm_auth.build_providers(cfg, opus_model=_reasoning_model(cfg))
    if not providers:
        return None
    max_tokens = int(cfg.get("max_tokens", 8000))

    def call(system: str, user: str):
        def _do_call(client, model: str):
            resp = client.messages.create(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}])
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "refusal"
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return (text, None) if text else (None, "empty_reply")

        try:
            text, reason, _used = llm_auth.make_call(
                providers, _do_call, context="altdata_brain")
        except Exception as e:  # noqa: BLE001
            log.warning("altdata_brain call failed: %s", e)
            return None, "llm_error"
        return text, reason

    return call


# --------------------------------------------------------------------------- evidence pack
def _read_json(p: Path):
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def gather_evidence(root=None) -> dict | None:
    """Assemble the point-in-time evidence pack from the deterministic artifacts. Returns
    None when there's no convergence substrate to reason over."""
    root = Path(root) if root else config.ROOT
    data = root / "data" / "altdata"
    bt = _read_json(data / "by_ticker.json")
    if not bt or not bt.get("tickers"):
        return None
    feed = _read_json(data / "feed.json") or {}
    influence = _read_json(data / "influence_graph.json") or _read_json(root / "site" / "altdata" / "influence.json") or {}
    track = _read_json(root.joinpath(*_TRACK))

    cfg = _cfg()
    min_w = float(cfg.get("min_weighted", 0.9))
    # graph affiliations per ticker (for the cluster context)
    affil = {}
    for w in influence.get("watch", []):
        affil[w.get("ticker")] = w.get("actors", [])

    ranked = sorted(
        (r for r in bt["tickers"].values()
         if (r.get("weighted_score") or 0) >= min_w or int(r.get("convergence_score", 0) or 0) >= 2),
        key=lambda r: (r.get("weighted_score") or 0, r.get("convergence_score") or 0), reverse=True)

    clusters = []
    for r in ranked[: int(cfg.get("max_clusters", 12))]:
        tk = r["ticker"]
        rs = altdata_picks._rs_vs_spy(tk, root)
        clusters.append({
            "ticker": tk,
            "weighted_score": r.get("weighted_score"),
            "convergence_score": r.get("convergence_score"),
            "channels": r.get("channels"),
            "trump_linked": r.get("trump_linked"),
            "affiliated": r.get("affiliated"),
            "metrics": {k: v for k, v in r.items() if k not in
                        ("ticker", "channels", "convergence_score", "weighted_score",
                         "trump_linked", "affiliated")},
            "actors": affil.get(tk, []),
            "rs_vs_spy_60d": rs,
            "extended": bool(rs is not None and rs > _EXTENDED_PP),
            "scorable": _desk._level_asof(tk, root, bt.get("as_of")) is not None,
        })
    if not clusters:
        return None

    sig = feed.get("signals", {})
    return {
        "as_of": bt.get("as_of"),
        "clusters": clusters,
        "bill_catalysts": sig.get("bills", [])[:12],
        "label_mismatches": influence.get("mismatches", [])[:6],
        "new_affiliations": influence.get("recent", [])[:10],
        "track_record": track if isinstance(track, dict) else None,
        "n_clusters": len(clusters),
    }


# --------------------------------------------------------------------------- falsifier
def _derive_check(ticker: str, lean: str, horizon: int, rel_thr: float) -> dict:
    if lean == "overweight":
        op, thr = "<", -rel_thr                  # FALSE if it underperforms SPY by >= thr
    elif lean in ("underweight", "avoid"):
        op, thr = ">", rel_thr                   # FALSE if it outperforms SPY by >= thr
    else:
        return {"kind": "soft", "reason": f"lean '{lean}' has no relative-return rule"}
    return {"kind": "rel_return", "subject_ticker": ticker, "vs": BENCH,
            "op": op, "threshold": thr, "horizon_d": horizon}


_ACTION_RANK = {"AVOID": 0, "WATCH": 1, "ACCUMULATE": 2}
_CONV_RANK = {"low": 0, "medium": 1, "high": 2}
# Lean is also a ceiling axis: overweight > underweight > avoid.
# The LLM may de-escalate (e.g. say "underweight" when ceiling is "overweight") but may
# not escalate above the deterministic ceiling lean.
_LEAN_RANK = {"avoid": 0, "underweight": 1, "overweight": 2}


def _det_baseline(t: dict, min_weighted: float = 0.9) -> tuple[str, str, str]:
    """Derive the DETERMINISTIC ceiling for (action, conviction, lean) from cluster fields.

    INVARIANT: every rule in this function reads ONLY deterministic cluster fields
    (rs_vs_spy_60d, channels, weighted_score, extended).  It NEVER reads any LLM-proposed
    field (lean, action, conviction).  This is the enforcement point of the de-escalation-
    only law: action and conviction ceilings must be a function of deterministic evidence,
    never of what the LLM proposed.

    Directional witness determination:
      (a) rs_vs_spy_60d present and >= 0  → deterministic lean = "overweight"
      (b) rs_vs_spy_60d present and <  0  → deterministic lean = "underweight"
      (c) rs_vs_spy_60d is None           → look for a bullish channel witness in
          _BULLISH_WITNESS_CHANNELS.  At least one present → deterministic lean =
          "overweight".  None present → deterministic lean = "watch_only" (no direction;
          action ceiling = WATCH, conviction ceiling = "low").

    Action ceiling:
      ACCUMULATE  ← det_lean == "overweight" AND weighted_score >= min_weighted AND NOT extended
      WATCH       ← det_lean == "overweight" but evidence too weak or extended,
                    OR det_lean == "watch_only" (no directional witness)
      AVOID       ← det_lean == "underweight"

    Conviction ceiling:
      "medium"    ← det_lean == "overweight" AND weighted_score >= min_weighted
      "low"       ← otherwise (underweight, watch_only, or weak-evidence overweight)

    The returned det_lean is mapped back to a canonical lean for the audit trail:
      "watch_only" → "underweight" (no directional support; display lean is neutral-to-negative)
    """
    ws = float(t.get("weighted_score") or 0.0)
    extended = bool(t.get("extended"))
    rs = t.get("rs_vs_spy_60d")  # None when price series unavailable (e.g. split-affected names)
    channels = set(t.get("channels") or [])

    # --- deterministic directional witness ---
    if rs is not None:
        # (a)/(b): price series available — RS sign is the sole directional witness.
        det_lean = "overweight" if rs >= 0 else "underweight"
    elif channels & _BULLISH_WITNESS_CHANNELS:
        # (c-i): no price series but at least one unambiguously bullish channel present.
        det_lean = "overweight"
    else:
        # (c-ii): no price series AND no bullish channel witness → no directional support.
        det_lean = "watch_only"

    # --- action ceiling ---
    if det_lean == "overweight" and ws >= min_weighted and not extended:
        det_action = "ACCUMULATE"
    elif det_lean == "overweight":
        det_action = "WATCH"
    elif det_lean == "watch_only":
        det_action = "WATCH"
    else:  # underweight
        det_action = "AVOID"

    # --- conviction ceiling ---
    if det_lean == "overweight" and ws >= min_weighted:
        det_conv = "medium"
    else:
        det_conv = "low"

    # Map "watch_only" to "underweight" for the returned lean (canonical display value).
    ret_lean = "underweight" if det_lean == "watch_only" else det_lean
    return det_action, det_conv, ret_lean


def _reconcile(t: dict, min_weighted: float = 0.9) -> dict:
    """DE-ESCALATION-ONLY clamp (house law: LLMs may not originate signals/escalations).

    Step 1 — derive the DETERMINISTIC baseline (ceiling) from cluster evidence fields.
    Step 2 — clamp each axis: LLM output may only stay AT or BELOW the ceiling rank;
             any escalation above it is forced back down to the ceiling.
    Step 3 — apply the original hard blocks as additional guardrails:
             ACCUMULATE on an extended name → WATCH
             ACCUMULATE on a bearish lean   → AVOID

    The LLM may de-escalate further (e.g. propose WATCH when the ceiling is ACCUMULATE,
    or lower conviction to "low") — de-escalation is always respected.

    Fields `clamped` and `det_baseline` are added for audit trail when any axis is
    overridden; they are NOT present when no clamping occurs.
    """
    det_action, det_conv, det_lean = _det_baseline(t, min_weighted)

    llm_action = str(t.get("action") or "WATCH").strip().upper()
    llm_action = llm_action if llm_action in _ACTIONS else "WATCH"
    llm_conv = str(t.get("conviction") or "low").strip().lower()
    llm_conv = llm_conv if llm_conv in _CONV else "low"
    llm_lean = str(t.get("lean") or "avoid").strip().lower()

    clamp_notes: list[str] = []

    # --- lean clamp (de-escalation only: only clamp when LLM lean rank exceeds ceiling) ---
    if _LEAN_RANK.get(llm_lean, 1) > _LEAN_RANK.get(det_lean, 1):
        clamp_notes.append(f"lean {llm_lean!r} → {det_lean!r} (deterministic witness)")
        t["lean"] = det_lean

    # --- conviction clamp (LLM rank must not exceed deterministic ceiling) ---
    if _CONV_RANK.get(llm_conv, 0) > _CONV_RANK[det_conv]:
        clamp_notes.append(f"conviction {llm_conv!r} → {det_conv!r} (deterministic ceiling)")
        t["conviction"] = det_conv

    # --- action clamp (LLM rank must not exceed deterministic ceiling) ---
    # det_action already reflects the post-lean-clamp lean (det_lean), so use it directly.
    if _ACTION_RANK.get(llm_action, 0) > _ACTION_RANK[det_action]:
        clamp_notes.append(f"action {llm_action!r} → {det_action!r} (deterministic ceiling)")
        t["action"] = det_action
        llm_action = det_action   # update for hard-block check below

    # --- hard blocks (additional guardrails, unchanged from original) ---
    action_now = t.get("action", llm_action)
    if t.get("extended") and action_now == "ACCUMULATE":
        t["action"] = "WATCH"
        clamp_notes.append("extended → WATCH (entry already gone)")
    if t.get("lean") in ("underweight", "avoid") and t.get("action") == "ACCUMULATE":
        t["action"] = "AVOID"
        clamp_notes.append("bearish lean cannot ACCUMULATE")

    if clamp_notes:
        t["clamped"] = "; ".join(clamp_notes)
        t["det_baseline"] = {"action": det_action, "conviction": det_conv, "lean": det_lean}
    return t


def _build_thesis(t: dict, cluster_index: dict, asof: str, cfg: dict) -> dict | None:
    if not isinstance(t, dict):
        return None
    tk = str(t.get("ticker") or "").strip().upper()
    lean = str(t.get("lean") or "").strip().lower()
    if not tk or lean not in _LEANS:
        return None
    cl = cluster_index.get(tk, {})
    try:
        horizon = int(t.get("horizon_d") or cfg.get("horizon_d", 63))
    except Exception:  # noqa: BLE001
        horizon = int(cfg.get("horizon_d", 63))
    horizon = max(20, min(90, horizon))
    conv = str(t.get("conviction") or "low").strip().lower()
    conv = conv if conv in _CONV else "low"
    action = str(t.get("action") or "WATCH").strip().upper()
    action = action if action in _ACTIONS else "WATCH"
    out = {
        "ticker": tk, "lean": lean, "conviction": conv, "action": action,
        "horizon_d": horizon,
        "thesis": t.get("thesis"), "thesis_zh": t.get("thesis_zh"),
        "second_order": [str(s) for s in (t.get("second_order") or []) if s][:6],
        "evidence": [str(e) for e in (t.get("evidence") or []) if e][:8],
        "dissent": t.get("dissent"),
        "weighted_score": cl.get("weighted_score"),
        "channels": cl.get("channels"),
        "rs_vs_spy_60d": cl.get("rs_vs_spy_60d"),
        "extended": bool(cl.get("extended")),
        "scorable": bool(cl.get("scorable")),
        "falsifier": {"text": t.get("falsifier_text"),
                      "check": _derive_check(tk, lean, horizon, float(cfg.get("rel_threshold", 0.05)))},
        "check_by": _check_by(asof, horizon),
    }
    min_w = float(cfg.get("min_weighted", _DEFAULTS["min_weighted"]))
    return _reconcile(out, min_weighted=min_w)


def _check_by(asof, horizon: int) -> str | None:
    try:
        import pandas as pd
        return (pd.Timestamp(asof) + pd.offsets.BusinessDay(int(horizon))).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- Article-3 review
# Evidence mapping:
#   hits  = round(hit_rate * n_dates)  from qledger track_record.json by_family['altdata']['5']
#   n     = n_dates (independent date-cluster observations at h=5d; qledger ACCRUING state)
#   base_rate = 0.5  (sign-test base: direction call is correct above chance when hit_rate > 0.5)
#   evidence_asof = track_record.generated_at date
# Justification: the qledger grades each brain thesis on whether the subject ticker
# outperformed SPY over h days (binary outcome). The base rate for a random direction call
# is 0.5 (sign-test). Using qledger hit_rate as the realized precision and n_dates as the
# sample size maps cleanly onto grant_authority's {hits, n, base_rate, evidence_asof}.
# n_dates is the correct sample-size unit: this function does NOT read the stored
# track_record wilson_ci_low — it reconstructs cluster-honest evidence itself as
# hits=round(hit_rate*n_dates), n=n_dates (independent date clusters per qledger's
# by_family output).  No de-duplication is performed here; n_dates is taken as-is.
# Floors (min_n=25 dates = qledger GRADED_MIN_DATES; min_events=8 = Article-3 min-events
# floor matching the can_force precedent).

_ARTICLE3_FLOORS = {"min_n": 25, "min_events": 8}
_ARTICLE3_BASE_RATE = 0.5   # sign-test base for direction calls


def article3_actionable_verdict(root=None) -> GrantResult:
    """Evaluate Article-3 gate for altdata_brain's actionable flag.

    Reads qledger track_record.json (site/qledger/track_record.json) for the
    'altdata' family at h=5d horizon.  Maps qledger evidence onto the
    grant_authority() contract:
      hits        = round(hit_rate * n_dates)  (direction-correct independent date clusters)
      n           = n_dates                    (independent date clusters, qledger canonical)
      base_rate   = 0.5                        (sign-test floor for direction calls)
      evidence_asof = track_record generated_at date

    n_dates is the correct sample-size unit: this function does NOT read the stored
    track_record wilson_ci_low — it reconstructs cluster-honest evidence itself as
    hits=round(hit_rate*n_dates), n=n_dates (independent date clusters per qledger's
    by_family output).  No de-duplication is performed here; n_dates is taken as-is
    from the stored by_family cell.  The min_n floor of 25 matches qledger's
    GRADED_MIN_DATES constant (the same 25-cluster floor the promotion gate uses).

    Returns a GrantResult.  Never raises — returns refused with
    reason='track_record_unavailable' when the data file is missing.
    """
    try:
        tr_path = (Path(root) if root else config.ROOT) / "site" / "qledger" / "track_record.json"
        if not tr_path.exists():
            return GrantResult(
                granted=False, lift_lb=None, wilson_lb=None,
                reason="track_record_unavailable: site/qledger/track_record.json missing",
                lapses_at=None,
            )
        tr = json.loads(tr_path.read_text())
        cell = (tr.get("by_family") or {}).get("altdata", {}).get("5") or {}
        # Use n_dates: independent date clusters (qledger canonical unit for Wilson CI)
        n_dates = int(cell.get("n_dates") or 0)
        hit_rate = cell.get("hit_rate")
        generated_at = str(tr.get("generated_at") or "")
        # evidence_asof: use date portion of generated_at
        try:
            evidence_asof = generated_at[:10]  # ISO date
        except Exception:  # noqa: BLE001
            evidence_asof = None
        if hit_rate is None or n_dates == 0:
            return GrantResult(
                granted=False, lift_lb=None, wilson_lb=None,
                reason="track_record_no_hit_rate: altdata family h=5d has null hit_rate or zero n_dates",
                lapses_at=None,
            )
        hits = round(float(hit_rate) * n_dates)
        evidence = {
            "hits": hits,
            "n": n_dates,
            "base_rate": _ARTICLE3_BASE_RATE,
            "evidence_asof": evidence_asof,
        }
        return grant_authority(
            evidence,
            floors=_ARTICLE3_FLOORS,
            target_level=AuthorityLevel.A1_EXPLAIN,  # not A7; Article 1 is not implicated
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("altdata_brain: article3_actionable_verdict failed: %s", exc)
        return GrantResult(
            granted=False, lift_lb=None, wilson_lb=None,
            reason=f"verdict_error: {exc}",
            lapses_at=None,
        )


def _emit_article3_governance(prev_granted: bool | None, result: GrantResult, root=None) -> None:
    """Append an article3_review governance event.  On transitions, also appends
    authority_grant or authority_lapse.  Fail-open: never raises."""
    now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    append_event(
        "article3_review",
        "altdata_brain.actionable",
        article=3,
        authored_by="altdata_brain.article3_actionable_verdict",
        evidence={
            "granted": result.granted,
            "lift_lb": result.lift_lb,
            "wilson_lb": result.wilson_lb,
            "reason": result.reason,
            "lapses_at": result.lapses_at,
            "floors": _ARTICLE3_FLOORS,
            "base_rate": _ARTICLE3_BASE_RATE,
        },
        root=root,
    )
    if prev_granted is None:
        return  # no transition info — first evaluation, review event is sufficient
    if not prev_granted and result.granted:
        # grant transition
        append_event(
            "authority_grant",
            "altdata_brain.actionable",
            article=3,
            authored_by="altdata_brain.article3_actionable_verdict",
            before={"granted": False},
            after={"granted": True, "lapses_at": result.lapses_at},
            evidence={"lift_lb": result.lift_lb, "reason": result.reason},
            note="Article-3 evidence cleared; altdata_brain.actionable auto-re-granted",
            root=root,
        )
    elif prev_granted and not result.granted:
        # lapse transition
        append_event(
            "authority_lapse",
            "altdata_brain.actionable",
            article=3,
            authored_by="altdata_brain.article3_actionable_verdict",
            before={"granted": True},
            after={"granted": False},
            evidence={"reason": result.reason},
            note="Article-3 evidence insufficient; actionable flag lapsed",
            root=root,
        )


# --------------------------------------------------------------------------- synthesize
def _build_user(state: dict) -> str:
    return ("Today's deterministic alt-data evidence pack (JSON). Produce your desk read per "
            "your instructions — accountable, falsifiable, never sized, never chasing an "
            "extended name.\n<evidence>\n" + json.dumps(state, indent=2, default=str) + "\n</evidence>")


def synthesize(state: dict, cfg: dict | None = None, call=None,
               root=None, _prev_granted: bool | None = None) -> dict:
    """Run the Opus analyst over the evidence pack. Always returns a record (degraded fields
    flagged); never raises. `call` is injectable so tests run without a token.

    Article-3 review: the actionable flag and is_context_only are set by
    article3_actionable_verdict() — not hardcoded.  The brief gains an additive
    article3 block with the full verdict.  Governance events are emitted on
    transitions (and on every call for the article3_review event type).
    """
    cfg = cfg or _cfg()
    asof = state.get("as_of")
    cluster_index = {c["ticker"]: c for c in state.get("clusters", [])}

    # Article-3 evaluation — evidence-driven, never hardcoded
    a3 = article3_actionable_verdict(root=root)
    try:
        _emit_article3_governance(_prev_granted, a3, root=root)
    except Exception as _gov_exc:  # noqa: BLE001 — governance failure never blocks synthesis
        log.warning("altdata_brain: governance emit failed (fail-open): %s", _gov_exc)

    brief = {
        "schema": SCHEMA,
        "actionable": a3.granted,
        "is_context_only": not a3.granted,
        "article3": {
            "granted": a3.granted,
            "lift_lb": a3.lift_lb,
            "reason": a3.reason,
            "evidence_asof": a3.evidence_asof,   # real track_record date, present on all outcomes
            "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(), "state_asof": asof,
        "model": _reasoning_model(cfg),
        "regime_read": None, "regime_read_zh": None, "theses": [],
        "track_record": state.get("track_record"),
        "confidence": "low", "n_clusters": state.get("n_clusters"),
        "raw_text": None, "degraded_reason": None, "disclaimer": DISCLAIMER,
    }
    # evidence_asof is now carried directly from GrantResult.evidence_asof on all outcomes
    # (granted and refused alike). No backtrack from lapses_at needed.
    fn = call or _make_call(cfg)
    if fn is None:
        brief["degraded_reason"] = "no_client_or_token"
        return brief
    reply, reason = fn(_SYSTEM, _build_user(state))
    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"
        return brief
    brief["regime_read"] = parsed.get("regime_read")
    brief["regime_read_zh"] = parsed.get("regime_read_zh")
    conf = str(parsed.get("confidence") or "low").strip().lower()
    brief["confidence"] = conf if conf in _CONV else "low"
    raw = parsed.get("theses") if isinstance(parsed.get("theses"), list) else []
    theses = []
    for t in raw[: int(cfg.get("max_clusters", 12))]:
        th = _build_thesis(t, cluster_index, asof, cfg)
        if th is not None:
            theses.append(th)
    brief["theses"] = theses
    if reason:
        brief["degraded_reason"] = reason
    return brief


# --------------------------------------------------------------------------- ledger + persist
def _entry_levels(check: dict, asof, root) -> dict:
    out = {}
    for key in ("subject_ticker", "vs"):
        t = check.get(key)
        if t:
            lv = _desk._level_asof(t, root, asof)
            if lv is not None:
                out[t] = lv
    return out


def _active_subjects(rows: list, asof: str) -> set:
    return {r.get("ticker") for r in rows if r.get("ticker") and str(r.get("check_by", "")) >= asof}


def _append_ledger(brief: dict, root) -> list:
    """Append each SCORABLE thesis to brain_theses.jsonl (vintage-deduped per window).
    Only names with a price series are logged (so the scorer can grade them)."""
    theses = brief.get("theses") or []
    asof = brief.get("state_asof")
    if not theses or not asof:
        return []
    path = Path(root).joinpath(*_LEDGER)
    existing = _scorer._load_jsonl(path)
    active = _active_subjects(existing, asof)
    existing_ids = {r.get("id") for r in existing}
    regime = quad_label(root)
    new = []
    for t in theses:
        tk = t["ticker"]
        if tk in active or not t.get("scorable"):
            continue
        check = (t.get("falsifier") or {}).get("check") or {}
        entry = _entry_levels(check, asof, root)
        if check.get("subject_ticker") not in entry or BENCH not in entry:
            continue                              # not scorable → never logged
        rid = f"{asof}-{tk}-brain"
        if rid in existing_ids:
            continue
        new.append({
            "id": rid, "ticker": tk, "logged_at": brief["generated_at"], "state_asof": asof,
            "subject": f"{tk} alt-data brain {t['action']}",
            "lean": t["lean"], "conviction": t["conviction"], "action": t["action"],
            "horizon_d": t["horizon_d"], "falsifier": t["falsifier"], "check_by": t["check_by"],
            "entry_levels": entry, "regime": regime,
            "status": "open", "scored_at": None, "outcome": None, "realized": None,
        })
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            for r in new:
                fh.write(json.dumps(r, default=str) + "\n")
        log.info("altdata_brain ledger: logged %d thesis(es): %s",
                 len(new), ", ".join(r["ticker"] for r in new))
    return new


def score(root=None, today=None) -> dict | None:
    """Grade matured brain theses vs SPY (reusing the ai_desk_scorer evaluators)."""
    try:
        root = Path(root) if root else config.ROOT
        today = today or date.today()
        ledger = _scorer._dedupe_by_id(_scorer._load_jsonl(root.joinpath(*_LEDGER)))
        already = _scorer._dedupe_by_id(_scorer._load_jsonl(root.joinpath(*_SCORED)))
        new_rows = []
        for tid, row in ledger.items():
            if tid in already:
                continue
            res = _scorer._score_one(row, root, today)
            if res is not None:
                new_rows.append(res)
        combined = list(_scorer._dedupe_by_id(list(already.values()) + new_rows).values())
        track = _scorer._aggregate(combined, ledger, today)
        track["schema"] = _TRACK_SCHEMA
        track["note"] = ("Alt-data brain theses graded vs SPY. The actionable axis is "
                         "calibrated by this track record; conviction defers to it.")
        sp = root.joinpath(*_SCORED)
        sp.parent.mkdir(parents=True, exist_ok=True)
        if new_rows:
            with open(sp, "a") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r, default=str) + "\n")
        root.joinpath(*_TRACK).write_text(json.dumps(track, indent=2, default=str))
        site = config.ROOT / "site" / "altdata"
        site.mkdir(parents=True, exist_ok=True)
        (site / "brain_track_record.json").write_text(json.dumps(track, indent=2, default=str))
        return track
    except Exception as e:  # noqa: BLE001
        log.error("altdata_brain score failed: %s", e)
        return None


def load(root=None) -> dict:
    """Read the persisted brain brief (for the emit + page render). Empty when absent."""
    p = (Path(root) if root else config.ROOT) / "data" / "altdata" / "brain.json"
    return _read_json(p) or {}


def _persist(brief: dict, root) -> None:
    try:
        d = Path(root) / "data" / "altdata"
        d.mkdir(parents=True, exist_ok=True)
        (d / "brain.json").write_text(json.dumps(brief, indent=2, default=str))
        site = Path(root) / "site" / "altdata"
        if site.parent.is_dir():
            site.mkdir(parents=True, exist_ok=True)
            pub = {k: v for k, v in brief.items() if k != "raw_text"}
            (site / "brain.json").write_text(json.dumps(pub, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("altdata_brain persist failed: %s", e)


def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Gather → synthesize → persist + append ledger → score. Gated; NEVER raises."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        log.info("altdata_brain: disabled (config altdata_brain.enabled=false)")
        return None
    try:
        root = Path(root) if root else config.ROOT
        state = gather_evidence(root)
        if state is None:
            log.info("altdata_brain: no convergence substrate — nothing to reason over")
            return None
        # Read prior actionable flag so transition events (authority_grant / authority_lapse)
        # fire correctly when the Article-3 verdict changes between runs.
        _prior = load(root)
        _prev_granted: bool | None = _prior.get("actionable") if _prior else None
        # Pass root so Article-3 verdict reads the live track_record.json
        brief = synthesize(state, cfg, call=call, root=root, _prev_granted=_prev_granted)
        if persist:
            _persist(brief, root)
            _append_ledger(brief, root)
            score(root=root)
        return brief
    except Exception as e:  # noqa: BLE001 — additive overlay, never fatal
        log.error("altdata_brain run failed: %s", e)
        return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    # honor the config gate (the CI step invokes this) — `--force` overrides for manual runs
    b = run(persist=True, force=("--force" in sys.argv))
    if not b:
        print("altdata_brain: no-op (disabled / no substrate)")
    else:
        print(f"altdata_brain: {len(b.get('theses', []))} theses, "
              f"degraded={b.get('degraded_reason')}, confidence={b.get('confidence')}")
