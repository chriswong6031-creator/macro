"""engine.price_pressure.artifact — the display snapshot ``data/price_pressure/latest.json``.

Schema ``price_pressure.v1``.  Fixed shape, fail-open: any source this module
cannot read appends a note to ``gaps[]`` and drops that block — it never raises
and never leaves a block rendered under a borrowed stamp.

The authority block is five literal ``false`` values (govrev pattern).  That is
not decoration: it is the machine-readable statement that nothing downstream may
rank, size, gate, originate, or escalate off this file.

**Ordering law** (masterplan §9, review finding 11): every list here is
most-recent-first then ticker alphabetical.  Sorting the event list by |resid_z|
would BE a ranking, which the block above says this artifact cannot do — and a
reader will treat the top row as the best idea whatever the authority block says.

**Family chips**: an EDGAR-uncovered name reads "filings not tracked for this
name", never "no filing on record".

No LLM anywhere; every field is engine-computed (constitution A7).
"""
from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.price_pressure import (
    ENGINE_VERSION,
    LEDGER_HORIZONS,
    SCHEMA_LATEST,
    TERMINAL_PRIMARY,
    TOP_EVENTS_PER_SIDE,
)
from engine.price_pressure.base_rates import AUTHORITY, summary_for_artifact
from engine.price_pressure.context import FAMILY_LABELS, day_character
from engine.price_pressure.ledger import display_order

log = logging.getLogger("price_pressure.artifact")

ARTIFACT_REL: tuple[str, ...] = ("price_pressure", "latest.json")

#: How many recently-resolved episodes the "here is how these actually ended"
#: block carries (masterplan §9 item 2 — the band's proof of honesty).
RESOLVED_CAP = 8

#: Calendar days the day-character banner may lag the current day before it is
#: dropped: it describes TODAY, so a seed or lagging-store artifact gets none.
DAY_CHARACTER_MAX_AGE_DAYS = 4

#: Scope sentence every consumer must relay verbatim.  Windows, not certainties;
#: no falsifier/refutation vocabulary (operator law 2026-07-27).
SCOPE_SENTENCE = (
    "These states describe the tracked window only — context, not a pick list."
)

#: Emitted even when the frozen tables are missing, so a surface can always name
#: the receipt behind the copy it prints.
PROVENANCE: dict[str, str] = {
    "study": "reports/liquidity-shock-reversal-phase0.md",
    "study_title": "Liquidity-shock reversal classifier — phase 0 (LSR-P0)",
    "registry_key": "DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER",
    "backfill_report": "reports/price-pressure-backfill.md",
    "masterplan": "research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md",
}


def artifact_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*ARTIFACT_REL)


def _f(v: object) -> float | None:
    """float(v) for a real number only — bool/None/NaN/inf -> None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _s(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and not np.isfinite(v):
        return None
    s = str(v).strip()
    return s or None


def retrace_to_date(row: dict) -> tuple[float | None, int | None]:
    """The freshest fully-elapsed retrace fraction, and the horizon it came from."""
    best, best_h = None, None
    for h in LEDGER_HORIZONS:
        v = _f(row.get(f"retrace_{h}"))
        if v is not None:
            best, best_h = v, h
    return best, best_h


def event_view(row: dict, basket_labels: dict | None = None) -> dict:
    """One event as the surface reads it: PIT facts + family + state + progress.

    ``ret`` is the raw day move and leads the copy ("fell 9.8%"); ``resid`` /
    ``resid_z`` are what makes it a residual shock rather than a big red number.

    ``peer_ret`` is always emitted, but ``peer_basis`` decides how it may be
    SPOKEN: on a market-basis row the honest phrase is "vs the market" and the
    word "peers" must never print (masterplan §4.1, review finding 6).
    ``comparison`` carries that phrase so a template never has to choose.
    """
    frac, frac_h = retrace_to_date(row)
    basis = _s(row.get("peer_basis")) or "market"
    fam = _s(row.get("family")) or "filing-coverage-unknown"
    basket = _s(row.get("basket"))
    labels = (basket_labels or {}).get(basket) or {}
    return {
        "ticker": _s(row.get("ticker")),
        "date": _s(pd.Timestamp(row["date"]).strftime("%Y-%m-%d")) if row.get("date") is not None else None,
        "side": _s(row.get("side")),
        "era": _s(row.get("era")),
        "sector": _s(row.get("sector")),
        "family": fam,
        "family_label": FAMILY_LABELS.get(fam, fam),
        "edgar_covered": bool(row.get("edgar_covered")),
        "peer_basis": basis,
        "comparison": "sector peers" if basis == "sector" else "the market",
        "peer_ret": _f(row.get("peer_ret")),
        "ret": _f(row.get("ret")),
        "resid": _f(row.get("resid")),
        "resid_z": _f(row.get("resid_z")),
        "vol_multiple": _f(row.get("vol_multiple")),
        "price": _f(row.get("price")),
        "pos52": _f(row.get("pos52")),
        "basket": basket,
        "basket_en": labels.get("en"),
        "basket_zh": labels.get("zh"),
        "basket_ret": _f(row.get("basket_ret")),
        "basket_resid": _f(row.get("basket_resid")),
        "state": _s(row.get("state")),
        "state_pending": _s(row.get("state_pending")),
        "state_asof": _s(row.get("state_asof")),
        "days_open": (int(_f(row.get("sessions_elapsed")) or 0)
                      if _f(row.get("sessions_elapsed")) is not None else None),
        "sessions_elapsed": _f(row.get("sessions_elapsed")),
        "retrace_frac": frac,
        "retrace_frac_horizon_d": frac_h,
        "truncated": bool(row.get("truncated")),
        "episode_id": _s(row.get("episode_id")),
        "first_of_episode": bool(row.get("first_of_episode")),
    }


def _open_events(ledger: pd.DataFrame, gaps: list[str],
                 basket_labels: dict | None = None) -> tuple[list[dict], dict]:
    """Currently tracked events, both sides, recency-then-ticker (§9 item 3).

    Both sides always: an open list that showed only down-shocks would read as a
    dip screen whatever the copy said.  The per-side cap is applied to each side
    separately so one noisy side cannot crowd the other out, and the merged list
    is re-sorted back into the one legal order.
    """
    meta = {"total": {"down": 0, "up": 0}, "more": {"down": 0, "up": 0},
            "cap_per_side": TOP_EVENTS_PER_SIDE}
    if ledger.empty:
        gaps.append("open_events: ledger empty")
        return [], meta
    live = ledger[~ledger["closed"].fillna(False).astype(bool)]
    kept = []
    for side in ("down", "up"):
        rows = display_order(live[live["side"] == side])
        meta["total"][side] = int(len(rows))
        meta["more"][side] = max(0, int(len(rows)) - TOP_EVENTS_PER_SIDE)
        kept.append(rows.head(TOP_EVENTS_PER_SIDE))
    merged = pd.concat(kept, ignore_index=True) if kept else live
    if merged.empty:
        gaps.append("open_events: no events still inside their grading window")
        return [], meta
    return ([event_view(r, basket_labels) for r in display_order(merged).to_dict("records")],
            meta)


def _recently_resolved(ledger: pd.DataFrame,
                       basket_labels: dict | None = None) -> list[dict]:
    """The last few episodes that actually finished, and how they ended.

    The band leads with the RESOLVED ledger rather than today's dips (§9, review
    finding 12): "here is what usually happens" is a different artifact from
    "here is what is cheap now", and only one of them is honest to lead with.
    """
    if ledger.empty:
        return []
    term = f"terminal_state_{TERMINAL_PRIMARY}d"
    done = ledger[ledger["closed"].fillna(False).astype(bool)]
    done = done[done[term].notna()]
    if done.empty:
        return []
    out = []
    for r in display_order(done).head(RESOLVED_CAP).to_dict("records"):
        v = event_view(r, basket_labels)
        v[term] = _s(r.get(term))
        v["terminal_state"] = _s(r.get(term))
        v["terminal_horizon_d"] = TERMINAL_PRIMARY
        v["closed_at"] = _s(r.get("closed_at"))
        out.append(v)
    return out


def _day_block(ledger: pd.DataFrame, root: Path, base_rates: dict | None,
               gaps: list[str], *, allow_live_drivers: bool = True) -> dict:
    """Numeric day facts + the LIVE-only day-character banner (fail-open).

    The mechanical broad-selloff marker is ``panel_shock_count`` at or above its
    frozen backfill P90 — a number with a plain-word label, never a taxonomy
    (DNR:KILL-PARALLEL-SHOCK-CLASSIFIER).  ``market_drivers`` vocabulary is
    attached for the CURRENT day only: that organ's graded history is 17 rows,
    so it can describe today and could never label a five-year backfill.
    """
    out: dict = {"asof": None, "panel_shock_count": None, "panel_share_z2": None,
                 "spy_ret_z": None, "broad_selloff": None,
                 "broad_selloff_threshold": None, "character": None, "banner": None,
                 "down_today": 0, "up_today": 0}
    if not ledger.empty:
        day = pd.Timestamp(ledger["date"].max()).normalize()
        rows = ledger[pd.to_datetime(ledger["date"]).dt.normalize() == day]
        out["asof"] = day.strftime("%Y-%m-%d")
        out["down_today"] = int((rows["side"] == "down").sum())
        out["up_today"] = int((rows["side"] == "up").sum())
        if len(rows):
            out["panel_shock_count"] = _f(rows["panel_shock_count"].iloc[0])
            out["panel_share_z2"] = _f(rows["panel_share_z2"].iloc[0])
            out["spy_ret_z"] = _f(rows["spy_ret_z"].iloc[0])
    p90 = None
    if isinstance(base_rates, dict):
        p90 = _f(((base_rates.get("day_facts") or {}).get("panel_shock_count_p90")))
    out["broad_selloff_threshold"] = p90
    if p90 is not None and out["panel_shock_count"] is not None:
        out["broad_selloff"] = bool(out["panel_shock_count"] >= p90)
        out["broad_selloff_label"] = (
            "most of today's pressure is market-wide, not single-name"
            if out["broad_selloff"] else "today's pressure is name-by-name"
        )
    else:
        gaps.append("day: broad-selloff threshold unavailable (frozen base rates absent)")

    # The banner describes THE CURRENT DAY. An artifact whose newest session is
    # weeks old (the historical seed, or a nightly running against a lagging
    # store) must not borrow today's vocabulary for a day it is not describing.
    fresh = False
    if out["asof"]:
        age = (pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
               - pd.Timestamp(out["asof"])).days
        fresh = age <= DAY_CHARACTER_MAX_AGE_DAYS
    if fresh:
        out["character"] = day_character(root, gaps, allow_snapshot=allow_live_drivers)
    else:
        gaps.append("day_character: newest session is not the current day — "
                    "no day-character banner attached")

    # `banner` is the one plain-word sentence the band may lead with. It stays
    # NULL unless there is something live to say: a stale artifact borrowing
    # today's vocabulary is exactly the failure the freshness check above exists
    # for, and an empty banner is more honest than a confident stale one.
    if fresh and out["broad_selloff"] is True:
        out["banner"] = "Most of today's pressure is market-wide, not single-name."
    elif fresh and out["broad_selloff"] is False and out["character"]:
        out["banner"] = "Today's pressure is name-by-name, not market-wide."
    return out


def build(ledger: pd.DataFrame, *, root: Path, panel_names: int,
          panel_span: tuple[str, str], design: dict,
          base_rates: dict | None = None, sector_covered_share: float | None = None,
          basket_labels: dict | None = None,
          extra_gaps: list[str] | None = None,
          allow_live_drivers: bool = True) -> dict:
    """Assemble ``price_pressure.v1``.  Never raises; degrades into ``gaps[]``."""
    gaps: list[str] = list(extra_gaps or [])
    payload: dict = {
        "schema": SCHEMA_LATEST,
        "engine_version": ENGINE_VERSION,
        "asof": None,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "display_only": True,
        "authority": dict(AUTHORITY),
        "scope": SCOPE_SENTENCE,
        "design": design,
        "coverage": {},
        "day": {},
        "open_events": [],
        "open_events_meta": {},
        "recently_resolved": [],
        "base_rates": {},
        "exemplars": {},
        "provenance": dict(PROVENANCE),
        "gaps": gaps,
    }
    try:
        ledger = ledger if isinstance(ledger, pd.DataFrame) else pd.DataFrame()
        if not ledger.empty:
            payload["asof"] = pd.Timestamp(ledger["date"].max()).strftime("%Y-%m-%d")
        n = max(len(ledger), 1)
        era_counts = (ledger["era"].astype(str).value_counts().to_dict()
                      if not ledger.empty else {})
        basis = (ledger["peer_basis"].astype(str).value_counts().to_dict()
                 if not ledger.empty else {})
        basis_shares = {str(k): round(float(v) / n, 4) for k, v in basis.items()}
        payload["coverage"] = {
            "panel_names": int(panel_names),
            "panel_span": [panel_span[0], panel_span[1]],
            "sector_covered_share": (round(float(sector_covered_share), 4)
                                     if sector_covered_share is not None else None),
            "edgar_covered_share": (round(float(ledger["edgar_covered"].fillna(False)
                                                 .astype(bool).mean()), 4)
                                    if not ledger.empty else None),
            # Share of EVENTS residualized against sector peers rather than the
            # whole-universe mean. Distinct from sector_covered_share, which is
            # the share of the PANEL carrying a GICS label at all.
            "sector_basis_share": basis_shares.get("sector"),
            "peer_basis_shares": basis_shares,
            "basket_context_share": (round(float(ledger["basket"].notna().mean()), 4)
                                     if not ledger.empty else None),
            "ledger_rows": int(len(ledger)),
            "era_counts": {str(k): int(v) for k, v in era_counts.items()},
            "open_rows": (int((~ledger["closed"].fillna(False).astype(bool)).sum())
                          if not ledger.empty else 0),
        }
        payload["day"] = _day_block(ledger, Path(root), base_rates, gaps,
                                    allow_live_drivers=allow_live_drivers)
        events, meta = _open_events(ledger, gaps, basket_labels)
        payload["open_events"] = events
        payload["open_events_meta"] = meta
        payload["recently_resolved"] = _recently_resolved(ledger, basket_labels)
        payload["ordering"] = {
            "rule": "most-recent-first, then ticker alphabetically",
            "why": ("ordering by size of move would be a ranking, which the "
                    "authority block above says this artifact cannot do"),
        }
        if isinstance(base_rates, dict) and base_rates:
            payload["base_rates"] = summary_for_artifact(base_rates)
            payload["exemplars"] = base_rates.get("exemplars") or {}
            payload["provenance"] = {**PROVENANCE, **(base_rates.get("provenance") or {})}
            payload["survivorship"] = base_rates.get("survivorship") or []
        else:
            gaps.append("base_rates: frozen tables absent — run the backfill")
    except Exception as exc:  # noqa: BLE001 — a display artifact never kills a lane
        log.debug("price_pressure: artifact build degraded (%s)", exc)
        gaps.append(f"artifact: build failed ({type(exc).__name__})")
    return payload


def write(payload: dict, data_root: Path) -> Path:
    """Atomic write (temp-file + rename), the house builder pattern."""
    p = artifact_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str, sort_keys=False)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent,
                                     prefix=f".tmp_{p.name}_", suffix=".json",
                                     delete=False) as tf:
        tf.write(text + "\n")
        tmp = Path(tf.name)
    tmp.replace(p)
    return p
