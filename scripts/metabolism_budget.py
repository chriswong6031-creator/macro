"""scripts/metabolism_budget.py — Budget governor + circuit breaker (A7).

Manages the per-cycle budget ledger at data/metabolism/budget_ledger.json.
Reads operator-ratified caps from config/metabolism_budget.yml (IMMUTABLE).

CONTRACT:
  - append-only ledger within a cycle (decrements per stage spend)
  - over-cap → clean no-op return value + journal entry (never raises)
  - circuit breaker: N consecutive failed PRs for a lobe → auto-set per-lobe
    pause flag in the ledger (mirrors healthcheck.py breaker pattern)

Budget ledger schema (metabolism.budget_ledger.v1):
  {
    "schema": "metabolism.budget_ledger.v1",
    "cycle_id": str,
    "started_at": ISO str,
    "updated_at": ISO str,
    "usd_cap": float,
    "token_cap": int,
    "usd_spent": float,   # running total
    "token_spent": int,   # running total
    "entries": [          # append-only list of spend events
      {
        "stage": str,
        "ts": ISO str,
        "usd": float,
        "tokens": int,
        "note": str | null,
      },
      ...
    ],
    "lobes": {            # per-lobe state
      "<lobe>": {
        "failed_pr_streak": int,
        "paused": bool,
      }
    },
  }

NEVER-RAISE CONTRACT: all public functions return safe fallbacks on any error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CONFIG_REL = Path("config") / "metabolism_budget.yml"
_LEDGER_REL = Path("data") / "metabolism" / "budget_ledger.json"
_SCHEMA = "metabolism.budget_ledger.v1"


# ── Path helpers ─────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _LEDGER_REL


def _config_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _CONFIG_REL


# ── Config loader ─────────────────────────────────────────────────────────────

def _load_config(root: Path | None = None) -> dict[str, Any]:
    """Load and return the budget config.  Returns sensible defaults on error."""
    try:
        import yaml
        p = _config_path(root)
        with open(p) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg
    except ImportError:
        log.warning("metabolism_budget: pyyaml not installed; using hardcoded defaults")
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget: could not load config: %s", exc)
    # Hardcoded defaults mirror config/metabolism_budget.yml
    return {
        "per_cycle_usd_cap": 25.0,
        "per_cycle_token_cap": 25_000_000,
        "max_docket_size": 5,
        "circuit_breaker_trip": 3,
    }


def _get_lobe_cap(cfg: dict, lobe: str, key: str, default: Any) -> Any:
    """Get a per-lobe cap, falling back to the global cap."""
    lobe_cfg = (cfg.get("lobe_caps") or {}).get(lobe) or {}
    return lobe_cfg.get(key, cfg.get(key, default))


# ── Ledger read/write ─────────────────────────────────────────────────────────

def _read_ledger(root: Path | None = None) -> dict[str, Any]:
    p = _ledger_path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget: corrupt ledger: %s", exc)
        return {}


def _write_ledger(data: dict[str, Any], root: Path | None = None) -> bool:
    try:
        p = _ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget: write failed: %s", exc)
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Public API ────────────────────────────────────────────────────────────────

def init_cycle(cycle_id: str, root: Path | None = None) -> dict[str, Any]:
    """Initialize (or reset) the budget ledger for a new cycle.

    Idempotent: if the ledger already has this cycle_id, returns it unchanged.

    Returns
    -------
    dict — ledger data.  Never raises.
    """
    try:
        existing = _read_ledger(root)
        if existing.get("cycle_id") == cycle_id:
            return existing

        cfg = _load_config(root)
        ledger: dict[str, Any] = {
            "schema": _SCHEMA,
            "cycle_id": cycle_id,
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "usd_cap": float(cfg.get("per_cycle_usd_cap", 25.0)),
            "token_cap": int(cfg.get("per_cycle_token_cap", 25_000_000)),
            "usd_spent": 0.0,
            "token_spent": 0,
            "entries": [],
            "lobes": {},
        }
        _write_ledger(ledger, root)
        return ledger
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget.init_cycle: %s", exc)
        return {}


def record_spend(
    cycle_id: str,
    stage: str,
    usd: float = 0.0,
    tokens: int = 0,
    note: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Append a spend event to the ledger.

    Returns
    -------
    dict with keys:
        ok (bool)            — True if spend recorded; False if over cap or error
        over_cap (bool)      — True if this spend exceeded the cap
        usd_remaining (float)
        token_remaining (int)
        ledger (dict)        — current ledger state
    Never raises.
    """
    try:
        ledger = _read_ledger(root)
        if ledger.get("cycle_id") != cycle_id:
            ledger = init_cycle(cycle_id, root)

        usd_cap = float(ledger.get("usd_cap", 25.0))
        token_cap = int(ledger.get("token_cap", 25_000_000))
        usd_spent = float(ledger.get("usd_spent", 0.0)) + usd
        token_spent = int(ledger.get("token_spent", 0)) + tokens

        over_cap = usd_spent > usd_cap or token_spent > token_cap

        entry: dict[str, Any] = {
            "stage": stage,
            "ts": _now_iso(),
            "usd": usd,
            "tokens": tokens,
        }
        if note:
            entry["note"] = note
        if over_cap:
            entry["over_cap"] = True

        entries = list(ledger.get("entries") or [])
        entries.append(entry)

        ledger["usd_spent"] = round(usd_spent, 6)
        ledger["token_spent"] = token_spent
        ledger["entries"] = entries
        ledger["updated_at"] = _now_iso()

        _write_ledger(ledger, root)

        return {
            "ok": not over_cap,
            "over_cap": over_cap,
            "usd_remaining": round(usd_cap - usd_spent, 6),
            "token_remaining": token_cap - token_spent,
            "ledger": ledger,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget.record_spend: %s", exc)
        return {"ok": False, "over_cap": False, "usd_remaining": 0.0, "token_remaining": 0, "ledger": {}}


def check_cap(cycle_id: str, root: Path | None = None) -> dict[str, Any]:
    """Check whether the current cycle is over its cap without recording spend.

    Returns
    -------
    dict with keys:
        ok (bool)            — True if under cap
        over_cap (bool)
        usd_remaining (float)
        token_remaining (int)
    Never raises.
    """
    try:
        ledger = _read_ledger(root)
        usd_cap = float(ledger.get("usd_cap", 25.0))
        token_cap = int(ledger.get("token_cap", 25_000_000))
        usd_spent = float(ledger.get("usd_spent", 0.0))
        token_spent = int(ledger.get("token_spent", 0))
        over_cap = usd_spent >= usd_cap or token_spent >= token_cap
        return {
            "ok": not over_cap,
            "over_cap": over_cap,
            "usd_remaining": round(usd_cap - usd_spent, 6),
            "token_remaining": token_cap - token_spent,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget.check_cap: %s", exc)
        return {"ok": True, "over_cap": False, "usd_remaining": 25.0, "token_remaining": 25_000_000}


# ── Circuit breaker ───────────────────────────────────────────────────────────

def record_pr_outcome(
    cycle_id: str,
    lobe: str,
    success: bool,
    root: Path | None = None,
) -> dict[str, Any]:
    """Record a PR outcome for a lobe and update the circuit breaker.

    If a lobe accumulates N consecutive failures (config: circuit_breaker_trip),
    its 'paused' flag is set to True in the ledger.

    Returns
    -------
    dict with keys:
        lobe (str)
        paused (bool)      — True if the breaker is now tripped
        failed_streak (int)
    Never raises.
    """
    try:
        ledger = _read_ledger(root)
        if ledger.get("cycle_id") != cycle_id:
            ledger = init_cycle(cycle_id, root)

        cfg = _load_config(root)
        trip = int(_get_lobe_cap(cfg, lobe, "breaker_trip",
                                 cfg.get("circuit_breaker_trip", 3)))

        lobes = dict(ledger.get("lobes") or {})
        lobe_state = dict(lobes.get(lobe) or {})

        if success:
            lobe_state["failed_pr_streak"] = 0
        else:
            lobe_state["failed_pr_streak"] = lobe_state.get("failed_pr_streak", 0) + 1

        streak = lobe_state["failed_pr_streak"]
        tripped = streak >= trip
        lobe_state["paused"] = tripped

        if tripped:
            log.warning(
                "metabolism_budget: circuit breaker TRIPPED for lobe=%s "
                "(streak=%d >= trip=%d) — lobe auto-paused",
                lobe, streak, trip,
            )
            try:
                sys.path_for_notify = True  # suppress unused import
                from scripts.notify import send_telegram  # type: ignore[import]
                send_telegram(
                    f"METABOLISM: circuit breaker TRIPPED for lobe={lobe!r} "
                    f"(streak={streak} >= trip={trip}). Lobe auto-paused."
                )
            except Exception:  # noqa: BLE001
                pass

        lobes[lobe] = lobe_state
        ledger["lobes"] = lobes
        ledger["updated_at"] = _now_iso()
        _write_ledger(ledger, root)

        return {"lobe": lobe, "paused": tripped, "failed_streak": streak}
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget.record_pr_outcome: %s", exc)
        return {"lobe": lobe, "paused": False, "failed_streak": 0}


def is_lobe_paused(lobe: str, root: Path | None = None) -> bool:
    """Return True if the lobe's circuit breaker is tripped.  Never raises."""
    try:
        ledger = _read_ledger(root)
        return bool(ledger.get("lobes", {}).get(lobe, {}).get("paused", False))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_budget.is_lobe_paused: %s", exc)
        return False


# Import sys late to avoid unused import in non-notify path
import sys  # noqa: E402
