"""scripts/audit_options_entry_coverage.py — options entry feature coverage audit.

NEXT3 W-OC (PR-β) — RUL-U5 fences apply: read-only over all inputs except the
coverage.json output.

Reads:
  data/options_entry/state.parquet          — feature snapshot (403 × 28 today)
  data/options_entry/gate.json              — per-family gate status + family_size
  data/us_board_ledger/retro_grades.parquet — stamped board-ledger rows
  engine/options_stamp.py STAMP_COLS        — options family registry constants

Emits:
  data/options_entry/coverage.json          — committed, single-writer, vintage-stamped

Coverage sections emitted
─────────────────────────
1. per-feature non-null count + share (state.parquet snapshot) + per-ticker coverage
2. per-family stamp coverage on ledger rows: n_cond/n_base now + new-stamped-fire
   counts per ISO week (derived from ledger as_of — NO stamp-arrival column)
3. readiness forecast per family: projected date n_cond>=30 from trailing cadence ×
   trailing condition-hit share — ONLY when >=14 days of post-W-C stamped-fire history;
   else forecast:"unknown" with counts printed
4. structural-null ledger: iv_rank_* (ruling A9), pin_risk (by-design opex_days<=5 gate),
   gamma_regime per-name constancy caveat
5. consistency rows: BH test-count drift (registry 28 vs gate.json 22 vs docstring 22 —
   a TEST count, not a bucket count; print only — fix owned by W-OVC); stale as_of ages;
   audit_options_accrual last-run status

Usage:
    python -m scripts.audit_options_entry_coverage           # writes coverage.json
    python -m scripts.audit_options_entry_coverage --check   # prints, no write
    python -m scripts.audit_options_entry_coverage --root /path/to/repo
    python -m scripts.audit_options_entry_coverage --json    # stdout JSON

Wired as an end-of-collect audit step via run_as_collect_step().
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("audit_options_entry_coverage")

# ---------------------------------------------------------------------------
# W-C cutoff: the date stamp_options_state W-C PR merged.
# Rows with as_of > W_C_CUTOFF are "post-W-C stamped fires" eligible for the
# readiness forecast.  The adjudication (§2.5.6 / RUL-U5) confirms that all
# rows in today's ledger are pre-W-C (as_of through 2026-06-24 at PR-β build
# time); the 14-day minimum history guard will produce "unknown" until the
# accrual catches up.
# ---------------------------------------------------------------------------
_W_C_CUTOFF = date(2026, 7, 5)          # W-C merged 2026-07-05
_READINESS_MIN_DAYS = 14                # minimum post-W-C history to emit a forecast
_READINESS_TARGET = 30                  # n_cond threshold to forecast


# ---------------------------------------------------------------------------
# Resolve repo root
# ---------------------------------------------------------------------------

def _resolve_root(root: Path | None) -> Path:
    if root is not None:
        return root
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers: safe readers
# ---------------------------------------------------------------------------

def _read_parquet(path: Path) -> "pd.DataFrame | None":  # type: ignore[name-defined]
    """Load a parquet file; return None on any failure."""
    try:
        import pandas as pd
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("coverage_audit: parquet read failed (%s): %s", path, exc)
        return None


def _read_json(path: Path) -> dict | None:
    """Load a JSON file; return None on failure."""
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("coverage_audit: json read failed (%s): %s", path, exc)
        return None


def _read_quality_audit(root: Path) -> dict | None:
    """Read data/quality/options_accrual_audit.json written by audit_options_accrual."""
    p = root / "data" / "quality" / "options_accrual_audit.json"
    return _read_json(p)


# ---------------------------------------------------------------------------
# Next OPEX date (from engine/opex._third_friday)
# ---------------------------------------------------------------------------

def _next_opex_date(ref: date | None = None) -> date:
    """Return the next monthly OPEX (3rd Friday >= ref)."""
    try:
        from engine.opex import _third_friday
        ref = ref or datetime.now(timezone.utc).date()
        for delta in range(3):
            m = ((ref.month - 1 + delta) % 12) + 1
            y = ref.year + (ref.month - 1 + delta) // 12
            candidate = _third_friday(y, m)
            if candidate >= ref:
                return candidate
        # fallback: should never reach
        return _third_friday(ref.year, ref.month + 3)
    except Exception as exc:  # noqa: BLE001
        log.warning("coverage_audit: next_opex_date failed: %s", exc)
        return date(ref.year if ref else datetime.now(timezone.utc).year, 12, 31)


# ---------------------------------------------------------------------------
# Section 1: per-feature non-null coverage from state.parquet
# ---------------------------------------------------------------------------

def _feature_coverage(df: "pd.DataFrame") -> dict:
    """Non-null count + share per feature, plus per-ticker coverage."""
    import pandas as pd

    n_total = len(df)
    n_tickers = df["ticker"].nunique() if "ticker" in df.columns else 0

    features: list[dict] = []
    for col in df.columns:
        if col in ("ticker", "as_of"):
            continue
        nn = int(df[col].notna().sum())
        features.append({
            "feature": col,
            "n_nonnull": nn,
            "n_total": n_total,
            "share_nonnull": round(nn / n_total, 4) if n_total > 0 else 0.0,
        })

    # per-ticker: how many features are non-null for each ticker
    # report distribution only (n tickers with ≥75%/≥50%/<50% features covered)
    feature_cols = [c for c in df.columns if c not in ("ticker", "as_of")]
    if feature_cols and n_tickers > 0:
        coverage_frac = df[feature_cols].notna().mean(axis=1)
        tier_full = int((coverage_frac >= 0.75).sum())
        tier_partial = int(((coverage_frac >= 0.50) & (coverage_frac < 0.75)).sum())
        tier_thin = int((coverage_frac < 0.50).sum())
        ticker_coverage = {
            "n_tickers": n_tickers,
            "n_rows": n_total,
            "n_tickers_ge75pct_features": tier_full,
            "n_tickers_50to74pct_features": tier_partial,
            "n_tickers_lt50pct_features": tier_thin,
        }
    else:
        ticker_coverage = {"n_tickers": n_tickers, "n_rows": n_total}

    return {
        "n_rows": n_total,
        "n_features": len(features),
        "features": features,
        "ticker_coverage": ticker_coverage,
    }


# ---------------------------------------------------------------------------
# Section 2: per-family stamp coverage on board-ledger rows
# ---------------------------------------------------------------------------

def _family_stamp_coverage(
    ledger_df: "pd.DataFrame",
    gate: dict,
    today: date,
) -> list[dict]:
    """Per-family n_cond/n_base + weekly new-stamped-fire counts from ledger as_of.

    NOTE: the ledger carries NO stamp-arrival column (adj. §2.5.6 correction).
    We derive week buckets from the row's as_of date (the fire date, not the stamp
    arrival date), which is the only proxy available.

    Families are taken from gate["per_family_status"] keys.
    """
    import pandas as pd

    # gate.json tests block has per-family n_cond / n_base
    gate_tests = gate.get("tests", {})
    per_family_status = gate.get("per_family_status", {})

    # Build mapping: family_key -> relevant ledger column(s)
    # Family prefixes match STAMP_COLS naming from engine/options_stamp.py
    FAMILY_COL_MAP: dict[str, list[str]] = {
        "S-IVR":       ["opt_iv_rank_252"],
        "S-DOI":       ["opt_doi_slope_5d"],
        "S-VOI":       ["opt_voi_flag"],
        "S-IVSPREAD-F": ["opt_ivspread_rel"],
        "S-SKEW_DECEL": ["opt_skew_5d_chg", "opt_skew"],
        "S-TOP_RISK":  ["opt_skew_5d_chg", "opt_ivspread_rel"],
        "S-PIN_RISK":  ["opt_pin_risk"],
        "S-VOI2":      ["opt_voi_flag"],  # stricter variant, same underlying col
    }

    # ISO-week bucketed fire counts: rows with a non-null core opt_ column that
    # post-dates W_C_CUTOFF.  Use any non-null STAMP_COVERAGE_COLS as "stamped".
    try:
        from engine.options_stamp import STAMP_COVERAGE_COLS
        stamp_detect_cols = [c for c in STAMP_COVERAGE_COLS if c in ledger_df.columns]
    except Exception:  # noqa: BLE001
        stamp_detect_cols = ["opt_gamma_regime", "opt_voi_flag", "opt_iv30"]

    # Only rows where at least one stamp detect col is non-null are "stamped fires"
    if stamp_detect_cols:
        stamped_mask = ledger_df[stamp_detect_cols].notna().any(axis=1)
    else:
        stamped_mask = pd.Series(False, index=ledger_df.index)

    stamped_df = ledger_df[stamped_mask].copy()

    # Parse as_of dates; derive ISO week buckets
    try:
        asos = pd.to_datetime(stamped_df["as_of"]) if len(stamped_df) > 0 else pd.Series([], dtype="datetime64[ns]")
    except Exception:  # noqa: BLE001
        asos = pd.Series([], dtype="datetime64[ns]")

    if len(asos) > 0:
        stamped_df = stamped_df.copy()
        stamped_df["_iso_week"] = asos.dt.isocalendar().apply(
            lambda r: f"{int(r['year'])}-W{int(r['week']):02d}", axis=1
        )
        # Post-W-C: as_of > W_C_CUTOFF
        stamped_df["_as_of_date"] = asos.dt.date
        post_wc = stamped_df[stamped_df["_as_of_date"] > _W_C_CUTOFF]
    else:
        stamped_df["_iso_week"] = pd.Series([], dtype=str)
        stamped_df["_as_of_date"] = pd.Series([], dtype=object)
        post_wc = stamped_df.iloc[0:0]

    # Global weekly fire counts (all stamped rows, for cadence estimation)
    if len(stamped_df) > 0 and "_iso_week" in stamped_df.columns:
        weekly_fires: dict[str, int] = (
            stamped_df.groupby("_iso_week").size().to_dict()
        )
    else:
        weekly_fires = {}

    # Post-W-C weekly fires
    if len(post_wc) > 0:
        post_wc_weekly: dict[str, int] = (
            post_wc.groupby("_iso_week").size().to_dict()
        )
        # Span of post-W-C data in days: from W-C cutoff to latest observed fire date
        # (spec §5.1: "≥14 days of post-W-C stamped-fire history", not wall-clock)
        post_wc_max_date = post_wc["_as_of_date"].max()
        post_wc_span_days = (post_wc_max_date - _W_C_CUTOFF).days
    else:
        post_wc_weekly = {}
        post_wc_span_days = 0

    n_post_wc_fires = len(post_wc)

    results: list[dict] = []
    for family in per_family_status:
        # n_cond / n_base from gate.json tests (authoritative from validate_options_entry.py)
        test_block = gate_tests.get(family, {})
        n_cond = test_block.get("n_cond", 0) or 0
        n_base = test_block.get("n_base", 0) or 0

        # Condition-hit share among recent stamped fires (from ledger):
        # among stamped rows, what fraction have the family's condition column non-null?
        cond_cols = FAMILY_COL_MAP.get(family, [])
        if cond_cols and len(stamped_df) > 0:
            available_cond_cols = [c for c in cond_cols if c in stamped_df.columns]
            if available_cond_cols:
                cond_mask = stamped_df[available_cond_cols].notna().any(axis=1)
                n_stamped_total = len(stamped_df)
                n_stamped_cond = int(cond_mask.sum())
                cond_hit_share = round(n_stamped_cond / n_stamped_total, 4) if n_stamped_total > 0 else 0.0
            else:
                n_stamped_cond = 0
                cond_hit_share = 0.0
        else:
            n_stamped_cond = 0
            cond_hit_share = 0.0

        # Readiness forecast: only when >=14 days of post-W-C stamped-fire history
        if n_cond >= _READINESS_TARGET:
            # Target already met — no projection needed
            forecast = {
                "forecast": "already_ready",
                "n_cond": n_cond,
            }
        elif post_wc_span_days >= _READINESS_MIN_DAYS and n_post_wc_fires > 0:
            # trailing cadence: post-W-C fires per day
            cadence_per_day = n_post_wc_fires / post_wc_span_days
            # trailing condition-hit share (use post-W-C subset for the family)
            if cond_cols and len(post_wc) > 0:
                available_cond_cols = [c for c in cond_cols if c in post_wc.columns]
                if available_cond_cols:
                    post_wc_cond_mask = post_wc[available_cond_cols].notna().any(axis=1)
                    post_wc_cond_share = float(post_wc_cond_mask.mean()) if len(post_wc_cond_mask) > 0 else 0.0
                else:
                    post_wc_cond_share = 0.0
            else:
                post_wc_cond_share = 0.0

            if cadence_per_day > 0 and post_wc_cond_share > 0:
                days_needed_from_now = (_READINESS_TARGET - n_cond) / (cadence_per_day * post_wc_cond_share)
                forecast_date = (today + timedelta(days=days_needed_from_now)).isoformat()
                forecast = {
                    "forecast": "date",
                    "forecast_date": forecast_date,
                    "basis": (
                        f"n_cond={n_cond}/{_READINESS_TARGET} needed; "
                        f"post-W-C cadence={cadence_per_day:.3f}/day × "
                        f"cond_hit_share={post_wc_cond_share:.3f} → "
                        f"{days_needed_from_now:.0f} days"
                    ),
                    "post_wc_fires": n_post_wc_fires,
                    "post_wc_span_days": post_wc_span_days,
                }
            else:
                forecast = {
                    "forecast": "unknown",
                    "reason": "zero cadence or zero cond_hit_share in post-W-C window",
                    "post_wc_fires": n_post_wc_fires,
                    "post_wc_span_days": post_wc_span_days,
                }
        else:
            # Insufficient post-W-C history
            forecast = {
                "forecast": "unknown",
                "reason": (
                    f"post-W-C history {post_wc_span_days}d < {_READINESS_MIN_DAYS}d minimum; "
                    f"n_post_wc_fires={n_post_wc_fires}"
                ),
                "post_wc_fires": n_post_wc_fires,
                "post_wc_span_days": post_wc_span_days,
            }

        results.append({
            "family": family,
            "status": per_family_status.get(family, "unknown"),
            "n_cond": n_cond,
            "n_base": n_base,
            "target_n_cond": _READINESS_TARGET,
            "weekly_fires": dict(sorted(weekly_fires.items())),
            "n_stamped_cond": n_stamped_cond,
            "cond_hit_share": cond_hit_share,
            "readiness_forecast": forecast,
        })

    return results


# ---------------------------------------------------------------------------
# Section 4: structural-null ledger
# ---------------------------------------------------------------------------

def _structural_nulls(root: Path, today: date) -> dict:
    """Document structurally-null columns and their root causes."""
    next_opex = _next_opex_date(today)
    opex_days_now = sum(
        1 for i in range(1, (next_opex - today).days + 1)
        if (today + timedelta(days=i)).weekday() < 5
    )

    return {
        "iv_rank_252": {
            "columns": ["opt_iv_rank_252", "iv_rank_252"],
            "null_share": 1.0,
            "root_cause": "ruling A9 — IV-backfill PR (W-E0) not yet merged; "
                          "column created always-null in options_stamp.py by design. "
                          "Will become non-null when W-E0 lands.",
            "resolution": "W-E0 (87/88 roots at 15y as of 2026-07-06); accrual ongoing",
        },
        "pin_risk": {
            "columns": ["opt_pin_risk", "pin_risk"],
            "null_share": 1.0,
            "root_cause": "by-design opex_days<=5 gate — "
                          "opt_pin_risk requires opex_days<=5 AND gamma='long' AND "
                          "min_wall_dist<=2%. Gate only fires in the final week before "
                          "monthly OPEX.",
            "pin_risk_gate_condition": "opex_days<=5 AND gamma_regime='long' AND "
                                       "min(|wall_dist_up_pct|, |wall_dist_down_pct|)<=2.0",
            "current_opex_days": opex_days_now,
            "next_opex_date": next_opex.isoformat(),
            "note": "pin_risk will be non-null only in the 5 trading days before each "
                    "monthly OPEX. Current build date has opex_days>5 — no fires expected.",
        },
        "gamma_regime_constancy": {
            "columns": ["gamma_regime", "gamma_regime_structurally_constant", "opt_gamma_regime"],
            "caveat": "gamma_regime_structurally_constant=True for all rows where GEX data "
                      "is present (audit #29 — single-name GEX snapshots represent a "
                      "single point-in-time, not intraday dynamics). The column is not "
                      "a defect but a documented interpretation caveat. "
                      "Per-name gamma_regime should be read as 'dominant regime on fire date', "
                      "not 'intraday regime'.",
            "state_pct_structurally_constant": "see feature_coverage gamma_regime_structurally_constant",
        },
    }


# ---------------------------------------------------------------------------
# Section 5: consistency rows
# ---------------------------------------------------------------------------

def _consistency_rows(gate: dict, root: Path, today: date) -> list[dict]:
    """BH test-count drift, stale as_of ages, accrual audit status."""
    rows: list[dict] = []

    # --- BH test-count drift (print only — fix owned by W-OVC) ---
    gate_family_size = gate.get("fdr_family", {}).get("family_size", None)
    gate_description = gate.get("fdr_family", {}).get("description", "")
    # Count mentions of "×N" patterns in the description to derive registered tests
    # The masterplan registered 28 after #1674 per adjudication §5.1 / §2 census note
    REGISTERED_TEST_COUNT = 28      # registry value post-#1674 (per adjudication §5.1)
    VALIDATE_DOCSTRING_COUNT = 22   # validate_options_entry.py docstring FDR statement
    rows.append({
        "check": "bh_test_count_drift",
        "registry_registered": REGISTERED_TEST_COUNT,
        "gate_json_family_size": gate_family_size,
        "validate_docstring_count": VALIDATE_DOCSTRING_COUNT,
        "note": (
            f"BH test-count drift: registry after #1674 = {REGISTERED_TEST_COUNT} tests; "
            f"gate.json fdr_family.family_size = {gate_family_size}; "
            f"validate_options_entry.py FDR docstring = {VALIDATE_DOCSTRING_COUNT}. "
            "These are TEST counts (the BH family size), not bucket counts. "
            "Discrepancy is printed only — fix owned by W-OVC as first obligation (RUL-U5)."
        ),
    })

    # --- stale as_of ages per source ---
    state_p = root / "data" / "options_entry" / "state.parquet"
    gate_asof = gate.get("generated_at", None)
    ledger_p = root / "data" / "us_board_ledger" / "retro_grades.parquet"

    stale_checks: list[dict] = []

    if state_p.exists():
        try:
            import pandas as pd
            state_df = pd.read_parquet(state_p, columns=["as_of"])
            latest_state = str(state_df["as_of"].max())
            age_days = (today - date.fromisoformat(latest_state)).days
            stale_checks.append({
                "source": "options_entry/state.parquet",
                "latest_as_of": latest_state,
                "age_days_from_today": age_days,
                "status": "FRESH" if age_days <= 2 else "STALE",
            })
        except Exception as exc:  # noqa: BLE001
            stale_checks.append({
                "source": "options_entry/state.parquet",
                "error": str(exc),
                "status": "READ_ERROR",
            })
    else:
        stale_checks.append({
            "source": "options_entry/state.parquet",
            "status": "ABSENT",
        })

    if gate_asof:
        try:
            # gate.json generated_at is like "2026-07-06 08:36 UTC"
            ga = gate_asof.replace(" UTC", "").strip()
            gate_date = date.fromisoformat(ga[:10])
            age_days = (today - gate_date).days
            stale_checks.append({
                "source": "options_entry/gate.json",
                "latest_as_of": gate_asof,
                "age_days_from_today": age_days,
                "status": "FRESH" if age_days <= 2 else "STALE",
            })
        except Exception as exc:  # noqa: BLE001
            stale_checks.append({
                "source": "options_entry/gate.json",
                "error": str(exc),
                "status": "READ_ERROR",
            })

    if ledger_p.exists():
        try:
            import pandas as pd
            led_df = pd.read_parquet(ledger_p, columns=["as_of"])
            latest_ledger = str(led_df["as_of"].max())
            age_days = (today - date.fromisoformat(latest_ledger)).days
            stale_checks.append({
                "source": "us_board_ledger/retro_grades.parquet",
                "latest_as_of": latest_ledger,
                "age_days_from_today": age_days,
                "status": "FRESH" if age_days <= 5 else "STALE",
            })
        except Exception as exc:  # noqa: BLE001
            stale_checks.append({
                "source": "us_board_ledger/retro_grades.parquet",
                "error": str(exc),
                "status": "READ_ERROR",
            })
    else:
        stale_checks.append({
            "source": "us_board_ledger/retro_grades.parquet",
            "status": "ABSENT",
        })

    rows.append({
        "check": "stale_asof_ages",
        "sources": stale_checks,
    })

    # --- audit_options_accrual last-run status ---
    accrual_audit = _read_quality_audit(root)
    if accrual_audit:
        rows.append({
            "check": "audit_options_accrual_last_run",
            "generated_at": accrual_audit.get("generated_at"),
            "ok": accrual_audit.get("ok"),
            "fail_reasons": accrual_audit.get("fail_reasons", []),
            "warnings": accrual_audit.get("warnings", []),
        })
    else:
        rows.append({
            "check": "audit_options_accrual_last_run",
            "status": "NOT_YET_RUN",
            "note": "data/quality/options_accrual_audit.json absent — "
                    "audit_options_accrual.py has not yet run (wired in this PR, W-OC)",
        })

    return rows


# ---------------------------------------------------------------------------
# Core audit runner
# ---------------------------------------------------------------------------

def run(root: Path | None = None, write: bool = True) -> dict:
    """Run the full options entry coverage audit.  Returns summary dict."""
    t0 = time.monotonic()
    root = _resolve_root(root)
    today = datetime.now(timezone.utc).date()

    # --- read inputs ---
    state_p = root / "data" / "options_entry" / "state.parquet"
    gate_p = root / "data" / "options_entry" / "gate.json"
    ledger_p = root / "data" / "us_board_ledger" / "retro_grades.parquet"

    state_df = _read_parquet(state_p)
    gate = _read_json(gate_p) or {}
    ledger_df = _read_parquet(ledger_p)

    state_absent = state_df is None
    gate_absent = not gate
    ledger_absent = ledger_df is None

    absent_stores: list[str] = []
    if state_absent:
        absent_stores.append("data/options_entry/state.parquet")
        log.warning("coverage_audit: state.parquet absent — feature coverage will be empty")
    if gate_absent:
        absent_stores.append("data/options_entry/gate.json")
        log.warning("coverage_audit: gate.json absent — family coverage will be empty")
    if ledger_absent:
        absent_stores.append("data/us_board_ledger/retro_grades.parquet")
        log.warning("coverage_audit: ledger absent — stamp coverage will be empty")

    # --- section 1: feature coverage ---
    if state_df is not None:
        feature_section = _feature_coverage(state_df)
    else:
        feature_section = {"absent": True, "n_rows": 0, "n_features": 0, "features": [], "ticker_coverage": {}}

    # --- section 2+3: family stamp coverage + readiness forecast ---
    if ledger_df is not None and gate:
        family_section = _family_stamp_coverage(ledger_df, gate, today)
    elif ledger_df is None and gate:
        # Gate present but no ledger — emit family status from gate only
        family_section = [
            {
                "family": f,
                "status": s,
                "n_cond": gate.get("tests", {}).get(f, {}).get("n_cond", 0),
                "n_base": gate.get("tests", {}).get(f, {}).get("n_base", 0),
                "target_n_cond": _READINESS_TARGET,
                "weekly_fires": {},
                "n_stamped_cond": 0,
                "cond_hit_share": 0.0,
                "readiness_forecast": {
                    "forecast": "unknown",
                    "reason": "ledger absent — cannot derive weekly fire cadence",
                },
            }
            for f, s in gate.get("per_family_status", {}).items()
        ]
    else:
        family_section = []

    # --- section 4: structural nulls ---
    structural_nulls = _structural_nulls(root, today)

    # --- section 5: consistency rows ---
    consistency = _consistency_rows(gate, root, today)

    # --- assemble vintage stamp (simplified: no price-plane reference for infra audit) ---
    stamp = {
        "audit": "options_entry_coverage.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "absent_stores": absent_stores,
    }

    payload: dict[str, Any] = {
        "schema": "options_entry_coverage.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "absent_stores": absent_stores,
        "feature_coverage": feature_section,
        "family_stamp_coverage": family_section,
        "structural_nulls": structural_nulls,
        "consistency": consistency,
        "_stamp": stamp,
    }

    elapsed = time.monotonic() - t0
    n_families = len(family_section)
    n_features = feature_section.get("n_features", 0)
    n_absent = len(absent_stores)
    log.info(
        "options_entry_coverage audit: %d features, %d families, %d absent stores (%.2fs)",
        n_features, n_families, n_absent, elapsed,
    )

    if write:
        _write_json(payload, root)

    return payload


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _write_json(payload: dict, root: Path) -> None:
    """Write data/options_entry/coverage.json (single-writer)."""
    out = root / "data" / "options_entry" / "coverage.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, separators=(",", ": ")))
        log.info("options_entry_coverage: wrote %s", out)
    except Exception as exc:  # noqa: BLE001
        log.warning("options_entry_coverage: json write failed: %s", exc)


# ---------------------------------------------------------------------------
# Collect step hook
# ---------------------------------------------------------------------------

def run_as_collect_step() -> None:
    """End-of-collect hook — must never raise; wraps run() in a broad except."""
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        log.error("[options_entry_coverage] audit crashed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="print results without writing outputs")
    ap.add_argument("--root", default=None,
                    help="repo root (default: parent of scripts/)")
    ap.add_argument("--json", action="store_true",
                    help="print JSON summary to stdout")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    root = Path(args.root) if args.root else None
    payload = run(root=root, write=not args.check)

    if args.json or args.check:
        print(json.dumps(payload, indent=2))
    else:
        gat = payload.get("generated_at", "")[:10]
        feat = payload["feature_coverage"].get("n_features", 0)
        fam = len(payload["family_stamp_coverage"])
        absent = payload.get("absent_stores", [])
        print(f"\nOptions Entry Coverage Audit — {gat}")
        print(f"  {feat} features, {fam} families, {len(absent)} absent stores")
        if absent:
            for s in absent:
                print(f"  ABSENT: {s}")
        print()
        # Feature coverage table
        print(f"{'Feature':<40} {'n_nonnull':>9} {'share':>7}")
        print("-" * 60)
        for f in payload["feature_coverage"].get("features", []):
            print(f"  {f['feature']:<38} {f['n_nonnull']:>9} {f['share_nonnull']:>7.1%}")
        print()
        # Family readiness
        print(f"{'Family':<20} {'n_cond':>7} {'n_base':>7}  {'forecast'}")
        print("-" * 60)
        for fam_row in payload["family_stamp_coverage"]:
            fc = fam_row["readiness_forecast"]
            fc_str = fc.get("forecast_date") or fc.get("forecast", "unknown")
            print(f"  {fam_row['family']:<18} {fam_row['n_cond']:>7} {fam_row['n_base']:>7}  {fc_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
