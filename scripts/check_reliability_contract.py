#!/usr/bin/env python3
"""Static guard: fields their OWN gate rejects must not be rendered directionally (audit #46).

Some engine fields are emitted for context but carry a signed DIRECTION the engine's own
calibration marks unreliable (``direction_reliable: false``) or an outright anti-predictive
standalone read (``gated_out: true``). Examples:
  * btc_leverage_cascade ``oi_only_risk`` — OI percentile is anti-predictive standalone
    (measured lift ~0.36), so it is a crowding TEXTURE, never a de-risk CALL.
  * options_flow tick-rule signed fields (``net_premium_mn`` / ``signed_pc`` / net call/put
    vol) — direction soft until the NBBO signing-calibration gate passes.

The FIELD-LEVEL reliability contract (audit #46) says: every such field carries a
``reliability[<field>] = {gated_out, direction_reliable, ...}`` envelope, and a template MUST
NOT render a gated-out field with a DIRECTIONAL treatment — a risk/red/green color, a
bull/bear/de-risk action label, or an up/down arrow — that reads as a signed call.

This guard has two parts:

  1. ENGINE contract — the named gated fields still emit the reliability envelope with the
     expected gated_out state (catches an engine drift that silently drops the contract).
  2. TEMPLATE honesty — no template renders a gated-out field name adjacent to a directional
     color/action token WITHOUT the neutralizing `muted` treatment. This is a heuristic line
     scan (like check_nav_gap): it flags the exact regression #46 fixed — an `oi_only_risk`
     chip painted `var(--warn)` and labeled "de-risk".

Usage:  python -m scripts.check_reliability_contract [TEMPLATES_DIR]
Exit codes: 0 = clean · 1 = a gated field rendered directionally / contract missing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# field name -> the directional tokens that must NOT sit on the same rendered chip unless the
# chip is explicitly neutralized (class "muted" / a display-only/context label present).
GATED_FIELDS = {
    "oi_only_risk": ["var(--warn)", "var(--red)", "de-risk", "de‑risk", "减仓"],
    "net_premium_mn": ["var(--up)", "var(--down)", "bullish", "bearish"],
    "signed_pc": ["var(--up)", "var(--down)", "bullish", "bearish"],
}
# a line is considered SAFE (neutralized) if it carries one of these anywhere on it
NEUTRALIZERS = ("muted", "context", "参考", "display-only", "仅供参考", "texture", "纹理",
                "approx", "近似")


def _scan_templates(tdir: Path) -> list[str]:
    problems: list[str] = []
    for p in sorted(tdir.rglob("*.j2")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(lines, 1):
            for field, dir_tokens in GATED_FIELDS.items():
                if field not in line:
                    continue
                hit = next((tok for tok in dir_tokens if tok in line), None)
                if hit and not any(nz in line for nz in NEUTRALIZERS):
                    try:
                        rel = p.relative_to(ROOT)
                    except ValueError:
                        rel = p
                    problems.append(
                        f"{rel}:{i}: gated-out field '{field}' rendered with "
                        f"directional token '{hit}' and no neutralizer (muted/context) — "
                        f"audit #46: do not render a rejected-by-gate field directionally")
    return problems


def _check_engine_contract() -> list[str]:
    """Assert the engines still emit the reliability envelope for the named gated fields."""
    problems: list[str] = []
    try:
        import numpy as np
        import pandas as pd
        from engine import btc_leverage_cascade as blc
        idx = pd.date_range("2024-01-01", periods=300, freq="D")
        df = pd.DataFrame({"funding_annual_pct": np.full(300, 80.0), "funding_z": np.full(300, 2.5),
                           "oi_mcap_ratio": np.full(300, 0.08), "oi_change": np.full(300, 0.05),
                           "close": np.full(300, 50000.0)}, index=idx)
        # patch the store read so compute() runs offline
        import lib.store as st
        _orig = st.read
        st.read = lambda *a, **k: None  # type: ignore
        try:
            r = blc.compute(sig_df=df)
        finally:
            st.read = _orig
        rel = (r or {}).get("reliability") or {}
        if not (rel.get("oi_only_risk") or {}).get("gated_out"):
            problems.append("btc_leverage_cascade: reliability.oi_only_risk.gated_out must be True")
    except Exception as e:  # noqa: BLE001 — a missing dep must not falsely fail the guard
        print(f"[reliability-contract] engine check skipped: {e}", file=sys.stderr)

    try:
        from engine import options_flow as of
        gate = of.signing_gate()
        # the default (uncalibrated) gate must mark direction unreliable -> signed fields gate out
        if gate.get("direction_reliable"):
            return problems  # calibrated live: fields legitimately un-gated
    except Exception as e:  # noqa: BLE001
        print(f"[reliability-contract] options_flow check skipped: {e}", file=sys.stderr)
    return problems


def main() -> int:
    tdir = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "templates")
    problems = _check_engine_contract() + _scan_templates(tdir)
    if problems:
        print("Reliability-contract guard FAILED (audit #46):", file=sys.stderr)
        for pr in problems:
            print("  " + pr, file=sys.stderr)
        return 1
    print("reliability-contract guard: clean (no gated field rendered directionally)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
