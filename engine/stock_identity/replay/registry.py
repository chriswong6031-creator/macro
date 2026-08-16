"""The family registry — keys minted from producer receipts, never invented (registration §3).

Every entry's ``family_key``, ``producer``, era pin and ``spec_hash`` is derived from a
value that exists in the producing code or in a committed ledger. Nothing here is a name
someone liked: ``grey_dot_macro``'s era IS ``engine.signal_quality.ANCHOR_ERA``, the
cascade's IS ``engine.confluence_tiers.ANCHOR_ERA``, the weekly organ's IS its own
``SCHEMA`` string, and STARTER's IS ``us_early_turn.UNION_ADMISSION_ERA``. A producer edit
moves the hash, which moves the family's identity, which is the whole point of pinning it.

Provenance classes (masterplan §5):

``R``  replayed in W2 from a store or by the producer's own function
``B``  locked-spec backcast — the only available specification postdates the measured
       history, so every row is stamped ``spec_postdates_history`` and the family may never
       be cited as evidence that it, as it then existed, localized anything
``P``  prospective-only — the family did not exist before its birth date, so it has NO
       history and ships **zero rows**. Enumerated here for structural-absence honesty:
       a reader must be able to see that the silence was checked, not overlooked
``C``  conditional — resolved this wave by the registration's consequence matrix

The Class P entries are the ones most likely to be misread. ``amber_early`` was born on
2026-08-11 when the Terminal carved it out of the grey dot; ``door_r_rearm``'s own charter
forbids backfill; the turn-watch deck and the GC-v2 scores keep no fire ledger; the Radar
C1/C2 LIVE-state detectors inherit the minute-reconstruction rule. **Structural absence is
never negative evidence** — none of these zeros says the family does nothing.
"""
from __future__ import annotations

from typing import Any

from engine.stock_identity.authority import authority_block
from engine.stock_identity.replay import (
    bottom_watch,
    confirmed_buy,
    grey_dot,
    naive,
    reclaim_waiver,
    sea,
    starter,
    tiers,
    washout_turn,
)
from engine.stock_identity.replay import events as ev

__all__ = ["REGISTRY_SCHEMA", "CLASS_P_FAMILIES", "build_registry", "class_p_entries"]

REGISTRY_SCHEMA = "stock_identity.expert_family_registry.v0"

#: Class P: enumerated with ZERO rows, test-enforced. Each entry names the reason its
#: history does not exist and the date from which it can ever accrue.
CLASS_P_FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "family_key": "amber_early",
        "producer": "charting-app confluence_v2 washout-promoted EARLY marker",
        "family": "amber_early",
        "family_first_available": "2026-08-11",
        "family_era": "terminal-935389d4-2026-08-11",
        "reason": (
            "the family was CREATED on 2026-08-11 when the Terminal began promoting a "
            "washout-context grey dot to an amber EARLY marker. It has no history before "
            "that date because it did not exist. The as-restated grey-dot reading (the "
            "in_washout_context flag on grey_dot_macro) is how W2 shows what WOULD have "
            "been carved out — it is not this family's history and is never labelled as it."
        ),
    },
    {
        "family_key": "door_r_rearm",
        "producer": "engine.prophet_doors Door R (re-arm / trend reclaim)",
        "family": "reentry_trend_reclaim",
        "family_first_available": None,
        "family_era": "prospective-only by charter",
        "reason": (
            "the organ's own charter forbids historical backfill — every row must be a real "
            "forward call. Replaying it would violate the charter that created it."
        ),
    },
    {
        "family_key": "turn_watch_deck",
        "producer": "engine.us_turn_watch:compute_deck",
        "family": "turn_watch",
        "family_first_available": None,
        "family_era": "nightly artifact only",
        "reason": (
            "the deck publishes a nightly artifact and keeps no fire ledger, so no past "
            "fire was ever recorded and none can be recovered from a committed artifact."
        ),
    },
    {
        "family_key": "gc_v2_scores",
        "producer": "charting-app confluence_v2::build_v2 keeper / recipe / structure legs",
        "family": "gc_v2",
        "family_first_available": None,
        "family_era": "per-request computation",
        "reason": (
            "computed per request with no persistence located in either repo, and its cited "
            "source lab (harness/e_factors.py) does not exist in either repo — so there is "
            "neither a store to read nor a specification to port."
        ),
    },
    {
        "family_key": "radar_c1_c2",
        "producer": "Live Entry Radar C1/C2 LIVE-state detectors",
        "family": "radar_live_state",
        "family_first_available": None,
        "family_era": "live-forward only",
        "reason": (
            "the Radar contract §5 replay rule: historical replay of a LIVE-state input "
            "requires minute reconstruction of what the indicator showed at the decision "
            "timestamp. No U.S. equity intraday bars exist in-repo, so these detectors are "
            "live-forward only and may never be backfilled from EOD values."
        ),
    },
)


def _entry(
    *,
    family_key: str,
    producer: str,
    family: str,
    subtypes: list[str],
    stage: str,
    eras: list[str],
    family_first_available: str | None,
    provenance_class: str,
    constants: dict[str, Any],
    replay_notes: str,
    parity_notes: str | None = None,
) -> dict[str, Any]:
    return {
        "family_key": family_key,
        "producer": producer,
        "family": family,
        "subtypes": subtypes,
        "stage": stage,
        "era_pins": eras,
        "family_first_available": family_first_available,
        "provenance_class": provenance_class,
        "spec_hash": ev.spec_hash(constants),
        "spec_constants": constants,
        "replay_notes": replay_notes,
        "parity_notes": parity_notes,
    }


def class_p_entries() -> list[dict[str, Any]]:
    """The Class P rows — enumerated, zero-row, with their reasons attached."""
    out: list[dict[str, Any]] = []
    for f in CLASS_P_FAMILIES:
        out.append({
            "family_key": f["family_key"],
            "producer": f["producer"],
            "family": f["family"],
            "subtypes": [],
            "stage": "PROSPECTIVE",
            "era_pins": [f["family_era"]],
            "family_first_available": f["family_first_available"],
            "provenance_class": "P",
            "spec_hash": None,
            "spec_constants": None,
            "replay_notes": f["reason"],
            "parity_notes": None,
            "expected_rows": 0,
        })
    return out


def build_registry(
    *,
    universe_as_of: str,
    price_plane_ids: list[str],
    pilot_symbols: list[str],
    coverage_frac: float | None,
    reclaim_state_as_of: str | None,
    washout_ledger_first_session: str | None,
    starter_verdict: dict[str, Any],
) -> dict[str, Any]:
    """The complete family registry, ready to serialize."""
    naive_specs = {k: naive.constants(k) for k in naive.FAMILY_KEYS}

    families: list[dict[str, Any]] = [
        _entry(
            family_key=grey_dot.MACRO_FAMILY_KEY,
            producer="engine.signal_quality:signal_frame.early",
            family="grey_dot",
            subtypes=["early"],
            stage="ANTICIPATION",
            eras=[grey_dot.MACRO_ERA],
            family_first_available=None,
            provenance_class="R",
            constants=grey_dot.macro_constants(),
            replay_notes=(
                "the engine's own `early` column, read off signal_frame and never "
                "re-derived. Published as a DUAL series: every fire carries "
                "`in_washout_context`, so the as-recorded reading (all fires) and the "
                "as-restated reading (fires today's promotion rule would carve out to "
                "amber_early) are both available from one store. The as-restated view is "
                "expressed as typed edges, never by deleting rows."
            ),
            parity_notes=(
                "measured against grey_dot_terminal on the pilot; the two families are kept "
                "separate regardless of the counts (registration §3)"
            ),
        ),
        _entry(
            family_key=grey_dot.TERMINAL_FAMILY_KEY,
            producer="charting-app confluence_v2::early_dots (locked-spec port)",
            family="grey_dot",
            subtypes=["early"],
            stage="ANTICIPATION",
            eras=[grey_dot.TERMINAL_ERA],
            family_first_available=None,
            provenance_class="B",
            constants=grey_dot.terminal_constants(),
            replay_notes=(
                "the Terminal twin persists nothing and G-8 forbids running Terminal "
                "internals, so this is the Radar contract §3.2 fallback: a Macro-side "
                "locked-spec reproduction, Class B on every row."
            ),
            parity_notes=(
                "four measured divergence axes vs grey_dot_macro: (1) oscillator family — "
                "signal_quality imports engine.technicals.rsi (bare ewm), the port pins "
                "engine.canon (SMA-seeded RMA); (2) 2D bucketing — absolute session anchor "
                "vs calendar resample('2B') with a PIT searchsorted join; (3) the rising "
                "leg — two bars on the prior CLOSED bar vs exactly one strictly-greater "
                "bar; (4) Macro carries rsi14 < 65, the Terminal spec does not. NAMED "
                "DEVIATION: the port cuts 3D bars on the Macro absolute anchor because the "
                "Terminal's per-symbol listing anchor (bar_anchor) is not reproducible from "
                "anything committed here — so the anchor axis is held fixed, not measured."
            ),
        ),
        _entry(
            family_key=confirmed_buy.FAMILY_BUY,
            producer="engine.signal_quality:analyze -> data/signal_archive/track_record.parquet",
            family="confirmed_buy",
            subtypes=["buy", "cb_3d_confluence"],
            stage="CONFIRMED",
            eras=[confirmed_buy.ERA],
            family_first_available=None,
            provenance_class="R",
            constants=confirmed_buy.constants(),
            replay_notes=(
                "two arms, never merged. Ledger rows (field_origin=ledger_recorded) carry "
                "the buy-filter verdict and scored_authority=True, which records what that "
                "surface's authority WAS. The deeper recompute (field_origin="
                "replay_recomputed, subtype cb_3d_confluence) is the PRE-FILTER 3D "
                "confluence cross with scored_authority=False; reading it as 'the ledger, "
                "extended' would silently promote a raw cross into a graded verdict. "
                "spec_postdates_history is stamped on every recomputed row the ledger does "
                "not cover. Ledger outcome columns (fwd_*, trade_*, outcome) are never read."
            ),
        ),
        _entry(
            family_key=confirmed_buy.FAMILY_REBUY,
            producer="engine.signal_quality:analyze -> data/signal_archive/track_record.parquet",
            family="confirmed_buy",
            subtypes=["rebuy"],
            stage="CONFIRMED",
            eras=[confirmed_buy.ERA],
            family_first_available=None,
            provenance_class="R",
            constants=confirmed_buy.constants(),
            replay_notes=(
                "ledger-only: REBUY is a distinct ledger `type` with no separate recompute "
                "arm, so the family carries exactly the committed rows."
            ),
        ),
        _entry(
            family_key=reclaim_waiver.FAMILY_KEY,
            producer="engine.signal_quality:washout_qualifier + reclaim_waiver_for",
            family="reentry_block_repair",
            subtypes=["reclaim_waived"],
            stage="ADMISSION",
            eras=[reclaim_waiver.ERA],
            family_first_available=reclaim_state_as_of,
            provenance_class="R",
            constants=reclaim_waiver.constants(),
            replay_notes=(
                "re-derived ONLY over the committed nightly state artifact's own era. That "
                "artifact is overwritten nightly and carries one as_of, so the replayable "
                "window is [as_of, as_of + 5 sessions] and there is nothing earlier to "
                "replay. A zero here is a STRUCTURAL ABSENCE (the state history was never "
                "kept), never evidence that the waiver does nothing. Synthesizing "
                "peer-group state to extend the window is forbidden by the registration."
            ),
        ),
        _entry(
            family_key=washout_turn.FAMILY_KEY,
            producer="engine.washout_turn:compute_symbol_washout + data/washout_turn/ledger.jsonl",
            family="weekly_washout_turn",
            subtypes=["WASHOUT_TURN", "TURN_WATCH"],
            stage="ORGAN",
            eras=[washout_turn.ERA],
            family_first_available=washout_ledger_first_session,
            provenance_class="R",
            constants=washout_turn.constants(),
            replay_notes=(
                "ledger arm (pure filter, keep-FIRST) union an earlier recompute that calls "
                "the organ's own pure function on the frame TRUNCATED at each weekly bar. "
                "Truncation is the correctness argument, not an optimization: the organ's "
                "depth percentile is a whole-sample statistic, so a single-pass evaluation "
                "over the full series would let a bar's qualification depend on bars that "
                "had not happened yet."
            ),
        ),
        _entry(
            family_key=sea.FAMILY_KEY,
            producer="engine.stock_events -> data/stock_events",
            family="sea_event_class",
            subtypes=["<grid>_<direction>"],
            stage="CONTEXT",
            eras=["pre2010", "post2010"],
            family_first_available=None,
            provenance_class="R",
            constants=sea.constants(),
            replay_notes=(
                "pure filter over the committed SEA store, backfill union live months, "
                "keep-FIRST on the store's own key. The store's forward-outcome columns are "
                "OUTCOME content and are never read into a W2 artifact."
            ),
        ),
        _entry(
            family_key=bottom_watch.FAMILY_KEY,
            producer="charting-app confluence_v2 bottom_watch (locked-spec port)",
            family="bottom_watch",
            subtypes=[bottom_watch.KIND_DOT, bottom_watch.KIND_BLOCKED],
            stage="WATCH",
            eras=[bottom_watch.ERA],
            family_first_available=None,
            provenance_class="B",
            constants=bottom_watch.constants(),
            replay_notes=(
                "locked-spec C5 port per Radar contract §3.4. The blocked_trigger / "
                "early_dot de-duplication is recorded as a typed `dedup_suppressed_by` "
                "edge; both rows survive, because deleting the dot would destroy the honest "
                "count of how often the two coincide."
            ),
            parity_notes=(
                "declared approximation: the 'blocked' half is the CB/revBuy trigger firing "
                "below the 200-session average, because the Terminal's own block verdict is "
                "produced by machinery this program may not import. Declared rather than "
                "invented."
            ),
        ),
        _entry(
            family_key=starter.SIGNATURE_FAMILY_KEY,
            producer="engine.us_early_turn:union_admission legs",
            family="starter_signature",
            subtypes=["relaxed_cross", "early_dot"],
            stage="EARLY",
            eras=[starter.ERA],
            family_first_available=None,
            provenance_class="R",
            constants=starter.constants(),
            replay_notes=(
                "the SIGNATURE only — the admission legs, with no licence claimed. This "
                "family exists because the registration's consequence matrix resolved the "
                "licensing context as NOT PIT-reconstructable; see `starter_resolution`."
            ),
        ),
    ]

    for t, key in tiers.FAMILY_KEYS.items():
        families.append(_entry(
            family_key=key,
            producer="engine.confluence_tiers:tier_stream",
            family="tier_cascade",
            subtypes=[t],
            stage="TIER",
            eras=[tiers.ERA],
            family_first_available=None,
            provenance_class="B",
            constants=tiers.constants() | {"tier": t},
            replay_notes=(
                f"{t} ONSET events (entry into the tier), recomputed via tier_stream under "
                "the cascade's own ANCHOR_ERA, which postdates almost all of the recomputed "
                "history — hence Class B on every row. The stream's trailing row is dropped "
                "because it reads the in-progress partial bucket; the residual ~8% of days "
                "where this stream and the LIVE board differ is a live-vs-replay basis "
                "difference, not a leak, and W2 makes no claim about the live board."
            ),
        ))

    for key in naive.FAMILY_KEYS:
        families.append(_entry(
            family_key=key,
            producer=f"engine.stock_identity.replay.naive:{key}",
            family="naive_comparator",
            subtypes=[],
            stage="REFERENCE",
            eras=[naive.ERA],
            family_first_available=None,
            provenance_class="R",
            constants=naive_specs[key],
            replay_notes=(
                "a frozen REFERENCE construction minted by this registration — not a "
                "production engine. Canon oscillator core only (one RSI family), completed "
                "bars, close basis."
            ),
        ))

    # Class C -> the consequence matrix's outcome, recorded per family.
    reconstructable = starter_verdict.get("verdict") == "PIT_RECONSTRUCTABLE"
    for key in starter.TRIO_FAMILY_KEYS:
        families.append({
            "family_key": key,
            "producer": "engine.prophet_bridge:evaluate_entry_zone (STARTER zone lifecycle)",
            "family": "starter_zone",
            "subtypes": [],
            "stage": "PROSPECTIVE" if not reconstructable else "EARLY",
            "era_pins": [starter.ERA],
            "family_first_available": None,
            "provenance_class": "R" if reconstructable else "P",
            "spec_hash": None,
            "spec_constants": None,
            "expected_rows": None if reconstructable else 0,
            "replay_notes": (
                "Class C resolved by the registration §3 consequence matrix: "
                + str(starter_verdict.get("consequence"))
                + " The signature half ships separately as starter_signature; the trio is "
                "never merged with it and never partially faked."
            ),
            "parity_notes": None,
        })

    families.extend(class_p_entries())

    return {
        "schema": REGISTRY_SCHEMA,
        "wave": "W2",
        "registration": "research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md",
        "authority": authority_block(),
        "authority_note": (
            "every family, every event row and every edge in this store carries the "
            "five-key all-false block. scored_authority on a row records what the "
            "EMITTER's authority was at the time — a fact about the past, never a grant."
        ),
        "vintage_stamp": ev.vintage_stamp(
            price_plane_ids=price_plane_ids,
            universe_as_of=universe_as_of,
            coverage_frac=coverage_frac,
            era_law_cohort="pre2010 | post2010 (DNR:LAW-ERA-SPLIT — never pooled across the break)",
        ),
        "event_schema": {
            "name": ev.EVENT_SCHEMA,
            "columns": list(ev.EVENT_COLUMNS),
            "radar_compatibility": (
                "Radar's nested source_identity{source_hash, signal_era, "
                "detector_spec_hash} is carried as three top-level columns under its own "
                "inner field names, so a PR-7 union is a rename-free concat."
            ),
            "field_origin_values": list(ev.FIELD_ORIGINS),
            "field_origin_extension": (
                "ledger_recorded and replay_recomputed extend Radar's "
                "{emitter_verbatim, radar_derived} for historical provenance"
            ),
        },
        "edge_schema": {"name": ev.EDGE_SCHEMA, "columns": list(ev.EDGE_COLUMNS),
                        "relations": list(ev.RELATIONS)},
        "no_ruler_content": (
            "W2 publishes NO ruler metric — no lead/lag, distance, MAE, capture, recall, "
            "precision, composite, fit, rank or best exists as a column, key or identifier "
            "in this store. Those are PR-3's object (registration §0.1). The only "
            "aggregates published are inventory counts and join-coverage counts."
        ),
        "pilot_symbols": sorted(pilot_symbols),
        "starter_resolution": starter_verdict,
        "families": families,
    }
