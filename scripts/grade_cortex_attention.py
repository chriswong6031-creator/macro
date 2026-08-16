"""scripts/grade_cortex_attention.py — Nightly cortex attention grader + A2 earn-in.

SINGLE-WRITER: this script is the ONLY writer to
  data/reflexes/cortex_attention/grades.jsonl

WHAT IT DOES
------------
1. Reads data/reflexes/cortex_attention/firings.jsonl (attention claims).
2. Finds matured claims (asof + horizon_d elapsed as of today).
3. Grades each matured claim per falsifier class:
   - realized_move   → engine.grading.forward_metrics on the symbol.
                       direction != 0 → SIGNED excess vs SPY (a directional bet).
                       direction == 0 → |excess| vs the symbol's own pre-asof
                       placebo distribution (a MAGNITUDE test; see below).
   - escalation      → check alert artifact for downstream alert within horizon_d
   - verdict_change  → check world_state history for call change in predicted direction

DIRECTION 0 IS NOT A LONG BET
-----------------------------
A direction=0 attention flag makes NO directional claim — it says the scope is
worth WATCHING.  Grading it on the SIGN of excess-vs-SPY answers a question the
claim never asked, and scores a coin flip as skill.  Until W3 this module did
exactly that: `int(direction or 1)` mapped 0 → +1, so every salience flag was
graded as a long call (24 of 25 live firings are direction=0).

The honest test for a direction=0 claim is MAGNITUDE: did the scope realise an
unusually LARGE move over the horizon?  "Unusually large" is defined against the
scope's OWN history, not an assumed prior — the threshold is the
`_MAGNITUDE_Q` quantile of |excess vs SPY| over horizon-length windows that
closed STRICTLY BEFORE asof, so the base rate of a hit is (1 - _MAGNITUDE_Q)
BY CONSTRUCTION.  No lookahead, no assumed 0.5.

GRADED vs UNGRADEABLE (nulls are printed, not hidden)
-----------------------------------------------------
`outcome_hit` is TRI-STATE.  False means "the criterion was evaluated and did
not fire" (a real miss).  None means "the criterion could not be evaluated"
(a null) — no price data for a macro scope, no dated alert artifact, no
world_state history covering the window, a compound criterion no single grader
can test, or an unrecognised falsifier.  Nulls are WRITTEN to the ledger with a
reason and EXCLUDED from the A2 earn-in denominator.

This distinction is load-bearing.  Before W3 every ungradeable claim was scored
`outcome_hit=False`, i.e. a fabricated miss, which both understated the hit rate
and inflated n — so the A2 gate (`wilson_lb(hits, n) / base_rate > 1.25`) could
never clear no matter how good attention actually was.  A grader that returns a
constant is not a measurement.
4. Writes graded outcomes to data/reflexes/cortex_attention/grades.jsonl
   (sidecar rows, one per claim_id that matured).
5. Runs A2 earn-in via constitution.grant_authority on the graded record.
6. Writes result to data/neuralweb/cortex/probation.json (single source).
7. Appends governance events ON TRANSITIONS ONLY (granted ↔ refused).

GRADE SCHEMA (reflex.cortex_attention.grade.v1)
-----------------------------------------------
  claim_id          str   — matches the firings.jsonl claim_id
  graded_at         str   — ISO-8601 date (today)
  grader_version    str
  falsifier_class   str   realized_move | escalation | verdict_change | unknown
  outcome_hit       bool|None — True fired / False did not fire / None ungradeable
  outcome_detail    dict  — evidence detail; carries ungradeable_reason when None
  gradeable         bool  — False iff outcome_hit is None (explicit, greppable)
  horizon_d         int
  asof              str
  symbol            str
  direction         int   — the claim's OWN direction, never coerced
  base_rate         float — base rate OF THE CRITERION ACTUALLY APPLIED
                            (signed: 0.5; magnitude: 1 - _MAGNITUDE_Q)

A2 EARN-IN
----------
  After grading, constitution.grant_authority is called with:
    hits  = graded rows where outcome_hit=True
    n     = GRADEABLE rows only (outcome_hit is not None) — nulls excluded
    base_rate = mean of the per-row base_rate over those gradeable rows, so the
                lift denominator matches the criteria actually applied
    min_n = 25, min_events = 8
  Result → data/neuralweb/cortex/probation.json
  Governance event appended ON TRANSITIONS ONLY (refused→granted or granted→refused).

STATUS NOTE
  A2 stays refused while the gradeable record is under the n>=25 floor.  The
  live corpus is entirely scope_type='macro' with no price-resolvable scope, so
  most rows grade as disclosed nulls; probation.json reports the null count
  alongside n and hits so the refusal reason is legible rather than implied.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

_GRADER_VERSION = "W3-PR1"
_GRADE_SCHEMA = "reflex.cortex_attention.grade.v1"
_BASE_RATE_DEFAULT = 0.5   # conservative prior for a SIGNED (directional) outcome

# --- Magnitude grading (direction == 0) -----------------------------------
# The hit threshold is the _MAGNITUDE_Q quantile of the scope's own pre-asof
# |excess vs SPY| distribution, so P(hit | no skill) = 1 - _MAGNITUDE_Q exactly.
# 0.70 keeps the bar meaningful ("moved more than it does 70% of the time")
# while leaving the A2 floor of 8 hits in 25 reachable: clearing
# wilson_lb/0.30 > 1.25 needs ~13 of 25, a real but attainable bar.
_MAGNITUDE_Q = 0.70
_MAGNITUDE_BASE_RATE = round(1.0 - _MAGNITUDE_Q, 4)   # 0.30
# Refuse to mint a threshold from a thin sample — a quantile over a handful of
# windows is noise, and a fabricated threshold is worse than a disclosed null.
_MIN_PLACEBO_N = 60


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _root_path(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _data(root: Path, *parts: str) -> Path:
    return root / "data" / Path(*parts)


def _firings_path(root: Path) -> Path:
    return _data(root, "reflexes", "cortex_attention", "firings.jsonl")


def _grades_path(root: Path) -> Path:
    return _data(root, "reflexes", "cortex_attention", "grades.jsonl")


def _probation_path(root: Path) -> Path:
    return _data(root, "neuralweb", "cortex", "probation.json")


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _is_synthetic(row: dict) -> bool:
    """Return True if the row is a dry-run synthetic item that must be excluded from grading.

    Synthetic rows must never contribute to the probation counter (n) or hits — they are
    dry-run artefacts seeded at system initialisation, not real cortex attention events.
    Exclusion is at READ/GRADE time only; ledger rows are never deleted (append-only law).
    A row is synthetic if ANY of the following hold:
      - trigger_key == "SYNTHETIC_TICKER"  (legacy dry-run marker)
      - scope_key == "SYNTHETIC_TICKER"
      - "(dry-run synthetic item)" appears in the falsifier field
      - explicit field synthetic: true
    """
    trigger_key = str(row.get("trigger_key") or "")
    scope_key = str(row.get("scope_key") or "")
    falsifier = str(row.get("falsifier") or "")
    synthetic_flag = row.get("synthetic", False)
    return (
        trigger_key == "SYNTHETIC_TICKER"
        or scope_key == "SYNTHETIC_TICKER"
        or "(dry-run synthetic item)" in falsifier
        or synthetic_flag is True
    )


def _load_firings(root: Path) -> list[dict]:
    """Load real (non-synthetic) firing rows from firings.jsonl.

    Synthetic dry-run items (ticker=SYNTHETIC_TICKER or explicit marker) are excluded
    at read time — they must never enter the grading loop or the probation counter.
    The ledger itself is never modified (append-only law).
    """
    p = _firings_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if _is_synthetic(row):
                log.debug("grade_cortex_attention: skipping synthetic row claim_id=%s", row.get("claim_id", "?"))
                continue
            rows.append(row)
        except Exception:  # noqa: BLE001
            pass
    return rows


def _is_synthetic_grade(row: dict) -> bool:
    """Return True if a grade row corresponds to a dry-run synthetic item.

    Mirrors _is_synthetic() for firing rows.  Grade rows use different field names
    (symbol instead of trigger_key/scope_key; outcome_detail.symbol for the resolved
    entity), so we must check all analogous paths to avoid silent leakage if a future
    synthetic grade row lacks a top-level symbol field.

    A grade row is synthetic if ANY of the following hold:
      - top-level symbol == "SYNTHETIC_TICKER"
      - outcome_detail.symbol == "SYNTHETIC_TICKER"
      - "(dry-run synthetic item)" appears in the falsifier field (carried through
        from the original firing row)
      - explicit field synthetic: true
    """
    symbol = str(row.get("symbol") or "")
    outcome_symbol = str((row.get("outcome_detail") or {}).get("symbol") or "")
    falsifier = str(row.get("falsifier") or "")
    synthetic_flag = row.get("synthetic", False)
    return (
        symbol == "SYNTHETIC_TICKER"
        or outcome_symbol == "SYNTHETIC_TICKER"
        or "(dry-run synthetic item)" in falsifier
        or synthetic_flag is True
    )


def _load_grades(root: Path) -> list[dict]:
    """Load real (non-synthetic) grade rows from grades.jsonl.

    Synthetic grades are excluded at read time so they never inflate n or hits.
    Uses _is_synthetic_grade() which mirrors all four conditions of _is_synthetic()
    (the firing-row predicate) to ensure both readers agree on what 'synthetic' means.
    Ledger rows are never deleted (append-only law).
    """
    p = _grades_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if _is_synthetic_grade(row):
                log.debug("grade_cortex_attention: skipping synthetic grade claim_id=%s", row.get("claim_id", "?"))
                continue
            rows.append(row)
        except Exception:  # noqa: BLE001
            pass
    return rows


def _graded_ids(root: Path) -> set[str]:
    return {r.get("claim_id") for r in _load_grades(root) if r.get("claim_id")}


def _claim_direction(claim: dict) -> int:
    """The claim's OWN direction.  0 is a real value, never a missing one.

    `int(claim.get("direction") or 1)` — the pre-W3 form — collapses 0, None, ""
    and absent alike onto +1, silently turning every direction=0 salience flag
    into a long call.  A missing direction is 0 (no directional claim), which is
    also the honest reading: a claim that did not state a direction did not make
    a directional bet.
    """
    raw = claim.get("direction", 0)
    if raw is None or raw == "":
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Falsifier class detection
# ---------------------------------------------------------------------------

# Falsifier vocabularies.  Matched on WORD BOUNDARIES, never as naked substrings.
#
# The naked-substring version of this router mis-classified every realized_move it
# ever emitted on live data: "move" matched inside "REmove attention if ..." (3 rows)
# and "return" matched inside "if the radar RETURNS below caution" (1 row).  All four
# were then graded as price bets on a macro scope with no price series.  Word
# boundaries alone fix both — \bmove\b does not match "remove", and "returns" is not
# in the vocabulary at all (see below).
_ESCALATION_TERMS = (
    r"escalat\w*",
    r"alerts?",
    r"tripwires?",
)
# Deliberately NARROW.  Only genuinely price-relative language qualifies.
# Excluded on purpose:
#   "return(s)"       — "the radar returns below caution" is a state transition.
#                       The price sense is covered by "excess/total return".
#   "falls"/"gains"/"rises" — used for macro LEVELS as often as prices in this
#                       corpus ("the 10-year real yield falls at least 20bp",
#                       "HY OAS widens above 3.25%"), which are not tradeable
#                       excess-return criteria.
#   "price"           — appears in "priced in", a sentiment phrase.
_PRICE_TERMS = (
    r"outperform\w*",
    r"underperform\w*",
    r"excess returns?",
    r"total returns?",
    r"pullbacks?",
    r"drawdowns?",
    r"rall(?:y|ies)",
    r"moves?", r"moved", r"movements?",
)
_STATE_TERMS = (
    r"regimes?",
    r"verdicts?",
    r"labels?",
    r"radar",
    r"flags?",
    r"conflicts?",
    r"tensions?",
    r"diverge\w*", r"divergen\w*",
    r"confirmations?",
    r"states?",
    r"risk[-_ ]o(?:n|ff)",
    # Regime-quadrant labels.  Several falsifiers name the transition without ever
    # using the word "regime" ("Remove attention if China exits Q3 into Q1/Q2 ...").
    r"Q[1-4]",
)
# Most specific first.  A claim matching several families is COMPOUND: its
# falsifier is a conjunction no single grader can evaluate, and it is graded as a
# disclosed null rather than partially tested against whichever clause happened
# to win the tie-break.
_FAMILY_ORDER = ("escalation", "realized_move", "verdict_change")
_FAMILY_TERMS = {
    "escalation": _ESCALATION_TERMS,
    "realized_move": _PRICE_TERMS,
    "verdict_change": _STATE_TERMS,
}
_FAMILY_RE = {
    fam: re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.IGNORECASE)
    for fam, terms in _FAMILY_TERMS.items()
}


def _price_symbol(claim: dict, root: Path | None) -> str | None:
    """Return the claim's scope as a symbol ONLY if a price series actually exists.

    Resolution is by file existence, never by guessing from the name — the live
    corpus is entirely scope_type='macro' with scope_keys like
    'Open Long-Treasuries overweight theses', which must never be handed to a
    price grader as if it were a ticker.
    """
    symbol = str(claim.get("scope_key") or claim.get("symbol") or "").strip()
    if not symbol or root is None:
        return None
    if (root / "data" / "yahoo" / f"{symbol}.parquet").exists():
        return symbol
    return None


def _classify(claim: dict, root: Path | None = None) -> dict[str, Any]:
    """Classify a claim's falsifier.  Returns class, matched families and evidence."""
    falsifier = str(claim.get("falsifier") or "")
    families = [fam for fam in _FAMILY_ORDER if _FAMILY_RE[fam].search(falsifier)]
    matched = {
        fam: sorted({m.group(0).lower() for m in _FAMILY_RE[fam].finditer(falsifier)})
        for fam in families
    }
    direction = _claim_direction(claim)
    price_symbol = _price_symbol(claim, root)

    # Structure first: a scope that resolves to a real price series is gradeable
    # on price, and that beats any amount of prose inference.
    if price_symbol and (direction != 0 or "realized_move" in families or not families):
        cls = "realized_move"
    elif families:
        cls = families[0]
    else:
        cls = "unknown"

    return {
        "class": cls,
        "families": families,
        "matched_terms": matched,
        "compound": len(families) > 1,
        "price_symbol": price_symbol,
    }


def _detect_falsifier_class(claim: dict, root: Path | None = None) -> str:
    """Detect falsifier class from the claim's falsifier field and scope."""
    return str(_classify(claim, root)["class"])


# ---------------------------------------------------------------------------
# Falsifier class graders
# ---------------------------------------------------------------------------

def _abs_excess_placebo(
    close,
    spy_close,
    horizon_d: int,
    asof,
) -> tuple[list[float], str]:
    """|horizon-length excess vs SPY| for windows that CLOSED strictly before asof.

    This is the null distribution the magnitude test is scored against — "how big
    is a normal move for THIS scope over THIS horizon", measured on the scope's own
    history rather than assumed.

    No lookahead: a window is kept only when its EXIT bar is strictly before asof,
    so every observation had fully resolved by the time the claim was made.

    The fill convention matches engine.grading.forward_metrics exactly — entry at
    bar i+1, exit at bar i+1+H — because the threshold and the statistic it judges
    must measure the same quantity.
    """
    import pandas as pd  # noqa: PLC0415

    cutoff = pd.Timestamp(asof)
    if spy_close is not None:
        joined = pd.concat({"sym": close, "spy": spy_close}, axis=1).dropna()
        basis = "excess_vs_spy"
    else:
        joined = pd.concat({"sym": close}, axis=1).dropna()
        basis = "raw"
    if joined.empty:
        return [], basis

    entry = joined.shift(-1)
    exit_ = joined.shift(-(1 + horizon_d))
    ret = exit_ / entry - 1.0
    exit_dates = pd.Series(joined.index, index=joined.index).shift(-(1 + horizon_d))
    closed_before = exit_dates < cutoff   # NaT compares False → tail dropped

    ex = ret["sym"] - ret["spy"] if basis == "excess_vs_spy" else ret["sym"]
    ex = ex[closed_before].dropna()
    return [abs(float(v)) for v in ex.to_numpy()], basis


def _grade_realized_move(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool | None, dict]:
    """Grade realized-move claims via forward_metrics.

    direction != 0 → SIGNED excess vs SPY (the claim bet on a direction).
    direction == 0 → |excess| vs the scope's own pre-asof placebo distribution.
                     A salience flag claims the scope is worth WATCHING, not that
                     it goes up; scoring the SIGN of its excess answers a question
                     the claim never asked.

    Returns (None, detail) when the criterion cannot be evaluated — no
    price-resolvable scope, horizon not elapsed, or too little history to mint a
    threshold.  A null is disclosed, never rounded down to a miss.
    """
    scope_raw = str(claim.get("scope_key") or claim.get("symbol") or "")
    horizon_d = int(claim.get("horizon_d") or 5)
    direction = _claim_direction(claim)
    asof_str = str(claim.get("asof") or "")

    detail: dict[str, Any] = {
        "symbol": scope_raw,
        "horizon_d": horizon_d,
        "direction": direction,
        "criterion": "signed_excess_vs_spy" if direction != 0 else "abs_excess_vs_placebo",
    }

    symbol = _price_symbol(claim, root)
    if not symbol or not asof_str:
        detail["ungradeable_reason"] = (
            "missing asof" if symbol and not asof_str
            else f"scope {scope_raw!r} is not a price-resolvable symbol"
        )
        return None, detail

    try:
        from engine.grading import forward_metrics  # type: ignore[import]

        close = _load_close(root, symbol)
        spy_close = _load_close(root, "SPY")

        if close is None or len(close) < 5:
            detail["ungradeable_reason"] = f"no price data for {symbol}"
            return None, detail

        fm = forward_metrics(close, asof_str, horizons=(horizon_d,))
        fwd_ret = fm.get(f"fwd_ret_{horizon_d}")
        if fwd_ret is None:
            detail["ungradeable_reason"] = f"horizon {horizon_d}d not yet elapsed"
            return None, detail

        spy_ret = None
        if spy_close is not None:
            spy_fm = forward_metrics(spy_close, asof_str, horizons=(horizon_d,))
            spy_ret = spy_fm.get(f"fwd_ret_{horizon_d}")

        excess = float(fwd_ret) - float(spy_ret) if spy_ret is not None else float(fwd_ret)

        detail.update({
            "fwd_ret": round(float(fwd_ret), 4),
            "spy_ret": round(float(spy_ret), 4) if spy_ret is not None else None,
            "excess": round(float(excess), 4),
        })

        if direction != 0:
            hit = (excess > 0) if direction > 0 else (excess < 0)
            detail["base_rate"] = _BASE_RATE_DEFAULT
            return bool(hit), detail

        # --- direction == 0: MAGNITUDE, never sign -------------------------
        placebo, basis = _abs_excess_placebo(
            close,
            spy_close if spy_ret is not None else None,
            horizon_d,
            asof_str,
        )
        detail["placebo_basis"] = basis
        detail["placebo_n"] = len(placebo)
        if len(placebo) < _MIN_PLACEBO_N:
            detail["ungradeable_reason"] = (
                f"only {len(placebo)} pre-asof {horizon_d}d windows "
                f"(need {_MIN_PLACEBO_N}) to mint a magnitude threshold"
            )
            return None, detail

        import numpy as np  # noqa: PLC0415

        threshold = float(np.quantile(np.asarray(placebo, dtype=float), _MAGNITUDE_Q))
        abs_excess = abs(excess)
        detail.update({
            "abs_excess": round(abs_excess, 4),
            "threshold": round(threshold, 4),
            "threshold_q": _MAGNITUDE_Q,
            "base_rate": _MAGNITUDE_BASE_RATE,
        })
        return bool(abs_excess > threshold), detail

    except Exception as exc:  # noqa: BLE001
        log.debug("grade_realized_move: %s (%s)", symbol, exc)
        detail["error"] = str(exc)
        detail["ungradeable_reason"] = f"grader raised: {exc}"
        return None, detail


def _grade_escalation(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool | None, dict]:
    """Grade escalation claims: did an alert fire within horizon_d?

    Returns None when the alert store carries NO dated artifacts at all — with
    nothing dated to read, "no alert fired" and "no alert was ever recorded" are
    indistinguishable, and only the first is a miss.  When the store is live
    (dated artifacts exist), an absence inside the window is a genuine miss.
    """
    symbol = claim.get("scope_key") or ""
    horizon_d = int(claim.get("horizon_d") or 5)
    asof_str = str(claim.get("asof") or "")
    detail: dict[str, Any] = {"symbol": symbol, "horizon_d": horizon_d}

    try:
        asof_date = date.fromisoformat(asof_str[:10])
        deadline = asof_date + timedelta(days=horizon_d)
        detail["horizon_window"] = f"{asof_date} to {deadline}"

        alerts_dir = _data(root, "alerts")
        if not alerts_dir.exists():
            detail["ungradeable_reason"] = "no alerts directory"
            return None, detail

        found_alert = False
        dated_files = 0
        for alert_file in sorted(alerts_dir.glob("*.json")):
            try:
                content = json.loads(alert_file.read_text(encoding="utf-8"))
                alert_date_str = str(content.get("date") or alert_file.stem[:10])
                alert_date = date.fromisoformat(alert_date_str[:10])
            except Exception:  # noqa: BLE001
                continue
            dated_files += 1
            if asof_date < alert_date <= deadline:
                content_str = json.dumps(content)
                if symbol and symbol.lower() in content_str.lower():
                    found_alert = True
                    detail["alert_file"] = alert_file.name
                    break

        detail["dated_alert_files"] = dated_files
        if dated_files == 0:
            detail["ungradeable_reason"] = (
                "alert store carries no dated artifacts — cannot tell a "
                "non-escalation from an unrecorded one"
            )
            return None, detail

        return found_alert, detail

    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        detail["ungradeable_reason"] = f"grader raised: {exc}"
        return None, detail


def _grade_verdict_change(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool | None, dict]:
    """Grade verdict-change claims via world_state.

    direction != 0 → the claim predicted WHICH WAY the call would move, and the
    current world_state snapshot is keyword-tested for that direction.

    direction == 0 → the claim predicted only that the state would CHANGE.
    Answering that needs world_state HISTORY spanning the window; the repo keeps
    a single current snapshot (data/neuralweb/world_state.json), so there is
    nothing to difference against and the claim is a disclosed null.  Returning
    False here — the pre-W3 behaviour, via an unconditional `else: hit = False`
    — scored every state claim as a miss it never had a chance to pass.
    """
    symbol = claim.get("scope_key") or ""
    horizon_d = int(claim.get("horizon_d") or 5)
    direction = _claim_direction(claim)
    asof_str = str(claim.get("asof") or "")
    detail: dict[str, Any] = {"symbol": symbol, "direction": direction}

    if direction == 0:
        detail["ungradeable_reason"] = (
            "direction=0 state claim needs world_state history spanning the "
            "horizon; only a single current snapshot is kept"
        )
        return None, detail

    try:
        # Check world_state for regime change
        ws_path = _data(root, "neuralweb", "world_state.json")
        if not ws_path.exists():
            detail["ungradeable_reason"] = "world_state not available"
            return None, detail

        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        asof_date = date.fromisoformat(asof_str[:10])
        ws_date_str = str(ws.get("as_of") or "")[:10]

        if not ws_date_str:
            detail["ungradeable_reason"] = "world_state has no as_of"
            return None, detail

        ws_date = date.fromisoformat(ws_date_str)
        deadline = asof_date + timedelta(days=horizon_d)

        if ws_date < asof_date or ws_date > deadline:
            detail["ungradeable_reason"] = (
                f"world_state date {ws_date} outside window {asof_date}..{deadline}"
            )
            return None, detail

        # Look for any regime/verdict change in the world state
        verdict = ws.get("verdict") or ""
        risk_state = ws.get("risk_radar_state") or ""

        # Simple heuristic: if direction=-1 and verdict/risk_state contains
        # escalatory keywords, that's a verdict change.
        # direction == 0 never reaches here — it returned a null above.
        if direction < 0:
            hit = any(kw in (verdict + " " + risk_state).lower()
                      for kw in ("risk-off", "risk_off", "elevated", "critical"))
        else:
            hit = any(kw in (verdict + " " + risk_state).lower()
                      for kw in ("risk-on", "risk_on", "positive", "recovery"))

        detail.update({
            "verdict": verdict,
            "risk_state": risk_state,
            "window": f"{asof_date} to {deadline}",
            "base_rate": _BASE_RATE_DEFAULT,
        })
        return bool(hit), detail

    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        detail["ungradeable_reason"] = f"grader raised: {exc}"
        return None, detail


def _load_close(root: Path, symbol: str):
    """Load close series for a symbol from yahoo parquet."""
    try:
        import pandas as pd  # noqa: PLC0415
        p = root / "data" / "yahoo" / f"{symbol}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        s = df["close"].dropna()
        s.name = symbol
        return s
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# A2 earn-in evaluation
# ---------------------------------------------------------------------------

def _load_previous_probation(root: Path) -> dict:
    p = _probation_path(root)
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_probation(
    root: Path,
    probation: dict,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    p = _probation_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(probation, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_cortex_attention: could not write probation.json (%s)", exc)


def _emit_governance_transition(
    event_type: str,
    result,
    root: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type,
            target="cortex_attention_queue",
            article=2,
            authored_by="grade_cortex_attention",
            evidence={
                "granted": result.granted,
                "reason": result.reason,
                "lift_lb": result.lift_lb,
                "wilson_lb": result.wilson_lb,
                "lapses_at": result.lapses_at,
                "evidence_asof": result.evidence_asof,
            },
            note=(
                f"A2 earn-in: {event_type} — {result.reason}. "
                f"Probation status updated in data/neuralweb/cortex/probation.json."
            ),
            root=str(root),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_cortex_attention: governance event failed (%s)", exc)


def evaluate_a2_earn_in(
    grades: list[dict],
    root: Path,
    dry_run: bool,
    now: datetime,
) -> dict[str, Any]:
    """Evaluate A2 earn-in from graded attention record.  Returns probation dict."""
    from engine.neuralweb.constitution import (  # type: ignore[import]
        AuthorityLevel, grant_authority,
    )

    # Only GRADEABLE rows enter the denominator.  A claim the grader could not
    # evaluate is a null, not a miss — counting it as a miss both understates the
    # hit rate and inflates n, which is a one-way ratchet against ever clearing
    # the Article-3 gate.  Nulls are still written to the ledger and reported.
    gradeable = [g for g in grades if g.get("outcome_hit") is not None]
    ungradeable_n = len(grades) - len(gradeable)
    n = len(gradeable)
    hits = sum(1 for g in gradeable if g.get("outcome_hit"))
    evidence_asof = None
    if gradeable:
        dates = [g.get("graded_at") for g in gradeable if g.get("graded_at")]
        if dates:
            evidence_asof = max(str(d)[:10] for d in dates)

    # The lift denominator must be the base rate of the criteria ACTUALLY applied.
    # Magnitude grades carry 1 - _MAGNITUDE_Q, signed grades carry 0.5; scoring a
    # mixed record against a flat 0.5 tests the wrong null.
    rates = []
    for g in gradeable:
        try:
            rates.append(float(g.get("base_rate", _BASE_RATE_DEFAULT)))
        except (TypeError, ValueError):
            rates.append(_BASE_RATE_DEFAULT)
    base_rate = round(sum(rates) / len(rates), 6) if rates else _BASE_RATE_DEFAULT

    evidence = {
        "hits": hits,
        "n": n,
        "base_rate": base_rate,
        "evidence_asof": evidence_asof,
    }

    result = grant_authority(
        evidence,
        floors={"min_n": 25, "min_events": 8},
        target_level=AuthorityLevel.A2_ATTEND,
        now=now,
    )

    prev = _load_previous_probation(root)
    prev_granted = prev.get("granted", False)

    probation: dict[str, Any] = {
        "schema": "neuralweb.cortex_probation.v1",
        "as_of": now.date().isoformat(),
        "granted": result.granted,
        "tier": "A2 granted" if result.granted else "A0/A1 shadow",
        "reason": result.reason,
        "lift_lb": result.lift_lb,
        "wilson_lb": result.wilson_lb,
        "lapses_at": result.lapses_at,
        "evidence_asof": result.evidence_asof,
        "attention_track_record": {
            "n": n,
            "hits": hits,
            "base_rate": base_rate,
            # Printed, not hidden: how much of the record could not be graded.
            "ungradeable": ungradeable_n,
            "total_rows": len(grades),
        },
        "is_context_only": True,
    }

    # Governance events ON TRANSITIONS ONLY
    transition = prev_granted != result.granted
    if transition:
        event_type = "authority_grant" if result.granted else "authority_lapse"
        _emit_governance_transition(event_type, result, root, dry_run)
        log.info(
            "grade_cortex_attention: A2 transition %s→%s — %s",
            prev_granted, result.granted, result.reason,
        )
    else:
        log.info(
            "grade_cortex_attention: A2 unchanged (granted=%s) — %s. "
            "n=%d, hits=%d. Running at %s.",
            result.granted, result.reason, n, hits,
            "A2/ATTEND" if result.granted else "A0/A1 (observe+explain)",
        )

    _write_probation(root, probation, dry_run)
    return probation


# ---------------------------------------------------------------------------
# Main grading loop
# ---------------------------------------------------------------------------

def grade_attention(
    root: Path | str | None = None,
    dry_run: bool = False,
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Grade matured attention claims and update A2 earn-in.  Returns summary."""
    root_p = _root_path(root) if not isinstance(root, Path) else root
    if today is None:
        today = datetime.now(timezone.utc).date()
    if now is None:
        now = datetime.now(timezone.utc)

    firings = _load_firings(root_p)
    already_graded = _graded_ids(root_p)

    matured = []
    for claim in firings:
        cid = claim.get("claim_id")
        if not cid or cid in already_graded:
            continue
        asof_str = str(claim.get("asof") or "")[:10]
        horizon_d = claim.get("horizon_d") or 5
        if not asof_str:
            continue
        try:
            asof_date = date.fromisoformat(asof_str)
            deadline = asof_date + timedelta(days=int(horizon_d))
            if today >= deadline:
                matured.append(claim)
        except Exception:  # noqa: BLE001
            pass

    log.info(
        "grade_cortex_attention: %d total firings, %d already graded, %d matured today",
        len(firings), len(already_graded), len(matured),
    )

    new_grades = []
    for claim in matured:
        cid = claim.get("claim_id", "unknown")
        symbol = claim.get("scope_key") or claim.get("symbol") or "macro"
        horizon_d = int(claim.get("horizon_d") or 5)
        direction = _claim_direction(claim)
        asof_str = str(claim.get("asof") or "")[:10]

        cls = _classify(claim, root_p)
        fc = str(cls["class"])
        detail: dict[str, Any]
        hit: bool | None

        if cls["compound"]:
            # The falsifier conjoins criteria from several families.  No single
            # grader tests the stated condition, and grading one clause would
            # report on a different claim than the one that was made.
            hit = None
            detail = {
                "symbol": symbol,
                "ungradeable_reason": (
                    "compound falsifier spans " + "+".join(cls["families"])
                    + "; no single grader tests the stated conjunction"
                ),
            }
        elif fc == "realized_move":
            hit, detail = _grade_realized_move(claim, root_p, today)
        elif fc == "escalation":
            hit, detail = _grade_escalation(claim, root_p, today)
        elif fc == "verdict_change":
            hit, detail = _grade_verdict_change(claim, root_p, today)
        else:
            hit = None
            detail = {
                "symbol": symbol,
                "ungradeable_reason": "falsifier matched no known criterion family",
            }

        detail.setdefault("families", cls["families"])
        detail.setdefault("matched_terms", cls["matched_terms"])

        grade_row: dict[str, Any] = {
            "schema": _GRADE_SCHEMA,
            "claim_id": cid,
            "graded_at": today.isoformat(),
            "grader_version": _GRADER_VERSION,
            "falsifier_class": fc,
            "outcome_hit": hit,
            "gradeable": hit is not None,
            "outcome_detail": detail,
            "horizon_d": horizon_d,
            "asof": asof_str,
            "symbol": symbol,
            "direction": direction,
            "base_rate": float(detail.get("base_rate", _BASE_RATE_DEFAULT)),
        }
        new_grades.append(grade_row)
        log.info(
            "grade_cortex_attention: graded %s (class=%s, hit=%s)",
            cid[:12], fc, "null" if hit is None else hit,
        )

    # Write new grades (single-writer; append to sidecar)
    if new_grades and not dry_run:
        grades_p = _grades_path(root_p)
        try:
            grades_p.parent.mkdir(parents=True, exist_ok=True)
            with grades_p.open("a", encoding="utf-8") as fh:
                for g in new_grades:
                    fh.write(json.dumps(g, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.warning("grade_cortex_attention: grades write failed (%s)", exc)

    # Reload all grades (including newly written ones if not dry_run)
    all_grades = _load_grades(root_p) if not dry_run else (
        _load_grades(root_p) + new_grades
    )

    # A2 earn-in
    probation = evaluate_a2_earn_in(all_grades, root_p, dry_run, now)

    # adapt_reflexes join: mark graded firings in spine by updating query layer
    # (query.adapt_reflexes will pick up grades.jsonl via the join documented in
    # the scout — the grader writes grades.jsonl; adapt_reflexes is updated to
    # read and join it onto firings rows by claim_id)

    summary = {
        "as_of": today.isoformat(),
        "grader_version": _GRADER_VERSION,
        "dry_run": dry_run,
        "total_firings": len(firings),
        "already_graded": len(already_graded),
        "matured_today": len(matured),
        "new_grades": len(new_grades),
        "new_nulls": sum(1 for g in new_grades if g.get("outcome_hit") is None),
        "all_grades_n": len(all_grades),
        "a2_earn_in": {
            "granted": probation.get("granted"),
            "reason": probation.get("reason"),
            "n": probation.get("attention_track_record", {}).get("n", 0),
            "hits": probation.get("attention_track_record", {}).get("hits", 0),
            "ungradeable": probation.get("attention_track_record", {}).get("ungradeable", 0),
            "base_rate": probation.get("attention_track_record", {}).get("base_rate"),
        },
    }

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [grade_cortex_attention] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Cortex attention grader + A2 earn-in (W7b PR2)"
    )
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = grade_attention(root=args.root, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("grade_cortex_attention: fatal (%s)", exc, exc_info=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
