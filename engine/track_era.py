"""Era boundary + fail-closed publish guard for the US track record ledger.

WHY THIS MODULE EXISTS
======================
``site/factordata/us_track_ledger.json`` is a PUBLIC record: the Track-record dialog's
verdict cards, the hero win-rate / average-trade / interval on ``us_track_record.html``,
and the dashboard Track-record chip all read its ``summary``. Until 2026-08-07 those
numbers were not well-defined night to night.

The incumbent exit leg (``scripts/grade_us_board._ob_mask``) reads
``engine.confluence_tiers._tf_bars(c, 3)`` — ``daily.resample("3B")`` — whose bin edges
anchored to the SERIES' FIRST TIMESTAMP, and ``emit_ledger`` calls it on the full rolling
close cache. The smallcap/midcap ``data/*/_closes_cache.parquet`` stores are a rolling
window, so as their start rolled off, every 3D bucket in the WHOLE history re-phased:
overbought flags from weeks ago flipped and the realised P&L of episodes that closed long
ago moved, on zero new information about those episodes. Measured in
``reports/ob_mask_track_record_blast_radius.md``: dropping 4 leading sessions with the end
date and every retained price held IDENTICAL moved 126 of 359 already-matured episodes
(35.1%), max 28.9 pp.

PR #4732 migrated ``_tf_bars`` to an absolute session anchor in place (era
``abs-session-2026-08-06``, ratified in
``research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md``). Because
``_ob_mask`` imports ``_tf_bars`` directly, the repair reached this consumer for free —
and that is exactly the hazard the era stamp exists to close: the fix changes every
published historical number here without appearing in any diff a reader of this artifact
would think to check.

Ruled by the Fable main loop on 2026-08-07
(``research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`` §0.1): the ``abs-session-2026-08-06``
era EXTENDS to this artifact. Refusing the break would have preserved the instability, not
the numbers.

WHAT THIS MODULE OWNS
=====================
1. ``US_TRACK_ANCHOR_ERA`` — the era string the ACTIVE grading construction writes.
2. ``US_TRACK_PRE_ERA`` — the pre-era headline, frozen. Nothing is deleted by an era
   break; the old numbers stay readable beside the new ones on every consuming surface.
3. ``check_publish`` — the permanent fail-closed guard. A write of this artifact whose
   headline numbers MOVE without carrying the active era stamp is refused, not published.

WHY THE PRE-ERA BLOCK IS A CONSTANT, NOT A READ OF THE LIVE FILE
---------------------------------------------------------------
The obvious implementation — "on write, copy the outgoing file's summary into
``meta.pre_era``" — is self-erasing: the second recompute would preserve the FIRST
recompute's numbers and the genuine pre-era headline would be gone after one night. A
frozen constant, cross-checked in tests against the committed byte snapshot at
``reports/us_track_ledger_pre_era_2026-07-31.json``, is stable under any number of
recomputes.
"""
from __future__ import annotations

import math as _math
from typing import Any

#: The era the ACTIVE grading construction produces. Bump this string — and add a new
#: pre-era block — whenever a change re-phases the buckets under already-graded rows.
#: A recompute that moves the headline while carrying a stale or absent stamp is refused
#: by ``check_publish`` below.
US_TRACK_ANCHOR_ERA = "abs-session-2026-08-06"

#: Label for the construction that produced everything published BEFORE the break: 3B
#: buckets anchored to the price series' first timestamp.
US_TRACK_PRE_ERA_NAME = "series-first-legacy"

#: Byte snapshot of the last artifact published under the pre-era construction. Committed
#: so the old record survives in full (rows included), not just its headline.
US_TRACK_PRE_ERA_SNAPSHOT = "reports/us_track_ledger_pre_era_2026-07-31.json"

#: The pre-era headline, frozen verbatim from that snapshot (as_of 2026-07-31). Read the
#: file, not this dict, if you need the rows; this is what ships inside every subsequent
#: artifact so a reader always has the old numbers next to the new ones.
US_TRACK_PRE_ERA_SUMMARY: dict[str, Any] = {
    "metric": "pnl",
    "horizon": 10,
    "n_matured": 173,
    "n_inflight": 281,
    "n_skipped_no_price": 0,
    "n_board_days": 8,
    "win_pct": 63.6,
    "expectancy_pct": 1.19,
    "median_pct": 1.74,
    "avg_win_pct": 4.54,
    "avg_loss_pct": -4.67,
    "profit_factor": 1.7,
    "ci_lo_pct": 55.6,
    "ci_hi_pct": 69.8,
    "exp_lo_pct": 0.21,
    "exp_hi_pct": 1.98,
    "median_hold": 9,
    "capture": 0.71,
    "mfe_median_pct": 3.44,
    "mae_median_pct": -2.14,
    "mae_p10_pct": -8.81,
}

#: The date the record was re-measured under the new construction — what the surfaces
#: show the reader as "measurement updated".
US_TRACK_ERA_FROM = "2026-08-07"

#: The as_of of the last pre-era publication.
US_TRACK_PRE_ERA_AS_OF = "2026-07-31"


def us_pre_era_block() -> dict[str, Any]:
    """The ``meta.pre_era`` block stamped onto every US track ledger write.

    Data only — the reader-facing sentences live in the templates
    (``templates/us_track_record.html.j2``, ``templates/_track_record_dlg.html.j2``), which
    is where the bilingual copy guards can see them.
    """
    return {
        "anchor_era": US_TRACK_PRE_ERA_NAME,
        "as_of": US_TRACK_PRE_ERA_AS_OF,
        "snapshot": US_TRACK_PRE_ERA_SNAPSHOT,
        "summary": dict(US_TRACK_PRE_ERA_SUMMARY),
    }


def us_era_meta() -> dict[str, Any]:
    """``extra_meta`` fragment for ``engine.track_ledger.build_shell``.

    ``anchor_era`` names the construction that produced the numbers in front of the
    reader; ``era_from`` is the date it took effect; ``pre_era`` carries what it replaced.
    """
    return {
        "anchor_era": US_TRACK_ANCHOR_ERA,
        "era_from": US_TRACK_ERA_FROM,
        "pre_era": us_pre_era_block(),
    }


# --------------------------------------------------------------------------- #
# The guard
# --------------------------------------------------------------------------- #

#: Artifact this guard fences. Scoped by basename because the shared writer
#: (``engine.track_ledger.atomic_write``) serves four markets and only this one carries a
#: ruled era boundary.
GUARDED_BASENAME = "us_track_ledger.json"

#: The PUBLISHED headline — the fields a reader actually sees on the chip, the dialog
#: cards, and the page hero. Counts (``n_matured``/``n_inflight``/``n_board_days``) are
#: deliberately excluded: they move every night by ordinary accrual, which is not the
#: silent re-bake this guard exists to catch.
HEADLINE_KEYS: tuple[str, ...] = (
    "win_pct", "expectancy_pct", "median_pct", "profit_factor",
    "avg_win_pct", "avg_loss_pct", "capture",
    "ci_lo_pct", "ci_hi_pct", "exp_lo_pct", "exp_hi_pct",
)

#: Per-key movement tolerance. The percent-valued fields ship rounded to one decimal, so
#: 0.05 is one rounding step — anything larger is a real move. ``profit_factor`` and
#: ``capture`` are ratios on a ~0–2 scale where the same absolute slack would be far too
#: loose, so they get their own floor.
_TOL_DEFAULT = 0.05
_TOL_BY_KEY = {"profit_factor": 0.01, "capture": 0.01}


def _num(v: Any) -> float | None:
    """Coerce a published summary value to a comparable float, or None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (_math.isnan(f) or _math.isinf(f)) else f


def headline_moves(prev: dict | None, new: dict | None) -> list[str]:
    """Headline keys whose value moved beyond tolerance between two summaries.

    A key that gains or loses a value (None <-> number) counts as moved — an appearing or
    vanishing published number is exactly as visible to a reader as a changed one. Two
    Nones are not a move (the naive ``!=`` mistake this repo has made before).
    """
    prev = prev if isinstance(prev, dict) else {}
    new = new if isinstance(new, dict) else {}
    moved: list[str] = []
    for k in HEADLINE_KEYS:
        a, b = _num(prev.get(k)), _num(new.get(k))
        if a is None and b is None:
            continue
        if a is None or b is None:
            moved.append(k)
            continue
        if abs(b - a) > _TOL_BY_KEY.get(k, _TOL_DEFAULT):
            moved.append(k)
    return moved


def check_publish(path: Any, doc: dict, prev_doc: dict | None) -> tuple[bool, str]:
    """Fail-closed publish check for the US track ledger. Returns ``(ok, message)``.

    Ruled 2026-08-07 (``research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md``): a write whose
    headline numbers move beyond a small tolerance WITHOUT carrying the active
    construction's ``meta.anchor_era`` must refuse to publish rather than re-bake the
    public record silently. Refusal keeps the previously published file in place, which is
    the safe state — a stale number a reader can still reconcile beats a fresh one nobody
    can.

    A missing or unreadable predecessor is NOT a refusal: a first write has nothing to move
    away from. Movement is measured against what is actually on disk.

    Callers get ``ok=False`` and are expected to leave the file alone. The annotation is
    printed here, at line start, with a bare ``print`` — a logger would prefix the line and
    GitHub would silently drop the annotation (house law; ``tests/
    test_gh_annotation_line_start.py``).
    """
    if str(getattr(path, "name", "") or str(path).rsplit("/", 1)[-1]) != GUARDED_BASENAME:
        return True, ""

    era = ((doc or {}).get("meta") or {}).get("anchor_era")
    new_sum = (doc or {}).get("summary")
    prev_sum = (prev_doc or {}).get("summary") if isinstance(prev_doc, dict) else None

    if prev_doc is None:
        # No predecessor on disk — nothing has moved. Still say so when the stamp is
        # absent, because an unstamped artifact is the state the ruling closed.
        if era != US_TRACK_ANCHOR_ERA:
            print(f"::warning title=track-ledger-era::{GUARDED_BASENAME} written with "
                  f"anchor_era={era!r}, expected {US_TRACK_ANCHOR_ERA!r}. No previous file "
                  f"to compare against, so the headline cannot have moved — published.",
                  flush=True)
        return True, ""

    moved = headline_moves(prev_sum, new_sum)
    if not moved:
        if era != US_TRACK_ANCHOR_ERA:
            print(f"::warning title=track-ledger-era::{GUARDED_BASENAME} written with "
                  f"anchor_era={era!r}, expected {US_TRACK_ANCHOR_ERA!r}. The headline did "
                  f"not move, so this is published — but the stamp should name the "
                  f"construction that produced it.", flush=True)
        return True, ""

    if era == US_TRACK_ANCHOR_ERA:
        return True, ""

    detail = ", ".join(
        f"{k} {(prev_sum or {}).get(k)}→{(new_sum or {}).get(k)}" for k in moved[:6]
    )
    msg = (f"REFUSED to publish {GUARDED_BASENAME}: the headline moved ({detail}) but "
           f"meta.anchor_era is {era!r}, not the active {US_TRACK_ANCHOR_ERA!r}. Moving a "
           f"published record without naming the construction that moved it is the silent "
           f"re-bake ruled out on 2026-08-07 "
           f"(research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md). The previously published "
           f"file is left in place. Stamp the era via engine.track_era.us_era_meta(), or "
           f"bump US_TRACK_ANCHOR_ERA and add a pre_era block if the construction really "
           f"changed.")
    print(f"::error title=track-ledger-era::{msg}", flush=True)
    return False, msg
