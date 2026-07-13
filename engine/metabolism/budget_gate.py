"""engine.metabolism.budget_gate — Metabolism V11 budget-gate engine.

Computes per-key utilisation from live ratelimit response headers (or
estimated fallback) and produces gate verdicts for the three auto modes
that drive the new UX:

    5h_max     — run until all enabled keys reach ≥80% of their 5-hour window
    weekly_max — run until all enabled keys reach ≥80% of their weekly quota,
                 pausing between 5-hour windows as needed
    manual     — blocked only when ALL enabled keys are known ≥90% weekly

FROZEN API (do not change signatures without updating the orchestrator spec):

    load_budget_cfg(root=None) -> dict
    key_budget(key_id, root=None) -> dict
    gate_verdict(mode, root=None) -> dict
    write_status(root=None) -> str

CLI:
    python -m engine.metabolism.budget_gate --mode 5h_max|weekly_max|manual
    Prints ONE JSON line to stdout.  exit 0 always (NEVER-RAISE contract).

NEVER-RAISE CONTRACT: every public function catches all exceptions and
returns the safe fail-open default.  Token values are never logged.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CFG_REL = "config/metabolism_budget.yml"
_STATUS_REL = "data/metabolism/key_budget_status.json"
_STATUS_SCHEMA = "metab_budget_status.v1"

# ── hardcoded defaults (operator overrides via metabolism_budget.yml V11 section)
_DEFAULTS: dict[str, Any] = {
    "fivehour_done_pct": 80,
    "weekly_done_pct": 80,
    "weekly_key_stop_pct": 85,
    "manual_floor_pct": 90,
    "est_budget_5h_tokens": None,
    "est_budget_weekly_tokens": None,
    "duration_noop_floor_s": 300,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


# ── Config ────────────────────────────────────────────────────────────────────

def load_budget_cfg(root: Path | None = None) -> dict:
    """Load config/metabolism_budget.yml and return the V11 gate-policy section.

    Falls back to hardcoded defaults on any error.  NEVER raises.
    """
    try:
        import yaml  # noqa: PLC0415
        base = root if root is not None else _repo_root()
        p = base / _CFG_REL
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        # V11 gate policy lives under the top-level keys directly (operator
        # may add them alongside the existing V1 keys, or in a sub-section).
        # We read from "gate_policy" sub-dict if present, else top-level.
        src = raw.get("gate_policy", raw)
        cfg: dict[str, Any] = dict(_DEFAULTS)
        for key in _DEFAULTS:
            if key in src:
                cfg[key] = src[key]
        return cfg
    except Exception as exc:  # noqa: BLE001
        log.warning("budget_gate.load_budget_cfg: %s — using defaults", exc)
        return dict(_DEFAULTS)


# ── Header parsing ────────────────────────────────────────────────────────────

def _pct_from_str(val: str | None) -> float | None:
    """Parse '42', '42%', 42 → 42.0; None/unparseable → None."""
    if val is None:
        return None
    try:
        s = str(val).strip().rstrip("%")
        return float(s)
    except (ValueError, TypeError):
        return None


# Patterns to classify a header name as 5h or weekly.
_RE_5H = re.compile(r"5.?h|five.?hour", re.I)
_RE_WEEKLY = re.compile(r"7.?d|seven.?day|week", re.I)
# Patterns to identify utilisation/used vs reset.
_RE_USED = re.compile(r"utiliz|used|percent|pct|remaining", re.I)
_RE_RESET = re.compile(r"reset", re.I)


def _parse_headers(headers: dict) -> dict:
    """Extract pct_5h, pct_weekly, reset_5h, reset_weekly from ratelimit headers.

    The Anthropic API header names are not yet stable; we parse generically:
      - header name contains '5h'/'five-hour' → window bucket
      - header name contains '7d'/'seven-day'/'week' → weekly bucket
      - header value looks numeric (possibly %-suffixed) → utilisation percentage
      - header name contains 'reset' → ISO reset hint

    Returns dict with keys pct_5h, pct_weekly, reset_5h, reset_weekly (all
    may be None).
    """
    pct_5h: float | None = None
    pct_weekly: float | None = None
    reset_5h: str | None = None
    reset_weekly: str | None = None

    for raw_k, v in headers.items():
        k = raw_k.lower()
        if not k.startswith("anthropic-ratelimit"):
            continue
        is_5h = bool(_RE_5H.search(k))
        is_weekly = bool(_RE_WEEKLY.search(k))
        is_reset = bool(_RE_RESET.search(k))
        is_used = bool(_RE_USED.search(k))

        if is_reset:
            if is_5h and reset_5h is None:
                reset_5h = str(v)
            elif is_weekly and reset_weekly is None:
                reset_weekly = str(v)
            # also handle bare reset without horizon hint
            elif not is_5h and not is_weekly:
                # default to 5h if no hint
                if reset_5h is None:
                    reset_5h = str(v)
        elif is_used or is_5h or is_weekly:
            pv = _pct_from_str(str(v))
            if pv is not None:
                if is_5h and pct_5h is None:
                    pct_5h = pv
                elif is_weekly and pct_weekly is None:
                    pct_weekly = pv

    return {
        "pct_5h": pct_5h,
        "pct_weekly": pct_weekly,
        "reset_5h": reset_5h,
        "reset_weekly": reset_weekly,
    }


# ── Per-key budget ────────────────────────────────────────────────────────────

def key_budget(key_id: str, root: Path | None = None) -> dict:
    """Compute utilisation info for one key.

    Returns:
        pct_5h:      float|None — percentage of 5h window used (0-100)
        src_5h:      "reported"|"est"|None
        pct_weekly:  float|None — percentage of weekly quota used
        src_weekly:  "reported"|"est"|None
        reset_5h:    str|None — ISO reset hint
        reset_weekly: str|None — ISO reset hint

    Sources:
        "reported" — parsed from freshest ratelimit_headers row
        "est"      — computed from est_tokens / est_budget_*_tokens config
        None       — unknown (no data and no budget config)

    NEVER raises.
    """
    result: dict[str, Any] = {
        "pct_5h": None, "src_5h": None,
        "pct_weekly": None, "src_weekly": None,
        "reset_5h": None, "reset_weekly": None,
    }
    try:
        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root)
        cfg = load_budget_cfg(root)

        # Find the row for this key_id
        row: dict[str, Any] | None = None
        for r in rows:
            if r.get("key_id") == key_id:
                row = r
                break

        if row is None:
            # Key not in snapshot at all — check est fallback
            _apply_est_fallback(result, cfg, est_5h_tokens=0, est_weekly_tokens=0)
            return result

        # Try reported headers first
        headers: dict = row.get("ratelimit_headers") or {}
        if headers:
            parsed = _parse_headers(headers)
            if parsed["pct_5h"] is not None:
                result["pct_5h"] = parsed["pct_5h"]
                result["src_5h"] = "reported"
            if parsed["pct_weekly"] is not None:
                result["pct_weekly"] = parsed["pct_weekly"]
                result["src_weekly"] = "reported"
            if parsed["reset_5h"] is not None:
                result["reset_5h"] = parsed["reset_5h"]
            if parsed["reset_weekly"] is not None:
                result["reset_weekly"] = parsed["reset_weekly"]

        # Est fallback for any dimension still unknown
        est_5h = int(row.get("window_5h_est_tokens") or 0)
        est_wk = int(row.get("weekly_est_tokens") or 0)
        _apply_est_fallback(result, cfg, est_5h_tokens=est_5h, est_weekly_tokens=est_wk)

    except Exception as exc:  # noqa: BLE001
        log.warning("budget_gate.key_budget(%s): %s", key_id, exc)
    return result


def _apply_est_fallback(
    result: dict,
    cfg: dict,
    est_5h_tokens: int,
    est_weekly_tokens: int,
) -> None:
    """Fill in est-based pct where reported is still None."""
    if result["pct_5h"] is None:
        budget_5h = cfg.get("est_budget_5h_tokens")
        if budget_5h and budget_5h > 0:
            result["pct_5h"] = 100.0 * est_5h_tokens / budget_5h
            result["src_5h"] = "est"

    if result["pct_weekly"] is None:
        budget_wk = cfg.get("est_budget_weekly_tokens")
        if budget_wk and budget_wk > 0:
            result["pct_weekly"] = 100.0 * est_weekly_tokens / budget_wk
            result["src_weekly"] = "est"


# ── Gate verdicts ─────────────────────────────────────────────────────────────

def _enabled_key_ids_for_gate(root: Path | None = None) -> list[str]:
    """Return enabled+present key_ids from the pool snapshot. NEVER raises."""
    try:
        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root)
        return [
            r["key_id"] for r in rows
            if r.get("enabled") and r.get("present")
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("budget_gate._enabled_key_ids_for_gate: %s", exc)
        return []


def gate_verdict(mode: str, root: Path | None = None) -> dict:
    """Compute a gate verdict for the given mode.

    mode must be one of: "5h_max", "weekly_max", "manual"

    Returns:
        mode:          str
        per_key:       {key_id: key_budget-dict, ...}
        eligible_keys: [key_id, ...]
        all_done:      bool
        blocked:       bool
        reason:        str
        ts:            ISO timestamp

    NEVER raises.
    """
    result: dict[str, Any] = {
        "mode": mode,
        "per_key": {},
        "eligible_keys": [],
        "all_done": False,
        "blocked": False,
        "reason": "",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        cfg = load_budget_cfg(root)
        key_ids = _enabled_key_ids_for_gate(root)

        if not key_ids:
            result["reason"] = "no_enabled_keys"
            return result

        # Compute per-key budgets
        per_key: dict[str, dict] = {}
        for kid in key_ids:
            per_key[kid] = key_budget(kid, root)
        result["per_key"] = per_key

        fivehour_done = cfg["fivehour_done_pct"]
        weekly_done = cfg["weekly_done_pct"]
        weekly_stop = cfg["weekly_key_stop_pct"]
        manual_floor = cfg["manual_floor_pct"]

        if mode == "5h_max":
            eligible = []
            any_known_5h = False
            for kid, kb in per_key.items():
                if kb["pct_5h"] is not None:
                    any_known_5h = True
                # Operator rule: no sessions on keys past the 90% weekly floor
                # regardless of mode — a session started on such a key would likely
                # trip the weekly limit mid-run.  Unknown weekly does NOT exclude
                # (fail-open: we may not have a reading yet).
                pct_wk = kb["pct_weekly"]
                if pct_wk is not None and pct_wk >= manual_floor:
                    continue
                if kb["pct_5h"] is None or kb["pct_5h"] < fivehour_done:
                    eligible.append(kid)
            result["eligible_keys"] = eligible
            # Never disarm on pure unknowns (spec: "unknown_usage" when no known pct)
            if not any_known_5h:
                result["all_done"] = False
                result["reason"] = "unknown_usage"
            elif not eligible:
                result["all_done"] = True
                result["reason"] = "all_keys_at_5h_threshold"
            else:
                result["reason"] = "eligible_keys_available"

        elif mode == "weekly_max":
            eligible = []
            # all_done = every enabled key has a KNOWN pct_weekly >= weekly_done_pct
            all_weekly_known_done = True  # assume until disproved
            any_weekly_known = False
            for kid, kb in per_key.items():
                pct_wk = kb["pct_weekly"]
                pct_5h = kb["pct_5h"]
                # eligible: weekly below per-key stop AND 5h below window threshold
                wk_ok = pct_wk is None or pct_wk < weekly_stop
                fiveh_ok = pct_5h is None or pct_5h < fivehour_done
                if wk_ok and fiveh_ok:
                    eligible.append(kid)
                # Track whether ALL keys have known weekly >= weekly_done_pct
                if pct_wk is not None:
                    any_weekly_known = True
                    if pct_wk < weekly_done:
                        all_weekly_known_done = False
                else:
                    all_weekly_known_done = False  # unknown = not considered done

            result["eligible_keys"] = eligible

            # all_done is independent of eligible — it reflects weekly quota state
            if any_weekly_known and all_weekly_known_done:
                result["all_done"] = True
                result["reason"] = "all_keys_at_weekly_threshold"
            elif not eligible:
                # Not all done, but nothing eligible either (5h exhausted or all at stop)
                result["all_done"] = False
                result["reason"] = "5h_exhausted_waiting_reset"
            else:
                result["reason"] = "eligible_keys_available"

        elif mode == "manual":
            # blocked only when ALL keys have known pct_weekly >= manual_floor
            all_known_above_floor = True
            for kid, kb in per_key.items():
                pct_wk = kb["pct_weekly"]
                if pct_wk is None or pct_wk < manual_floor:
                    all_known_above_floor = False
                    break

            eligible = [
                kid for kid, kb in per_key.items()
                if kb["pct_weekly"] is None or kb["pct_weekly"] < manual_floor
            ]
            result["eligible_keys"] = eligible

            if all_known_above_floor and len(per_key) > 0:
                result["blocked"] = True
                result["reason"] = f"all_enabled_keys_at_or_above_{manual_floor}pct_weekly"
            else:
                result["reason"] = "manual_run_allowed"

        else:
            result["reason"] = f"unknown_mode:{mode}"
            log.warning("budget_gate.gate_verdict: unknown mode %r", mode)

    except Exception as exc:  # noqa: BLE001
        log.warning("budget_gate.gate_verdict(%s): %s", mode, exc)
        result["reason"] = f"error:{exc}"

    return result


# ── Status snapshot ───────────────────────────────────────────────────────────

def write_status(root: Path | None = None) -> str:
    """Write data/metabolism/key_budget_status.json and return its path.

    Never raises — logs on error and returns the intended path regardless.
    """
    base = root if root is not None else _repo_root()
    out_path = base / _STATUS_REL
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cfg = load_budget_cfg(root)
        key_ids = _enabled_key_ids_for_gate(root)
        per_key: dict[str, dict] = {kid: key_budget(kid, root) for kid in key_ids}

        verdicts: dict[str, dict] = {}
        for mode in ("5h_max", "weekly_max", "manual"):
            v = gate_verdict(mode, root)
            verdicts[mode] = {
                "eligible_keys": v["eligible_keys"],
                "all_done": v["all_done"],
                "blocked": v["blocked"],
                "reason": v["reason"],
            }

        payload = {
            "schema": _STATUS_SCHEMA,
            "ts": ts,
            "per_key": per_key,
            "verdicts": verdicts,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("budget_gate.write_status: %s", exc)
    return str(out_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli_main(argv: list[str] | None = None) -> int:
    """Print one JSON line of the verdict for the requested mode.  exit 0 always."""
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(
        description="Budget gate — print one JSON line for the requested mode."
    )
    ap.add_argument(
        "--mode",
        default="manual",
        help="Gate mode: 5h_max | weekly_max | manual (default: manual)",
    )
    ap.add_argument(
        "--write-status",
        action="store_true",
        help="Also write data/metabolism/key_budget_status.json.",
    )
    ap.add_argument(
        "--root",
        default=None,
        help="Repo root override (for tests).",
    )
    try:
        args = ap.parse_args(argv)
        root = Path(args.root) if args.root else None
        if args.write_status:
            write_status(root)
        verdict = gate_verdict(args.mode, root)
        print(json.dumps(verdict, default=str))
    except Exception as exc:  # noqa: BLE001
        log.warning("budget_gate CLI: %s", exc)
        # Still print one JSON line and exit 0
        print(json.dumps({"error": str(exc), "mode": "unknown", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
