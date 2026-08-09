"""Rolling 13F filing-season handoff for the Ownership Intelligence Desk.

The canonical smart-money boards must never combine managers from different
reporting quarters.  Before a strict majority reports they remain on the complete
prior-quarter roster, while this module exposes incoming books manager by manager.
After the handoff, the canonical boards use only the paired incoming reporters.

The Early Filing Radar is deliberately temporary.  It appears after the first
active manager files the expected quarter and retires when that quarter becomes
the modal/majority book in the tracked roster.  At that handoff the main boards
are already materially the new quarter, so a separate "early" panel would be
duplicative.

All ranking is disclosure-importance only: position size, action magnitude,
position rank, and the manager's historical descriptive grade.  It is never an
expected-return score and never enters allocation, Neural Web, or Prophet.
"""
from __future__ import annotations

from datetime import date
import math
from typing import Any


_ACTION_BASE = {"new": 36.0, "exit": 34.0, "add": 24.0, "trim": 20.0}
_GRADE_BONUS = {"A": 10.0, "B": 6.0, "C": 3.0, "D": 0.0, "n/a": 0.0}


def quarter_label(period_end: str | None) -> str:
    """Return a compact calendar-quarter label from an ISO quarter end."""
    if not period_end:
        return "Unavailable"
    try:
        d = date.fromisoformat(str(period_end)[:10])
    except (TypeError, ValueError):
        return str(period_end)
    q = {3: 1, 6: 2, 9: 3, 12: 4}.get(d.month)
    return f"Q{q} {d.year}" if q else str(period_end)


def _active_grid(clock: dict) -> list[dict]:
    return [r for r in (clock.get("filed_pending") or [])
            if r.get("status") != "closed"]


def transition_counts(clock: dict) -> dict:
    """Pure filing-rollout counts and labels derived from the season clock."""
    grid = _active_grid(clock)
    expected = str(clock.get("quarter_end") or "")
    filed = [r for r in grid if r.get("status") == "filed"]
    notices = [r for r in grid if r.get("status") == "notice"]
    total = len(grid)

    period_counts: dict[str, int] = {}
    for row in grid:
        pe = str(row.get("period_end") or "")
        if pe:
            period_counts[pe] = period_counts.get(pe, 0) + 1
    display_period = (max(period_counts, key=lambda p: (period_counts[p], p))
                      if period_counts else "")
    display_count = period_counts.get(display_period, 0)

    # A strict majority avoids switching a 50-manager board on a 25/25 tie.
    # Before this threshold, the canonical boards remain on the complete prior
    # quarter and this radar is the only surface that consumes incoming deltas.
    majority_at = (total // 2 + 1) if total else 0
    filed_n = len(filed)
    notice_n = len(notices)
    obligation_n = filed_n + notice_n
    if obligation_n == 0:
        state = "awaiting_first"
    elif obligation_n == total:
        state = "complete"
    elif filed_n < majority_at:
        state = "early_roll"
    elif filed_n < total:
        state = "bulk_roll"
    else:
        state = "bulk_roll"

    baseline_periods = {p: n for p, n in period_counts.items() if p != expected}
    baseline_period = (max(baseline_periods, key=lambda p: (baseline_periods[p], p))
                       if baseline_periods else display_period)
    incoming_is_canonical = bool(expected and filed_n >= majority_at)
    canonical_period = expected if incoming_is_canonical else baseline_period
    canonical_slugs = (
        [str(r.get("slug") or "") for r in filed]
        if incoming_is_canonical
        else [str(r.get("slug") or "") for r in grid]
    )

    return {
        "state": state,
        "expected_period": expected,
        "expected_label": quarter_label(expected),
        "display_period": display_period,
        "display_label": quarter_label(display_period),
        "display_count": display_count,
        "filed_count": filed_n,
        "notice_count": notice_n,
        "obligation_count": obligation_n,
        "pending_count": max(0, total - obligation_n),
        "active_count": total,
        "active_slugs": [str(r.get("slug") or "") for r in grid],
        "majority_at": majority_at,
        "progress_pct": round(100.0 * filed_n / total, 1) if total else 0.0,
        "is_mixed": len(period_counts) > 1,
        "period_counts": period_counts,
        "show_early_radar": bool(obligation_n > 0 and not incoming_is_canonical),
        "canonical_period": canonical_period,
        "canonical_label": quarter_label(canonical_period),
        "canonical_slugs": canonical_slugs,
        "canonical_count": len(canonical_slugs),
        "canonical_coverage_pct": (
            round(100.0 * len(canonical_slugs) / total, 1) if total else 0.0),
        "cohort_basis": ("paired_reporters" if incoming_is_canonical
                         else "complete_baseline"),
        "filed_rows": sorted(filed, key=lambda r: (
            str(r.get("filing_date") or ""), str(r.get("slug") or "")), reverse=True),
        "notice_rows": sorted(notices, key=lambda r: (
            str(r.get("notice_filing_date") or ""), str(r.get("slug") or "")),
            reverse=True),
    }


def _importance(action: str, book_pct: float, shares_change_pct: float | None,
                position_rank: int | None, grade: str | None) -> tuple[float, str]:
    """Deterministic disclosure-importance score; not an alpha/return score."""
    score = _ACTION_BASE.get(action, 0.0)
    score += min(34.0, max(0.0, float(book_pct)) * 5.0)
    if shares_change_pct is not None and action in ("add", "trim"):
        score += min(10.0, abs(float(shares_change_pct)) / 10.0)
    if position_rank is not None:
        score += 8.0 if position_rank <= 5 else 5.0 if position_rank <= 10 else 0.0
    score += _GRADE_BONUS.get(str(grade or "n/a"), 0.0)
    score = round(min(100.0, score), 1)
    label = "major" if score >= 72 else "notable" if score >= 52 else "monitor"
    return score, label


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def build_filing_transition(funds: dict[str, dict], clock: dict,
                            tracker: dict | None = None,
                            max_changes: int = 16) -> dict:
    """Build the temporary early-filer payload from on-disk immutable snapshots.

    A failure for one manager is isolated.  The counts/labels remain available even
    when ticker resolution or a snapshot read fails, so the header never lies about
    rollout coverage merely because enrichment degraded.
    """
    counts = transition_counts(clock)
    lb = {r.get("slug"): r for r in ((tracker or {}).get("leaderboard") or [])}
    expected = counts["expected_period"]
    changes: list[dict[str, Any]] = []
    filers: list[dict[str, Any]] = []
    unresolved = 0

    if counts["filed_count"]:
        try:
            from engine.smart_money import (
                _read_period_pair, diff_snapshots, full_cusip_map, name_ticker_map,
                position_rank_and_tilt, resolve_tickers,
            )
            name_map = name_ticker_map()
            cusip_map, _ = full_cusip_map()
        except Exception:  # noqa: BLE001 - counts still provide an honest shell
            name_map = cusip_map = None

        for meta in counts["filed_rows"]:
            slug = str(meta.get("slug") or "")
            spec = funds.get(slug) or {}
            action_counts = {"new": 0, "add": 0, "trim": 0, "exit": 0}
            fund_changes: list[dict] = []
            book_value = None
            n_positions = None
            value_unit_adjusted = False
            grade = (lb.get(slug) or {}).get("grade")

            try:
                if name_map is None or cusip_map is None:
                    raise RuntimeError("ticker maps unavailable")
                prev, latest = _read_period_pair(slug, expected)
                if latest is None or latest.empty:
                    raise RuntimeError("latest snapshot unavailable")
                latest_period = (str(latest["period_end"].iloc[0])
                                 if "period_end" in latest.columns else "")
                if latest_period != expected:
                    raise RuntimeError("latest snapshot does not match expected quarter")

                latest_sh = latest[latest.get("sh_type", "SH") == "SH"]
                book_value = float(latest_sh["value_usd"].sum()) if len(latest_sh) else 0.0
                n_positions = int(latest_sh["cusip"].nunique()) if len(latest_sh) else 0
                if "value_unit_inference" in latest.columns and len(latest):
                    value_unit_adjusted = str(
                        latest["value_unit_inference"].iloc[0]
                    ).startswith("post-2023-legacy-thousands")
                prior_total = 0.0
                if prev is not None and not prev.empty:
                    prior_sh = prev[prev.get("sh_type", "SH") == "SH"]
                    prior_total = float(prior_sh["value_usd"].sum())

                diff = diff_snapshots(prev, latest)
                if diff.empty:
                    raise RuntimeError("empty quarter diff")
                diff = resolve_tickers(diff, name_map, cusip_map)
                diff = position_rank_and_tilt(diff)

                for row in diff.itertuples(index=False):
                    action = str(getattr(row, "action", "") or "")
                    if action not in action_counts:
                        continue
                    action_counts[action] += 1
                    ticker = getattr(row, "ticker", None)
                    if not ticker:
                        unresolved += 1
                        continue
                    value_usd = _finite_float(
                        getattr(row, "value_usd", 0.0), 0.0) or 0.0
                    book_pct = _finite_float(
                        getattr(row, "pct_portfolio", 0.0), 0.0) or 0.0
                    if action == "exit" and prior_total > 0:
                        book_pct = 100.0 * value_usd / prior_total
                    rank_raw = getattr(row, "rank", None)
                    rank_number = _finite_float(rank_raw)
                    rank = (int(rank_number)
                            if rank_number is not None and action != "exit" else None)
                    shares_change = _finite_float(
                        getattr(row, "shares_change_pct", None))
                    score, label = _importance(action, book_pct, shares_change, rank, grade)
                    rec = {
                        "ticker": str(ticker),
                        "issuer": str(getattr(row, "issuer", "") or ""),
                        "action": action,
                        "book_pct": round(book_pct, 2),
                        "shares_change_pct": shares_change,
                        "value_usd": round(value_usd, 0),
                        "position_rank": rank,
                        "slug": slug,
                        "fund_name": spec.get("name", slug),
                        "filing_date": str(meta.get("filing_date") or ""),
                        "manager_grade": grade,
                        "importance_score": score,
                        "importance_label": label,
                    }
                    fund_changes.append(rec)
                    changes.append(rec)
            except Exception:  # noqa: BLE001 - isolate one fund, preserve rollout counts
                pass

            fund_changes.sort(key=lambda r: (
                -r["importance_score"], r["ticker"]))
            filers.append({
                "slug": slug,
                "name": spec.get("name", slug),
                "filing_date": str(meta.get("filing_date") or ""),
                "period_end": str(meta.get("period_end") or ""),
                "grade": grade,
                "book_value_usd": book_value,
                "n_positions": n_positions,
                "value_unit_adjusted": value_unit_adjusted,
                "action_counts": action_counts,
                "top_changes": fund_changes[:3],
                "max_importance": (fund_changes[0]["importance_score"]
                                   if fund_changes else None),
            })

    changes.sort(key=lambda r: (
        -r["importance_score"], r["filing_date"], r["ticker"]))
    filers.sort(key=lambda r: (
        -(r.get("max_importance") or -1), r.get("filing_date") or ""))

    result = {k: v for k, v in counts.items()
              if k not in {"filed_rows", "notice_rows"}}
    result.update({
        "automation_mode": "rolling_filing_season",
        "filers": filers,
        "notices": [
            {
                "slug": str(row.get("slug") or ""),
                "name": str(row.get("name") or row.get("slug") or ""),
                "filing_date": str(row.get("notice_filing_date") or ""),
                "period_end": str(row.get("notice_period_end") or ""),
                "form": str(row.get("notice_form") or "13F-NT"),
                "accession": str(row.get("notice_accession") or ""),
            }
            for row in counts.get("notice_rows", [])
        ],
        "ranked_changes": changes[:max_changes],
        "n_ranked_changes": len(changes),
        "unresolved_changes": unresolved,
        "value_unit_adjustments": sum(
            1 for filer in filers if filer.get("value_unit_adjusted")),
        "importance_note": (
            "Disclosure importance ranks action type, book weight, share-count change, "
            "position rank, and the manager's descriptive historical grade. It is not "
            "an expected-return or buy score."
        ),
        "retire_note": (
            f"This radar retires automatically at {counts['majority_at']}/"
            f"{counts['active_count']} filings, when the expected quarter becomes "
            "a strict majority and the main boards switch to the paired-reporter cohort."
        ),
        "unit_note": (
            "The original SEC-reported value is retained. Post-2023 filings that "
            "still match the legacy thousands-unit shape are normalized and flagged."
        ),
        "notice_note": (
            "A 13F-NT satisfies a filing obligation but contains no holdings book. "
            "It is shown separately and never counted as a zero-position portfolio."
        ),
    })
    return result
