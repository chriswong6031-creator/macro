"""CoVe entailment gate — deterministic numeric fabrication detector for LLM briefs (P2).

Chain-of-Verification, the cheap deterministic half: an LLM brief (master_brain / ai_desk /
news summaries) must only cite NUMBERS that the computed engine fields actually contain. This
strips/flags any figure the model invented — a VIX "at 28" when the state says 19, a score the
engines never produced. No LLM and no topical matching: it's number-against-number entailment.

Pragmatic + unit-aware (%, bps, ×, plain), tolerant of rounding and of the common transforms a
field can appear in (raw, ×100, ÷100, |·|, rounded). It is ADVISORY by design — derived numbers
(a spread = a − b) can't all be matched, so the output is a fail-rate to gate a build to a
REVIEW chip when fabrication spikes, not a hard per-claim block. Pure stdlib.
"""
from __future__ import annotations

import re

# standalone numbers (NOT glued to a letter on the left → excludes 'Q1', 'H2', 'S&P500'):
# 19, 19.2, -23.8, 1,250, +0.05
_NUM = re.compile(r"(?<![A-Za-z])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
_BPS = re.compile(r"bps\b|basis points?\b", re.I)
_ALLOWED_AFTER = set("bBxX%")     # a letter here is a unit (bps / ×), not 'glued to a word' (10y, 5G)
_TOL = 0.02            # relative tolerance for a match (rounding slack)
_ABS_TOL = 0.005       # absolute floor so small numbers (0.05 vs 0.051) still match


def extract_numbers(text: str) -> list:
    """Standalone numeric mentions in `text` as (raw, value, unit), unit ∈ {'pct','bps',''}.
    Digits glued to letters (Q1, 10y, 5G) are NOT numeric claims and are skipped."""
    out = []
    if not text:
        return out
    s = str(text)
    for m in _NUM.finditer(s):
        end = m.end()
        nxt = s[end] if end < len(s) else ""
        if nxt.isalpha() and nxt not in _ALLOWED_AFTER:   # glued to a word → not a claim
            continue
        try:
            val = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        tail = s[end: end + 14].lstrip()
        unit = "pct" if tail.startswith("%") else ("bps" if _BPS.match(tail) else "")
        out.append((m.group(0), val, unit))
    return out


def _field_values(fields) -> set:
    """Flatten a state dict/list into the set of numeric values the engines COMPUTED (the
    'truth' set). Only real numeric fields — NOT digits embedded in label strings (a 'Q1'
    quad or a '2026-01-05' date would otherwise pollute the truth with spurious 1 / 2026)."""
    vals: set = set()

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            try:
                vals.add(round(float(o), 6))
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
    walk(fields)
    return vals


def _matches(value: float, unit: str, truth: set) -> bool:
    cands = {value, abs(value), -value}
    if unit == "pct":
        cands |= {value / 100.0, -value / 100.0}        # "5%" may be stored as 0.05
    if unit == "bps":
        cands |= {value / 1e4, -value / 1e4}            # "45 bps" → 0.0045
    for c in cands:
        for t in truth:
            if abs(c - t) <= max(_ABS_TOL, _TOL * max(abs(c), abs(t))):
                return True
    return False


def verify_claims(text: str, fields) -> dict:
    """Check every number in `text` against the computed `fields`. Returns
    {n_numbers, supported, unsupported, unsupported_values, fail_rate} — fail_rate is the
    fraction of cited numbers NOT entailed by any field value (the fabrication signal). With
    no numeric fields to verify against, it passes (fail_rate 0): can't verify ≠ fabricated."""
    nums = extract_numbers(text)
    truth = _field_values(fields)
    if not truth:
        return {"n_numbers": len(nums), "supported": len(nums), "unsupported": 0,
                "unsupported_values": [], "fail_rate": 0.0, "note": "no computed fields"}
    unsupported = [raw for (raw, v, u) in nums if not _matches(v, u, truth)]
    n = len(nums)
    return {"n_numbers": n, "supported": n - len(unsupported),
            "unsupported": len(unsupported), "unsupported_values": unsupported,
            "fail_rate": round(len(unsupported) / n, 4) if n else 0.0}


def entailment_gate(text: str, fields, max_fail_rate: float = 0.34) -> dict:
    """Advisory gate: pass=False (→ route to a review chip) when the fabricated-number rate
    exceeds `max_fail_rate`. Degrade-never-raise; a brief with no numbers trivially passes."""
    try:
        rep = verify_claims(text, fields)
    except Exception:  # noqa: BLE001
        return {"pass": True, "fail_rate": 0.0, "error": "verify_failed"}
    rep["pass"] = rep["fail_rate"] <= max_fail_rate
    return rep


__all__ = ["extract_numbers", "verify_claims", "entailment_gate"]
