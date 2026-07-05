"""engine.neuralweb.factor_contradictions — Pair G: borrowed_strength per-name detector.

PURPOSE
-------
Dedicated module (§5.2, P1-D).  Fires a 'borrowed_strength' contradiction record when
a name fires as T1 or T2 on today's standout board AND its 20d alibi share is in the
top quintile of the trailing-252d cross-sectional distribution (high_alibi_flag=True per
PREREG §2.5 H2 definition).

CONSTITUTIONAL FRAME (P1-D binding)
-------------------------------------
- display_only=True unconditionally.
- severity='note' unconditionally.  Promotion to 'tension' only after H2 GATE-PASSED.
- NO write to Article-2 surfaces (alert_triage, board_ordering, top_setups,
  attention_queue, push_floor).
- Single-writer law: this module is the SOLE writer of
  data/reflexes/factor_attention/firings.jsonl (Lane 1, §5.3).  It NEVER writes to
  cortex_attention firings.jsonl.

INPUTS
------
- Panel partition: data/factordata/panel/ (monthly parquet, partitioned by YYYY-MM).
  Must contain alibi_share_20d per (ticker, date).
- Panel HISTORY for trailing-252d cross-sectional Q80 breakpoint: all monthly partitions
  up to and including today's date are loaded, providing the panel history up to t.
- Standout fires artifact: site/factordata/us_standouts.json.
  The buy lane entries carry signal.tier_cascade = T1|T2|T3|T4|None.
  Only T1 and T2 fires trigger Pair G.

RULING-E DORMANCY
-----------------
If fewer than 60 distinct panel dates are present in history (panel has not been
backfilled), no records are emitted and a dormancy gap note is appended:
  'factor_contradictions: panel history {n}d < 60d floor — detector dormant until backfill'

OUTPUT
------
- Contradiction ledger: data/neuralweb/factor_contradictions.jsonl
  Append-only, keyed (date, ticker).  Rerunning the same date dedupes on load before
  append.  RULING-F.
- Factor attention firings: data/reflexes/factor_attention/firings.jsonl via
  engine.neuralweb.reflexes.record_firing (Lane 1, §5.3).

FAIL-OPEN CONTRACT
------------------
Never raises.  All errors are caught and appended to gaps list.

FALSIFIER TEXT (RULING-G exact text)
-------------------------------------
  'direction=-1; hit = name underperforms SPY at horizon_d=21 (graded by _grade_realized_move)'

RECORD SHAPE (mirrors contradictions.py _record convention)
------------------------------------------------------------
{
  "pair_id": "borrowed_strength:{ticker}:{date}",
  "a": {"artifact": "site/factordata/us_standouts.json",
         "reading": "<tier_cascade> fire for <ticker> as_of <date>"},
  "b": {"artifact": "data/factordata/panel/",
         "reading": "alibi_share_20d=<val> >= Q80=<q80>"},
  "kind": "label-tension",
  "severity": "note",    # hardcoded — never promoted here
  "as_of": "<date>",
  "note": "<plain-language>",
  "display_only": true,  # hardcoded by _record
  "ticker": "<ticker>",  # extra field for consumer filtering
  "date": "<date>"       # extra field for consumer filtering
}
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date as date_type
from pathlib import Path
from typing import Any

# Module-level import for testability (patching requires the name in this namespace).
# Lazy fallback inside _fire_factor_attention for environments without the engine.
try:
    from engine.neuralweb.reflexes import record_firing  # type: ignore[import]
except ImportError:  # pragma: no cover
    record_firing = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum distinct panel dates before the detector becomes active (RULING-E).
_MIN_PANEL_DATES = 60

#: Q80 cross-sectional breakpoint window (trailing 252 calendar days, §2.5).
_ALIBI_Q80_WINDOW_DAYS = 252

#: Tiers that qualify as "T1 or T2" fires per §5.2.
_QUALIFYING_TIERS = {"T1", "T2"}

#: Output ledger name (relative to data/neuralweb/).
_LEDGER_NAME = "factor_contradictions.jsonl"

#: Reflex name for Lane 1 firings (single-writer law — never 'cortex_attention').
_REFLEX_NAME = "factor_attention"

#: Grading horizon (days).
_HORIZON_D = 21

#: Falsifier text per RULING-G (exact wording required by test suite).
_FALSIFIER = (
    "direction=-1; hit = name underperforms SPY at horizon_d=21 "
    "(graded by _grade_realized_move)"
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _panel_dir(root: Path) -> Path:
    return root / "data" / "factordata" / "panel"


def _ledger_path(root: Path) -> Path:
    return root / "data" / "neuralweb" / _LEDGER_NAME


def _standouts_path(root: Path) -> Path:
    return root / "site" / "factordata" / "us_standouts.json"


# ---------------------------------------------------------------------------
# JSON / numpy-safe encoder
# ---------------------------------------------------------------------------

def _json_safe(obj: Any) -> Any:
    """Recursively convert numpy scalars/NaN to JSON-safe Python types.

    Applies allow_nan=False discipline: NaN and Inf become None.
    """
    try:
        import numpy as np  # noqa: PLC0415
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            v = float(obj)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [_json_safe(x) for x in obj.tolist()]
    except ImportError:
        pass
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return obj


def _dumps_safe(obj: Any) -> str:
    """json.dumps with NaN/Inf coercion (allow_nan=False discipline)."""
    return json.dumps(_json_safe(obj), allow_nan=False)


# ---------------------------------------------------------------------------
# Internal record builder (mirrors contradictions.py convention)
# ---------------------------------------------------------------------------

def _record(
    pair_id: str,
    a_artifact: str,
    a_reading: str,
    b_artifact: str,
    b_reading: str,
    kind: str,
    severity: str,
    as_of: str,
    note: str,
    ticker: str,
    date_str: str,
) -> dict[str, Any]:
    """Build a typed contradiction record.  severity is clamped to 'note'."""
    # Severity clamp: P1-D severity is 'note' unconditionally.
    # Promotion to 'tension' only after H2 GATE-PASSED — never from this module.
    effective_severity = "note"
    if severity not in ("note", "tension"):
        log.warning(
            "factor_contradictions: invalid severity %r, clamping to 'note'", severity
        )
    return {
        "pair_id": pair_id,
        "a": {"artifact": a_artifact, "reading": a_reading},
        "b": {"artifact": b_artifact, "reading": b_reading},
        "kind": kind,
        "severity": effective_severity,
        "as_of": as_of,
        "note": note,
        "display_only": True,  # hardcoded — law
        "ticker": ticker,
        "date": date_str,
    }


# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------

def _load_panel_history(panel_dir: Path, as_of_date: str) -> "Any | None":
    """Load all panel partitions with date <= as_of_date.

    Returns a pandas DataFrame with at least (ticker, date, alibi_share_20d)
    columns, or None on failure.  PIT: only loads partitions whose YYYY-MM <=
    as_of_date[:7].
    """
    try:
        import pandas as pd  # noqa: PLC0415

        if not panel_dir.exists():
            log.warning("factor_contradictions: panel_dir %s does not exist", panel_dir)
            return None

        as_of_month = as_of_date[:7]  # "YYYY-MM"
        parts = sorted(panel_dir.glob("*/panel.parquet"))
        if not parts:
            return None

        dfs = []
        for p in parts:
            month_str = p.parent.name  # "YYYY-MM"
            if month_str > as_of_month:
                continue  # PIT: skip future months
            try:
                df = pd.read_parquet(p, columns=["ticker", "date", "alibi_share_20d"])
                dfs.append(df)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "factor_contradictions: could not read %s — %s", p, exc
                )

        if not dfs:
            return None

        combined = pd.concat(dfs, ignore_index=True)
        # PIT filter: keep only rows with date <= as_of_date
        combined = combined[combined["date"] <= as_of_date]
        return combined
    except Exception as exc:  # noqa: BLE001
        log.warning("factor_contradictions: panel load failed — %s", exc)
        return None


def _count_distinct_dates(panel_df: "Any") -> int:
    """Count distinct panel dates in the loaded history."""
    try:
        return int(panel_df["date"].nunique())
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Q80 breakpoint computation (trailing-252d cross-sectional)
# ---------------------------------------------------------------------------

def _compute_q80_breakpoint(panel_df: "Any", as_of_date: str) -> float | None:
    """Compute the trailing-252 calendar-day cross-sectional Q80 of alibi_share_20d.

    PIT: uses only dates in [as_of_date - 252 calendar days, as_of_date].
    Returns None if fewer than 10 non-null rows.
    """
    try:
        import pandas as pd  # noqa: PLC0415

        cutoff_start = (
            pd.Timestamp(as_of_date) - pd.Timedelta(days=_ALIBI_Q80_WINDOW_DAYS)
        ).strftime("%Y-%m-%d")

        window_df = panel_df[
            (panel_df["date"] >= cutoff_start)
            & (panel_df["date"] <= as_of_date)
            & panel_df["alibi_share_20d"].notna()
        ]

        if len(window_df) < 10:
            log.debug(
                "factor_contradictions: Q80 window only %d rows — too thin",
                len(window_df),
            )
            return None

        q80 = float(window_df["alibi_share_20d"].quantile(0.80))
        return q80
    except Exception as exc:  # noqa: BLE001
        log.warning("factor_contradictions: Q80 computation failed — %s", exc)
        return None


# ---------------------------------------------------------------------------
# Standouts loader — T1/T2 fires for today
# ---------------------------------------------------------------------------

def _load_t1_t2_fires(root: Path, as_of_date: str) -> list[dict[str, Any]]:
    """Read us_standouts.json buy lane and return T1/T2 fire entries.

    Returns list of dicts with at least: ticker, tier_cascade, as_of.
    """
    p = _standouts_path(root)
    if not p.exists():
        log.warning("factor_contradictions: us_standouts.json not found at %s", p)
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("factor_contradictions: us_standouts.json unreadable — %s", exc)
        return []

    artifact_as_of = str(raw.get("as_of") or as_of_date)
    buy_lane: list[dict] = raw.get("buy") or []

    fires = []
    for entry in buy_lane:
        ticker = str(entry.get("ticker") or "")
        if not ticker:
            continue
        sig = entry.get("signal") or {}
        tier = sig.get("tier_cascade")
        if tier not in _QUALIFYING_TIERS:
            continue
        fires.append(
            {
                "ticker": ticker,
                "tier_cascade": tier,
                "as_of": artifact_as_of,
            }
        )
    return fires


# ---------------------------------------------------------------------------
# Panel alibi_share_20d lookup for today
# ---------------------------------------------------------------------------

def _get_today_alibi(
    panel_df: "Any",
    ticker: str,
    as_of_date: str,
) -> float | None:
    """Return alibi_share_20d for the given ticker on as_of_date from panel."""
    try:
        row = panel_df[
            (panel_df["ticker"] == ticker) & (panel_df["date"] == as_of_date)
        ]
        if row.empty:
            return None
        val = row["alibi_share_20d"].iloc[0]
        if val is None:
            return None
        try:
            import numpy as np  # noqa: PLC0415
            if isinstance(val, (float, np.floating)) and math.isnan(float(val)):
                return None
        except ImportError:
            if isinstance(val, float) and math.isnan(val):
                return None
        return float(val)
    except Exception as exc:  # noqa: BLE001
        log.debug(
            "factor_contradictions: alibi lookup failed for %s — %s", ticker, exc
        )
        return None


# ---------------------------------------------------------------------------
# Ledger append (RULING-F: append-only, dedupe on load)
# ---------------------------------------------------------------------------

def _load_existing_ledger(ledger_path: Path) -> set[tuple[str, str]]:
    """Load existing (date, ticker) keys from the ledger for dedup."""
    existing: set[tuple[str, str]] = set()
    if not ledger_path.exists():
        return existing
    try:
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                date_val = str(rec.get("date") or "")
                ticker_val = str(rec.get("ticker") or "")
                if date_val and ticker_val:
                    existing.add((date_val, ticker_val))
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "factor_contradictions: ledger read failed during dedup — %s", exc
        )
    return existing


def _append_to_ledger(
    ledger_path: Path,
    records: list[dict[str, Any]],
    existing_keys: set[tuple[str, str]],
) -> int:
    """Append new records to the ledger, skipping duplicates.  Returns n appended."""
    if not records:
        return 0
    n_written = 0
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as fh:
            for rec in records:
                key = (str(rec.get("date") or ""), str(rec.get("ticker") or ""))
                if key in existing_keys:
                    log.debug(
                        "factor_contradictions: skipping duplicate (%s, %s)", *key
                    )
                    continue
                fh.write(_dumps_safe(rec) + "\n")
                n_written += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("factor_contradictions: ledger append failed — %s", exc)
    return n_written


# ---------------------------------------------------------------------------
# factor_attention reflex firing (Lane 1, §5.3)
# ---------------------------------------------------------------------------

def _fire_factor_attention(
    ticker: str,
    tier_cascade: str,
    alibi_share_20d: float,
    q80: float,
    as_of_date: str,
    root: Path,
    gaps: list[str],
) -> None:
    """File a Lane 1 firing to data/reflexes/factor_attention/firings.jsonl.

    SINGLE-WRITER LAW: this function is the SOLE writer of factor_attention firings.
    It NEVER references cortex_attention.
    claim_family is auto-stamped by record_firing as 'reflex.factor_attention'.
    No hand-set claim_family per §5.3.
    """
    try:
        from datetime import datetime, timezone  # noqa: PLC0415

        # Use the module-level record_firing (imported at top of module for testability).
        _rf = record_firing
        if _rf is None:
            gaps.append(
                f"factor_attention reflex: record_firing unavailable "
                f"(engine.neuralweb.reflexes not importable) for {ticker}"
            )
            return

        ts = datetime.now(timezone.utc).isoformat()
        trigger_key = f"borrowed_strength:{ticker}:{as_of_date}"

        payload: dict[str, Any] = {
            "ts": ts,
            "trigger_key": trigger_key,
            "trigger_type": "borrowed_strength_fire",
            "action_taken": (
                f"Pair G contradiction recorded: {ticker} T{tier_cascade[-1]} fire "
                f"with high alibi_share_20d={alibi_share_20d:.4f} >= Q80={q80:.4f}"
            ),
            "scope_type": "entity",
            "scope_key": ticker,
            "direction": -1,
            "horizon_d": _HORIZON_D,
            "asof": as_of_date,
            "falsifier": _FALSIFIER,
            "extra": {
                "pair": "borrowed_strength",
                "tier_cascade": tier_cascade,
                "alibi_share_20d": _json_safe(alibi_share_20d),
                "q80_breakpoint": _json_safe(q80),
                "display_only": True,
                "severity": "note",
            },
            # claim_family is auto-stamped by record_firing — do NOT set it here
        }

        _rf(_REFLEX_NAME, payload, root=str(root))
        log.debug(
            "factor_contradictions: factor_attention firing filed for %s", ticker
        )
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"factor_attention reflex fire failed for {ticker}: {exc}")
        log.warning(
            "factor_contradictions: factor_attention fire failed for %s — %s",
            ticker, exc,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_factor_contradictions(
    root: Path | str | None = None,
    as_of_date: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Detect Pair G (borrowed_strength) contradiction records for today's T1/T2 fires.

    Parameters
    ----------
    root:
        Repo root override.
    as_of_date:
        ISO date string (YYYY-MM-DD) for today.  Defaults to today UTC.

    Returns
    -------
    (records, gaps)
        records: list of typed contradiction records written (not including duplicates).
        gaps:    list of diagnostic strings for any source or step that failed.
        Never raises.
    """
    repo = _repo_root(root)
    records: list[dict[str, Any]] = []
    gaps: list[str] = []

    # Resolve as_of
    if as_of_date is None:
        from datetime import datetime, timezone  # noqa: PLC0415
        as_of_date = datetime.now(timezone.utc).date().isoformat()

    # ── Load panel history ──────────────────────────────────────────────────
    panel_dir = _panel_dir(repo)
    panel_df = _load_panel_history(panel_dir, as_of_date)

    if panel_df is None or len(panel_df) == 0:
        gap_note = (
            f"factor_contradictions: panel history 0d < {_MIN_PANEL_DATES}d floor "
            "— detector dormant until backfill"
        )
        gaps.append(gap_note)
        log.info(gap_note)
        return records, gaps

    n_dates = _count_distinct_dates(panel_df)
    if n_dates < _MIN_PANEL_DATES:
        gap_note = (
            f"factor_contradictions: panel history {n_dates}d < {_MIN_PANEL_DATES}d floor "
            "— detector dormant until backfill"
        )
        gaps.append(gap_note)
        log.info(gap_note)
        return records, gaps

    # ── Compute Q80 breakpoint ──────────────────────────────────────────────
    q80 = _compute_q80_breakpoint(panel_df, as_of_date)
    if q80 is None:
        gaps.append(
            f"factor_contradictions: Q80 breakpoint unavailable for {as_of_date} "
            "— alibi_share_20d column may be absent or all-null in panel history"
        )
        log.warning("factor_contradictions: Q80 unavailable — no records emitted")
        return records, gaps

    log.info(
        "factor_contradictions: n_dates=%d, Q80_alibi_share_20d=%.4f (as_of=%s)",
        n_dates, q80, as_of_date,
    )

    # ── Load T1/T2 fires ────────────────────────────────────────────────────
    fires = _load_t1_t2_fires(repo, as_of_date)
    if not fires:
        log.info(
            "factor_contradictions: no T1/T2 fires found in us_standouts.json "
            "(as_of=%s) — 0 Pair G records", as_of_date,
        )
        return records, gaps

    log.info(
        "factor_contradictions: %d T1/T2 fires loaded, checking against Q80=%.4f",
        len(fires), q80,
    )

    # ── Load existing ledger for dedup ──────────────────────────────────────
    ledger_path = _ledger_path(repo)
    existing_keys = _load_existing_ledger(ledger_path)

    # ── Detect Pair G per fire ──────────────────────────────────────────────
    new_records: list[dict[str, Any]] = []
    for fire in fires:
        ticker = fire["ticker"]
        tier_cascade = fire["tier_cascade"]

        # Get today's alibi_share_20d
        alibi = _get_today_alibi(panel_df, ticker, as_of_date)
        if alibi is None:
            gaps.append(
                f"factor_contradictions: alibi_share_20d missing for "
                f"{ticker} on {as_of_date} — skipped"
            )
            continue

        # high_alibi_flag = alibi_share_20d >= Q80 (PREREG H2, §2.5)
        high_alibi = alibi >= q80

        if not high_alibi:
            continue  # Pair G does not fire

        # Build the contradiction record
        rec = _record(
            pair_id=f"borrowed_strength:{ticker}:{as_of_date}",
            a_artifact="site/factordata/us_standouts.json",
            a_reading=(
                f"{tier_cascade} fire for {ticker} as_of {as_of_date} "
                f"(source: us_standouts.json buy lane)"
            ),
            b_artifact="data/factordata/panel/",
            b_reading=(
                f"alibi_share_20d={alibi:.4f} >= Q80={q80:.4f} "
                f"(trailing-252d cross-sectional, panel history n_dates={n_dates})"
            ),
            kind="label-tension",
            severity="note",  # hardcoded — never promoted in P1-D
            as_of=as_of_date,
            note=(
                f"{ticker} fired {tier_cascade} on {as_of_date} but its 20-day "
                f"alibi share ({alibi:.3f}) is above the trailing-252d cross-sectional "
                f"Q80 ({q80:.3f}), meaning most of its recent move is explained by factor "
                f"streams rather than idiosyncratic residual.  This raises the question of "
                f"whether the entry is genuine stock selection or factor-stream return "
                f"laundered through the technicals.  Display-only context — "
                f"severity='note' until H2 PREREG gate passes."
            ),
            ticker=ticker,
            date_str=as_of_date,
        )
        new_records.append(rec)

        # ── Lane 1: fire factor_attention reflex ────────────────────────────
        _fire_factor_attention(
            ticker=ticker,
            tier_cascade=tier_cascade,
            alibi_share_20d=alibi,
            q80=q80,
            as_of_date=as_of_date,
            root=repo,
            gaps=gaps,
        )

    # ── Append to ledger ────────────────────────────────────────────────────
    n_written = _append_to_ledger(ledger_path, new_records, existing_keys)
    records.extend(new_records)

    log.info(
        "factor_contradictions: Pair G fired %d records for %s "
        "(%d new written to ledger, %d duplicates skipped)",
        len(new_records), as_of_date, n_written,
        len(new_records) - n_written,
    )

    return records, gaps


# ---------------------------------------------------------------------------
# CLI entrypoint (allows python -m engine.neuralweb.factor_contradictions)
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [factor_contradictions] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Pair G (borrowed_strength) detector — P1-D"
    )
    parser.add_argument("--root", default=None)
    parser.add_argument("--as-of", default=None, dest="as_of",
                        help="ISO date (default: today UTC)")
    args = parser.parse_args()

    records, gaps = detect_factor_contradictions(
        root=args.root, as_of_date=args.as_of,
    )
    print(
        _dumps_safe({
            "records_fired": len(records),
            "gaps": gaps,
        })
    )


if __name__ == "__main__":
    _main()
