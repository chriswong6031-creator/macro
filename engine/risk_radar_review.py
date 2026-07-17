"""Risk Radar — Opus SELF-CORRECTION loop (Phase C).

The radar grades every call (engine/risk_radar_audit.py). This loop closes the feedback:
Opus reads the realized scorecard + the recent MISTAKES (false positives + missed drawdowns)
+ the current calibration, reasons about WHY each wrong call happened, and proposes calibration
deltas (alert bands, per-leg thresholds, the drawdown-probability surface, alert tier) to cut
false positives and catch the misses.

TWO HARD GUARDS so a self-tuning risk engine can't tune itself off a cliff:
  1. CODE CLAMP — every proposed delta is bounded (bands move <= +/-12 and stay ordered; leg
     thr_pct in [0.80,0.97]; prob_cal in [0,0.6] and kept monotonic; alert_from cannot drop below
     'caution'). Opus can only nudge within rails.
  2. DO-NO-HARM BACKTEST GATE — even a clamped proposal is APPLIED only if it improves the
     historical alert F1 (full AND 2020+) without breaking the evidence gate (validated legs still
     lead). engine.risk_radar_backtest.compare_calib decides; Opus never writes the engine directly.

Accepted changes are written to data/risk_radar/calibration.json (the overlay risk_radar reads)
and EVERY proposal+verdict is logged to data/risk_radar/review_log.jsonl (full audit trail).
Gate-outs BEFORE a proposal (disabled / insufficient_graded / no_client_or_key /
no_usable_proposal) are NOT logged — review_log.jsonl does not exist until the loop first
arms and Opus produces a usable proposal (synapse lobe risk-radar-review-log is declared
dormant until then).

A6 LANE-(ii) GOVERNANCE (W7a PR2):
  Every Opus PROPOSAL appends an a6_llm_proposed governance event (event_type 'a6_llm_proposed')
  to the Neural Web governance ledger BEFORE any apply decision.  The event carries:
    - the proposal payload (analysis + proposed deltas)
    - the pre-committed gate it must pass (the do-no-harm F1 predicate)
  Every APPLY appends a6_auto_apply + the backtest evidence (before/after calibration state).
  Every REJECT appends the verdict with honest nulls.
  Governance logging NEVER blocks the loop (fail-open; any logging exception is swallowed).

ARMING NOTE (W7a PR2): config.yml now carries risk_radar_review.enabled: true (the correct
arm path — config.load() overlay overrides _DEFAULTS on every run).  Even armed, the loop
no-ops until >=30 graded radar calls exist (min_graded self-gate) and every apply passes the
do-no-harm F1 backtest + hard clamps.

OAuth-first, never raises. Reuses the risk_brain/narrative_brain pattern.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine.catalyst_tone import _extract_json
from engine.neuralweb.governance import append_event
from lib import config

log = logging.getLogger(__name__)

# Pre-committed A6 lane-(ii) gate description — recorded in every governance event so the
# ledger carries the gate that was in force at the time of the proposal/apply/reject.
_A6_GATE_SPEC = (
    "do-no-harm F1 predicate: proposed calibration must improve historical alert F1 "
    "(full+2020+) without breaking the evidence gate (n_graded >= min_graded=30 first); "
    "hard clamps: bands +/-12 from default and strictly ordered; "
    "leg thr_pct in [0.80,0.97]; prob_cal in [0,0.6] monotonic; alert_from in {caution,elevated,risk-off}"
)

# NOTE: _DEFAULTS["enabled"] is False here.  The real arm is config.yml
# (risk_radar_review.enabled: true — W7a PR2 arming-predicate, 2026-07-04).
# config.load() overlay in _cfg() takes precedence over _DEFAULTS on every
# run, so touching this constant is NOT the correct arm mechanism.  See
# engine/neuralweb/constitution.py A6 lane definitions.
_DEFAULTS = {
    "enabled": False,
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "api_key_env": "ANTHROPIC_API_KEY",
    "model": "claude-opus-4-8",
    "interval_days": 7,            # retune weekly (needs matured outcomes to learn from)
    "max_tokens": 4000,
    "min_graded": 30,              # don't retune until enough calls have been graded
    "band_max_delta": 12.0,        # bands may move at most this far from the baked default
    "oauth_pool_lane": "risk-radar-review",  # pool key expansion for this lane
    "usage_lane": "risk-radar-review",       # ai_costs attribution
}

# clamp rails for the CODE guard
_THR_LO, _THR_HI = 0.80, 0.97
_PROB_LO, _PROB_HI = 0.0, 0.6
_ALERT_ALLOWED = {"caution", "elevated", "risk-off"}

_SYSTEM = (
    "You are the risk-model calibration officer for a market drawdown-risk radar. You are given "
    "the radar's REALIZED scorecard (alert precision/recall), its recent MISTAKES (false positives "
    "= alerted but no drawdown; misses = a >=5% drawdown that was NOT alerted), and its CURRENT "
    "calibration. Your job: propose SMALL calibration changes to cut false positives AND catch the "
    "misses — improving the precision/recall tradeoff, not just trading one for the other.\n\n"
    "Reason from the EVIDENCE (the mistakes + scorecard), not from priors. For false positives, "
    "look at which scare-type/leg fired without a follow-through and whether a higher band/threshold "
    "or a confirmation would have suppressed it. For misses, look at what was elevated-but-below-"
    "alert and whether a lower band would have caught it without flooding FPs. Be conservative: "
    "a do-no-harm backtest will REJECT any change that doesn't improve historical F1, so propose "
    "targeted nudges, not sweeping changes.\n\n"
    "Return ONLY a JSON object (no fences):\n"
    '  analysis: string (the systematic error patterns you see),\n'
    '  deltas: { bands: {watch?,caution?,elevated?,risk_off?},\n'
    '            legs: { <leg>: {thr_pct} },\n'
    '            prob_cal: { h5?:{...}, h10?:{...}, h21?:{...} },\n'
    '            alert_from: "caution"|"elevated"|"risk-off" },\n'
    '  rationale: string'
)


def _cfg() -> dict:
    try:
        return {**_DEFAULTS, **(config.load().get("risk_radar_review") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def _make_call(cfg):
    """Return a call(system, user) -> text | None callable, or None.

    Refactored to use llm_auth.build_providers for pool-aware failover and
    usage capture.  The external call signature is unchanged.
    """
    try:
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(cfg, opus_model=cfg.get("model", "claude-opus-4-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_review: provider build failed (%s)", e)
        return None
    if not providers:
        return None
    max_tokens = int(cfg.get("max_tokens", 4000))
    model = cfg.get("model", "claude-opus-4-8")

    def call(system, user):
        def _call_fn(client, m: str):
            resp = client.messages.create(
                model=m, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}])
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "refusal", resp
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return text or None, None, resp

        model_providers = [{**p, "model": model} for p in providers]
        try:
            text, _, _ = llm_auth.make_call(model_providers, _call_fn,
                                             context="risk_radar_review")
            return text or None
        except Exception as e:  # noqa: BLE001
            log.warning("risk_radar_review call failed: %s", e)
            return None
    return call


def _clamp(deltas: dict, base_calib: dict, cfg: dict) -> dict:
    """Apply the proposed deltas to a copy of base_calib, CLAMPED to the safety rails. Returns the
    proposed full calibration (always valid + ordered), never raising."""
    from engine.risk_radar import _DEFAULT_BANDS
    out = {"bands": dict(base_calib["bands"]),
           "legs": {k: dict(v) for k, v in base_calib["legs"].items()},
           "scares": base_calib["scares"],
           "prob_cal": {h: dict(v) for h, v in base_calib["prob_cal"].items()},
           "alert_from": base_calib.get("alert_from", "elevated")}
    d = deltas or {}
    bmax = float(cfg.get("band_max_delta", 12.0))
    for k, v in (d.get("bands") or {}).items():
        if k in out["bands"]:
            try:
                base = float(_DEFAULT_BANDS[k]); want = float(v)
                out["bands"][k] = max(base - bmax, min(base + bmax, want))
            except (TypeError, ValueError):
                pass
    # keep bands strictly ordered watch<caution<elevated<risk_off
    order = ["watch", "caution", "elevated", "risk_off"]
    for i in range(1, len(order)):
        out["bands"][order[i]] = max(out["bands"][order[i]], out["bands"][order[i - 1]] + 1.0)
    for leg, dd in (d.get("legs") or {}).items():
        if leg in out["legs"] and "thr_pct" in (dd or {}):
            try:
                out["legs"][leg]["thr_pct"] = max(_THR_LO, min(_THR_HI, float(dd["thr_pct"])))
            except (TypeError, ValueError):
                pass
    for h, sd in (d.get("prob_cal") or {}).items():
        if h in out["prob_cal"]:
            for st, val in (sd or {}).items():
                if st in out["prob_cal"][h]:
                    try:
                        out["prob_cal"][h][st] = max(_PROB_LO, min(_PROB_HI, float(val)))
                    except (TypeError, ValueError):
                        pass
            # keep monotonic across states
            so = ["calm", "watch", "caution", "elevated", "risk-off"]
            for i in range(1, len(so)):
                out["prob_cal"][h][so[i]] = max(out["prob_cal"][h][so[i]], out["prob_cal"][h][so[i - 1]])
    af = d.get("alert_from")
    if af in _ALERT_ALLOWED:
        out["alert_from"] = af
    return out


def _evidence_pack(scorecard: dict, calib: dict) -> str:
    sc = scorecard or {}
    mistakes = sc.get("recent_mistakes") or []
    lines = [
        f"REALIZED SCORECARD: graded={sc.get('n_graded')}, alert_precision={sc.get('alert_precision')}, "
        f"recall_dd5_h21={sc.get('recall_dd5_h21')}, alerts={sc.get('n_alerts')} "
        f"(TP={sc.get('n_true_pos')}, FP={sc.get('n_false_pos')}).",
        f"BY-STATE hit-rate: {json.dumps(sc.get('by_state'), default=str)}",
        f"CURRENT bands: {json.dumps(calib['bands'])}; alert_from={calib.get('alert_from')}.",
        f"CURRENT leg thr_pct: {json.dumps({k: v.get('thr_pct') for k, v in calib['legs'].items()})}",
        "RECENT MISTAKES (fix these):",
    ]
    for m in mistakes[:20]:
        lines.append(f"  {m.get('asof')} {m.get('kind')} state={m.get('state')} "
                     f"dominant={m.get('dominant_scare')} fwd_dd_h21={m.get('fwd_dd_h21')} "
                     f"scares={json.dumps(m.get('scares'), default=str)}")
    return "\n".join(lines)


def _append_review_log(rec: dict, root=None) -> None:
    try:
        base = config.data_dir() if root is None else (Path(root) / "data")
        p = base / "risk_radar" / "review_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_review log append failed: %s", e)


def _gov_proposal(proposal: dict, proposed_deltas: dict, root=None) -> None:
    """A6 lane-(ii): append a6_llm_proposed governance event for an Opus proposal.
    Includes the pre-committed gate so the ledger shows what test the proposal must pass.
    Fail-open: any exception is swallowed."""
    try:
        append_event(
            "a6_llm_proposed",
            "data/risk_radar/calibration.json",
            article=6,
            authored_by="risk_radar_review",
            evidence={
                "lane": "ii",
                "pre_committed_gate": _A6_GATE_SPEC,
                "proposal_analysis": str(proposal.get("analysis") or "")[:500],
                "proposed_deltas_summary": {
                    "n_band_changes": len((proposal.get("deltas") or {}).get("bands") or {}),
                    "n_leg_changes": len((proposal.get("deltas") or {}).get("legs") or {}),
                    "alert_from": (proposal.get("deltas") or {}).get("alert_from"),
                },
            },
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("risk_radar_review: governance proposal event failed: %s", exc)


def _gov_apply(out: dict, base_calib: dict, proposed: dict, root=None) -> None:
    """A6 lane-(ii): append a6_auto_apply governance event when calibration is applied.
    Carries before/after calibration state + backtest evidence. Fail-open."""
    try:
        bt = out.get("backtest") or {}
        append_event(
            "a6_auto_apply",
            "data/risk_radar/calibration.json",
            article=6,
            authored_by="risk_radar_review",
            before={"bands": base_calib.get("bands"), "alert_from": base_calib.get("alert_from")},
            after={"bands": proposed.get("bands"), "alert_from": proposed.get("alert_from")},
            evidence={
                "lane": "ii",
                "gate": _A6_GATE_SPEC,
                "backtest": bt,
                "applied": True,
            },
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("risk_radar_review: governance apply event failed: %s", exc)


def _gov_reject(out: dict, base_calib: dict, proposed: dict, root=None) -> None:
    """A6 lane-(ii): append reject governance event when do-no-harm gate blocks apply.
    Honest nulls. Fail-open."""
    try:
        bt = out.get("backtest") or {}
        append_event(
            "a6_llm_proposed",
            "data/risk_radar/calibration.json",
            article=6,
            authored_by="risk_radar_review",
            evidence={
                "lane": "ii",
                "gate": _A6_GATE_SPEC,
                "backtest": bt,
                "applied": False,
                "reject_reason": out.get("degraded_reason"),
            },
            note="proposal rejected by do-no-harm gate",
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("risk_radar_review: governance reject event failed: %s", exc)


def _write_calibration(calib: dict, root=None) -> None:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "risk_radar" / "calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bands": calib["bands"], "alert_from": calib["alert_from"],
                             "legs": {k: {"thr_pct": v.get("thr_pct")} for k, v in calib["legs"].items()},
                             "prob_cal": calib["prob_cal"],
                             "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                            indent=2, default=str))


def run(persist: bool = True, root=None, force: bool = False, call=None,
        scorecard: dict | None = None, compare=None) -> dict:
    """Gate -> Opus proposes bounded deltas -> CLAMP -> do-no-harm backtest -> apply iff it improves.
    Logs every verdict. `call`/`scorecard`/`compare` injectable for hermetic tests. Never raises."""
    cfg = _cfg()
    out = {"schema": "risk_radar_review.v1",
           "asof": datetime.now(timezone.utc).date().isoformat(), "applied": False}
    if not force and not cfg.get("enabled", False):
        out["degraded_reason"] = "disabled"
        return out
    try:
        if scorecard is None:
            from engine import risk_radar_audit as rra
            scorecard = rra.scorecard(root=root)
        if (scorecard or {}).get("n_graded", 0) < int(cfg.get("min_graded", 30)):
            out["degraded_reason"] = "insufficient_graded"
            out["n_graded"] = (scorecard or {}).get("n_graded", 0)
            return out
        from engine.risk_radar import _calib
        base_calib = _calib(root=root)
        call = call or _make_call(cfg)
        if call is None:
            out["degraded_reason"] = "no_client_or_key"
            return out
        text = call(_SYSTEM, _evidence_pack(scorecard, base_calib))
        proposal = _extract_json(text) if text else None
        if not proposal or "deltas" not in proposal:
            out["degraded_reason"] = "no_usable_proposal"
            return out
        proposed = _clamp(proposal.get("deltas") or {}, base_calib, cfg)

        # A6 lane-(ii): record the proposal + pre-committed gate BEFORE apply decision
        _gov_proposal(proposal, proposed, root=root)

        # do-no-harm backtest gate
        cmp = compare or (lambda p: __import__("engine.risk_radar_backtest",
                                               fromlist=["compare_calib"]).compare_calib(p, base_calib))
        verdict = cmp(proposed)
        out["analysis"] = proposal.get("analysis")
        out["proposed_bands"] = proposed["bands"]
        out["proposed_alert_from"] = proposed["alert_from"]
        out["backtest"] = {k: verdict.get(k) for k in ("base", "proposed", "improves", "legs_ok")}
        if verdict.get("improves"):
            if persist:
                _write_calibration(proposed, root=root)
            out["applied"] = True
            # A6 lane-(ii): record the apply with before/after calibration + backtest evidence
            _gov_apply(out, base_calib, proposed, root=root)
        else:
            out["degraded_reason"] = "rejected_by_do_no_harm"
            # A6 lane-(ii): record the reject with honest nulls
            _gov_reject(out, base_calib, proposed, root=root)
        if persist:
            _append_review_log({**out, "rationale": proposal.get("rationale"),
                                "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                               root=root)
        return out
    except Exception as e:  # noqa: BLE001 — never fatal
        log.error("risk_radar_review failed: %s", e)
        out["degraded_reason"] = "review_error"
        return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    r = run(force=a.force)
    print(json.dumps({"applied": r.get("applied"), "degraded": r.get("degraded_reason"),
                      "improves": (r.get("backtest") or {}).get("improves")}, indent=2, default=str))
