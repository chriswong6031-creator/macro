"""Calibration Hub — the unified observability surface for the self-improving AI suite (P2).

The suite produces a lot of self-improvement telemetry but never surfaced it together. This
consolidates it into ONE read:

  * every Phase-C desk's track record (hit-rate, by_regime, by_conviction) — are the
    falsifiable-thesis loops live, and are they right?
  * the Trial Ledger (engine.trial_ledger) — how many trials each calibrator HONESTLY
    counted, and the declared multiple-testing budgets (the P3 keystone made visible).
  * a per-desk CALIBRATION / health read: is conviction monotone (do 'high' calls hit more
    than 'low'?), and is the desk cold (tiny sample), weak (<50%), or inverted?

Display-only: reads the scorers' outputs, never a score / size / allocation. Writes
data/calibration/summary.json (+ a self-contained site/calibration.html). Degrade-never-raise.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from lib import config
from lib.pages import write_page
from engine.trial_ledger import TrialLedger

log = logging.getLogger(__name__)

SCHEMA = "calibration_hub.v1"

# --------------------------------------------------------------------------- #
# PROMOTION GATE — pre-registered constants.
#
# Moving a desk from "cold" to "calibrated" is a PROMOTION to authority: it is the label
# that says the loop's track record means something. Per the house epistemics it is held to
# the promotion standard (pre-registered bars, nulls printed, not implied) while display-tier
# accrual is untouched — a desk that fails every bar below keeps logging and grading theses
# exactly as before.
#
# The bar is the desk's OWN empirical null, not 0.5. `hit` is a NOT-FALSIFIED metric: a
# thesis "hits" when its falsifier did not trigger, which for a typical rel_return falsifier
# happens ~80-85% of the time by chance alone (engine/desk_placebo.py measures it per desk).
# Calling 0.5 the "coin-flip" null for that endpoint manufactures an edge out of leniency —
# the error condition C1 of research/macro_tx/L6_PHASE0_REPORT.md attaches to its own
# floored favorable-excursion endpoint (~88% base rate).
# --------------------------------------------------------------------------- #
_MIN_SAMPLE = 10                 # below this a desk is "cold" — track record not yet meaningful
_MIN_INDEPENDENT_BLOCKS = 10     # non-overlapping forward windows required to promote
_PROMOTE_ALPHA = 0.05            # one-sided, Holm-adjusted across the desks tested
_PROMOTE_MARGIN = 0.05           # observed must clear its own null by >= 5pp, not just "significantly"
_MIN_CONVICTION_BUCKET = 5       # a conviction tier is evidence only at this many calls

# NOT the null, and never the promotion bar. A not-falsified rate below one-half is so far
# under any plausible null for this endpoint that it demotes a desk even when the placebo
# sweep is unavailable. Used for demotion only — the asymmetry is deliberate.
_DEMOTION_FLOOR = 0.5

# SA-R10's pre-registered cluster-unit floor for the standout board tracks (see the note in
# _standout_track_row — that endpoint's null really is ~one-half, but a floor still gates it).
_STANDOUT_FLOOR = 25

# The Phase-C falsifiable-thesis desks (label, track_record.json path).
#
# This list is the governed set: a desk absent from it gets no null, no verdict, and no row —
# it accrues a track record that nobody grades. It therefore mirrors engine.desk_scorer's
# POOL_DESKS (the desks the system already treats as first-class) plus master_brain, whose
# durability loop is graded by engine/master_brain_scorer.py. thematic_desk in particular was
# invisible here while running 57% not-falsified against 43% directional — the
# lenient-endpoint-vs-wrong-direction divergence this gate exists to catch.
_DESKS = (
    ("AI Desk", "ai_desk"),
    ("Policy Intent", "policy_intent"),
    ("Alt-Data Brain", "altdata"),
    ("Divergence Radar", "radar"),
    ("Stock Desk", "stock_desk"),
    ("Demand Chain", "demand_chain"),
    ("Thematic Desk", "thematic_desk"),
    ("Narrative Brain", "narrative_brain"),
    ("Master Brain", "master_brain"),
)

# SA-W5: Standout Board tracks — read-only entries surfacing board accountability
# alongside the Phase-C desk loops.  These are buy-board track records, not
# falsifiable-thesis loops, so they use a separate reader that maps the
# us_board_track.json / cn_standout_track schema.
#
# CN note (F2): the real CN ledger is data/china_standout_track/board.parquet
# (committed, 38KB).  data/cn_standout_track.json does not exist — nothing produces
# it.  We store the parquet path and let _standout_track_row detect the .parquet
# extension and read it directly (pandas, never-raise).
_STANDOUT_TRACKS = (
    ("Prophet US — board track", "site/factordata/us_board_track.json", "US"),
    ("Prophet China — board track", "data/china_standout_track/board.parquet", "CN"),
)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None


def _conviction_read(by_conv: dict) -> dict:
    """Was conviction ordering actually TESTED, and what did the test say?

    The old read returned None whenever fewer than two tiers had a sample — and every desk
    to date logs a single tier — so the check could never fail, yet the health note asserted
    "conviction ordering holds" regardless. A property that was never evaluated is reported
    as untested, with the reason, and never as a property that holds.

    A tier counts as evidence only at `_MIN_CONVICTION_BUCKET` calls: three medium-conviction
    calls at 100% is not evidence that conviction orders anything.

    Returns {"verdict": True | False | None, "note": str, "tiers": {tier: n}}.
    """
    tiers = {c: int(((by_conv.get(c) or {}).get("n") or 0)) for c in ("high", "medium", "low")}
    eligible = [(c, (by_conv.get(c) or {}).get("hit_rate"), tiers[c])
                for c in ("high", "medium", "low")
                if tiers[c] >= _MIN_CONVICTION_BUCKET and (by_conv.get(c) or {}).get("hit_rate") is not None]
    total = sum(tiers.values())
    if len(eligible) < 2:
        populated = [f"{c} {n}" for c, n in tiers.items() if n]
        if len(populated) <= 1:
            where = f"all {total} calls are single-tier ({populated[0]})" if populated else "no calls tiered"
        else:
            verb = "has" if len(eligible) == 1 else "have"
            where = (f"only {len(eligible)} of 3 tiers {verb} {_MIN_CONVICTION_BUCKET}+ calls "
                     f"({', '.join(populated)})")
        return {"verdict": None, "tiers": tiers,
                "note": f"conviction ordering untested — {where}"}
    ordered = " ≥ ".join(f"{c} {_pct(r)}" for c, r, _ in eligible)
    holds = all(a[1] >= b[1] for a, b in zip(eligible, eligible[1:]))
    counts = ", ".join(f"{c} n={n}" for c, _, n in eligible)
    if holds:
        return {"verdict": True, "tiers": tiers,
                "note": f"conviction ordering holds ({ordered}; {counts})"}
    return {"verdict": False, "tiers": tiers,
            "note": f"conviction inverted — higher-conviction calls hit no more than lower "
                    f"({ordered.replace(' ≥ ', ' vs ')}; {counts})"}


def _conviction_monotone(by_conv: dict) -> bool | None:
    """Back-compatible accessor for the conviction verdict (True / False / not tested)."""
    return _conviction_read(by_conv)["verdict"]


def _placebo_phrase(null: dict) -> str:
    """Plain-words statement of the measured null, or of why there isn't one."""
    if null.get("null_hit_rate") is None:
        return f"no placebo baseline ({null.get('reason') or 'unavailable'})"
    kinds = null.get("by_kind") or {}
    # The endpoint kinds have very different nulls (rel-return is lenient, level is harsh), so
    # the mix is load-bearing whenever there is more than one of them.
    mix = ("" if len(kinds) < 2 else ", ".join(
        f"{v['n']} {k.replace('_', '-')}" for k, v in sorted(
            kinds.items(), key=lambda kv: -kv[1]["n"])) + "; ")
    n, n_dec = null.get("n") or 0, null.get("n_decided") or 0
    scope = f"{n} graded" if n >= n_dec else f"the {n} of {n_dec} graded we could price"
    blocks = null.get("independent_blocks") or 0
    return (f"{_pct(null['null_hit_rate'])} of these same falsifiers go untriggered by chance "
            f"({mix}{scope}, {blocks} independent window{'s' if blocks != 1 else ''})")


def _desk_health(track: dict, null: dict | None = None, p_hit_adj: float | None = None,
                 p_dir_adj: float | None = None, family_n: int | None = None) -> tuple[str, str]:
    """Classify a desk from its track record → (health, note).

    States, strongest demotion first:
      cold       — too few graded outcomes to say anything.
      inverted   — the desk points the wrong way: directional accuracy below ITS OWN null,
                   or conviction ordering decisively inverted.
      weak       — not-falsified rate below its own null (or below the demotion floor when
                   no placebo could be measured).
      unproven   — sample is there and nothing is wrong, but the promotion evidence is not:
                   the null was not cleared, or the graded windows are not independent enough.
      calibrated — cleared every pre-registered bar above.

    Demotion and promotion carry deliberately asymmetric burdens: a point estimate on the
    wrong side of the null demotes, while promotion needs the margin, the adjusted p-value,
    and the independence floor together.

    `family_n` is the size of the Holm family `p_hit_adj` was actually corrected against —
    the desks eligible for the promotion test, NOT the desks tracked. Quoting len(_DESKS)
    there claimed more multiplicity correction than was applied (6 tracked, 1 tested), which
    overstates rigor in exactly the direction the gate is supposed to police.
    """
    null = null or {}
    overall = track.get("overall") or {}
    n = overall.get("n") or 0
    hr = overall.get("hit_rate")
    dir_acc = overall.get("dir_accuracy")
    conv = _conviction_read(track.get("by_conviction") or {})
    if n < _MIN_SAMPLE:
        return "cold", f"only {n} scored — check-by windows still maturing; treat as provisional"

    # `available` gates PROMOTION (it means observed outcomes pair exactly to their nulls).
    # A partial null still demotes — asymmetric burden, and a partial measurement is real
    # information about the endpoint.
    has_null = bool(null.get("available"))
    null_hr, null_dir = null.get("null_hit_rate"), null.get("null_dir_rate")
    # dir_accuracy IS a directional metric, so one-half is a defensible fallback null for it
    # — the thing that is emphatically NOT true of the not-falsified rate.
    dir_bar = null_dir if null_dir is not None else _DEMOTION_FLOOR
    dir_bar_src = "by chance" if null_dir is not None else "a coin flip"

    # Every note carries the observed reading and the null it is being judged against.
    head = f"not-falsified {_pct(hr)} vs {_placebo_phrase(null)}"
    if dir_acc is not None:
        head += f"; direction called right {_pct(dir_acc)} vs {_pct(dir_bar)} {dir_bar_src}"

    if dir_acc is not None and dir_acc < dir_bar:
        return "inverted", (f"{head} — the leans point the WRONG WAY; a lenient not-falsified "
                            f"rate cannot rescue that. {conv['note']}.")
    if conv["verdict"] is False:
        return "inverted", f"{conv['note']}. {head}."
    if null_hr is not None and hr is not None and hr < null_hr:
        return "weak", f"{head} — below its own null. {conv['note']}."
    if null_hr is None and hr is not None and hr < _DEMOTION_FLOOR:
        return "weak", (f"{head} — under one-half, which no honest null for a not-falsified "
                        f"endpoint sits below. {conv['note']}.")

    # --- promotion: every bar must clear ---
    # Direction carries its own evidence, reported but never promoted on: the desk's own
    # falsifiers define `hit`, so that is the endpoint the promotion test judges.
    dir_tail = ""
    if p_dir_adj is not None and p_dir_adj < _PROMOTE_ALPHA and dir_acc is not None \
            and null_dir is not None and dir_acc > null_dir:
        # Descriptive only, and it inherits the same overlap problem — say so, rather than
        # replacing one overclaimed metric with another.
        caveat = ("" if (null.get("independent_blocks") or 0) >= _MIN_INDEPENDENT_BLOCKS
                  else ", though on windows this overlapping that is a lead to follow, not a "
                       "result")
        dir_tail = (f" Direction, not the not-falsified rate, is where this desk's signal "
                    f"would be (p {p_dir_adj:.3f}{caveat}).")
    if not has_null:
        return "unproven", (f"{head} — cannot promote without a null covering every graded "
                            f"call ({null.get('reason') or 'unavailable'}). "
                            f"{conv['note']}.{dir_tail}")
    blocks = null.get("independent_blocks") or 0
    margin_ok = hr is not None and null_hr is not None and (hr - null_hr) >= _PROMOTE_MARGIN
    alpha_ok = p_hit_adj is not None and p_hit_adj < _PROMOTE_ALPHA
    if not margin_ok:
        gap = "" if hr is None or null_hr is None else f" (gap {round((hr - null_hr) * 100):+d}pp)"
        return "unproven", (f"{head} — no separation from its own null{gap}; needs "
                            f"{round(_PROMOTE_MARGIN * 100)}pp. {conv['note']}.{dir_tail}")
    if not alpha_ok:
        pv = "not computable" if p_hit_adj is None else f"p {p_hit_adj:.2f}"
        family = ("the desks tested alongside it" if family_n is None
                  else f"the {family_n} desk{'s' if family_n != 1 else ''} eligible for the test")
        return "unproven", (f"{head} — lift not significant after correcting across "
                            f"{family} ({pv}). {conv['note']}.{dir_tail}")
    if blocks < _MIN_INDEPENDENT_BLOCKS:
        return "unproven", (f"{head} — clears its null, but the graded theses overlap in time: "
                            f"{blocks} independent window{'s' if blocks != 1 else ''} of "
                            f"{_MIN_INDEPENDENT_BLOCKS} required. {conv['note']}.{dir_tail}")
    return "calibrated", (f"{head} — clears its own null by "
                          f"{round((hr - null_hr) * 100):+d}pp over {n} scored across {blocks} "
                          f"independent windows (p {p_hit_adj:.3f}). {conv['note']}.")


def _promotion_eligible(track: dict, null: dict) -> bool:
    """Is this desk actually up for promotion this run — i.e. does the alpha bar get consulted?

    Both conditions are pre-registered and independent of the observed p-value: the sample
    floor and a null that covers every graded call. `_desk_health` returns 'cold' below the
    floor and 'unproven' without a null, in both cases before reading `p_hit_adj`. This is
    the Holm family (see `build`).
    """
    n = ((track or {}).get("overall") or {}).get("n") or 0
    return n >= _MIN_SAMPLE and bool((null or {}).get("available"))


def _standout_track_row_from_parquet(label: str, rel_path: str, region: str, root: Path) -> dict:
    """Build a display-only row from a standout board.parquet file.

    Used for the CN track (data/china_standout_track/board.parquet) because no JSON
    summary is produced in this wave — the real ledger is the parquet.

    Derives: n_rows (total rows in parquet), n_graded (rows with non-null fwd_mfe_21),
    date span, and health.  Hit rate is ACCRUING until n_graded >= _MIN_SAMPLE and
    fwd_mfe_21 represents an honest 21d-excess measure.

    Never raises; absent / parse-fail → cold ACCRUING row.
    """
    _cold = {
        "name": label, "region": region, "rel_path": rel_path,
        "board_dates": 0, "graded_rows": 0,
        "h21_hit_rate": None, "h21_n": 0,
        "health": "cold", "health_note": "no track record yet (ACCRUING)",
    }
    try:
        import pandas as pd  # local import — keep calibration_hub import-light
        p = root / rel_path
        if not p.exists():
            return _cold
        df = pd.read_parquet(p)
        board_definition = None
        if region.lower() == "cn":
            from engine import china_standout_track as _cn_track  # noqa: PLC0415

            df, board_definition = _cn_track._latest_definition_frame(df)  # noqa: SLF001
            board_definition = board_definition or "legacy"
        n_rows = len(df)
        # n_graded: rows where the 21d forward metric has matured (non-null)
        graded_col = "fwd_mfe_21"
        n_graded = int(df[graded_col].notna().sum()) if graded_col in df.columns else 0
        # date span from 'date' column
        date_col = "date"
        board_dates = 0
        if date_col in df.columns:
            board_dates = int(df[date_col].nunique())
        if n_rows == 0:
            return dict(_cold, board_dates=board_dates)
        # hit rate: ACCRUING until n_graded >= floor — fwd_mfe_21 is MFE not excess;
        # we only count ACCRUING for now (no excess-vs-CSI300 column yet).
        note = (
            f"{n_rows} board rows, {n_graded} graded (fwd_mfe_21 non-null) — "
            "ACCRUING; hit-rate requires excess_21d column (not yet wired)"
        )
        return {
            "name": label, "region": region, "rel_path": rel_path,
            "board_definition": board_definition,
            "board_dates": board_dates,
            "graded_rows": n_graded,
            "h21_hit_rate": None, "h21_n": n_graded,
            "health": "cold", "health_note": note,
        }
    except Exception:  # noqa: BLE001
        return _cold


def _standout_track_row(label: str, rel_path: str, region: str, root: Path) -> dict:
    """Build a display-only row from a standout/board track JSON or parquet.

    Dispatches to _standout_track_row_from_parquet when rel_path ends in .parquet
    (used for the CN ledger: data/china_standout_track/board.parquet).

    Reads the track's top-level summary fields (board_dates_total, graded_rows_total,
    per_horizon h21 buy_lane hit_rate) and maps them to a calibration-hub-compatible
    dict.  Never raises; absent or corrupt file → cold state.

    This is read-only context (SA-W5 §3 / SA-R10 — display_only, ACCRUING until floors).
    These entries appear separately from _DESKS so the hub can show board-track records
    in one place without conflating them with Phase-C falsifiable-thesis loops.
    """
    if rel_path.endswith(".parquet"):
        return _standout_track_row_from_parquet(label, rel_path, region, root)
    track = _read_json(root / rel_path)
    if not track:
        return {
            "name": label, "region": region, "rel_path": rel_path,
            "board_dates": 0, "graded_rows": 0,
            "h21_hit_rate": None, "h21_n": 0,
            "health": "cold", "health_note": "no track record yet (ACCRUING)",
        }
    if track.get("empty"):
        return {
            "name": label, "region": region, "rel_path": rel_path,
            "board_dates": track.get("board_dates_total", 0),
            "graded_rows": track.get("graded_rows_total", 0),
            "h21_hit_rate": None, "h21_n": 0,
            "health": "cold", "health_note": "no matured rows yet (ACCRUING — first read ~2026-09)",
        }
    h21 = (track.get("per_horizon") or {}).get("h21") or {}
    buy = (h21.get("buy_lane") or {}).get("vs_spy") or {}
    n = buy.get("n") or 0
    hr = buy.get("hit_rate")
    # This endpoint is "beat SPY over 21 days", which — unlike the desks' not-falsified rate
    # — genuinely does sit near one-half, so it is compared to one-half honestly. But a point
    # estimate over one-half is still not a track record: promotion waits for the
    # pre-registered SA-R10 cluster-unit floor. If anything one-half FLATTERS a single-name
    # board (the median stock trails a cap-weighted index), so it demotes but cannot promote.
    if n < _MIN_SAMPLE or hr is None:
        health = "cold"
        note = (f"only {n} matured 21-day rows — still accruing; "
                f"floor is {_STANDOUT_FLOOR} cluster-unit rows")
    elif hr < _DEMOTION_FLOOR:
        health = "weak"
        note = (f"beat SPY on {hr:.1%} of {n} 21-day windows — under the roughly half a "
                f"coin-flip pick clears")
    elif n < _STANDOUT_FLOOR:
        health = "unproven"
        note = (f"beat SPY on {hr:.1%} of {n} 21-day windows — over half, but the "
                f"pre-registered floor of {_STANDOUT_FLOOR} cluster-unit rows is not met yet")
    else:
        health = "calibrated"
        note = f"beat SPY on {hr:.1%} of {n} 21-day windows, past the {_STANDOUT_FLOOR}-row floor"
    return {
        "name": label, "region": region, "rel_path": rel_path,
        "board_dates": track.get("board_dates_total", 0),
        "graded_rows": track.get("graded_rows_total", 0),
        "h21_hit_rate": hr, "h21_n": n,
        "health": health, "health_note": note,
    }


def _desk_row(label: str, slug: str, track: dict, null: dict, p_hit_adj: float | None,
              p_dir_adj: float | None = None, family_n: int | None = None) -> dict:
    overall = track.get("overall") or {}
    conv = _conviction_read(track.get("by_conviction") or {})
    health, note = (_desk_health(track, null, p_hit_adj, p_dir_adj, family_n) if overall
                    else ("cold", "no track record yet"))
    return {
        "name": label, "slug": slug,
        "scored": track.get("scored_total") or 0,
        "open": track.get("open") or 0,
        "hit_rate": overall.get("hit_rate"),
        "dir_accuracy": overall.get("dir_accuracy"),
        # What the SAME falsifiers score by chance — the bar `hit_rate` is judged against.
        "null_hit_rate": null.get("null_hit_rate"),
        "null_dir_rate": null.get("null_dir_rate"),
        "p_hit": null.get("p_hit"),
        "p_hit_holm": p_hit_adj,
        "p_dir": null.get("p_dir"),
        "p_dir_holm": p_dir_adj,
        "independent_blocks": null.get("independent_blocks"),
        "placebo_coverage": null.get("coverage"),
        "placebo_available": bool(null.get("available")),
        "placebo_note": null.get("reason") or "",
        "placebo_mix_source": null.get("mix_source"),
        "placebo_by_kind": null.get("by_kind") or {},
        "conviction_monotone": conv["verdict"],
        "conviction_note": conv["note"],
        "conviction_tiers": conv["tiers"],
        "regimes": sorted((track.get("by_regime") or {}).keys()),
        "health": health, "health_note": note,
    }


def _trial_ledger_summary(root: Path) -> dict:
    """How honestly the calibrators counted their multiple testing — the P3 keystone made
    visible: per signal family, the itemized trials + the declared upper-bound floor."""
    led = TrialLedger(Path(root).joinpath("data", "trial_ledger.jsonl"))
    fams = []
    for fam in led.families():
        fams.append({"family": fam, "itemized": led.literal_n(fam),
                     "declared": led.declared_budget(fam), "effective_n": led.effective_n(fam)})
    fams.sort(key=lambda f: f["effective_n"], reverse=True)
    return {"families": fams, "total_families": len(fams),
            "total_effective_n": sum(f["effective_n"] for f in fams)}


def build(root=None) -> dict:
    from engine import desk_placebo          # lazy — keeps calibration_hub import-light

    root = Path(root) if root else config.ROOT
    today = date.today()
    tracks = {slug: (_read_json(root / "data" / slug / "track_record.json") or {})
              for _, slug in _DESKS}
    # Pass 1: measure each desk's own null base rate for the falsifiers it actually graded.
    nulls = {slug: desk_placebo.null_baseline(root, slug, tracks[slug], today)
             for _, slug in _DESKS}
    # Pass 2: Holm-correct across the desks tested together (two separate families — the
    # not-falsified endpoint and the directional one), then classify.
    #
    # The family is the desks ELIGIBLE for the promotion test, not every desk tracked.
    # Holm-Bonferroni controls the chance of any false promotion across simultaneous tests;
    # a desk that cannot be promoted this run makes no such test and cannot contribute a
    # false one. Including it would only cost the eligible desks power — and would mean that
    # merely adding a cold desk to _DESKS silently tightens the bar on desks whose evidence
    # did not change. Eligibility is the pre-registered pair (`_MIN_SAMPLE` reached, null
    # measurable), decided without reference to any p-value, so scoping the family this way
    # does not relax FWER control.
    elig = {slug for _, slug in _DESKS if _promotion_eligible(tracks[slug], nulls[slug])}
    p_hit_raw = {slug: (nulls[slug].get("p_hit") if slug in elig else None)
                 for _, slug in _DESKS}
    p_dir_raw = {slug: (nulls[slug].get("p_dir") if slug in elig else None)
                 for _, slug in _DESKS}
    p_adj = desk_placebo.holm_adjust(p_hit_raw)
    p_dir_adj = desk_placebo.holm_adjust(p_dir_raw)
    hit_family_n = sum(1 for v in p_hit_raw.values() if v is not None)
    dir_family_n = sum(1 for v in p_dir_raw.values() if v is not None)
    desks = [_desk_row(label, slug, tracks[slug], nulls[slug], p_adj.get(slug),
                       p_dir_adj.get(slug), hit_family_n)
             for label, slug in _DESKS]

    live = sum(1 for d in desks if d["health"] != "cold")
    cold = len(desks) - live
    promoted = sum(1 for d in desks if d["health"] == "calibrated")
    unproven = sum(1 for d in desks if d["health"] == "unproven")
    note = (f"{live}/{len(desks)} desk loops live; {cold} still cold (windows maturing); "
            f"{promoted} promoted to calibrated. A desk is judged against the rate ITS OWN "
            "falsifiers go untriggered by chance, not against one-half — 'not falsified' is "
            "a lenient endpoint, and most leans clear it without any skill. "
            "Display-only — track records calibrate conviction, never size a position.")
    # SA-W5: standout board tracks (read-only; ACCRUING; separate from Phase-C desks)
    standout_tracks = [
        _standout_track_row(label, rel, region, root)
        for label, rel, region in _STANDOUT_TRACKS
    ]
    return {
        "schema": SCHEMA,
        "as_of": date.today().isoformat(),
        "desks": desks,
        "loops": {"total": len(desks), "live": live, "cold": cold,
                  "calibrated": promoted, "unproven": unproven},
        # The bars every desk was held to, written alongside the verdicts so a reader can
        # check the gate rather than take the label on faith.
        "promotion_gate": {
            "min_sample": _MIN_SAMPLE,
            "min_independent_blocks": _MIN_INDEPENDENT_BLOCKS,
            "alpha": _PROMOTE_ALPHA,
            # The family is the desks ELIGIBLE for promotion this run, not the desks tracked.
            "alpha_correction": (f"Holm-Bonferroni across the {hit_family_n} of "
                                 f"{len(_DESKS)} desks eligible for the test"),
            "desks_tracked": len(_DESKS),
            "holm_family_hit": hit_family_n,
            "holm_family_dir": dir_family_n,
            "holm_family": "desks with a measured null over at least min_sample graded calls",
            "min_margin_over_null": _PROMOTE_MARGIN,
            "min_conviction_bucket": _MIN_CONVICTION_BUCKET,
            "null": "per-desk empirical placebo (engine.desk_placebo) — the same falsifiers "
                    "swept over every historical entry date",
            "note": "hit_rate is a NOT-FALSIFIED rate, not a directional one; its null sits "
                    "far above one-half. Bars are pre-registered here; display-tier accrual "
                    "is unaffected by any of them.",
        },
        "trial_ledger": _trial_ledger_summary(root),
        "summary_note": note,
        # SA-W5: buy-board standing track records (display-only, SA-R10 ACCRUING state)
        "standout_tracks": standout_tracks,
    }


# --------------------------------------------------------------------------- #
# self-contained HTML (no theme/nav coupling) — one scannable observability page
# --------------------------------------------------------------------------- #
_HEALTH_COLOR = {"calibrated": "#1FA971", "weak": "#D98C00",
                 "inverted": "#E5484D", "cold": "#8B8D98", "unproven": "#5B8DEF"}


def _pct(x) -> str:
    return "—" if x is None else f"{round(x * 100):d}%"


def render_html(s: dict) -> str:
    rows = []
    for d in s["desks"]:
        c = _HEALTH_COLOR.get(d["health"], "#8B8D98")
        regimes = ", ".join(d["regimes"]) if d["regimes"] else "—"
        rows.append(
            f"<tr><td>{d['name']}</td><td style='text-align:right'>{d['scored']}</td>"
            f"<td style='text-align:right'>{d['open']}</td>"
            f"<td style='text-align:right'>{_pct(d['hit_rate'])}</td>"
            f"<td style='text-align:right;color:#8B8D98'>{_pct(d.get('null_hit_rate'))}</td>"
            f"<td style='text-align:right'>{_pct(d['dir_accuracy'])}</td>"
            f"<td style='text-align:right;color:#8B8D98'>{_pct(d.get('null_dir_rate'))}</td>"
            f"<td>{regimes}</td>"
            f"<td><span style='color:{c};font-weight:500'>{d['health']}</span><br>"
            f"<span style='color:#8B8D98;font-size:12px'>{d['health_note']}</span></td></tr>")
    gate = s.get("promotion_gate") or {}
    led_rows = "".join(
        f"<tr><td>{f['family']}</td><td style='text-align:right'>{f['itemized']}</td>"
        f"<td style='text-align:right'>{f['declared'] or '—'}</td>"
        f"<td style='text-align:right'>{f['effective_n']}</td></tr>"
        for f in s["trial_ledger"]["families"]) or \
        "<tr><td colspan=4 style='color:#8B8D98'>no trials counted yet</td></tr>"
    lp = s["loops"]
    # SA-W5: standout board track rows
    st_rows = "".join(
        f"<tr><td>{t['name']}</td><td>{t['region']}</td>"
        f"<td style='text-align:right'>{t['board_dates']}</td>"
        f"<td style='text-align:right'>{t['graded_rows']}</td>"
        f"<td style='text-align:right'>{_pct(t['h21_hit_rate'])}</td>"
        f"<td><span style='color:{_HEALTH_COLOR.get(t['health'], '#8B8D98')};font-weight:500'>"
        f"{t['health']}</span><br>"
        f"<span style='color:#8B8D98;font-size:12px'>{t['health_note']}</span></td></tr>"
        for t in s.get("standout_tracks", [])
    ) or "<tr><td colspan=6 style='color:#8B8D98'>no board tracks yet</td></tr>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Calibration Hub</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:920px;margin:2rem auto;
padding:0 1rem;color:#1a1a1a;background:#fff}}
h1{{font-size:22px;font-weight:500}}h2{{font-size:16px;font-weight:500;margin-top:2rem}}
.sub{{color:#8B8D98;font-size:14px}}table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:.5rem}}
th,td{{padding:8px 10px;border-bottom:1px solid #ececec;text-align:left;vertical-align:top}}
th{{color:#8B8D98;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.chips{{display:flex;gap:1.5rem;margin:1rem 0}}.chip b{{font-size:24px;font-weight:500}}
/* our own scrollbars */
*{{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,#8B8D98 50%,transparent) transparent}}
*::-webkit-scrollbar{{width:11px;height:11px}}
*::-webkit-scrollbar-track{{background:transparent}}
*::-webkit-scrollbar-thumb{{background:color-mix(in srgb,#8B8D98 50%,transparent);border-radius:999px;border:3px solid transparent;background-clip:padding-box}}
*::-webkit-scrollbar-thumb:hover{{background:color-mix(in srgb,#8B8D98 78%,transparent)}}
*::-webkit-scrollbar-corner{{background:transparent}}
@media(prefers-color-scheme:dark){{body{{background:#16171a;color:#e8e8e8}}th,td{{border-color:#2a2b2f}}*{{scrollbar-color:color-mix(in srgb,#c8ccd6 30%,transparent) transparent}}*::-webkit-scrollbar-thumb{{background:color-mix(in srgb,#c8ccd6 30%,transparent)}}}}
/* phone: the multi-column tables are wider than the screen — let each scroll
   horizontally within the page instead of pushing the whole page sideways. */
@media(max-width:700px){{table{{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}}.chips{{flex-wrap:wrap;gap:1rem}}}}
</style></head><body>
<h1>Calibration Hub</h1>
<div class="sub">The self-improving AI suite, made visible · as of {s['as_of']} · display-only</div>
<div class="chips">
<div class="chip"><b>{lp['live']}</b><div class="sub">live loops</div></div>
<div class="chip"><b>{lp['cold']}</b><div class="sub">cold (maturing)</div></div>
<div class="chip"><b>{lp.get('calibrated', 0)}</b><div class="sub">cleared their null</div></div>
<div class="chip"><b>{s['trial_ledger']['total_families']}</b><div class="sub">trial families</div></div>
</div>
<h2>Phase-C desks — are the falsifiable-thesis loops right?</h2>
<p class="sub"><b>Read the two grey columns first.</b> A thesis "hits" when its falsifier did
<i>not</i> trigger — so most leans clear it with no skill at all. <b>By chance</b> is what
these very same falsifiers score when swept over every historical entry date on the same
instruments and horizons. Only the gap between the black column and the grey one next to it
is evidence, and one-half is not the null for either.</p>
<table><tr><th>Desk</th><th>Scored</th><th>Open</th><th>Not falsified</th><th>By chance</th>
<th>Direction right</th><th>By chance</th><th>Regimes</th><th>Health</th></tr>{''.join(rows)}</table>
<p class="sub">Promotion to <b>calibrated</b> is pre-registered and requires all of:
{gate.get('min_sample')}+ graded outcomes · at least {gate.get('min_margin_over_null', 0) * 100:.0f}pp
over the desk's own null · one-sided p &lt; {gate.get('alpha')} after {gate.get('alpha_correction')} ·
{gate.get('min_independent_blocks')}+ non-overlapping forward windows (theses logged days apart
grade over the same tape, so raw counts overstate the evidence) · direction not below its own
null. Failing any bar changes the label only — every desk keeps logging and grading exactly
as before.</p>
<h2>Board track records — standing accuracy, all known boards (SA-W5, display-only)</h2>
<p class="sub">ACCRUING — cluster-unit floors (SA-R10) not yet met. First US read ~2026-09-15; CN ~2026-10-15.</p>
<table><tr><th>Board</th><th>Region</th><th>Board dates</th><th>Graded rows</th>
<th>h21 hit-rate</th><th>Health</th></tr>{st_rows}</table>
<h2>Trial Ledger — honest multiple-testing counts (P3 keystone)</h2>
<table><tr><th>Signal family</th><th>Itemized</th><th>Declared floor</th><th>Effective N</th></tr>{led_rows}</table>
<p class="sub">{s['summary_note']}</p>
</body></html>"""


def render_markdown(s: dict) -> str:
    L = [f"# Calibration Hub — {s['as_of']}", "", s["summary_note"], "",
         "## Phase-C desks", "",
         "| Desk | Scored | Not falsified | By chance | Direction | By chance | Health |",
         "|---|---|---|---|---|---|---|"]
    for d in s["desks"]:
        L.append(f"| {d['name']} | {d['scored']} | {_pct(d['hit_rate'])} | "
                 f"{_pct(d.get('null_hit_rate'))} | {_pct(d['dir_accuracy'])} | "
                 f"{_pct(d.get('null_dir_rate'))} | {d['health']} — {d['health_note']} |")
    L += ["", "## Trial Ledger", "", "| Family | Itemized | Declared | Effective N |", "|---|---|---|---|"]
    for f in s["trial_ledger"]["families"]:
        L.append(f"| {f['family']} | {f['itemized']} | {f['declared'] or '—'} | {f['effective_n']} |")
    return "\n".join(L)


def run(root=None, persist: bool = True) -> dict:
    """Build the consolidated summary; write data/calibration/summary.json + site/calibration.html."""
    root = Path(root) if root else config.ROOT
    s = build(root)
    if persist:
        try:
            out = Path(root) / "data" / "calibration"
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(json.dumps(s, indent=2, default=str))
            site = Path(root) / config.load()["storage"]["site_dir"]
            site.mkdir(parents=True, exist_ok=True)
            write_page(site / "calibration.html", render_html(s))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("calibration_hub: persist failed: %s", e)
    return s


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    s = run(persist=True)
    print(render_markdown(s))
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
