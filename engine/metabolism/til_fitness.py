"""engine.metabolism.til_fitness — TIL fitness card builder (A3, SENSE stage).

Reads the EXISTING immutable TIL sensors (read-only) and produces a typed
rollup at data/metabolism/fitness/til.json.

Immutable sensor artifacts (NEVER modified here):
  - data/foresight/earliness_grades.json    (foresight_leadlag.py → Stage 1)
  - data/foresight/theme_placebo_tape.jsonl (theme_placebo.py → Stage 2)
  - data/qledger/falsifier_evaluations.jsonl (qledger_falsifier.py → Stage 3)
  - data/qledger/claims.jsonl                (claim registry)

Fitness dimensions:
  1. front_run_lead   — front-run lead-days: median signed lead vs attention crowd.
                        Source: earliness_grades.json pooled_summary.
  2. placebo_hit_rate — placebo-adjusted hit-rate: fraction of covered non-WATCH legs
                        with a graded, non-null read that beat the placebo.
                        Source: theme_placebo_tape.jsonl cross-joined with grades.
  3. falsifier_honesty — thesis-ledger firing rate: confirmed / (confirmed + tripped).
                         Source: falsifier_evaluations.jsonl.
  4. live_leg_quality — fraction of covered legs that ever produced a graded,
                        non-null placebo-beating read.
                        Source: cross of claims.jsonl + falsifier_evaluations.

All 4 metrics are ACCRUING until at least 2026-10-15 (the first real check_by
in the pre-registered TIL trial contracts).  We print honest "accruing" flags,
NOT fake numbers, when sample size is below minimum.

Output schema: metabolism.til_fitness.v1
  {
    "schema": "metabolism.til_fitness.v1",
    "as_of":  ISO date,
    "lobe":   "til",
    "maturity": "accruing" | "partial" | "ready",
    "sensors": {
      "<name>": {
        "value":    float | null,
        "n":        int,
        "maturity": "accruing" | "ready",
        "source":   str,
        "note":     str | null,
      },
      ...
    },
    "authority": { is_context_only: true, ... },
    "notes": str,
  }

Authority block: is_context_only=True, all promotion flags False.
No LLM calls.  Tolerant reader (missing artifacts → honest null + accruing).
Always exits 0.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.til_fitness.v1"
OUTPUT_PATH = ("data", "metabolism", "fitness", "til.json")
LOBE = "til"

# Minimum N thresholds before a metric is considered "ready"
_MIN_N_LEAD = 10        # lead-days: need 10+ graded flags
_MIN_N_PLACEBO = 10     # placebo beat-rate: need 10+ entries with grade
_MIN_N_FALSIFIER = 5    # falsifier honesty: need 5+ evaluations (tripped + confirmed)
_MIN_N_LIVE_LEG = 10    # live-leg quality: need 10+ covered legs

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}


# ── Sensor 1: front-run lead-days ─────────────────────────────────────────────

def _read_lead_days(root: Path) -> dict[str, Any]:
    """Read earliness_grades.json and extract the pooled lead-days sensor."""
    path = root / "data" / "foresight" / "earliness_grades.json"
    if not path.exists():
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(path),
            "note": "earliness_grades.json not yet present — nightly grade_thematic must run first",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pooled = data.get("pooled_summary") or {}
        n_graded = int(pooled.get("n_graded_flags", 0))
        median_lead = pooled.get("overall_median_lead_days")
        share_led = pooled.get("share_led")

        maturity = "ready" if n_graded >= _MIN_N_LEAD else "accruing"
        value = float(median_lead) if (median_lead is not None and maturity == "ready") else None

        return {
            "value": value,
            "n": n_graded,
            "maturity": maturity,
            "source": str(path),
            "share_led": float(share_led) if share_led is not None else None,
            "note": (
                None if maturity == "ready"
                else f"accruing: {n_graded}/{_MIN_N_LEAD} flags graded (need {_MIN_N_LEAD})"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("til_fitness._read_lead_days: %s", exc)
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(path),
            "note": f"read error: {exc}",
        }


# ── Sensor 2: placebo-adjusted hit-rate ───────────────────────────────────────

def _read_placebo_hit_rate(root: Path) -> dict[str, Any]:
    """Read theme_placebo_tape.jsonl and compute the beat-rate vs placebo.

    The placebo tape records: for each graded non-WATCH flag, whether the real
    theme outperformed its K=3 random peer placebo themes.  We simply count
    rows where 'beats_placebo' is True vs total graded rows (non-null 'graded').
    """
    path = root / "data" / "foresight" / "theme_placebo_tape.jsonl"
    if not path.exists():
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(path),
            "note": "theme_placebo_tape.jsonl not yet present — nightly grade_thematic must run first",
        }
    try:
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue

        # Count graded rows (rows where 'graded' key exists and is not null)
        graded = [r for r in rows if r.get("graded") is not None]
        n = len(graded)
        maturity = "ready" if n >= _MIN_N_PLACEBO else "accruing"

        if maturity == "ready":
            beats = sum(1 for r in graded if r.get("beats_placebo") is True)
            value = float(beats / n) if n > 0 else None
        else:
            value = None
            beats = sum(1 for r in graded if r.get("beats_placebo") is True)

        return {
            "value": value,
            "n": n,
            "n_beats": beats,
            "maturity": maturity,
            "source": str(path),
            "note": (
                None if maturity == "ready"
                else f"accruing: {n}/{_MIN_N_PLACEBO} graded entries (need {_MIN_N_PLACEBO})"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("til_fitness._read_placebo_hit_rate: %s", exc)
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(path),
            "note": f"read error: {exc}",
        }


# ── Sensor 3: falsifier honesty ───────────────────────────────────────────────

def _read_falsifier_honesty(root: Path) -> dict[str, Any]:
    """Read falsifier_evaluations.jsonl and compute honesty = confirmed/(confirmed+tripped).

    Higher = more claims confirmed (surviving falsification attempts).
    Falsifier-tripped = the claim was falsified (a miss).
    Honesty focuses on whether the pre-committed claims held under scrutiny.
    """
    path = root / "data" / "qledger" / "falsifier_evaluations.jsonl"
    if not path.exists():
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(path),
            "note": "falsifier_evaluations.jsonl not yet present — nightly grade_thematic must run first",
        }
    try:
        n_confirmed = 0
        n_tripped = 0
        n_unverifiable = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            outcome = r.get("outcome", "")
            if outcome == "CONFIRMED":
                n_confirmed += 1
            elif outcome == "FALSIFIER_TRIPPED":
                n_tripped += 1
            elif outcome == "UNVERIFIABLE":
                n_unverifiable += 1

        n_scoreable = n_confirmed + n_tripped
        maturity = "ready" if n_scoreable >= _MIN_N_FALSIFIER else "accruing"
        value = float(n_confirmed / n_scoreable) if (n_scoreable > 0 and maturity == "ready") else None

        return {
            "value": value,
            "n": n_scoreable,
            "n_confirmed": n_confirmed,
            "n_tripped": n_tripped,
            "n_unverifiable": n_unverifiable,
            "maturity": maturity,
            "source": str(path),
            "note": (
                None if maturity == "ready"
                else f"accruing: {n_scoreable}/{_MIN_N_FALSIFIER} scoreable evaluations"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("til_fitness._read_falsifier_honesty: %s", exc)
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(path),
            "note": f"read error: {exc}",
        }


# ── Sensor 4: live-leg quality ────────────────────────────────────────────────

def _read_live_leg_quality(root: Path) -> dict[str, Any]:
    """Compute: fraction of covered legs that ever produced a graded non-null,
    placebo-beating read.

    'Covered leg' = a claim in claims.jsonl that has a falsifier + check_by.
    'Placebo-beating' = outcome=="CONFIRMED" in falsifier_evaluations.
    This is NOT raw coverage — raw coverage alone is worthless (a claim
    can accrue thousands of rows before any check_by fires).
    """
    claims_path = root / "data" / "qledger" / "claims.jsonl"
    evals_path = root / "data" / "qledger" / "falsifier_evaluations.jsonl"

    if not claims_path.exists() or not evals_path.exists():
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": f"{claims_path}, {evals_path}",
            "note": (
                "claims.jsonl or falsifier_evaluations.jsonl absent — "
                "nightly grade_thematic must run first"
            ),
        }
    try:
        # Load confirmed claim IDs from evaluations
        confirmed_ids: set[str] = set()
        for line in evals_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("outcome") == "CONFIRMED":
                    confirmed_ids.add(r.get("claim_id", ""))
            except Exception:  # noqa: BLE001
                continue

        # Count covered legs (claims with falsifier + check_by set)
        n_covered = 0
        n_quality = 0
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
                has_falsifier = bool(c.get("falsifier"))
                has_checkby = bool(c.get("check_by"))
                if has_falsifier and has_checkby:
                    n_covered += 1
                    claim_id = c.get("claim_id") or c.get("id") or ""
                    if claim_id and claim_id in confirmed_ids:
                        n_quality += 1
            except Exception:  # noqa: BLE001
                continue

        maturity = "ready" if n_covered >= _MIN_N_LIVE_LEG else "accruing"
        value = float(n_quality / n_covered) if (n_covered > 0 and maturity == "ready") else None

        return {
            "value": value,
            "n": n_covered,
            "n_quality_legs": n_quality,
            "maturity": maturity,
            "source": f"{claims_path.name}, {evals_path.name}",
            "note": (
                None if maturity == "ready"
                else f"accruing: {n_covered}/{_MIN_N_LIVE_LEG} covered legs (need {_MIN_N_LIVE_LEG})"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("til_fitness._read_live_leg_quality: %s", exc)
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": str(claims_path),
            "note": f"read error: {exc}",
        }


# ── Card assembler ────────────────────────────────────────────────────────────

def build_fitness_card(root: Path) -> dict[str, Any]:
    """Read all TIL sensors and return the assembled fitness card dict.

    This function reads only — it does NOT write the output file.
    Use scripts/build_til_fitness.py for the write path.

    Returns
    -------
    dict — fitness card (schema metabolism.til_fitness.v1).  Never raises.
    """
    try:
        sensors = {
            "front_run_lead": _read_lead_days(root),
            "placebo_hit_rate": _read_placebo_hit_rate(root),
            "falsifier_honesty": _read_falsifier_honesty(root),
            "live_leg_quality": _read_live_leg_quality(root),
        }

        # Roll-up maturity: all-ready → ready; any-accruing → accruing; mix → partial
        maturities = {s["maturity"] for s in sensors.values()}
        if maturities == {"ready"}:
            overall_maturity = "ready"
        elif "accruing" in maturities and "ready" not in maturities:
            overall_maturity = "accruing"
        else:
            overall_maturity = "partial"

        card: dict[str, Any] = {
            "schema": SCHEMA,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "lobe": LOBE,
            "maturity": overall_maturity,
            "sensors": sensors,
            "authority": AUTHORITY_BLOCK,
            "notes": (
                "All sensors are accruing until first TIL check_by dates fire (~2026-10-15). "
                "Values are display-context only; no signal-path authority. "
                "Maturity flag is honest: do NOT promote based on pre-maturity values."
            ),
        }
        return card
    except Exception as exc:  # noqa: BLE001
        log.warning("til_fitness.build_fitness_card: %s", exc)
        return {
            "schema": SCHEMA,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "lobe": LOBE,
            "maturity": "accruing",
            "sensors": {},
            "authority": AUTHORITY_BLOCK,
            "notes": f"Error building fitness card: {exc}",
        }
