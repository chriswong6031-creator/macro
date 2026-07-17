"""Policy Catalyst Calendar — W1b (Institutional Sector Intelligence Masterplan).

Reads data/federal_register/documents.parquet (W0b store) and produces:

1. Per-theme pipeline metrics:
   - days_to_next_comment_close  (forward-dated comment-close across ALL reg_stages —
     a comment-close date is a real dated event whether the doc is a notice, RFI,
     proposed rule or final rule; the surfaced event carries its true reg_stage)
   - days_to_next_rule_effective (final_rule rows with future comments_close_on — proxy;
     see note below on effective-date absence in W0b schema)
   - prorule_inflow_60d          (proposed_rule rows published in last 60 days)
   - rule_finalization_60d       (final_rule rows published in last 60 days)

2. Entity-List sub-signal: BIS (industry-and-security-bureau) docs whose title
   matches entity-list patterns → dated supply-chain-rewiring events for
   semis/minerals themes.

3. Empirical PRORULE→RULE latency (R1 resurrection clause): join PRORULE rows
   to their RULE counterpart via shared RIN (rin column). Reports per-theme
   median latency days as a MEASURED distribution (n, median, p25, p75 days).
   Only forward latency (RULE publication_date > PRORULE publication_date) is
   kept; PRORULE with no RULE counterpart → open / excluded from median.

Display-only. Nothing here feeds stock_score, spotlight, or regime.classify.
Forward-graded ledger: any "upcoming-event" claim seeds a row in
data/foresight/policy_calendar_ledger.jsonl (one row per theme per asof day,
deduped on (theme, asof)).

Evidence class: dated-structured (Federal Register events published at PIT).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity-list title patterns (BIS docs that signal supply-chain-rewiring)
# ---------------------------------------------------------------------------
_ENTITY_LIST_PATTERNS = [
    "entity list",
    "entity-list",
    "entities list",
    "export control",
    "export administration regulations",
    # semiconductor-specific advanced computing controls
    "advanced computing",
    "semiconductor manufacturing",
    "supercomputer",
]

# Themes that receive the BIS entity-list sub-signal
_ENTITY_LIST_THEMES = {"ai_semiconductors", "semicap_equipment", "rare_earth_critical_min",
                        "memory_storage"}

# How many days back to look for "recent" inflow (prorule_inflow_60d / rule_finalization_60d)
_INFLOW_WINDOW_DAYS = 60


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_policy_calendar(
    df: pd.DataFrame | None = None,
    today: date | None = None,
) -> dict | None:
    """Compute per-theme policy pipeline metrics and upcoming-events calendar.

    Args:
        df:    the documents DataFrame from W0b. Pass None to load from disk.
        today: reference date (defaults to UTC today). Injected in tests.

    Returns:
        dict with keys:
            asof           – ISO date string
            themes         – dict[basket_id -> per-theme dict]
            upcoming_events – list of dated-event dicts sorted by date asc
            entity_list_events – list of BIS entity-list event dicts
            latency_summary    – dict[basket_id -> {median_days, p25, p75, n, n_open}]
            note           – honesty blurb (display-only, dated-structured class)
        Returns None if the parquet store is absent or empty.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    if df is None:
        df = _load_documents()
    if df is None or df.empty:
        log.warning("policy_calendar: documents.parquet absent or empty — skipping")
        return None

    # Normalise dates — keep as strings for comparisons but also parse to date
    df = df.copy()
    df["publication_date"] = df["publication_date"].fillna("").astype(str)
    df["comments_close_on"] = df["comments_close_on"].fillna("").astype(str)
    df["reg_stage"] = df["reg_stage"].fillna("").astype(str)
    df["rin"] = df["rin"].fillna("").astype(str)
    df["title"] = df["title"].fillna("").astype(str)
    df["basket_id"] = df["basket_id"].fillna("").astype(str)
    df["agency_slug"] = df["agency_slug"].fillna("").astype(str)

    cutoff_60d = _date_minus_days(today, _INFLOW_WINDOW_DAYS).isoformat()

    # ------------------------------------------------------------------
    # Per-theme pipeline metrics
    # ------------------------------------------------------------------
    all_baskets = sorted(df[df["basket_id"] != ""]["basket_id"].unique())
    themes: dict[str, dict] = {}

    for basket in all_baskets:
        bdf = df[df["basket_id"] == basket]

        # Forward-dated rows: comments_close_on >= today (strict forward, not past)
        fwd_mask = (bdf["comments_close_on"] != "") & (bdf["comments_close_on"] >= today_str)
        fwd_df = bdf[fwd_mask].copy()

        # Days to next comment close (across any reg_stage)
        days_to_next_comment_close: int | None = None
        next_comment_close_date: str | None = None
        next_comment_close_title: str | None = None
        if not fwd_df.empty:
            fwd_df_sorted = fwd_df.sort_values("comments_close_on")
            earliest = fwd_df_sorted.iloc[0]
            next_comment_close_date = earliest["comments_close_on"]
            days_to_next_comment_close = _days_from_today(today, next_comment_close_date)
            next_comment_close_title = str(earliest["title"])[:120]

        # Days to next "rule effective" — W0b does not store a separate effective date.
        # We use final_rule rows that have a future comments_close_on as the nearest
        # forward-dated final rule signal (honest proxy; labeled as such in the output).
        days_to_next_rule_effective: int | None = None
        next_rule_effective_date: str | None = None
        next_rule_effective_title: str | None = None
        fr_fwd = fwd_df[fwd_df["reg_stage"] == "final_rule"].copy()
        if not fr_fwd.empty:
            fr_fwd_sorted = fr_fwd.sort_values("comments_close_on")
            earliest_fr = fr_fwd_sorted.iloc[0]
            next_rule_effective_date = earliest_fr["comments_close_on"]
            days_to_next_rule_effective = _days_from_today(today, next_rule_effective_date)
            next_rule_effective_title = str(earliest_fr["title"])[:120]

        # PRORULE inflow 60d
        pr_inflow = bdf[
            (bdf["reg_stage"] == "proposed_rule") & (bdf["publication_date"] >= cutoff_60d)
        ]
        prorule_inflow_60d = len(pr_inflow)

        # RULE finalization 60d
        fr_recent = bdf[
            (bdf["reg_stage"] == "final_rule") & (bdf["publication_date"] >= cutoff_60d)
        ]
        rule_finalization_60d = len(fr_recent)

        themes[basket] = {
            "basket_id": basket,
            "days_to_next_comment_close": days_to_next_comment_close,
            "next_comment_close_date": next_comment_close_date,
            "next_comment_close_title": next_comment_close_title,
            "days_to_next_rule_effective": days_to_next_rule_effective,
            "next_rule_effective_date": next_rule_effective_date,
            "next_rule_effective_title": next_rule_effective_title,
            "prorule_inflow_60d": prorule_inflow_60d,
            "rule_finalization_60d": rule_finalization_60d,
        }

    # ------------------------------------------------------------------
    # Upcoming events strip (all forward-dated rows, sorted by date)
    # ------------------------------------------------------------------
    fwd_all = df[(df["comments_close_on"] != "") & (df["comments_close_on"] >= today_str)].copy()
    upcoming_events: list[dict] = []
    for _, row in fwd_all.sort_values("comments_close_on").iterrows():
        upcoming_events.append({
            "date": row["comments_close_on"],
            "days_away": _days_from_today(today, row["comments_close_on"]),
            "basket_id": row["basket_id"],
            "reg_stage": row["reg_stage"],
            "title": str(row["title"])[:120],
            "event_type": "comment_close",
        })

    # ------------------------------------------------------------------
    # Entity-List sub-signal (BIS supply-chain-rewiring events)
    # ------------------------------------------------------------------
    entity_list_events = _compute_entity_list_events(df, today_str, cutoff_60d)

    # ------------------------------------------------------------------
    # Empirical PRORULE→RULE latency (R1 resurrection clause)
    # ------------------------------------------------------------------
    latency_summary = _compute_latency(df)

    # ------------------------------------------------------------------
    # Forward-graded ledger: seed a row per (theme, asof) for upcoming events
    # ------------------------------------------------------------------
    try:
        _append_ledger(themes, today_str)
    except Exception as e:  # noqa: BLE001
        log.warning("policy_calendar: ledger append failed (non-fatal): %s", e)

    return {
        "asof": today_str,
        "themes": themes,
        "upcoming_events": upcoming_events,
        "entity_list_events": entity_list_events,
        "latency_summary": latency_summary,
        "note": (
            "display-only; evidence class = dated-structured (Federal Register, PIT-stamped). "
            "days_to_next_rule_effective uses comments_close_on of final_rule rows as a proxy — "
            "W0b does not store a separate effective date field. "
            "PRORULE→RULE latency is empirical via RIN join; open PRORULE rows excluded from median."
        ),
    }


def format_policy_reg_chip(policy_row: dict | None, theme_key: str) -> dict | None:
    """Format a per-theme policy pipeline chip for cascade rationale injection.

    Mirrors engine/fda_scarcity.format_theme_feed_chip pattern.
    Returns None when no actionable signal is present (no forward dates, no recent inflow).
    """
    if policy_row is None:
        return None

    dtcc = policy_row.get("days_to_next_comment_close")
    dtrf = policy_row.get("days_to_next_rule_effective")
    pr60 = policy_row.get("prorule_inflow_60d") or 0
    fr60 = policy_row.get("rule_finalization_60d") or 0

    parts: list[str] = []
    if dtcc is not None:
        parts.append(f"comment close in {dtcc}d ({policy_row.get('next_comment_close_date','')})")
    if dtrf is not None and dtrf != dtcc:
        parts.append(f"rule effective in {dtrf}d")
    if pr60:
        parts.append(f"{pr60} proposed rule(s) last 60d")
    if fr60:
        parts.append(f"{fr60} final rule(s) last 60d")

    if not parts:
        return None

    return {
        "theme": theme_key,
        "summary": "; ".join(parts),
        "days_to_comment_close": dtcc,
        "days_to_rule_effective": dtrf,
        "prorule_inflow_60d": pr60,
        "rule_finalization_60d": fr60,
        "next_comment_close_date": policy_row.get("next_comment_close_date"),
        "next_comment_close_title": policy_row.get("next_comment_close_title"),
        "evidence_class": "dated-structured",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_documents() -> pd.DataFrame | None:
    """Load documents.parquet from the W0b store."""
    try:
        from lib import config  # type: ignore[import]
        p = config.data_dir() / "federal_register" / "documents.parquet"
    except Exception:  # noqa: BLE001
        p = Path(__file__).resolve().parent.parent / "data" / "federal_register" / "documents.parquet"
    if not p.exists():
        log.warning("policy_calendar: %s not found", p)
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("policy_calendar: failed to load %s: %s", p, e)
        return None


def _days_from_today(today: date, date_str: str) -> int | None:
    """Return (date_str - today).days. Returns None on parse failure."""
    if not date_str:
        return None
    try:
        d = date.fromisoformat(date_str)
        return (d - today).days
    except Exception:  # noqa: BLE001
        return None


def _date_minus_days(today: date, n: int) -> date:
    from datetime import timedelta
    return today - timedelta(days=n)


def _compute_entity_list_events(
    df: pd.DataFrame,
    today_str: str,
    cutoff_60d: str,
) -> list[dict]:
    """Extract BIS entity-list events: both upcoming and recent (60d)."""
    bis = df[df["agency_slug"] == "industry-and-security-bureau"].copy()
    if bis.empty:
        return []

    pat = "|".join(_ENTITY_LIST_PATTERNS)
    mask = bis["title"].str.contains(pat, case=False, na=False)
    el_docs = bis[mask].copy()
    if el_docs.empty:
        return []

    events: list[dict] = []
    for _, row in el_docs.iterrows():
        pub = row.get("publication_date", "")
        cco = row.get("comments_close_on", "") or ""
        # Include: upcoming (future comment close) OR recent (published last 60d)
        is_upcoming = cco and cco >= today_str
        is_recent = pub and pub >= cutoff_60d
        if not (is_upcoming or is_recent):
            continue
        events.append({
            "date": cco if is_upcoming else pub,
            "publication_date": pub,
            "comments_close_on": cco if cco else None,
            "reg_stage": row.get("reg_stage", ""),
            "title": str(row.get("title", ""))[:150],
            "agency": "industry-and-security-bureau",
            "affected_themes": sorted(_ENTITY_LIST_THEMES),
            "event_type": "entity_list",
            "is_upcoming": bool(is_upcoming),
            "is_recent_60d": bool(is_recent),
        })

    # Sort: upcoming first (by date asc), then recent
    events.sort(key=lambda x: (0 if x["is_upcoming"] else 1, x["date"]))
    return events


def _compute_latency(df: pd.DataFrame) -> dict[str, dict]:
    """Empirical PRORULE→RULE latency via RIN join.

    Only PRORULE rows with a non-empty RIN that also appear in a RULE row
    with a LATER publication_date are used. PRORULE rows with no RULE match
    are counted as 'open' and excluded from the median computation.

    Returns dict[basket_id -> {median_days, p25, p75, n, n_open, note}].
    """
    proposed = df[
        (df["reg_stage"] == "proposed_rule") & (df["rin"] != "") & df["rin"].notna()
    ][["rin", "publication_date", "basket_id"]].copy()
    final = df[
        (df["reg_stage"] == "final_rule") & (df["rin"] != "") & df["rin"].notna()
    ][["rin", "publication_date"]].copy()

    if proposed.empty or final.empty:
        return {}

    proposed["pub_date_pr"] = pd.to_datetime(proposed["publication_date"], errors="coerce")
    final["pub_date_fr"] = pd.to_datetime(final["publication_date"], errors="coerce")
    final = final.rename(columns={"rin": "rin_fr"})

    # Join on RIN (one PRORULE may match multiple RULE rows — take earliest RULE after PRORULE)
    joined = proposed.merge(final, left_on="rin", right_on="rin_fr", how="left")
    joined = joined[joined["pub_date_fr"] > joined["pub_date_pr"]]
    joined["latency_days"] = (joined["pub_date_fr"] - joined["pub_date_pr"]).dt.days

    # Deduplicate: one PRORULE rin/basket_id → keep earliest RULE match
    joined = joined.sort_values("pub_date_fr").groupby(["rin", "basket_id"], as_index=False).first()

    # Count open (PRORULE with no RULE yet)
    matched_rins = set(joined["rin"].unique())
    open_counts: dict[str, int] = {}
    for _, row in proposed.iterrows():
        if row["rin"] not in matched_rins:
            b = row["basket_id"]
            open_counts[b] = open_counts.get(b, 0) + 1

    result: dict[str, dict] = {}
    for basket, grp in joined.groupby("basket_id"):
        lats = grp["latency_days"].dropna()
        if len(lats) == 0:
            continue
        result[str(basket)] = {
            "median_days": int(lats.median()),
            "p25_days": int(lats.quantile(0.25)),
            "p75_days": int(lats.quantile(0.75)),
            "n": int(len(lats)),
            "n_open": open_counts.get(str(basket), 0),
            "note": "empirical PRORULE→RULE latency via RIN join; open rows excluded from median",
        }

    # Add baskets that have only open PROPOSEDs (no RULE match at all)
    for basket, n_open in open_counts.items():
        if basket not in result:
            result[basket] = {
                "median_days": None,
                "p25_days": None,
                "p75_days": None,
                "n": 0,
                "n_open": n_open,
                "note": "no matched RULE yet; all PRORULE rows open",
            }

    return result


def _append_ledger(themes: dict, asof: str) -> None:
    """Seed a forward-graded ledger row per (theme, asof) for any upcoming-event claim.

    Deduped on (theme, asof) — idempotent across same-day re-runs.
    Only themes with days_to_next_comment_close != None are considered a claim.

    Gate: COLLECT_LANE=nightly (US_LANE legacy alias) — nightly is the sole
    advancer of forward ledgers; this appender was the one missed by the
    #2598 gating sweep.
    """
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    if lane != "nightly":
        log.debug("policy_calendar._append_ledger: skipped (COLLECT_LANE != nightly)")
        return
    try:
        from lib import config  # type: ignore[import]
        d = config.data_dir() / "foresight"
    except Exception:  # noqa: BLE001
        d = Path(__file__).resolve().parent.parent / "data" / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "policy_calendar_ledger.jsonl"

    # Load existing (theme, asof) pairs for dedup
    seen: set[tuple] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                if e.get("theme") and e.get("asof"):
                    seen.add((e["theme"], e["asof"]))
            except Exception:  # noqa: BLE001
                continue

    ts = datetime.now(timezone.utc).isoformat()
    new_rows: list[str] = []
    for basket, row in themes.items():
        if row.get("days_to_next_comment_close") is None:
            continue  # no upcoming claim → no ledger row
        key = (basket, asof)
        if key in seen:
            continue
        entry = {
            "theme": basket,
            "asof": asof,
            "logged_utc": ts,
            "days_to_comment_close": row["days_to_next_comment_close"],
            "next_comment_close_date": row["next_comment_close_date"],
            "prorule_inflow_60d": row["prorule_inflow_60d"],
            "rule_finalization_60d": row["rule_finalization_60d"],
            "evidence_class": "dated-structured",
        }
        new_rows.append(json.dumps(entry))

    if new_rows:
        with p.open("a") as fh:
            fh.write("\n".join(new_rows) + "\n")
        log.info("policy_calendar: %d new ledger rows appended", len(new_rows))
