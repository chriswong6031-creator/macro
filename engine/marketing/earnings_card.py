"""engine.marketing.earnings_card — Earnings fast-lane helpers.

Callables used by the real-time earnings fast-lane daemon and tests.

Public API:
    todays_reporters(root, *, today=None) -> list[dict]
        Reads data/earnings/earnings.parquet and returns reporters for *today*
        (next_date == today). Each entry: {ticker, when: "pre"|"post"|"unknown",
        eps_est}.

    build_earnings_post(ticker, company_name, actual, est, rev_actual, rev_est,
                        root, *, quarter=None) -> dict
        Renders the branded SVG card + produces placeholder post copy.
        Returns {"headline": str, "body": str, "svg": str}.

Design notes:
    - Both functions are fail-soft: they log to stderr rather than raise so the
      fast-lane daemon stays alive after any single-ticker failure.
    - todays_reporters is cheap — reads parquet, does a date string comparison.
      Called once per arm cycle (morning pre-market + afternoon post-market).
    - build_earnings_post is the callable the future daemon invokes on a freshly
      detected earnings release. Copywriter integration is a follow-up; the
      placeholder body is honest about that gap.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Calendar reader
# ─────────────────────────────────────────────────────────────────────────────

_WHEN_MAP = {
    "time-pre-market": "pre",
    "time-after-hours": "post",
    "time-not-supplied": "unknown",
}


def todays_reporters(
    root: Path | str,
    *,
    today: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of tickers reporting today from the earnings calendar.

    Each entry:
        {
            "ticker":   str,   # uppercase
            "when":     str,   # "pre" | "post" | "unknown"
            "eps_est":  float | None,
        }

    Args:
        root: Repository root (or any parent that contains data/earnings/).
        today: ISO date string "YYYY-MM-DD". Defaults to the current UTC date.

    Returns:
        List (possibly empty) — never raises.
    """
    try:
        if today is None:
            from datetime import datetime, timezone
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        path = Path(root) / "data" / "earnings" / "earnings.parquet"
        if not path.exists():
            return []

        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)

        if "next_date" not in df.columns:
            return []

        # Filter to today — next_date is stored as strings "YYYY-MM-DD"
        mask = df["next_date"] == today
        subset = df[mask]

        results: list[dict[str, Any]] = []
        for ticker, row in subset.iterrows():
            raw_when = str(row.get("next_time", "time-not-supplied"))
            when = _WHEN_MAP.get(raw_when, "unknown")
            eps_est_raw = row.get("eps_forecast", None)
            try:
                eps_est: float | None = float(eps_est_raw) if eps_est_raw is not None else None
                if eps_est != eps_est:  # NaN guard
                    eps_est = None
            except (TypeError, ValueError):
                eps_est = None

            results.append({
                "ticker": str(ticker).upper(),
                "when": when,
                "eps_est": eps_est,
            })

        return results
    except Exception as exc:  # noqa: BLE001
        print(f"[earnings_card] todays_reporters error: {exc}", file=sys.stderr)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Post builder
# ─────────────────────────────────────────────────────────────────────────────

def build_earnings_post(
    ticker: str,
    company_name: str,
    actual: float,
    est: float,
    rev_actual: float | None,
    rev_est: float | None,
    root: Path | str,
    *,
    quarter: str | None = None,
) -> dict[str, str]:
    """Build an earnings post dict ready for the publisher.

    Args:
        ticker: Stock ticker (e.g. "AAPL").
        company_name: Full name (e.g. "Apple Inc.").
        actual: Reported EPS.
        est: Consensus EPS estimate.
        rev_actual: Reported revenue in dollars, or None for EPS-only.
        rev_est: Consensus revenue estimate in dollars, or None for EPS-only.
        root: Repository root — passed to resolve_logo + logo cache path.
        quarter: Quarter label, e.g. "Q2 2026". Optional.

    Returns:
        {
            "headline": str,   # social post headline (≤280 chars)
            "body":     str,   # post body copy (placeholder; copywriter follow-up)
            "svg":      str,   # self-contained SVG card from render_earnings_card
        }
        Never raises — on any error returns {"headline": "", "body": "", "svg": ""}.
    """
    EMPTY: dict[str, str] = {"headline": "", "body": "", "svg": ""}
    try:
        from engine.marketing.chart_render import render_earnings_card  # noqa: PLC0415

        svg = render_earnings_card(
            ticker,
            company_name,
            actual,
            est,
            rev_actual,
            rev_est,
            quarter=quarter,
            logo_root=root,
        )

        # ── Classify beat/miss/inline ──────────────────────────────────────
        if est == 0:
            surp_pct = 0.0
        else:
            surp_pct = (actual - est) / abs(est) * 100.0

        if abs(surp_pct) < 0.5:
            verdict = "INLINE"
        elif actual > est:
            verdict = "BEAT"
        else:
            verdict = "MISS"

        sign = "+" if surp_pct >= 0 else ""
        surp_str = f"{sign}{surp_pct:.1f}%"

        q_label = f" ({quarter})" if quarter else ""
        headline = (
            f"${ticker.upper()} EARNINGS {verdict}{q_label}: "
            f"EPS ${actual:.2f} vs ${est:.2f} est [{surp_str}]"
        )
        if rev_actual is not None and rev_est is not None:
            def _short_rev(v: float) -> str:
                if v >= 1e12:
                    return f"${v / 1e12:.2f}T"
                if v >= 1e9:
                    return f"${v / 1e9:.2f}B"
                if v >= 1e6:
                    return f"${v / 1e6:.1f}M"
                return f"${v:,.0f}"
            headline += f" | Rev {_short_rev(rev_actual)} vs {_short_rev(rev_est)} est"

        # Trim to 280 chars (safety)
        if len(headline) > 280:
            headline = headline[:277] + "..."

        # Placeholder body — copywriter integration is a follow-up (see
        # MARKETING_REALTIME_FASTLANE_ARCHITECTURE_BY_FABLE.md §4).
        body = (
            f"{company_name} reported {verdict.lower()} results{q_label}.\n"
            f"EPS: ${actual:.2f} (est ${est:.2f}, {surp_str} surprise).\n"
            + (
                f"Revenue: {_short_rev(rev_actual)} (est {_short_rev(rev_est)}).\n"
                if rev_actual is not None and rev_est is not None else ""
            )
            + "Source: Company IR · mastermind-x.com"
        )

        return {"headline": headline, "body": body, "svg": svg}

    except Exception as exc:  # noqa: BLE001
        print(f"[earnings_card] build_earnings_post({ticker}) error: {exc}", file=sys.stderr)
        return EMPTY
