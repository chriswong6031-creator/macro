"""scripts/run_watchlist_sentinel.py — Nightly runner for Watchlist Buy-Zone Sentinel.

Codex docket B6: connects operator Supabase watchlist → buy-zone enter-detection →
alert center + Discord dispatch.

Design invariants (house laws)
-------------------------------
- ONE Supabase REST call per nightly run (render budget law).
- Fail-soft on every external dependency: missing creds / table / network → log one
  line, emit nothing, exit 0.  The nightly must never crash on this step.
- No LLM calls anywhere.  All state is read from deterministic engine artifacts.
- Nightly is the sole advancer of forward stores: cooldown + prev-states are only
  written in this script (nightly path).  Same-day re-renders carry forward the
  existing state (idempotent: as_of == today → skip write).
- Privacy: v1 reads the OPERATOR account watchlist only (SUPABASE_OPERATOR_USER_ID
  is REQUIRED).  No other users' rows are logged or enumerated.
- Discord: uses DISCORD_WEBHOOK_WATCHLIST if set; falls back to DISCORD_WEBHOOK_URL.
  The webhook selection is logged once at startup.

Supabase schema (live, verified 2026-07-07)
-------------------------------------------
  watchlists       : {id, user_id, name, position, created_at}  — one row per list container
  watchlist_symbols: {id, watchlist_id, symbol, section, position, created_at}  — one row per ticker

The fetch uses ONE embedded PostgREST call:
  GET /rest/v1/watchlists?select=id,user_id,watchlist_symbols(symbol)&user_id=eq.{uid}
This flattens all symbols across the operator's lists in a single round-trip.

State files (committed JSON, advanced nightly)
----------------------------------------------
  data/alerts/watchlist_sentinel_states.json
      Per-ticker state snapshots for the PREVIOUS nightly run.  Shape:
      {"as_of": "YYYY-MM-DD", "states": {ticker: {entry_status, gate_eligible,
        gate_tier, in_blackout, extension_grade}}}

  data/alerts/watchlist_sentinel_cooldown.json
      Cooldown map.  Shape: {"as_of": "YYYY-MM-DD", "cooldown": {ticker: {...}}}

  data/alerts/watchlist_alerts.jsonl
      Append-only log of fired alerts, read by alert_triage.py.
      One JSON object per line:
      {"ts": "<ISO>", "source": "watchlist", "type": "buy_zone_enter",
       "asset": "<TICKER>", "severity": "info", "edge": "", "edge_zh": "",
       "detail": "<plain message>", "headline": "<plain message>",
       "ticker": "<TICKER>", ...}

Usage
-----
    python -m scripts.run_watchlist_sentinel [--dry-run] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config  # noqa: E402
from engine import earnings_blackout as _eb  # noqa: E402
from engine.watchlist_sentinel import (  # noqa: E402
    run_sentinel,
    update_cooldown,
    format_discord_message,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("watchlist_sentinel")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ALERTS_DIR = config.data_dir() / "alerts"
_STATES_PATH = _ALERTS_DIR / "watchlist_sentinel_states.json"
_COOLDOWN_PATH = _ALERTS_DIR / "watchlist_sentinel_cooldown.json"
_ALERTS_JSONL = _ALERTS_DIR / "watchlist_alerts.jsonl"

# ---------------------------------------------------------------------------
# Supabase watchlist fetch
# ---------------------------------------------------------------------------

def _fetch_operator_watchlist() -> list[str]:
    """Fetch the operator's watchlist tickers from Supabase.

    Returns a sorted, deduplicated list of ticker strings (upper-cased), or []
    on any failure.

    Requires env vars:
      SUPABASE_SERVICE_KEY (or SUPABASE_SERVICE_ROLE_KEY)  — service_role key
      SUPABASE_OPERATOR_USER_ID                             — operator's auth.users UUID
                                                              (REQUIRED; absent → skip)

    Uses ONE embedded PostgREST call that joins watchlists → watchlist_symbols:
      GET /rest/v1/watchlists?select=id,user_id,watchlist_symbols(symbol)
          &user_id=eq.{operator_uid}

    Live schema (verified 2026-07-07):
      watchlists        : id, user_id, name, position, created_at
      watchlist_symbols : id, watchlist_id, symbol, section, position, created_at
    """
    # --- Resolve Supabase URL from config (public, no secret) ----------
    sup_cfg = (config.load().get("watchlist", {}).get("supabase") or {})
    base_url: str | None = sup_cfg.get("url")
    if not base_url:
        log.info("watchlist_sentinel: no Supabase URL in config — skipping")
        return []

    # --- Service key (required for server-side table read bypassing RLS) ---
    service_key = (
        config.secret("SUPABASE_SERVICE_KEY")
        or config.secret("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not service_key:
        log.info(
            "watchlist_sentinel: SUPABASE_SERVICE_KEY not set — skipping watchlist fetch"
        )
        return []

    # --- Operator UUID is REQUIRED (multiple accounts exist; do not read other users' lists) ---
    operator_uid: str | None = config.secret("SUPABASE_OPERATOR_USER_ID")
    if not operator_uid:
        log.info("watchlist_sentinel: operator UUID not set — skipping")
        return []

    # --- ONE embedded PostgREST call: watchlists + nested watchlist_symbols ---
    rest_url = base_url.rstrip("/") + "/rest/v1/watchlists"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    params: dict[str, str] = {
        "select": "id,user_id,watchlist_symbols(symbol)",
        "user_id": f"eq.{operator_uid}",
    }

    try:
        r = requests.get(rest_url, headers=headers, params=params, timeout=20)
        if r.status_code != 200:
            log.info(
                "watchlist_sentinel: Supabase returned %d — skipping (%s)",
                r.status_code,
                r.text[:200],
            )
            return []
        rows = r.json()
    except Exception as exc:  # noqa: BLE001
        log.info("watchlist_sentinel: Supabase request failed — skipping (%s)", exc)
        return []

    if not rows:
        log.info("watchlist_sentinel: no watchlist rows found — empty list")
        return []

    # Privacy: log counts only, never UIDs or symbols individually.
    log.info("watchlist_sentinel: fetched %d watchlist container(s)", len(rows))

    # Flatten symbols from all the operator's list containers, dedupe, sort.
    seen: set[str] = set()
    tickers: list[str] = []
    for row in rows:
        symbols = row.get("watchlist_symbols") or []
        for entry in symbols:
            if not isinstance(entry, dict):
                continue
            raw = (entry.get("symbol") or "").strip().upper()
            if raw and raw not in seen:
                seen.add(raw)
                tickers.append(raw)

    tickers.sort()
    log.info("watchlist_sentinel: %d unique ticker(s) in operator watchlist", len(tickers))
    return tickers


# ---------------------------------------------------------------------------
# Per-ticker state assembly
# ---------------------------------------------------------------------------

def _load_per_ticker_states(today_str: str) -> dict[str, dict]:
    """Build per-ticker state dicts from committed nightly artifacts.

    Sources (no new network calls):
    - site/factordata/us_standouts.json: entry_signal.status per ticker
    - site/factordata/signal_gate.json: eligible, tier_cascade per ticker
    - earnings_blackout.assess(): called per ticker (module reads local store)

    Returns {ticker: state_dict} for ALL tickers found in artifacts.
    """
    site_fd = ROOT / "site" / "factordata"
    states: dict[str, dict] = {}

    # --- 1. signal_gate.json -----------------------------------------------
    sg_path = site_fd / "signal_gate.json"
    gate_verdicts: dict[str, dict] = {}
    if sg_path.exists():
        try:
            sg_data = json.loads(sg_path.read_text())
            gate_verdicts = sg_data.get("verdicts") or {}
        except Exception as exc:  # noqa: BLE001
            log.info("watchlist_sentinel: could not read signal_gate.json (%s)", exc)

    # --- 2. us_standouts.json ----------------------------------------------
    us_path = site_fd / "us_standouts.json"
    entry_by_ticker: dict[str, dict] = {}
    if us_path.exists():
        try:
            us_data = json.loads(us_path.read_text())
            for bucket in ("buy", "watch", "laggards"):
                for row in us_data.get(bucket) or []:
                    ticker = row.get("ticker")
                    if not ticker:
                        continue
                    es = row.get("entry_signal") or {}
                    sig = row.get("signal") or {}
                    entry_by_ticker[ticker] = {
                        "entry_status": es.get("status"),
                        "gate_eligible_row": sig.get("eligible"),
                        "gate_tier_row": sig.get("tier_cascade"),
                    }
        except Exception as exc:  # noqa: BLE001
            log.info("watchlist_sentinel: could not read us_standouts.json (%s)", exc)

    # --- Merge sources per ticker ------------------------------------------
    all_tickers = set(gate_verdicts.keys()) | set(entry_by_ticker.keys())
    for ticker in all_tickers:
        gv = gate_verdicts.get(ticker) or {}
        er = entry_by_ticker.get(ticker) or {}

        # Prefer signal_gate.json for gate fields (it is more granular)
        gate_eligible = gv.get("eligible") if gv else er.get("gate_eligible_row")
        gate_tier = gv.get("tier_cascade") if gv else er.get("gate_tier_row")

        entry_status: str | None = er.get("entry_status")

        # Derive extension_grade from entry_status (entry_signal already encodes it)
        ext_grade: str | None = None
        if entry_status in {"extended", "topping"}:
            ext_grade = "stretched"  # conservative label — both states are extension vetos

        states[ticker] = {
            "entry_status": entry_status,
            "gate_eligible": gate_eligible,
            "gate_tier": gate_tier,
            "in_blackout": None,  # filled below
            "extension_grade": ext_grade,
            "as_of": today_str,
        }

    # --- 3. earnings_blackout per ticker (local store read) ----------------
    # We call assess() only for tickers where the state was assembled above.
    # The module is fail-open on missing store — no crash risk.
    eb_stale_info = _eb.store_staleness()
    if eb_stale_info.get("stale", True):
        log.info(
            "watchlist_sentinel: earnings_blackout store stale (age=%s) — in_blackout=False",
            eb_stale_info.get("as_of_age_td"),
        )
        for t in states:
            states[t]["in_blackout"] = False
    else:
        for t in states:
            try:
                ev = _eb.assess(t)
                states[t]["in_blackout"] = bool(ev.get("in_blackout", False))
            except Exception as exc:  # noqa: BLE001
                states[t]["in_blackout"] = False
                log.debug("watchlist_sentinel: eb.assess(%s) failed (%s)", t, exc)

    return states


# ---------------------------------------------------------------------------
# Committed state persistence
# ---------------------------------------------------------------------------

def _load_prev_states() -> dict[str, dict]:
    if not _STATES_PATH.exists():
        return {}
    try:
        d = json.loads(_STATES_PATH.read_text())
        return d.get("states") or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("watchlist_sentinel: could not load prev states (%s)", exc)
        return {}


def _load_cooldown() -> dict[str, dict]:
    if not _COOLDOWN_PATH.exists():
        return {}
    try:
        d = json.loads(_COOLDOWN_PATH.read_text())
        return d.get("cooldown") or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("watchlist_sentinel: could not load cooldown (%s)", exc)
        return {}


def _save_states(today_str: str, states: dict[str, dict], dry_run: bool) -> None:
    if dry_run:
        return
    _ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    _STATES_PATH.write_text(
        json.dumps({"as_of": today_str, "states": states}, separators=(",", ":"))
    )


def _save_cooldown(today_str: str, cooldown: dict[str, dict], dry_run: bool) -> None:
    if dry_run:
        return
    _ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    _COOLDOWN_PATH.write_text(
        json.dumps({"as_of": today_str, "cooldown": cooldown}, separators=(",", ":"))
    )


# ---------------------------------------------------------------------------
# Alert JSONL — alert_triage reads this
# ---------------------------------------------------------------------------

def _append_alert_jsonl(alerts: list[dict], today_str: str, dry_run: bool) -> None:
    """Append fired alerts to the watchlist_alerts.jsonl feed.

    Format mirrors the bonds/forex/commodity JSONL that alert_triage._jsonl_raw()
    reads.  Required keys: ts, source, type, asset, severity, edge, edge_zh,
    detail, headline.
    """
    if not alerts or dry_run:
        return
    _ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    for a in alerts:
        ticker = a.get("ticker", "")
        headline = format_discord_message(a)
        reasons = "; ".join(a.get("reasons") or [])
        record = {
            "ts": now_iso,
            "source": "watchlist",
            "type": "buy_zone_enter",
            "asset": ticker,
            "severity": "info",
            "edge": "",
            "edge_zh": "",
            "detail": reasons,
            "headline": headline,
            "headline_zh": headline,
            "anchor": "",
            # Carry sentinel fields through for the admin capture tab
            "entry_status": a.get("entry_status"),
            "gate_tier": a.get("gate_tier"),
            "in_blackout": a.get("in_blackout"),
            "extension_grade": a.get("extension_grade"),
            "as_of": today_str,
        }
        lines.append(json.dumps(record, separators=(",", ":")))
    with open(_ALERTS_JSONL, "a") as fh:
        fh.write("\n".join(lines) + "\n")
    log.info("watchlist_sentinel: appended %d row(s) to watchlist_alerts.jsonl", len(lines))


# ---------------------------------------------------------------------------
# Discord dispatch
# ---------------------------------------------------------------------------

def _send_discord_watchlist(msg: str, dry_run: bool) -> bool:
    """Send one message to the watchlist Discord channel.

    Webhook priority: DISCORD_WEBHOOK_WATCHLIST → DISCORD_WEBHOOK_URL.
    Returns True on success, False on skip or failure.
    """
    url = config.secret("DISCORD_WEBHOOK_WATCHLIST") or config.secret("DISCORD_WEBHOOK_URL")
    if not url:
        log.info("watchlist_sentinel: no Discord webhook configured — skipping dispatch")
        return False
    if dry_run:
        print("[DRY-RUN] Discord message:")
        print(msg)
        return True
    try:
        r = requests.post(url, json={"content": msg[:1990]}, timeout=30)
        if r.status_code not in (200, 204):
            log.warning(
                "watchlist_sentinel: Discord dispatch failed (%d: %s)",
                r.status_code,
                r.text[:200],
            )
            return False
        log.info("watchlist_sentinel: Discord dispatch OK")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("watchlist_sentinel: Discord dispatch error (%s)", exc)
        return False


# ---------------------------------------------------------------------------
# Idempotence guard
# ---------------------------------------------------------------------------

def _is_same_day_rerender(today_str: str) -> bool:
    """Return True when both state stores already hold today's date."""
    try:
        s = json.loads(_STATES_PATH.read_text()) if _STATES_PATH.exists() else {}
        c = json.loads(_COOLDOWN_PATH.read_text()) if _COOLDOWN_PATH.exists() else {}
        return (
            s.get("as_of") == today_str
            and c.get("as_of") == today_str
        )
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Watchlist buy-zone sentinel")
    ap.add_argument("--dry-run", action="store_true", help="Print without sending or writing")
    ap.add_argument("--date", default=None, help="Override date (YYYY-MM-DD)")
    args = ap.parse_args()

    today_str = args.date or date.today().isoformat()
    dry_run: bool = args.dry_run

    log.info("watchlist_sentinel: running for %s (dry_run=%s)", today_str, dry_run)

    # --- Idempotence: skip writes (but still log) on same-day re-render --------
    same_day = _is_same_day_rerender(today_str)
    if same_day:
        log.info(
            "watchlist_sentinel: same-day re-render (as_of=%s) — "
            "state files already current; no new alerts emitted",
            today_str,
        )
        return 0

    # --- Step 1: fetch operator watchlist (one Supabase call) ------------------
    watched = _fetch_operator_watchlist()
    if not watched:
        # No watchlist or credentials absent — still update state files to keep them fresh
        log.info("watchlist_sentinel: no watched tickers — saving empty state and exiting")
        today_states = _load_per_ticker_states(today_str)
        _save_states(today_str, today_states, dry_run)
        _save_cooldown(today_str, {}, dry_run)
        return 0

    # --- Step 2: build today's per-ticker states from committed artifacts ------
    today_states = _load_per_ticker_states(today_str)

    # --- Step 3: load yesterday's states and cooldown --------------------------
    yesterday_states = _load_prev_states()
    cooldown = _load_cooldown()

    # --- Step 4: run sentinel --------------------------------------------------
    alerts = run_sentinel(
        watched_tickers=watched,
        today_states=today_states,
        yesterday_states=yesterday_states,
        cooldown=cooldown,
        today_str=today_str,
    )

    # --- Step 5: update cooldown and save state files (nightly advance) --------
    new_cooldown = update_cooldown(
        cooldown=cooldown,
        watched_tickers=watched,
        today_states=today_states,
        newly_alerted=alerts,
        today_str=today_str,
    )
    _save_states(today_str, today_states, dry_run)
    _save_cooldown(today_str, new_cooldown, dry_run)

    # --- Step 6: write alert JSONL (alert_triage reads this) ------------------
    _append_alert_jsonl(alerts, today_str, dry_run)

    # --- Step 7: dispatch to Discord ------------------------------------------
    dispatched = 0
    for a in alerts:
        msg = format_discord_message(a)
        if _send_discord_watchlist(msg, dry_run):
            dispatched += 1

    log.info(
        "watchlist_sentinel: %d alert(s) fired, %d dispatched to Discord",
        len(alerts),
        dispatched,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
