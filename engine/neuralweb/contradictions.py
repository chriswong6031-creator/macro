"""engine.neuralweb.contradictions — Generalized contradiction detector (Neural Web W4).

PURPOSE
-------
detect_contradictions(root) scans seven typed signal pairs across the committed bus
artifacts and returns a list of typed contradiction records.

HARD LAW — encoded here per design adjudication:
    Contradiction records are DISPLAY-ONLY annotations.  They NEVER gate, NEVER raise
    a ranking or alert priority, and carry NO cross-engine hard gate.  Promoting any
    record beyond display requires its own pre-registered gauntlet (the China
    falsification precedent).  severity vocabulary is limited to 'note' and 'tension';
    'critical' is reserved for the alert vocabulary (Article 2) and is forbidden here.

FAIL-OPEN CONTRACT
------------------
Every source read is fail-open: a missing, corrupt, or unreadable artifact yields no
records for that pair plus a gap entry.  detect_contradictions() always returns a list
(never raises).

FLIP-AWARE LABEL-LAG RULE (operator feedback 2026-07-04)
---------------------------------------------------------
For pairs where a categorical LABEL proxies a continuous backend scale (pair-a: regime
quad; any analogous label pair), an opposing signal against the label is NOT necessarily
a contradiction when the underlying scale is already near the boundary.

The regime quad is the argmax of (growth_score, inflation_score) but the backend carries
a continuous scale.  When the quad label is near a flip:

  NEAR-BOUNDARY (label-lag, kind='label-lag', severity='note'):
    Triggered when EITHER:
      • transition_state is 'TRANSITIONING' or 'RATCHETED-TRANSITION', OR
      • flip_margin < NEAR_FLIP_MARGIN_THRESHOLD (heuristic: 0.15 z-score units;
        flip_margin is |z| − z_threshold for the most fragile supporting component;
        at z_threshold ≈ 0.45 a margin of 0.15 ≈ 1/3 of the threshold; live example:
        flip_margin=0.05 on 2026-07-04 when the pair fired — well inside boundary).

    Reading: "quad label Q1/Goldilocks lags its own scale: flip_margin=X toward
    <flip_condition target>, transition_state=Y — underlying scores lean with the
    RISK_OFF verdict, label has not flipped yet."

  DEEP-IN-QUAD (directional-opposition, kind='directional-opposition', severity='tension'):
    Only when regime is NOT near the boundary (flip_margin >= threshold AND
    transition_state is 'STABLE' or 'WEAKENING').  This is the genuinely informative case.

Scale fields (growth_score, inflation_score, flip_margin, transition_state, confidence)
are ALWAYS included in pair-a's a.reading so the graph/world_state surfaces the scale
rather than just the label.

SEVEN v1 PAIRS
------------
a. regime quad vs market_state verdict
   Q1/Q2 growth labels vs RISK_OFF/caution verdicts from world_state.json (which
   carries both resolved).  Flip-aware: see above.

b. regime_vector growth trend vs risk_radar scare severity
   Rising growth (growth_score > 0 AND Q1/Q2) while a growth scare is 'caution'
   or 'severe' — co-existing acceleration + scare.

c. oracle complex direction vs sector_central call tier
   oracle_state.json complexes[].direction vs data/sector_central/calls.parquet
   latest row per id.  Complex ↔ sector mapped via rotation_groups membership
   overlap (unambiguous only).

d. vol_regime label vs market_state verdict
   Low-vol regime ('normalizing'/'low') while market_state verdict is 'RISK_OFF'.

e. briefing divergences ingestion
   Reads site/intelligence/briefing.json divergences list (already computed by
   engine/briefing.py) — counts and surfaces top-5 by priority as ticker-level
   demand vs supply oppositions.  NOT recomputed here.

f. cross_asset_confirm verdict as macro edge
   Reads the cross_asset_confirm block from data/regime/latest.json.  A 'diverge'
   verdict is a macro-level bonds+FX vs equity contradiction.

g. oracle complex out-rotation vs entry buy-list member
   oracle_state.json complexes[].direction=='out'|'decelerating' while a ticker on
   the site/factordata/us_standouts.json buy list belongs to that complex.
   Ticker→complex mapping: data/oracle/rotation_groups.json members (basket ids)
   cross-referenced with data/baskets/membership.json active tickers.  Unmappable
   tickers skip silently (fail-open).  severity='tension' max; purely descriptive.

RECORD SCHEMA
-------------
{
  "pair_id":  str,            # e.g. "regime-vs-market_state"
  "a": {"artifact": str, "reading": str},
  "b": {"artifact": str, "reading": str},
  "kind":     "directional-opposition" | "label-tension" | "label-lag",
  "severity": "note" | "tension",
  "as_of":    str,            # ISO date of the most recent artifact
  "note":     str,
  "display_only": true        # always true — hard law
}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regime quads that imply positive/accelerating growth
_GROWTH_QUADS = {"Q1", "Q2"}

# Market state verdicts that imply risk-off / caution
_RISK_OFF_VERDICTS = {"RISK_OFF", "caution", "CAUTION"}

# Risk-radar scare bands that qualify as 'elevated'
_ELEVATED_SCARE_BANDS = {"caution", "severe", "critical"}

# Vol regime labels considered 'low vol'
_LOW_VOL_LABELS = {"low", "normalizing", "compressing"}

# Oracle directions considered bullish/constructive
_BULLISH_DIRECTIONS = {"in", "accelerating"}
# Oracle directions considered bearish/defensive
_BEARISH_DIRECTIONS = {"out", "decelerating"}

# Sector_central labels considered bullish
_SC_BULLISH_LABELS = {"Constructive", "Accumulate"}
# Sector_central labels considered bearish
_SC_BEARISH_LABELS = {"Reduce", "Cautious"}

# Flip-aware label-lag rule (pair-a, operator feedback 2026-07-04).
# flip_margin is |z| − z_threshold for the most fragile supporting component
# (z-score units; z_threshold ≈ 0.45 in current engine config).
# A margin below this threshold means the quad label is dangerously close to
# flipping — the label is proxying a scale that already leans the other way.
# Heuristic: 0.15 ≈ 1/3 of the z_threshold; live episode (2026-07-04) had
# flip_margin=0.05 (well inside the boundary).
_NEAR_FLIP_MARGIN_THRESHOLD: float = 0.15

# transition_state values that indicate the regime is near a flip
_NEAR_FLIP_TRANSITION_STATES = {"TRANSITIONING", "RATCHETED-TRANSITION"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions: unreadable json %s — %s", p, exc)
        return None


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
) -> dict[str, Any]:
    """Build a typed contradiction record."""
    assert severity in ("note", "tension"), f"Invalid severity: {severity!r}"
    return {
        "pair_id": pair_id,
        "a": {"artifact": a_artifact, "reading": a_reading},
        "b": {"artifact": b_artifact, "reading": b_reading},
        "kind": kind,
        "severity": severity,
        "as_of": as_of,
        "note": note,
        "display_only": True,
    }


def _is_near_flip(flip_margin: float | None, transition_state: str | None) -> bool:
    """Return True when the regime quad label is near a boundary flip.

    Triggered when EITHER the regime engine is already flagging a transition
    OR the most fragile supporting component is within _NEAR_FLIP_MARGIN_THRESHOLD
    of its flip threshold (z-score units).  A label opposing market_state in this
    state is a label-lag (note), not a genuine directional contradiction (tension).
    """
    if transition_state in _NEAR_FLIP_TRANSITION_STATES:
        return True
    if flip_margin is not None and flip_margin < _NEAR_FLIP_MARGIN_THRESHOLD:
        return True
    return False


# ---------------------------------------------------------------------------
# Pair detectors
# ---------------------------------------------------------------------------

def _pair_a_regime_vs_market_state(
    world_state: dict,
    gaps: list[str],
) -> list[dict]:
    """Pair A: regime quad (Q1/Q2 = growth) vs market_state verdict (RISK_OFF/caution).

    Flip-aware (operator feedback 2026-07-04): the regime quad is the argmax of a
    continuous backend scale.  When the scale is near a flip boundary the label lags
    — an opposing verdict is a label-lag (kind='label-lag', severity='note'), not a
    tension.  The scale fields ride in a.reading regardless of which branch fires.
    """
    records: list[dict] = []
    try:
        regime = world_state.get("regime") or {}
        verdict_block = world_state.get("verdict") or {}

        quad = regime.get("quad") or regime.get("label")
        verdict = verdict_block.get("verdict")
        as_of = verdict_block.get("asof") or regime.get("asof") or "unknown"

        if quad is None or verdict is None:
            gaps.append("pair-a: missing quad or verdict in world_state")
            return records

        if quad in _GROWTH_QUADS and verdict in _RISK_OFF_VERDICTS:
            # Always pull the scale fields for the reading
            growth_score = regime.get("growth_score")
            inflation_score = regime.get("inflation_score")
            flip_margin = regime.get("flip_margin")
            transition_state = regime.get("transition_state")
            confidence = regime.get("confidence")
            _fc_raw = regime.get("flip_condition")
            flip_condition: dict = _fc_raw if isinstance(_fc_raw, dict) else {}
            flip_target = flip_condition.get("axis") or "unknown"

            # Build a rich reading that exposes the underlying scale, not just the label
            scale_reading = (
                f"quad={quad} (growth regime) | "
                f"growth_score={growth_score} inflation_score={inflation_score} | "
                f"flip_margin={flip_margin} transition_state={transition_state} "
                f"confidence={confidence}"
            )

            near_flip = _is_near_flip(flip_margin, transition_state)

            if near_flip:
                # The label is lagging its own scale — the underlying backend agrees
                # with the RISK_OFF verdict.  Not a genuine contradiction.
                records.append(_record(
                    pair_id="regime-vs-market_state",
                    a_artifact="data/regime/latest.json",
                    a_reading=scale_reading,
                    b_artifact="data/market_state/latest.json",
                    b_reading=f"verdict={verdict}",
                    kind="label-lag",
                    severity="note",
                    as_of=str(as_of),
                    note=(
                        f"Quad label {quad}/Goldilocks lags its own scale: "
                        f"flip_margin={flip_margin} toward {flip_target} flip, "
                        f"transition_state={transition_state} — underlying scores "
                        f"(growth={growth_score}, inflation={inflation_score}) "
                        f"lean with the {verdict} verdict; the label has not flipped yet.  "
                        "Not a live contradiction: the backend scale and market_state agree; "
                        "the categorical label is the lagging component.  Display-only."
                    ),
                ))
            else:
                # Deep-in-quad: the label is well-supported and the opposition is real
                records.append(_record(
                    pair_id="regime-vs-market_state",
                    a_artifact="data/regime/latest.json",
                    a_reading=scale_reading,
                    b_artifact="data/market_state/latest.json",
                    b_reading=f"verdict={verdict}",
                    kind="directional-opposition",
                    severity="tension",
                    as_of=str(as_of),
                    note=(
                        f"Regime labels growth ({quad}) while market_state signals "
                        f"{verdict}.  flip_margin={flip_margin} (>{_NEAR_FLIP_MARGIN_THRESHOLD}) "
                        f"and transition_state={transition_state} — quad is deep and stable; "
                        "this opposition is the genuinely informative case, not a label lag.  "
                        "Display-only context; not a gate."
                    ),
                ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-a failed: %s", exc)
        gaps.append(f"pair-a: {exc}")
    return records


def _pair_b_regime_vector_vs_risk_radar(
    world_state: dict,
    gaps: list[str],
) -> list[dict]:
    """Pair B: regime_vector growth trend vs risk_radar dominant scare severity."""
    records: list[dict] = []
    try:
        regime = world_state.get("regime") or {}
        rr = world_state.get("risk_radar_raw") or {}

        quad = regime.get("quad")
        growth_score = regime.get("growth_score")
        rr_state = rr.get("state")
        dominant_scare = rr.get("dominant_scare")
        top_score = rr.get("top_score")
        as_of = regime.get("asof") or "unknown"

        # "Rising growth" = Q1/Q2 AND growth_score > 0
        if quad is None or growth_score is None or rr_state is None:
            gaps.append("pair-b: missing quad/growth_score/rr_state in world_state")
            return records

        rising_growth = (quad in _GROWTH_QUADS and float(growth_score) > 0)
        elevated_scare = rr_state in _ELEVATED_SCARE_BANDS

        if rising_growth and elevated_scare and dominant_scare == "growth":
            records.append(_record(
                pair_id="regime_vector-vs-risk_radar",
                a_artifact="data/regime/latest.json:regime_vector",
                a_reading=f"quad={quad} growth_score={growth_score:.3f} (rising growth)",
                b_artifact="data/regime/latest.json:risk_radar",
                b_reading=(
                    f"state={rr_state} dominant_scare={dominant_scare} "
                    f"top_score={top_score}"
                ),
                kind="directional-opposition",
                severity="tension",
                as_of=str(as_of),
                note=(
                    "Regime vector places growth in positive territory while the risk radar "
                    f"flags an elevated growth scare ({rr_state}).  "
                    "This is typical of early growth-scare onset before the regime flips.  "
                    "Display-only; neither cancels the other."
                ),
            ))
        elif rising_growth and elevated_scare and dominant_scare is not None:
            records.append(_record(
                pair_id="regime_vector-vs-risk_radar",
                a_artifact="data/regime/latest.json:regime_vector",
                a_reading=f"quad={quad} growth_score={growth_score:.3f}",
                b_artifact="data/regime/latest.json:risk_radar",
                b_reading=(
                    f"state={rr_state} dominant_scare={dominant_scare}"
                ),
                kind="label-tension",
                severity="note",
                as_of=str(as_of),
                note=(
                    f"Rising growth regime ({quad}) while risk_radar elevated "
                    f"with dominant scare={dominant_scare}.  "
                    "Non-growth scare alongside positive growth vector is possible "
                    "in a diverging-risk environment.  Display-only context."
                ),
            ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-b failed: %s", exc)
        gaps.append(f"pair-b: {exc}")
    return records


def _pair_c_oracle_vs_sector_central(
    oracle_state: dict | None,
    rotation_groups: list[dict],
    calls_df: Any,
    gaps: list[str],
) -> list[dict]:
    """Pair C: oracle complex direction vs sector_central call tier.

    Maps each oracle complex to sector_central ids via rotation_groups membership
    overlap.  Unambiguous overlaps only — if multiple calls match a complex, use
    the majority direction.
    """
    records: list[dict] = []
    try:
        if oracle_state is None:
            gaps.append("pair-c: oracle_state unavailable (oracle_state.json absent)")
            return records
        if calls_df is None or len(calls_df) == 0:
            gaps.append("pair-c: sector_central/calls.parquet absent or empty")
            return records

        import pandas as pd  # noqa: PLC0415

        complexes = oracle_state.get("complexes") or []
        asof_oracle = oracle_state.get("asof") or "unknown"

        # Build a lookup from complex_id -> member basket ids
        complex_members: dict[str, list[str]] = {}
        for grp in rotation_groups:
            cid = grp.get("id") or ""
            members = grp.get("members") or []
            if cid:
                complex_members[cid] = [str(m) for m in members]

        # Get latest sector_central calls (one row per id = latest by date)
        latest_calls = calls_df.sort_values("date").groupby("id").last().reset_index()
        sc_label_map: dict[str, str] = dict(
            zip(latest_calls["id"], latest_calls["label"])
        )
        asof_sc = calls_df["date"].max() if len(calls_df) > 0 else "unknown"

        for cx in complexes:
            cx_id = cx.get("id") or ""
            cx_direction = cx.get("direction") or ""
            cx_tier = cx.get("tier") or ""

            if not cx_id or not cx_direction:
                continue

            # Only consider complexes with a clear directional stance
            is_oracle_bullish = cx_direction in _BULLISH_DIRECTIONS
            is_oracle_bearish = cx_direction in _BEARISH_DIRECTIONS
            if not is_oracle_bullish and not is_oracle_bearish:
                continue

            # Find matching sector_central ids from membership overlap
            members = complex_members.get(cx_id, [])
            if not members:
                continue

            # Collect matching sc labels (strip "b-" prefix for lookup)
            sc_matches: list[str] = []
            for m in members:
                # Try direct match and with b- prefix
                for key in [m, f"b-{m}", m.replace("us_sector_", "")]:
                    label = sc_label_map.get(key)
                    if label:
                        sc_matches.append(label)
                        break

            if not sc_matches:
                continue

            # Majority SC direction for this complex
            n_bullish = sum(1 for l in sc_matches if l in _SC_BULLISH_LABELS)
            n_bearish = sum(1 for l in sc_matches if l in _SC_BEARISH_LABELS)
            n_total = len(sc_matches)

            if n_total < 2:
                continue  # too thin for an unambiguous match

            sc_majority_bullish = n_bullish > n_bearish
            sc_majority_bearish = n_bearish > n_bullish

            # Contradiction: oracle bullish + sc majority bearish (or vice versa)
            if is_oracle_bullish and sc_majority_bearish:
                as_of = str(max(str(asof_oracle), str(asof_sc)))
                records.append(_record(
                    pair_id=f"oracle-vs-sector_central:{cx_id}",
                    a_artifact="site/basketdata/oracle_state.json",
                    a_reading=f"complex={cx_id} direction={cx_direction} tier={cx_tier}",
                    b_artifact="data/sector_central/calls.parquet",
                    b_reading=(
                        f"sector_central plurality=bearish "
                        f"({n_bearish}/{n_total} Reduce/Cautious calls, "
                        f"rest Neutral/mixed, n_matched={n_total})"
                    ),
                    kind="directional-opposition",
                    severity="tension",
                    as_of=as_of,
                    note=(
                        f"Oracle marks complex '{cx_id}' as {cx_direction} while "
                        f"sector_central shows plurality Reduce/Cautious calls "
                        f"({n_bearish}/{n_total} matched members, rest Neutral/mixed).  "
                        "Rotation vs sector-level signal disagree.  "
                        "Display-only; both are context signals."
                    ),
                ))
            elif is_oracle_bearish and sc_majority_bullish:
                as_of = str(max(str(asof_oracle), str(asof_sc)))
                records.append(_record(
                    pair_id=f"oracle-vs-sector_central:{cx_id}",
                    a_artifact="site/basketdata/oracle_state.json",
                    a_reading=f"complex={cx_id} direction={cx_direction} tier={cx_tier}",
                    b_artifact="data/sector_central/calls.parquet",
                    b_reading=(
                        f"sector_central plurality=bullish "
                        f"({n_bullish}/{n_total} Constructive/Accumulate calls, "
                        f"rest Neutral/mixed, n_matched={n_total})"
                    ),
                    kind="directional-opposition",
                    severity="tension",
                    as_of=as_of,
                    note=(
                        f"Oracle marks complex '{cx_id}' as {cx_direction} while "
                        f"sector_central shows plurality Constructive/Accumulate calls "
                        f"({n_bullish}/{n_total} matched members, rest Neutral/mixed).  "
                        "Rotation vs sector-level signal disagree.  "
                        "Display-only; both are context signals."
                    ),
                ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-c failed: %s", exc)
        gaps.append(f"pair-c: {exc}")
    return records


def _pair_d_vol_regime_vs_market_state(
    world_state: dict,
    gaps: list[str],
) -> list[dict]:
    """Pair D: vol_regime label vs market_state verdict."""
    records: list[dict] = []
    try:
        vol = world_state.get("vol") or {}
        verdict_block = world_state.get("verdict") or {}

        vol_label = vol.get("regime")
        verdict = verdict_block.get("verdict")
        as_of = verdict_block.get("asof") or vol.get("asof") or "unknown"

        if vol_label is None or verdict is None:
            gaps.append("pair-d: missing vol_regime.regime or verdict in world_state")
            return records

        if vol_label in _LOW_VOL_LABELS and verdict in _RISK_OFF_VERDICTS:
            records.append(_record(
                pair_id="vol_regime-vs-market_state",
                a_artifact="data/regime/latest.json:vol_regime",
                a_reading=f"vol_regime={vol_label} (low vol)",
                b_artifact="data/market_state/latest.json",
                b_reading=f"verdict={verdict}",
                kind="label-tension",
                severity="note",
                as_of=str(as_of),
                note=(
                    f"Vol regime is {vol_label} (low realized vol) while market_state "
                    f"signals {verdict}.  Consistent with complacency or 'calm before "
                    "storm' regimes.  Display-only context."
                ),
            ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-d failed: %s", exc)
        gaps.append(f"pair-d: {exc}")
    return records


def _pair_e_briefing_divergences(
    briefing: dict | None,
    gaps: list[str],
) -> list[dict]:
    """Pair E: ingest briefing.py ticker divergences from site/intelligence/briefing.json.

    Does NOT recompute — reads the already-committed intelligence bundle.
    Returns one summary record (not per-ticker) carrying the count and top-5.
    """
    records: list[dict] = []
    try:
        if briefing is None:
            gaps.append("pair-e: site/intelligence/briefing.json absent or unreadable")
            return records

        divs: list[dict] = briefing.get("divergences") or []
        n = len(divs)
        as_of = briefing.get("as_of") or briefing.get("generated_utc") or "unknown"

        if n == 0:
            return records

        top5 = divs[:5]
        top_tickers = [d.get("ticker", "?") for d in top5]

        records.append(_record(
            pair_id="briefing-divergences",
            a_artifact="site/intelligence/by_ticker.json (demand/tape)",
            a_reading=f"{n} ticker-level demand-vs-supply divergences",
            b_artifact="site/intelligence/briefing.json",
            b_reading=(
                f"n_divergences={n}, top tickers={top_tickers}"
            ),
            kind="directional-opposition",
            severity="note" if n < 20 else "tension",
            as_of=str(as_of),
            note=(
                f"{n} ticker-level demand (news_dir) vs supply (alt+radar) "
                "direction disagreements detected by engine/briefing.py.  "
                f"Top 5: {', '.join(top_tickers)}.  "
                "These are pre-computed; no recomputation here.  "
                "Display-only context (news_dir×supply_dir sign-product < 0 or "
                "early_edge/crowded_top labels)."
            ),
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-e failed: %s", exc)
        gaps.append(f"pair-e: {exc}")
    return records


def _pair_f_cross_asset_confirm(
    regime_latest: dict | None,
    gaps: list[str],
) -> list[dict]:
    """Pair F: cross_asset_confirm verdict == 'diverge' as macro edge."""
    records: list[dict] = []
    try:
        if regime_latest is None:
            gaps.append("pair-f: data/regime/latest.json absent")
            return records

        ca = regime_latest.get("cross_asset_confirm") or {}
        verdict = ca.get("verdict")
        headline = ca.get("headline_en") or ca.get("headline_zh") or ""
        n_agree = ca.get("agree_pct")
        as_of = regime_latest.get("asof") or "unknown"

        if verdict != "diverge":
            return records

        records.append(_record(
            pair_id="cross_asset_confirm-diverge",
            a_artifact="data/regime/latest.json:cross_asset_confirm (bonds/FX)",
            a_reading="bonds+FX cross-asset leg readings",
            b_artifact="data/regime/latest.json:regime (equity)",
            b_reading=f"cross_asset_confirm verdict=diverge, agree_pct={n_agree}",
            kind="directional-opposition",
            severity="tension",
            as_of=str(as_of),
            note=(
                f"cross_asset_confirm signals 'diverge': bonds/FX and equity "
                f"readings disagree.  {headline}  "
                "Note: MOVE-vs-VIX, dollar/EM-FX, FX carry are COINCIDENT not leading "
                "(engine/cross_asset_confirm.py:15-20).  "
                "Display-only macro context."
            ),
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-f failed: %s", exc)
        gaps.append(f"pair-f: {exc}")
    return records


def _pair_g_oracle_out_vs_entry_buy(
    oracle_state: dict | None,
    rotation_groups: list[dict],
    standouts: dict | None,
    gaps: list[str],
) -> list[dict]:
    """Pair G: oracle complex out-rotation vs entry buy-list member (PR-A4).

    When a complex has direction 'out' or 'decelerating' in oracle_state.json AND
    a ticker on the us_standouts.json buy list belongs to that complex via the
    rotation_groups basket membership, emit a 'tension' annotation.

    Ticker→complex mapping:
        rotation_groups[].members (basket ids)
        → data/baskets/membership.json active tickers (removed is None/absent)

    HARD LAWS (encoded per adjudication):
    - severity: 'tension' max
    - display_only: True always
    - records NEVER gate, NEVER suppress, NEVER reorder the board
    - unmappable tickers: skip silently (fail-open)
    - NO winner field, NO alert escalation
    - annotation text is purely descriptive: naming complex, direction, ticker, lane
    """
    records: list[dict] = []
    try:
        if oracle_state is None:
            gaps.append(
                "pair-g: oracle_state unavailable — "
                "site/basketdata/oracle_state.json absent"
            )
            return records
        if standouts is None:
            gaps.append(
                "pair-g: us_standouts unavailable — "
                "site/factordata/us_standouts.json absent"
            )
            return records

        # ── Build ticker → set[complex_id] from rotation_groups ──────────────
        # rotation_groups[].members = basket ids (strings like "aicompute",
        # "us_sector_energy").  We need basket membership files for ticker lists.
        # Those are passed in as a pre-built map via the caller.
        # We build the map inline if rotation_groups is available.
        complex_basket_members: dict[str, list[str]] = {}
        for grp in rotation_groups:
            cid = grp.get("id") or ""
            members = grp.get("members") or []
            if cid:
                complex_basket_members[cid] = [str(m) for m in members]

        if not complex_basket_members:
            gaps.append(
                "pair-g: rotation_groups empty — "
                "ticker→complex mapping unavailable; pair-g skipped"
            )
            return records

        # ── Identify out-direction complexes from oracle_state ────────────────
        oracle_complexes = oracle_state.get("complexes") or []
        asof_oracle = oracle_state.get("asof") or "unknown"

        out_complexes: dict[str, dict] = {}
        for cx in oracle_complexes:
            cx_id = cx.get("id") or ""
            direction = cx.get("direction") or ""
            if direction in _BEARISH_DIRECTIONS and cx_id:
                out_complexes[cx_id] = cx

        if not out_complexes:
            return records  # no out-direction complexes → nothing to check

        # ── Read buy list from standouts ──────────────────────────────────────
        buy_rows = standouts.get("buy") or []
        asof_standouts = standouts.get("as_of") or "unknown"

        if not buy_rows:
            return records  # empty buy list → nothing to check

        # ── pair-g needs basket_tickers map — passed in via caller ────────────
        # (The caller is responsible for loading baskets/membership.json and
        # building the basket_id → set[ticker] map.  If absent, we skip silently.)
        # We receive it via a kwarg injected by detect_contradictions().
        # Here we use a closure-captured dict populated below in the public API.
        # To avoid changing the function signature mid-stream, the caller passes
        # basket_tickers_map via the 'rotation_groups' parameter extended schema,
        # OR we re-read it here fail-open from the repo path passed via oracle_state.
        # Per the task spec: fail-open on unmappable — we build the map from
        # _basket_tickers_cache if present on the function object (injected by
        # detect_contradictions before calling us), else emit a gap.
        basket_tickers_map: dict[str, set[str]] = getattr(
            _pair_g_oracle_out_vs_entry_buy, "_basket_tickers_cache", {}
        )

        if not basket_tickers_map:
            gaps.append(
                "pair-g: basket_tickers_map not injected — "
                "ticker→complex mapping unavailable; pair-g skipped"
            )
            return records

        # Build ticker → frozenset[complex_id] once
        ticker_to_out_complexes: dict[str, list[str]] = {}
        for cx_id, basket_ids in complex_basket_members.items():
            if cx_id not in out_complexes:
                continue
            for basket_id in basket_ids:
                for ticker in basket_tickers_map.get(basket_id, set()):
                    ticker_to_out_complexes.setdefault(ticker, []).append(cx_id)

        # ── Scan buy list for members of out complexes ────────────────────────
        seen: set[tuple[str, str]] = set()  # (ticker, cx_id) dedupe
        as_of = str(max(str(asof_oracle), str(asof_standouts)))

        for row in buy_rows:
            ticker = row.get("ticker") or ""
            if not ticker:
                continue
            lane = row.get("lane") or "unknown"
            cx_ids = ticker_to_out_complexes.get(ticker, [])

            for cx_id in set(cx_ids):
                key = (ticker, cx_id)
                if key in seen:
                    continue
                seen.add(key)

                cx_info = out_complexes[cx_id]
                cx_name = cx_info.get("name") or cx_id
                cx_name_zh = cx_info.get("name_zh") or cx_name
                cx_direction = cx_info.get("direction") or "out"
                cx_tier = cx_info.get("tier") or ""

                records.append(_record(
                    pair_id=f"oracle-out-vs-entry-buy:{cx_id}:{ticker}",
                    a_artifact="site/basketdata/oracle_state.json",
                    a_reading=(
                        f"complex={cx_id} ({cx_name}) direction={cx_direction} "
                        f"tier={cx_tier}"
                    ),
                    b_artifact="site/factordata/us_standouts.json",
                    b_reading=(
                        f"ticker={ticker} on buy list lane={lane}"
                    ),
                    kind="directional-opposition",
                    severity="tension",
                    as_of=as_of,
                    note=(
                        f"Oracle: {cx_name} rotating {cx_direction}; "
                        f"Entry: {ticker} on buy list (lane={lane}).  "
                        f"Oracle marks complex '{cx_id}' as {cx_direction} while "
                        f"entry board shows {ticker} as a buy (lane={lane}).  "
                        "Rotation direction and entry signal disagree at the complex level.  "
                        "Display-only context; neither cancels the other — the entry signal "
                        "is ticker-level while rotation is complex-level."
                    ),
                ))
    except Exception as exc:  # noqa: BLE001
        log.warning("contradictions pair-g failed: %s", exc)
        gaps.append(f"pair-g: {exc}")
    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_contradictions(
    root: Path | str | None = None,
) -> tuple[list[dict], list[str]]:
    """Detect typed contradiction records across seven bus-artifact pairs.

    Parameters
    ----------
    root:
        Repo root override.  Defaults to three levels above this file.

    Returns
    -------
    (records, gaps)
        records: list of typed contradiction records (may be empty).
        gaps: list of diagnostic strings for sources that could not be read.
        Never raises.
    """
    repo = _repo_root(root)
    data_dir = repo / "data"
    site_dir = repo / "site"

    records: list[dict] = []
    gaps: list[str] = []

    # ── Read world_state (carries regime + verdict + vol + risk_radar_raw) ──
    ws_path = data_dir / "neuralweb" / "world_state.json"
    world_state = _read_json(ws_path) or {}
    if not world_state:
        # Fall back to reading regime/market_state directly (internal retry, not a gap)
        log.debug("contradictions: world_state.json absent — falling back to direct reads")
        regime_raw = _read_json(data_dir / "regime" / "latest.json") or {}
        ms_raw = _read_json(data_dir / "market_state" / "latest.json") or {}
        # Include scale fields so pair-a flip-aware logic works on the fallback path
        # (flip_margin, transition_state, confidence, inflation_score are present in
        # regime/latest.json when the regime engine has run; absent is handled by .get())
        _fc_raw = regime_raw.get("flip_condition")
        world_state = {
            "regime": {
                "quad": regime_raw.get("quad"),
                "growth_score": regime_raw.get("growth_score"),
                "inflation_score": regime_raw.get("inflation_score"),
                "flip_margin": regime_raw.get("flip_margin"),
                "transition_state": regime_raw.get("transition_state"),
                "confidence": regime_raw.get("confidence"),
                "flip_condition": _fc_raw if isinstance(_fc_raw, dict) else None,
                "asof": regime_raw.get("asof"),
            },
            "verdict": {
                "verdict": ms_raw.get("verdict"),
                "asof": ms_raw.get("asof"),
            },
            "risk_radar_raw": regime_raw.get("risk_radar"),
            "vol": {
                "regime": (regime_raw.get("vol_regime") or {}).get("regime"),
                "asof": regime_raw.get("asof"),
            },
        }

    # ── Read oracle_state ────────────────────────────────────────────────────
    oracle_path = site_dir / "basketdata" / "oracle_state.json"
    oracle_state = _read_json(oracle_path)
    if oracle_state is None:
        gaps.append(
            "site/basketdata/oracle_state.json absent — pair-c skipped; "
            "oracle_state is gitignored/Mac-local on this run"
        )

    # ── Read rotation_groups ─────────────────────────────────────────────────
    rg_path = data_dir / "oracle" / "rotation_groups.json"
    rg_raw = _read_json(rg_path) or {}
    rotation_groups: list[dict] = rg_raw.get("complexes") or []
    if not rotation_groups:
        gaps.append(
            "data/oracle/rotation_groups.json absent or empty — "
            "pair-c complex membership mapping unavailable"
        )

    # ── Read sector_central calls.parquet ────────────────────────────────────
    calls_df = None
    sc_path = data_dir / "sector_central" / "calls.parquet"
    if sc_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            calls_df = pd.read_parquet(sc_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("contradictions: calls.parquet read failed — %s", exc)
            gaps.append(f"data/sector_central/calls.parquet: {exc}")
    else:
        gaps.append(
            "data/sector_central/calls.parquet absent — pair-c sector_central skipped"
        )

    # ── Read briefing.json ───────────────────────────────────────────────────
    briefing_path = site_dir / "intelligence" / "briefing.json"
    briefing = _read_json(briefing_path)
    if briefing is None:
        gaps.append(
            "site/intelligence/briefing.json absent — pair-e divergences skipped"
        )

    # ── Read regime/latest.json directly for pair-f ──────────────────────────
    regime_latest = _read_json(data_dir / "regime" / "latest.json")
    if regime_latest is None:
        gaps.append("data/regime/latest.json absent — pair-f skipped")

    # ── Read us_standouts.json for pair-g ────────────────────────────────────
    standouts_path = site_dir / "factordata" / "us_standouts.json"
    standouts = _read_json(standouts_path)
    if standouts is None:
        gaps.append(
            "site/factordata/us_standouts.json absent — pair-g skipped"
        )

    # ── Build basket_tickers_map for pair-g (basket_id → set[active ticker]) ─
    # Uses data/baskets/membership.json.  Fail-open: missing → empty map.
    basket_tickers_map: dict[str, set[str]] = {}
    baskets_mb_path = data_dir / "baskets" / "membership.json"
    baskets_raw = _read_json(baskets_mb_path) or {}
    baskets_dict = baskets_raw.get("baskets") or {}
    if baskets_dict:
        for basket_id, info in baskets_dict.items():
            members = info.get("members") or []
            active: set[str] = set()
            for m in members:
                if isinstance(m, dict):
                    if m.get("removed") is None:
                        t = m.get("ticker")
                        if t:
                            active.add(str(t))
                elif isinstance(m, str):
                    active.add(m)
            basket_tickers_map[basket_id] = active
    else:
        gaps.append(
            "data/baskets/membership.json absent or empty — "
            "pair-g ticker→complex mapping partially unavailable"
        )

    # Inject basket_tickers_map into pair-g via function attribute (fail-open)
    _pair_g_oracle_out_vs_entry_buy._basket_tickers_cache = basket_tickers_map  # type: ignore[attr-defined]

    # ── Run seven pairs ───────────────────────────────────────────────────────
    records.extend(_pair_a_regime_vs_market_state(world_state, gaps))
    records.extend(_pair_b_regime_vector_vs_risk_radar(world_state, gaps))
    records.extend(_pair_c_oracle_vs_sector_central(
        oracle_state, rotation_groups, calls_df, gaps
    ))
    records.extend(_pair_d_vol_regime_vs_market_state(world_state, gaps))
    records.extend(_pair_e_briefing_divergences(briefing, gaps))
    records.extend(_pair_f_cross_asset_confirm(regime_latest, gaps))
    records.extend(_pair_g_oracle_out_vs_entry_buy(
        oracle_state, rotation_groups, standouts, gaps
    ))

    return records, gaps
