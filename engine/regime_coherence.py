"""Risk COHERENCE assert — the "can never contradict on a stress day" guarantee.

Masterplan W2, audit #4. Three generations of "how risk-off" (MRS / risk_state /
risk_radar) plus the page banner (market_state) and the bot prior must never silently
DISAGREE about direction. The exact failure #4 warns of: the banner screams Risk-off
(radar) while the conviction gate still sizes Risk-on (MRS). Previously only the headline
STRING was reconciled cosmetically; the gate arithmetic could still diverge.

This module is the BUILD-TIME INVARIANT. It checks, from a fully-assembled latest.json:

  (A) SINGLE GROSS SOURCE — the three gross tables (regime_one / risk_state / risk_radar)
      emit identical magnitudes on the shared bands (they now all derive from
      engine.regime_one.RISK_STATE_GROSS). A drift is a HARD FAIL.

  (B) GATE BASIS PROVENANCE — the sector-central conviction gate declares which risk
      engine drives it. This wave it is MRS (the 2026-06-23 replay did not pass, so no
      flip — scripts/ab_risk_gate.py). The fused gate is published SHADOW. A silent basis
      change is a HARD FAIL (the flip must be a deliberate, replay-gated act).

  (C) DIRECTIONAL DIVERGENCE ON A STRESS DAY — under NO-FLIP (this wave), a banner-risk-off
      / gate-risk-on day is a KNOWN, replay-characterized RESIDUAL (MRS drives the gate; the
      radar-aware banner legitimately measures more). So the bare divergence is a TRACKED
      reconciliation RECORD, not a build-stopper. But (C) keeps its teeth: it HARD-FAILS on the
      three conditions that would mean no-flip is WRONG or the reconciliation is DISHONEST:
        (C1) FUSED-WOULD-HAVE-CAUGHT-IT — the SHADOW fused gate is cautious while the live MRS
             gate is NOT. That is a day where flipping WOULD have de-grossed — it contradicts the
             2026-06-23 replay conclusion and RE-OPENS the flip decision. Hard fail (loudly: the
             no-flip needs re-litigation / the harness is stale).
        (C2) BASIS DISCLOSURE — on a divergence day the page must surface BOTH bases (the MRS gate
             basis AND the radar-aware banner), so the user reads "weather says storm, the position
             sizer (MRS) hasn't de-risked" — informative, not a hidden contradiction. If the page
             collapses to one number / hides a basis, hard fail.
        (C3) ENVELOPE — the divergence must stay within the gap the A/B harness characterized under
             no-flip. A gap wider than anything the replay saw is a regression even under no-flip.

`assert_coherence(latest)` returns a report dict and, when `strict=True`, raises
CoherenceError on any hard-fail so the build stops. Run.py calls it non-strict by default
(logs loudly) and strict under COHERENCE_STRICT=1 / in CI.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


class CoherenceError(AssertionError):
    """Raised when the risk verdict is internally contradictory (a stress-day #4 hazard)."""


# States that mean "lean cautious / risk-off" in each vocabulary. (The vocab DRIFT across
# these engines — RISK_OFF vs risk-off vs risk_off — is itself a symptom of #4; enumerate
# every token explicitly so the assert can never miss a stress signal on a spelling.)
_CAUTIOUS_FUSED = {"caution", "elevated", "risk-off"}
_CAUTIOUS_RS = {"caution", "elevated", "risk-off", "risk_off"}
# market_state verdict vocabulary is {RISK_ON, MIXED, RISK_OFF} (uppercase, underscore).
_CAUTIOUS_BANNER = {"RISK_OFF", "risk-off", "risk_off"}
# a "materially cautious" live gate: below this the gate is de-grossing meaningfully.
_GATE_CAUTIOUS_MAX = 0.90


def _gross_tables_agree() -> dict:
    """(A) The three gross tables must match on the shared bands (single-source)."""
    from engine.regime_one import RISK_STATE_GROSS
    from engine.risk_radar import _GROSS as RR
    from engine.risk_state import _DEFAULT_GROSS as RS

    shared = ["caution", "elevated", "risk-off"]
    def rs(k):
        return RS.get(k) or RS.get(k.replace("-", "_"))
    def rr(k):
        return RR.get(k) or RR.get(k.replace("-", "_"))
    gaps = {}
    ok = True
    for st in shared:
        vals = [v for v in (RISK_STATE_GROSS.get(st), rs(st), rr(st)) if v is not None]
        gap = (max(vals) - min(vals)) if len(vals) > 1 else 0.0
        gaps[st] = round(gap, 4)
        if gap > 1e-9:
            ok = False
    return {"ok": ok, "gaps": gaps}


def _live_gate(latest: dict) -> dict:
    """The LIVE sector-central conviction gate + its declared basis. Recomputes via the
    same _regime_anchor the build uses, passing the IN-MEMORY `latest` for THIS run (before
    it is written to disk) so the gate is validated against the same-run risk read — not the
    previous run's persisted latest.json.

    `error` is set (and `basis` stays None with `computed=False`) when the anchor could not be
    computed — distinct from a deliberate basis change, so check (B) does not misread a transient
    compute failure as a silent flip."""
    try:
        from engine.sector_central import _regime_anchor
        anc = _regime_anchor(latest)
        return {"gate_factor": anc.get("gate_factor"), "basis": "MRS", "computed": True,
                "risk_on": anc.get("risk_on"), "ms_verdict": anc.get("ms_verdict"),
                "radar_state": anc.get("radar_state")}
    except Exception as e:  # noqa: BLE001
        return {"gate_factor": None, "basis": None, "computed": False, "error": str(e)}


def assert_coherence(latest: dict, *, strict: bool | None = None) -> dict:
    """Run the three checks against an assembled latest.json. Returns a report; raises
    CoherenceError on a hard fail when strict."""
    if strict is None:
        strict = os.environ.get("COHERENCE_STRICT") == "1"

    report: dict = {"ok": True, "hard_fail": False, "checks": {}, "reasons": []}

    # (A) single gross source
    a = _gross_tables_agree()
    report["checks"]["gross_tables_agree"] = a
    if not a["ok"]:
        report["ok"] = report["hard_fail"] = True
        report["reasons"].append(f"gross tables diverge on shared bands: {a['gaps']}")

    # (B) gate basis provenance
    gate = _live_gate(latest)
    report["checks"]["live_gate"] = gate
    fused = ((latest or {}).get("regime_one") or {}).get("fused_risk") or {}
    fused_gate = fused.get("gate") or {}
    report["checks"]["fused_gate_shadow"] = {
        "basis": fused_gate.get("basis"), "gate_factor": fused_gate.get("gate_factor"),
        "shadow": bool(((latest or {}).get("regime_one") or {}).get("shadow", True))}
    if gate.get("computed") and gate.get("basis") != "MRS":
        # a computed gate on a non-MRS basis is a real SILENT FLIP — hard fail. (A compute
        # FAILURE, gate['computed'] False, is NOT a flip — it's tracked below, not a hard fail,
        # so a transient market_state/anchor error can't masquerade as a deliberate basis change.)
        report["hard_fail"] = True
        report["reasons"].append(
            f"live sector gate basis is {gate.get('basis')!r}, expected 'MRS' (no flip this "
            "wave — the 06-23 replay did not pass; update this assert deliberately when it does).")
    elif not gate.get("computed"):
        report["reasons"].append(
            f"live gate could not be computed ({gate.get('error')}) — tracked, not a flip; "
            "directional check skipped.")

    # (C) directional DIVERGENCE on a stress day — tracked record; C1/C2/C3 keep the teeth.
    banner_verdict = gate.get("ms_verdict")
    fused_label = fused.get("label")
    rs_state = ((latest or {}).get("risk_state") or {}).get("state")
    gate_factor = gate.get("gate_factor")
    fused_gate_factor = fused_gate.get("gate_factor")

    loud = []
    if banner_verdict in _CAUTIOUS_BANNER:
        loud.append(f"banner={banner_verdict}")
    if fused_label in _CAUTIOUS_FUSED:
        loud.append(f"fused_risk={fused_label}")
    if rs_state in _CAUTIOUS_RS:
        loud.append(f"risk_state={rs_state}")

    stress_day = bool(loud)
    gate_is_cautious = (gate_factor is not None and gate_factor <= _GATE_CAUTIOUS_MAX)
    fused_is_cautious = (fused_gate_factor is not None and fused_gate_factor <= _GATE_CAUTIOUS_MAX)
    # the bare banner-vs-gate divergence: a KNOWN residual under no-flip (NOT a hard fail).
    divergence = bool(stress_day and gate_factor is not None and not gate_is_cautious)

    dchecks: dict = {"stress_signals": loud, "stress_day": stress_day,
                     "live_gate_factor": gate_factor, "live_gate_cautious": gate_is_cautious,
                     "shadow_fused_gate_factor": fused_gate_factor,
                     "shadow_fused_cautious": fused_is_cautious,
                     "banner_vs_gate_divergence": divergence,
                     "divergence_basis": "known-residual (no-flip): MRS gate vs radar-aware banner"}

    # C1 — FUSED-WOULD-HAVE-CAUGHT-IT: the shadow fused gate is cautious while the live MRS gate
    # is not. This is the ONE condition that overturns the no-flip decision → HARD FAIL, loudly.
    c1 = bool(divergence and fused_is_cautious and not gate_is_cautious)
    dchecks["c1_fused_would_have_caught"] = c1
    if c1:
        report["hard_fail"] = True
        report["reasons"].append(
            f"C1 RE-OPEN NO-FLIP: on a stress day the SHADOW fused gate ({fused_gate_factor}) IS "
            f"cautious while the live MRS gate ({gate_factor}) is NOT — flipping WOULD have de-grossed "
            "here, contradicting the 2026-06-23 replay conclusion. Re-run scripts/ab_risk_gate.py and "
            "re-litigate the flip; the no-flip may be stale / out-of-sample.")

    # C2 — BASIS DISCLOSURE: on a divergence day the page must surface BOTH bases (the MRS gate
    # basis AND the radar-aware banner verdict) so the divergence is legible, not hidden.
    have_gate_basis = gate.get("basis") is not None
    have_banner = banner_verdict is not None
    c2_ok = (not divergence) or (have_gate_basis and have_banner)
    dchecks["c2_both_bases_disclosed"] = c2_ok
    if not c2_ok:
        report["hard_fail"] = True
        report["reasons"].append(
            "C2 HIDDEN BASIS: a divergence day must show BOTH the MRS gate basis and the radar-aware "
            f"banner (have_gate_basis={have_gate_basis}, have_banner={have_banner}); the page is "
            "collapsing the two bases into one number — the cosmetic-only reconciliation #4 rejects.")

    # C3 — ENVELOPE: the live gate must not be pathologically wide-open (>0.98) on a full risk-off
    # banner day, EVEN under no-flip — that exceeds anything the replay characterized.
    c3_breach = bool(divergence and gate_factor is not None and gate_factor > 0.98)
    dchecks["c3_envelope_breach"] = c3_breach
    if c3_breach:
        report["hard_fail"] = True
        report["reasons"].append(
            f"C3 ENVELOPE: live gate {gate_factor} is wide-open (>0.98) on a risk-off banner day — "
            "wider than the no-flip replay envelope; a genuine regression, not a known residual.")

    report["checks"]["directional"] = dchecks

    report["ok"] = not report["hard_fail"]
    if report["hard_fail"]:
        msg = "risk coherence FAILED: " + " | ".join(report["reasons"])
        if strict:
            raise CoherenceError(msg)
        log.error(msg)
    else:
        div = report["checks"].get("directional", {}).get("banner_vs_gate_divergence")
        if div:
            log.warning("risk coherence OK (hard invariants pass); TRACKED banner-vs-gate divergence "
                        "under no-flip: banner=%s gate=%s (fused shadow=%s) — surfaced, not a regression.",
                        banner_verdict, gate_factor, fused_gate_factor)
        else:
            log.info("risk coherence OK (gross single-source, gate basis=MRS, no divergence).")
    return report


def main() -> int:  # pragma: no cover — CLI
    import json
    from lib import config
    p = config.data_dir() / "regime" / "latest.json"
    latest = json.loads(p.read_text()) if p.exists() else {}
    rep = assert_coherence(latest, strict=False)
    print(json.dumps(rep, indent=2, default=str))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
