"""Risk Radar Scorecard — deterministic accuracy metrics over forward ledgers.

Reads the US and international forward-outcome ledgers (written by
engine/risk_radar_audit.py, engine/risk_radar_intl_audit.py) and the US
recovery log (engine/risk_radar_recovery_audit.py), then computes a pure-math
summary per the frozen contract in data/risk_radar/scorecard.json.

DISPLAY-TIER CONTEXT ACCRUAL — NOT a promotion claim.  No gate changes here.
Pure observation over already-graded rows.  No LLM, no signal origination.

Frozen schema: scorecard.json
  {schema, generated_at, markets: {us|cn|hk|ca: MARKET}}
  MARKET = {asof_last_row, monitoring: {log_fresh, last_logged_days_ago,
             ungraded_backlog, graded_n},
            windows: {full: WINDOW, y1: WINDOW}}
  WINDOW = {alerts, watch_caution, calm, by_scare, recovery}
  Each sub-block uses hit_rate/rate=null when n<5 (min-n honesty floor).

Never raises publicly: all errors are logged and produce fail-soft empty entries.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = "risk_radar_scorecard.v1"
_MIN_N = 5          # minimum rows before computing a rate (honesty floor)
_ALERT_STATES = frozenset(("elevated", "risk-off"))
_WATCH_CAUTION_STATES = frozenset(("watch", "caution"))
_LOG_FRESH_DAYS = 3     # last row this many days old or less = fresh
_UNGRADED_BACKLOG_AGE = 7  # rows older than this with graded=null count as backlog


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_root(root=None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from lib import config  # noqa: PLC0415
        return config.ROOT
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parent.parent


def _data_root(root=None) -> Path:
    if root is not None:
        return Path(root) / "data"
    try:
        from lib import config  # noqa: PLC0415
        return config.data_dir()
    except Exception:  # noqa: BLE001
        return _repo_root(root) / "data"


def _site_root(root=None) -> Path:
    if root is not None:
        return Path(root) / "site"
    try:
        from lib import config  # noqa: PLC0415
        return config.ROOT / config.load()["storage"]["site_dir"]
    except Exception:  # noqa: BLE001
        return _repo_root(root) / "site"


def _us_forward_path(root=None) -> Path:
    return _data_root(root) / "risk_radar" / "forward_log.jsonl"


def _us_recovery_path(root=None) -> Path:
    return _data_root(root) / "risk_radar" / "recovery_log.jsonl"


def _intl_forward_path(market: str, root=None) -> Path:
    return _data_root(root) / "risk_radar_intl" / f"{market}_forward_log.jsonl"


def _scorecard_data_path(root=None) -> Path:
    p = _data_root(root) / "risk_radar" / "scorecard.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _scorecard_site_path(root=None) -> Path:
    p = _site_root(root) / "riskdata" / "scorecard.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# JSONL reader — skip malformed lines, never raises
# ---------------------------------------------------------------------------

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return rows


# ---------------------------------------------------------------------------
# Monitoring block
# ---------------------------------------------------------------------------

def _monitoring(rows: list[dict]) -> dict:
    """Compute the monitoring meta-block for a ledger's rows (all rows, not just graded)."""
    try:
        from datetime import date  # noqa: PLC0415
        today = date.today()

        # Last row age
        last_logged_days_ago: int | None = None
        log_fresh = False
        asof_last_row: str | None = None
        if rows:
            last_asof = rows[-1].get("asof")
            asof_last_row = str(last_asof) if last_asof else None
            if last_asof:
                try:
                    asof_date = date.fromisoformat(str(last_asof)[:10])
                    last_logged_days_ago = (today - asof_date).days
                    log_fresh = last_logged_days_ago <= _LOG_FRESH_DAYS
                except Exception:  # noqa: BLE001
                    pass

        # Ungraded backlog: rows with graded=null older than 7 days
        ungraded_backlog = 0
        for r in rows:
            if r.get("graded") is not None:
                continue
            asof_str = r.get("asof")
            if not asof_str:
                continue
            try:
                asof_date = date.fromisoformat(str(asof_str)[:10])
                if (today - asof_date).days > _UNGRADED_BACKLOG_AGE:
                    ungraded_backlog += 1
            except Exception:  # noqa: BLE001
                pass

        graded_n = sum(1 for r in rows if r.get("graded") is not None)

        return {
            "log_fresh": log_fresh,
            "last_logged_days_ago": last_logged_days_ago,
            "ungraded_backlog": ungraded_backlog,
            "graded_n": graded_n,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("scorecard _monitoring failed: %s", e)
        return {"log_fresh": False, "last_logged_days_ago": None, "ungraded_backlog": 0, "graded_n": 0}


# ---------------------------------------------------------------------------
# Window math helpers
# ---------------------------------------------------------------------------

def _rate(num: int, denom: int) -> float | None:
    if denom < _MIN_N:
        return None
    return round(num / denom, 3)


def _alerts_block(graded: list[dict]) -> dict:
    """Alert window: rows with state in (elevated, risk-off)."""
    alert_rows = [r for r in graded if r.get("state") in _ALERT_STATES]
    n = len(alert_rows)
    tp = sum(1 for r in alert_rows if (r.get("graded") or {}).get("outcome") == "true_positive")
    fp = sum(1 for r in alert_rows if (r.get("graded") or {}).get("outcome") == "false_positive")
    return {"n": n, "tp": tp, "fp": fp, "hit_rate": _rate(tp, n)}


def _watch_caution_block(graded: list[dict]) -> dict:
    """Watch/caution window."""
    wc_rows = [r for r in graded if r.get("state") in _WATCH_CAUTION_STATES]
    n = len(wc_rows)
    tp = sum(1 for r in wc_rows if (r.get("graded") or {}).get("outcome") == "tp_watch")
    tn = sum(1 for r in wc_rows if (r.get("graded") or {}).get("outcome") == "tn_watch")
    return {"n": n, "tp": tp, "tn": tn, "precursor_rate": _rate(tp, n)}


def _calm_block(graded: list[dict]) -> dict:
    """Calm window: rows with state not in alert or watch/caution."""
    calm_rows = [r for r in graded
                 if r.get("state") not in _ALERT_STATES
                 and r.get("state") not in _WATCH_CAUTION_STATES]
    n = len(calm_rows)
    dd_missed = sum(1 for r in calm_rows if (r.get("graded") or {}).get("outcome") == "calm_dd")
    quiet = sum(1 for r in calm_rows if (r.get("graded") or {}).get("outcome") == "calm_quiet")
    return {"n": n, "dd_missed": dd_missed, "quiet": quiet, "quiet_rate": _rate(quiet, n)}


def _by_scare_block(graded: list[dict]) -> dict:
    """Per-dominant-scare breakdown for alert rows only."""
    alert_rows = [r for r in graded if r.get("state") in _ALERT_STATES]
    by_scare: dict[str, Any] = {}
    for r in alert_rows:
        scare = r.get("dominant_scare")
        if not scare:
            continue
        entry = by_scare.setdefault(scare, {"n": 0, "tp": 0, "fp": 0})
        entry["n"] += 1
        outcome = (r.get("graded") or {}).get("outcome")
        if outcome == "true_positive":
            entry["tp"] += 1
        elif outcome == "false_positive":
            entry["fp"] += 1
    result: dict[str, Any] = {}
    for scare, d in by_scare.items():
        result[scare] = {
            "n": d["n"],
            "tp": d["tp"],
            "fp": d["fp"],
            "hit_rate": _rate(d["tp"], d["n"]),
        }
    return result


def _recovery_block(recovery_rows: list[dict]) -> dict | None:
    """Recovery log summary: n graded, n ok (h21 fwd_ret > 0), rate."""
    graded = [r for r in recovery_rows if r.get("graded") is not None]
    if not graded:
        return None
    n = len(graded)
    ok = 0
    for r in graded:
        g = r.get("graded") or {}
        h21 = g.get("h21") or {}
        fwd_ret = h21.get("fwd_ret")
        if fwd_ret is not None and fwd_ret > 0:
            ok += 1
    return {"n": n, "ok": ok, "rate": _rate(ok, n)}


# ---------------------------------------------------------------------------
# Window builder for a set of graded rows + an optional cutoff
# ---------------------------------------------------------------------------

def _window(graded: list[dict], recovery_rows: list[dict] | None) -> dict:
    return {
        "alerts": _alerts_block(graded),
        "watch_caution": _watch_caution_block(graded),
        "calm": _calm_block(graded),
        "by_scare": _by_scare_block(graded),
        "recovery": _recovery_block(recovery_rows or []),
    }


def _trailing_365(all_graded: list[dict]) -> list[dict]:
    """Filter to rows with asof within the trailing 365 calendar days."""
    try:
        from datetime import date, timedelta  # noqa: PLC0415
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        return [r for r in all_graded if str(r.get("asof", "")) >= cutoff]
    except Exception:  # noqa: BLE001
        return []


def _trailing_365_recovery(recovery_graded: list[dict]) -> list[dict]:
    """Filter recovery graded rows to trailing 365 days."""
    try:
        from datetime import date, timedelta  # noqa: PLC0415
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        return [r for r in recovery_graded if str(r.get("asof", "")) >= cutoff]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Per-market builder
# ---------------------------------------------------------------------------

def _market_entry(
    market: str,
    forward_path: Path,
    recovery_path: Path | None = None,
) -> dict:
    """Build one MARKET block. Never raises; returns fail-soft entry on any error."""
    try:
        all_rows = _read_jsonl(forward_path)
        if not all_rows and not forward_path.exists():
            # Missing ledger: fail-soft
            return {
                "asof_last_row": None,
                "monitoring": {"log_fresh": False, "last_logged_days_ago": None,
                               "ungraded_backlog": 0, "graded_n": 0},
                "windows": {"full": _window([], []), "y1": _window([], [])},
            }

        monitoring = _monitoring(all_rows)
        # Filter defensively: graded must be a dict; a corrupt scalar value (e.g.
        # graded='CORRUPT') drops that single row without aborting the whole market.
        graded = [r for r in all_rows if isinstance(r.get("graded"), dict)]

        # Recovery rows (US only; intl markets pass None)
        recovery_all: list[dict] = []
        if recovery_path is not None:
            recovery_all = _read_jsonl(recovery_path)
        recovery_graded = [r for r in recovery_all if r.get("graded") is not None]

        asof_last_row = str(all_rows[-1].get("asof")) if all_rows else None
        y1_graded = _trailing_365(graded)
        y1_recovery = _trailing_365_recovery(recovery_graded)

        return {
            "asof_last_row": asof_last_row,
            "monitoring": monitoring,
            "windows": {
                "full": _window(graded, recovery_graded),
                "y1": _window(y1_graded, y1_recovery),
            },
        }
    except Exception as e:  # noqa: BLE001
        log.warning("scorecard _market_entry(%s) failed: %s", market, e)
        return {
            "asof_last_row": None,
            "monitoring": {"log_fresh": False, "last_logged_days_ago": None,
                           "ungraded_backlog": 0, "graded_n": 0},
            "windows": {"full": _window([], []), "y1": _window([], [])},
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build(root=None) -> dict:
    """Build and return the scorecard dict. Never raises."""
    try:
        us = _market_entry(
            "us",
            _us_forward_path(root),
            _us_recovery_path(root),
        )
        cn = _market_entry("cn", _intl_forward_path("cn", root))
        hk = _market_entry("hk", _intl_forward_path("hk", root))
        ca = _market_entry("ca", _intl_forward_path("ca", root))

        return {
            "schema": _SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "markets": {
                "us": us,
                "cn": cn,
                "hk": hk,
                "ca": ca,
            },
        }
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_scorecard.build failed: %s", e)
        return {
            "schema": _SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "markets": {"us": {}, "cn": {}, "hk": {}, "ca": {}},
        }


def _atomic_write(path: Path, payload: str) -> None:
    """Write JSON to path atomically via tmp+rename. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        log.warning("scorecard atomic write to %s failed: %s", path, e)
        try:
            os.unlink(tmp)
        except Exception:  # noqa: BLE001
            pass


def write(root=None) -> dict:
    """Build the scorecard, write atomically to both data/ and site/riskdata/ copies.

    Returns the scorecard dict. Never raises.

    Multi-writer convergence semantics: build_china, build_hk, and build_canada each
    call write() once per nightly run (right after their respective audit/tune block).
    Each call re-reads ALL market ledgers from disk, so whichever write lands last
    captures the most up-to-date state for every market seen so far.  The tmp+rename
    atomic write guarantees no reader ever sees a partial file.  Last writer wins;
    the operation is idempotent given the same ledger content.
    """
    try:
        sc = build(root)
        payload = json.dumps(sc, indent=2, default=str)
        _atomic_write(_scorecard_data_path(root), payload)
        _atomic_write(_scorecard_site_path(root), payload)
        log.info(
            "risk_radar_scorecard: wrote scorecard (us graded=%s, cn=%s, hk=%s, ca=%s)",
            (sc.get("markets", {}).get("us", {}).get("monitoring", {}).get("graded_n")),
            (sc.get("markets", {}).get("cn", {}).get("monitoring", {}).get("graded_n")),
            (sc.get("markets", {}).get("hk", {}).get("monitoring", {}).get("graded_n")),
            (sc.get("markets", {}).get("ca", {}).get("monitoring", {}).get("graded_n")),
        )
        return sc
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_scorecard.write failed: %s", e)
        return {}
