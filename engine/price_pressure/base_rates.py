"""engine.price_pressure.base_rates — the frozen honesty layer (masterplan §6).

``data/price_pressure/base_rates.json``: what actually happened to shocks like
these, cut by filing family and horizon, produced ONCE by the historical
backfill and refrozen only by an explicit re-run.  The nightly never touches it.

Four properties this module exists to hold, each of which a naive version of the
same table gets wrong:

1. **Families are coverage-gated.**  ``no-filing`` is defined only inside the
   EDGAR-covered universe; the ~54% of the panel EDGAR does not track gets
   ``filing-coverage-unknown``.  Conflating "we looked and found nothing" with
   "we did not look" was a review BLOCKER.
2. **Every cell carries its own uncertainty AND its clustering.**  Shock arrivals
   bunch on market-wide days, so a cell reports ``n_events``, the per-horizon
   episode honest-N (``first_in_h`` rows only), ``n_dates``, and a date-block
   bootstrap CI computed with LSR-P0's own inference function.  200 episodes can
   be three selloff days.
3. **Losers stay in the denominator.**  ``DELISTED_OR_HALTED`` is a terminal
   VALUE inside the terminal-state shares, and rows whose window has not elapsed
   are reported as ``open`` per cell — never silently dropped.
4. **The tables do not claim separation.**  LSR-P0 measured family separation at
   0/10 contrasts; the null sentence ships inside the artifact so no downstream
   surface can quote a family difference the record does not support.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.price_pressure import (
    ENGINE_VERSION,
    HEADLINE_HORIZONS,
    LEDGER_HORIZONS,
    RETRACE_FULL,
    RETRACE_PARTIAL,
    TERMINAL_PRIMARY,
    TERMINAL_SECONDARY,
)
from engine.price_pressure.context import FAMILIES
from engine.price_pressure.panel import date_block_ci

log = logging.getLogger("price_pressure.base_rates")

SCHEMA = "price_pressure.base_rates.v1"
ARTIFACT_REL: tuple[str, ...] = ("price_pressure", "base_rates.json")

#: Printed verbatim in the artifact and the report.  Not editable downstream:
#: any surface quoting a family difference must quote this next to it.
NULL_CONTRAST_STATEMENT = (
    "Family-level differences in forward outcomes were measured and are null "
    "(0/10 contrasts) — DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER; families "
    "are shown as context, not separation."
)

#: The authority block every DRL artifact carries (govrev pattern).
AUTHORITY: dict[str, bool] = {
    "can_rank": False, "can_size": False, "can_gate": False,
    "can_originate_signal": False, "can_escalate": False,
}


def artifact_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*ARTIFACT_REL)


def read_base_rates(data_root: Path) -> dict | None:
    """Read the frozen tables, or None.  Never raises."""
    p = artifact_path(data_root)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: base rates unreadable (%s)", exc)
        return None


# ---------------------------------------------------------------------------
# one cell
# ---------------------------------------------------------------------------

def _q(x: np.ndarray, p: float) -> float | None:
    return float(np.nanpercentile(x, p)) if x.size else None


def cell(rows: pd.DataFrame, horizon: int) -> dict:
    """One family x horizon cell, honest-N'd on ``first_in_h``.

    ``rows`` is already restricted to one (side, family).  Everything reported
    about the retrace DISTRIBUTION uses the horizon's own independence filter;
    the terminal-state shares use every row so no dead name escapes the table.
    """
    frac_col = f"retrace_{horizon}"
    fresh = rows[rows[f"first_in_{horizon}"].fillna(False).astype(bool)]
    graded = fresh[fresh[frac_col].notna()]
    x = graded[frac_col].to_numpy(dtype="float64")

    per_date_frac = graded.groupby(graded["date"])[frac_col].mean() if len(graded) else pd.Series(dtype=float)
    per_date_hit = (graded.assign(_h=(graded[frac_col] >= RETRACE_PARTIAL).astype(float))
                    .groupby("date")["_h"].mean()) if len(graded) else pd.Series(dtype=float)

    term_col = f"terminal_state_{TERMINAL_PRIMARY}d" if horizon <= TERMINAL_PRIMARY \
        else f"terminal_state_{TERMINAL_SECONDARY}d"
    terms = rows[term_col]
    graded_terms = terms[terms.notna() & (terms.astype(str) != "")]
    shares = {}
    if len(graded_terms):
        vc = graded_terms.astype(str).value_counts()
        shares = {str(k): round(float(v) / float(len(graded_terms)), 4) for k, v in vc.items()}

    return {
        "n_events": int(len(rows)),
        "episode_n": int(len(fresh)),
        "n_graded": int(len(graded)),
        "n_dates": int(graded["date"].nunique()) if len(graded) else 0,
        "retrace_frac": {
            "mean_ci": date_block_ci(per_date_frac) if len(per_date_frac) else None,
            "q25": _q(x, 25), "median": _q(x, 50), "q75": _q(x, 75),
        },
        "share_retraced_33pct": {
            "point": round(float((x >= RETRACE_PARTIAL).mean()), 4) if x.size else None,
            "ci": date_block_ci(per_date_hit) if len(per_date_hit) else None,
        },
        "share_retraced_80pct": round(float((x >= RETRACE_FULL).mean()), 4) if x.size else None,
        "share_still_lower": round(float((x < 0).mean()), 4) if x.size else None,
        "terminal_shares": shares,
        "n_terminal_graded": int(len(graded_terms)),
        "n_open": int(len(terms) - len(graded_terms)),
        "share_truncated": (round(float(rows["truncated"].fillna(False).astype(bool).mean()), 4)
                            if len(rows) else None),
        "share_delisted_or_halted": round(shares.get("DELISTED_OR_HALTED", 0.0), 4),
    }


def tables(ledger: pd.DataFrame,
           horizons: tuple[int, ...] = HEADLINE_HORIZONS) -> dict:
    """``{side: {horizon: {family: cell}}}`` — down primary, both sides published."""
    out: dict = {}
    for side in ("down", "up"):
        s = ledger[ledger["side"] == side]
        out[side] = {}
        for h in horizons:
            out[side][str(h)] = {
                fam: cell(s[s["family"] == fam], h) for fam in FAMILIES
            }
            out[side][str(h)]["ALL"] = cell(s, h)
    return out


# ---------------------------------------------------------------------------
# coverage / survivorship
# ---------------------------------------------------------------------------

def coverage_block(ledger: pd.DataFrame, panel_names: int,
                   span: tuple[str, str]) -> dict:
    n = max(len(ledger), 1)
    fam_counts = ledger["family"].astype(str).value_counts().to_dict() if len(ledger) else {}
    basis = ledger["peer_basis"].astype(str).value_counts().to_dict() if len(ledger) else {}
    return {
        "panel_names": int(panel_names),
        "panel_span": [span[0], span[1]],
        "span_note": (
            "Rolling store: a later re-run drops the oldest era, so these rates "
            "are span-bound and stamped. Five years of history, not twenty."
        ),
        "events_total": int(len(ledger)),
        "events_down": int((ledger["side"] == "down").sum()) if len(ledger) else 0,
        "events_up": int((ledger["side"] == "up").sum()) if len(ledger) else 0,
        "edgar_covered_share": round(float(ledger["edgar_covered"].fillna(False).astype(bool).mean()), 4) if len(ledger) else None,
        "revisions_covered_share": round(float(ledger["revisions_covered"].fillna(False).astype(bool).mean()), 4) if len(ledger) else None,
        "family_counts": {str(k): int(v) for k, v in fam_counts.items()},
        "peer_basis_shares": {str(k): round(float(v) / n, 4) for k, v in basis.items()},
        "basket_context_share": round(float(ledger["basket"].notna().mean()), 4) if len(ledger) else None,
        "truncated_share": round(float(ledger["truncated"].fillna(False).astype(bool).mean()), 4) if len(ledger) else None,
        "dead_tape_share": round(float(ledger["dead_tape"].fillna(False).astype(bool).mean()), 4) if len(ledger) else None,
    }


SURVIVORSHIP = [
    "Prices come from an UNADJUSTED vendor store; splits are repaired with the "
    "yahoo-verified detector and every repaired bar is stamped ineligible, so a "
    "genuine one-day crash on a split day is excluded rather than mislabelled.",
    "Dividends are not adjusted: a ~0.5% ex-date drop is noise against a 3-sigma "
    "trigger, but it is a small downward bias in every forward window.",
    "Names that stop trading keep their rows and grade DELISTED_OR_HALTED inside "
    "the terminal shares. Rows whose window has not elapsed are counted as open.",
    "The sector map covers 1,516 GICS names; the LSR peer helper backfills every "
    "other name with the whole-universe mean, so most rows residualize against "
    "the market, not sector peers. The peer_basis split is printed above.",
    "EDGAR covers 1,314 tickers. Outside that set the filing family is "
    "filing-coverage-unknown, which is not the same statement as no filing.",
]

PROVENANCE = {
    "study": "LSR-P0 — reports/liquidity-shock-reversal-phase0.md",
    "registry_key": "DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER",
    "measured": [
        "Information separation 0/10 contrasts: every no-news-minus-news interval spans zero.",
        "No-news down-shocks CONTINUE: −0.33% residual at 5d, interval excludes zero.",
        "Microstructure features 3/36 vs 1.8 expected by chance; none survives two horizons.",
        "Veto stand-in 0/6 gaps exclude zero.",
        "The real unconditional 5d reversal (+0.284% liquid decile spread) breaks even at 14.2 bp/leg.",
    ],
    "reading": (
        "Continuation is the modal outcome and the recovery that exists is "
        "sub-cost. This lobe displays that record; it does not re-litigate it."
    ),
}


def build(ledger: pd.DataFrame, *, panel_names: int, span: tuple[str, str],
          design: dict, exemplars: dict | None = None,
          day_facts: dict | None = None) -> dict:
    """Assemble the full frozen artifact payload."""
    return {
        "schema": SCHEMA,
        "engine_version": ENGINE_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "display_only": True,
        "authority": dict(AUTHORITY),
        "null_contrast_statement": NULL_CONTRAST_STATEMENT,
        "headline_horizons": list(HEADLINE_HORIZONS),
        "graded_horizons": list(LEDGER_HORIZONS),
        "terminal_windows": {
            "primary_d": TERMINAL_PRIMARY,
            "secondary_d": TERMINAL_SECONDARY,
            "note": (
                f"t+{TERMINAL_SECONDARY} is graded identically to t+{TERMINAL_PRIMARY} "
                "but sits BEYOND the measured record (LSR-P0 measured 1..21 sessions)."
            ),
        },
        "design": design,
        "coverage": coverage_block(ledger, panel_names, span),
        "day_facts": day_facts or {},
        "tables": tables(ledger),
        "survivorship": list(SURVIVORSHIP),
        "provenance": dict(PROVENANCE),
        "exemplars": exemplars or {},
    }


#: The plain-word read the surface prints above the tables (masterplan §9 item 1).
#: EN and ZH are authored together — the ZH is written as Chinese, not translated
#: word-for-word from the English shape (house law).
NOTE_EN = (
    "Across five years of shocks like these, the slide continued more often than "
    "it came back — and which kind of filing it was made no measurable difference."
)
NOTE_ZH = (
    "在过去五年的同类冲击中，继续下跌比回补更常见；至于属于哪一类公告，"
    "在结果上看不出可测量的差别。"
)

#: Terminal slots are the SAME measurement on both sides, under mirrored names:
#: "recovered" = the ≥80%-retraced slot (down RECOVERED / up GAVE_BACK); "accepted
#: lower" = the <33% slot (down ACCEPTED_LOWER / up KEPT — the move stuck).
_TERMINAL_SLOTS: dict[str, dict[str, str]] = {
    "down": {"recovered": "RECOVERED", "partial": "PARTIAL",
             "accepted_lower": "ACCEPTED_LOWER"},
    "up": {"recovered": "GAVE_BACK", "partial": "PARTIAL",
           "accepted_lower": "KEPT"},
}


def _side_summary(payload: dict, side: str) -> dict:
    """One side of the display embed, in the shape the stocks-hub band reads."""
    tabs = (payload.get("tables") or {}).get(side) or {}
    h5 = (tabs.get("5") or {}).get("ALL") or {}
    h21 = (tabs.get(str(TERMINAL_PRIMARY)) or {}).get("ALL") or {}
    shares = h21.get("terminal_shares") or {}
    slots = _TERMINAL_SLOTS[side]

    def _share(slot: str) -> float | None:
        v = shares.get(f"{slots[slot]}_{TERMINAL_PRIMARY}D")
        return None if v is None else round(float(v), 4)

    return {
        "n_events": h21.get("n_events"),
        "episode_n_h5": h5.get("episode_n"),
        "episode_n_h21": h21.get("episode_n"),
        "n_dates_h21": h21.get("n_dates"),
        "h5_median_retrace": (h5.get("retrace_frac") or {}).get("median"),
        "h21_median_retrace": (h21.get("retrace_frac") or {}).get("median"),
        "h21_share_recovered": _share("recovered"),
        "h21_share_partial": _share("partial"),
        "h21_share_accepted_lower": _share("accepted_lower"),
        "h21_share_delisted": (None if shares.get("DELISTED_OR_HALTED") is None
                               else round(float(shares["DELISTED_OR_HALTED"]), 4)),
        "h21_share_still_lower": h21.get("share_still_lower"),
        "h21_n_open": h21.get("n_open"),
        "terminal_labels": {k: f"{v}_{TERMINAL_PRIMARY}D" for k, v in slots.items()},
        "by_family": {
            fam: {
                "episode_n": ((tabs.get(str(TERMINAL_PRIMARY)) or {}).get(fam) or {}).get("episode_n"),
                "n_dates": ((tabs.get(str(TERMINAL_PRIMARY)) or {}).get(fam) or {}).get("n_dates"),
                "h21_median_retrace": (((tabs.get(str(TERMINAL_PRIMARY)) or {}).get(fam) or {})
                                       .get("retrace_frac") or {}).get("median"),
                "h21_share_still_lower": ((tabs.get(str(TERMINAL_PRIMARY)) or {}).get(fam) or {})
                .get("share_still_lower"),
            }
            for fam in FAMILIES
            if fam in (tabs.get(str(TERMINAL_PRIMARY)) or {})
        },
    }


def summary_for_artifact(payload: dict) -> dict:
    """The frozen-table embed the display artifact carries (masterplan §9 tier 1).

    Both sides, because the band shows both: a down-only embed would make the
    surface read as a dip screen no matter what its copy said.
    """
    if not isinstance(payload, dict):
        return {}
    cov = payload.get("coverage") or {}
    return {
        "span": cov.get("panel_span"),
        "span_note": cov.get("span_note"),
        "note_en": NOTE_EN,
        "note_zh": NOTE_ZH,
        "headline_horizons": payload.get("headline_horizons") or list(HEADLINE_HORIZONS),
        "terminal_horizon_d": TERMINAL_PRIMARY,
        "down": _side_summary(payload, "down"),
        "up": _side_summary(payload, "up"),
        "null_contrast_statement": payload.get("null_contrast_statement"),
        "frozen_generated_utc": payload.get("generated_utc"),
    }
