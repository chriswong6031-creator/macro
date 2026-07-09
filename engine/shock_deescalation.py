"""Shock de-escalation protocol — policy-shock program W2-E (D3).

Consumes ``repricing_coherence`` from ``engine.market_drivers`` and emits:

  * ``data/reflexes/shock_deescalation/firings.jsonl`` — nightly-only append,
    keep-first per date.  The ledger starts EMPTY and accrues forward from ship
    date (PS-R7/PS-R8).

  * ``site/live/shock_state.json`` — cross-cutting de-escalation flag read by
    the subsector-rotation / sector-rank surfaces, US action-board, and Oracle
    panel.  Active window = trigger date + 3 NYSE trading sessions.

TRIGGER (frozen v1, PS-R9):
  a) ``coherence_state == "SHOCK"``     → fires immediately; OR
  b) two consecutive nightly prints ``ELEVATED`` with ``driver_flip > 0`` on
     the *latest* print.

DE-ESCALATION LAW (PS-R3):
  Consumers may ONLY remove confidence (stale-mark, band-widen, fresh-entry
  caution).  Originating direction, reordering ranks, or touching sizing is
  FORBIDDEN.

CADENCE LAW (PS-R7):
  ``build_nightly()`` is the sole writer of ``data/reflexes/`` firings.  The
  ``build_intraday()`` fast-path may recompute ``shock_state`` from
  ``site/live/market_drivers.json`` and write ``site/live/`` only.

WOULD-HAVE-FIRED (backscan):
  ``backscan()`` evaluates the trigger on historical coherence columns from
  ``data/regime/market_drivers_log.parquet`` (2026-06→ today).  The result is
  DESCRIPTIVE only; it does not backfill the firings ledger (PS-R7/PS-R8).
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from lib import config
from lib.nyse_calendar import is_session, last_session_on_or_before

log = logging.getLogger("shock_deescalation")

# ── constants ──────────────────────────────────────────────────────────────────
_EXPIRY_SESSIONS = 3        # active window: trigger date + 3 NYSE sessions
_FIRINGS_REL = Path("reflexes") / "shock_deescalation" / "firings.jsonl"
_SHOCK_STATE_REL = Path("live") / "shock_state.json"
_MARKET_DRIVERS_REL = Path("live") / "market_drivers.json"  # intraday source

# Bilingual labels
_REASON_EN = {
    "state==SHOCK": "Repricing coherence reached SHOCK level — cross-asset fingerprints "
                    "are firing in a coherent shock pattern.",
    "two_consecutive_ELEVATED_with_flip": "Two consecutive nightly prints ELEVATED with "
                                          "primary-driver flip — a sequential coherent "
                                          "shift consistent with a policy shock.",
}
_REASON_ZH = {
    "state==SHOCK": "重定价一致性达到冲击级别——跨资产指纹以一致的冲击模式触发。",
    "two_consecutive_ELEVATED_with_flip": "连续两个夜间打印均为偏高状态且主驱动因子发生切换"
                                          "——序列一致性转变，与政策冲击的模式相符。",
}


# ── calendar helpers ────────────────────────────────────────────────────────────

def _add_sessions(start: date, n: int) -> date:
    """Return the date that is ``n`` NYSE sessions after ``start`` (exclusive).
    i.e. ``start`` + 1 session is the first session strictly after ``start``."""
    d = start
    count = 0
    while count < n:
        d += timedelta(days=1)
        if is_session(d):
            count += 1
    return d


def _active(since: date, expires: date, today: date | None = None) -> bool:
    today = today or date.today()
    last_session = last_session_on_or_before(today)
    return since <= last_session <= expires


# ── trigger evaluation ──────────────────────────────────────────────────────────

def _evaluate_trigger(
    coherence_state: str,
    driver_flip: int,
    prev_coherence_state: str | None,
) -> str | None:
    """Return the trigger_reason string if the trigger fires, else None.

    Args
    ----
    coherence_state      : today's coherence state ("QUIET" | "ELEVATED" | "SHOCK")
    driver_flip          : today's driver_flip component (0 or 30)
    prev_coherence_state : previous nightly print's coherence state (None if absent)
    """
    if coherence_state == "SHOCK":
        return "state==SHOCK"
    if (coherence_state == "ELEVATED"
            and driver_flip > 0
            and prev_coherence_state == "ELEVATED"):
        return "two_consecutive_ELEVATED_with_flip"
    return None


# ── nightly build ───────────────────────────────────────────────────────────────

def build_nightly(snap: dict | None = None) -> dict:
    """Nightly entry-point: evaluate trigger, append firings ledger if needed,
    write site/live/shock_state.json.

    Args
    ----
    snap : classify_day snapshot with ``repricing_coherence`` block attached.
           Pass None to load today's snapshot from ``engine.market_drivers``.

    Returns the shock_state dict (also written to site/live/shock_state.json).
    Never raises — degrades to ``active=False`` on any error.
    """
    try:
        if snap is None:
            from engine.market_drivers import snapshot as md_snapshot
            snap = md_snapshot()

        coh = snap.get("repricing_coherence") or {}
        coherence_state = coh.get("state", "QUIET")
        driver_flip = int((coh.get("components") or {}).get("driver_flip", 0))
        score = int(coh.get("score", 0))
        today_str = str(snap.get("asof") or date.today().isoformat())
        today = date.fromisoformat(today_str)
        primary_driver = snap.get("primary") or ""

        # load previous row from log to check consecutive ELEVATED
        prev_state = _prev_coherence_state_from_log(today_str)

        trigger_reason = _evaluate_trigger(coherence_state, driver_flip, prev_state)

        # load existing firings to check keep-first and to find the active window
        firings_path = config.data_dir() / _FIRINGS_REL
        firings = _load_firings(firings_path)

        if trigger_reason:
            firing = {
                "date": today_str,
                "score": score,
                "state": coherence_state,
                "trigger_reason": trigger_reason,
                "primary_driver": primary_driver,
                "expires": _add_sessions(today, _EXPIRY_SESSIONS).isoformat(),
            }
            firings = _append_firing(firings, firing, firings_path)
            log.info("shock_deescalation: FIRED date=%s reason=%s score=%d expires=%s",
                     today_str, trigger_reason, score, firing["expires"])
        else:
            log.info("shock_deescalation: no trigger date=%s state=%s score=%d prev_state=%s",
                     today_str, coherence_state, score, prev_state)

        # compute shock_state: find most recent unexpired firing
        shock_state = _compute_shock_state(firings, today)

        # attach would-have-fired descriptive table (nightly path only)
        shock_state["would_have_fired"] = backscan()

        _write_shock_state(shock_state)
        return shock_state

    except Exception as e:  # noqa: BLE001 — never fatal
        log.error("build_nightly error: %s", e)
        return _inactive_shock_state()


def build_intraday() -> dict:
    """Intraday fast-path: re-read site/live/market_drivers.json, recompute
    shock_state, write site/live/shock_state.json.

    PS-R7: intraday callers MUST NOT write data/ ledgers.  This function only
    reads the intraday market_drivers.json (which already includes the
    repricing_coherence block) and updates the site/ artifact.

    Returns the shock_state dict.
    """
    try:
        site = config.ROOT / config.load()["storage"]["site_dir"]
        drivers_path = site / _MARKET_DRIVERS_REL
        if not drivers_path.exists():
            log.warning("build_intraday: market_drivers.json absent — no update")
            return _inactive_shock_state()

        snap = json.loads(drivers_path.read_text())
        coh = snap.get("repricing_coherence") or {}
        coherence_state = coh.get("state", "QUIET")
        driver_flip = int((coh.get("components") or {}).get("driver_flip", 0))
        today_str = str(snap.get("asof") or date.today().isoformat())
        today = date.fromisoformat(today_str)

        # Previous state: read nightly log (NOT advanced intraday per PS-R7)
        prev_state = _prev_coherence_state_from_log(today_str)
        trigger_reason = _evaluate_trigger(coherence_state, driver_flip, prev_state)

        # Load the committed firings ledger (read-only in intraday path)
        firings_path = config.data_dir() / _FIRINGS_REL
        firings = _load_firings(firings_path)

        # If the intraday snap fires, add a transient entry for the state display
        # (NOT appended to the ledger — PS-R7 guard; nightly is the sole writer).
        if trigger_reason:
            score = int(coh.get("score", 0))
            primary_driver = snap.get("primary") or ""
            ephemeral = {
                "date": today_str,
                "score": score,
                "state": coherence_state,
                "trigger_reason": trigger_reason,
                "primary_driver": primary_driver,
                "expires": _add_sessions(today, _EXPIRY_SESSIONS).isoformat(),
                "_intraday_only": True,  # sentinel: this row is NOT in the ledger
            }
            # Only include if today is not already in the ledger
            if not any(f["date"] == today_str for f in firings):
                firings = firings + [ephemeral]

        shock_state = _compute_shock_state(firings, today)
        # No would_have_fired in intraday (expensive + not needed live)
        _write_shock_state(shock_state)
        log.info("build_intraday: active=%s expires=%s",
                 shock_state.get("active"), shock_state.get("expires"))
        return shock_state

    except Exception as e:  # noqa: BLE001 — never fatal
        log.error("build_intraday error: %s", e)
        return _inactive_shock_state()


# ── backscan ────────────────────────────────────────────────────────────────────

def backscan() -> list[dict]:
    """Descriptive backscan: evaluate the trigger on historical rows of
    ``data/regime/market_drivers_log.parquet`` (2026-06→ today).

    Returns a list of dicts, one per would-have-fired date.  The result is
    LABELED DESCRIPTIVE — the firings ledger itself is NOT backfilled (PS-R7/PS-R8).

    For each row the repricing_coherence block is (re-)computed from the log's
    own history (log rows strictly before that row's asof), following the same
    path as ``engine.market_drivers.repricing_coherence()``.  The breadth
    component is 0 in this path since the scores array is not stored in the log.

    Sanity anchor: 2026-07-07 must appear as a would-have-fired date.
    """
    try:
        from engine.market_drivers import repricing_coherence as _coh_fn

        p = config.data_dir() / "regime" / "market_drivers_log.parquet"
        if not p.exists():
            return []
        df = pd.read_parquet(p)
        if df.empty:
            return []
        df = df.sort_values("asof").reset_index(drop=True)

        # Filter to 2026-06 onward per contract (backscan window)
        df = df[df["asof"].astype(str) >= "2026-06-01"].reset_index(drop=True)
        if df.empty:
            return []

        # Compute coherence state for each row using the log as the only source
        computed: list[dict] = []
        for i, row in df.iterrows():
            asof = str(row["asof"])
            strength = float(row["strength"]) if pd.notna(row.get("strength")) else 0.0
            absorption = float(row["absorption_pctile"]) if pd.notna(row.get("absorption_pctile")) else None
            primary = row.get("primary") or ""

            snap_min = {
                "asof": asof,
                "verdict": row.get("verdict") or "clear",
                "primary": primary,
                "strength": strength,
                "absorption_pctile": absorption,
                "scores": [],  # breadth component = 0 (log doesn't store scores)
            }
            log_before = df[df["asof"].astype(str) < asof]
            coh = _coh_fn(snap_min, log_df=log_before)

            computed.append({
                "asof": asof,
                "score": coh["score"],
                "state": coh["state"],
                "driver_flip": coh["components"]["driver_flip"],
                "primary": primary,
            })

        # Apply trigger logic over the computed sequence
        would_have_fired = []
        for i, row in enumerate(computed):
            prev_state = computed[i - 1]["state"] if i > 0 else None
            trigger = _evaluate_trigger(
                row["state"], row["driver_flip"], prev_state
            )
            if trigger:
                asof_d = date.fromisoformat(row["asof"])
                would_have_fired.append({
                    "date": row["asof"],
                    "score": row["score"],
                    "state": row["state"],
                    "trigger_reason": trigger,
                    "primary_driver": row["primary"],
                    "expires": _add_sessions(asof_d, _EXPIRY_SESSIONS).isoformat(),
                    "descriptive": True,
                })

        return would_have_fired

    except Exception as e:  # noqa: BLE001
        log.error("backscan error: %s", e)
        return []


# ── helpers ─────────────────────────────────────────────────────────────────────

def _prev_coherence_state_from_log(today_str: str) -> str | None:
    """Return the coherence_state of the most recent log row strictly before today.
    Reads data/regime/market_drivers_log.parquet; returns None if absent/empty."""
    try:
        p = config.data_dir() / "regime" / "market_drivers_log.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df.empty or "coherence_state" not in df.columns:
            return None
        prev = df[df["asof"].astype(str) < today_str].sort_values("asof")
        if prev.empty:
            return None
        val = prev.iloc[-1].get("coherence_state")
        return str(val) if pd.notna(val) else None
    except Exception:  # noqa: BLE001
        return None


def _load_firings(path: Path) -> list[dict]:
    """Load all firings from JSONL path.  Returns [] if absent/empty."""
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except Exception:  # noqa: BLE001
        pass
    return rows


def _append_firing(firings: list[dict], firing: dict, path: Path) -> list[dict]:
    """Append a new firing to the JSONL ledger (keep-first per date).

    Returns the updated firings list.  Never raises — on write failure the
    in-memory list is still returned.
    """
    # keep-first: if today is already in the ledger, skip
    if any(f["date"] == firing["date"] for f in firings):
        log.debug("keep-first: %s already in firings ledger — skip", firing["date"])
        return firings
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(firing) + "\n")
        log.info("appended firing: %s", firing)
    except Exception as e:  # noqa: BLE001
        log.error("firing write error: %s", e)
    return firings + [firing]


def _compute_shock_state(firings: list[dict], today: date) -> dict:
    """Find the most recent unexpired firing and compute the active shock_state."""
    # Sort by date descending, find most recent unexpired
    active_firing = None
    for f in sorted(firings, key=lambda x: x["date"], reverse=True):
        try:
            expires = date.fromisoformat(f["expires"])
            since = date.fromisoformat(f["date"])
        except (ValueError, KeyError):
            continue
        if _active(since, expires, today):
            active_firing = f
            break

    if active_firing is None:
        return _inactive_shock_state()

    reason_key = active_firing.get("trigger_reason", "")
    reason_en = _REASON_EN.get(reason_key, reason_key)
    reason_zh = _REASON_ZH.get(reason_key, reason_key)

    return {
        "active": True,
        "score": active_firing.get("score"),
        "since": active_firing["date"],
        "expires": active_firing["expires"],
        "reason": reason_en,
        "reason_zh": reason_zh,
        "trigger_reason": reason_key,
        "primary_driver": active_firing.get("primary_driver", ""),
        "note": ("Shock de-escalation protocol active — stale-rank discount in effect. "
                 "PS-R3: de-escalation only; no direction, no reordering."),
        "note_zh": ("冲击降级协议激活——陈旧排名折扣生效。"
                    "PS-R3：仅降级，不产生方向，不重新排序。"),
        "schema": "shock_deescalation.v1",
    }


def _inactive_shock_state() -> dict:
    return {
        "active": False,
        "score": None,
        "since": None,
        "expires": None,
        "reason": None,
        "reason_zh": None,
        "trigger_reason": None,
        "primary_driver": None,
        "note": "No active shock de-escalation window.",
        "note_zh": "无激活的冲击降级窗口。",
        "schema": "shock_deescalation.v1",
    }


def _write_shock_state(shock_state: dict) -> None:
    """Write shock_state to site/live/shock_state.json (site/ only — PS-R7)."""
    try:
        site = config.ROOT / config.load()["storage"]["site_dir"]
        out_dir = site / "live"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "shock_state.json"
        out_path.write_text(json.dumps(shock_state, indent=2, default=str))
        log.info("wrote shock_state: active=%s expires=%s",
                 shock_state.get("active"), shock_state.get("expires"))
    except Exception as e:  # noqa: BLE001
        log.error("shock_state write failed: %s", e)


# ── CLI entry-point ─────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Shock de-escalation protocol (W2-E)")
    ap.add_argument("--intraday", action="store_true",
                    help="fast-path: read site/live/market_drivers.json, site/ writes only")
    ap.add_argument("--backscan-only", action="store_true",
                    help="print the would-have-fired table and exit")
    args = ap.parse_args()

    if args.backscan_only:
        rows = backscan()
        print("Would-have-fired backscan (descriptive):")
        for r in rows:
            print(f"  {r['date']}  state={r['state']}  score={r['score']}  "
                  f"trigger={r['trigger_reason']}  expires={r['expires']}")
        if not rows:
            print("  (none)")
        return 0

    if args.intraday:
        result = build_intraday()
    else:
        result = build_nightly()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
