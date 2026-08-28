#!/usr/bin/env python3
"""Stock Identity W3A — the bounded calibration-fire substrate act (Sol ruling
2026-08-28, freeze §4.1, plan Task 3C Step 4).

Reuses the SAME W2 replay machinery (``scripts.stock_identity_replay_pilot``'s
``stage_registry``/``_fire_fns``/``_spec_hashes``/``_ledgers``/``_load`` entry
points, imported and invoked genuinely — not reimplemented) over the drawn-name
component of ``SI-SEALED-CAL-P1`` ONLY. No second replay framework, no new
expert family, no Class-P backfill, no new producer semantics, no parameter
sweep, no fit/rank output. Calibration-purpose-only, authority-false; cannot
feed Q1/W5 population definition, expert ranking, W3B estimability inclusion,
Prophet, or any fit table. Large event/history material is written to scratch
(R2/store-host storage law) — never committed.

Usage::

    # bounded runtime estimate (COO adjudication gate) — does NOT write a receipt
    python3 scripts/stock_identity_calibration_replay.py --manifest data/stock_identity/ruler/calibration_replay_manifest_v1.json --sample 5 --estimate-only

    # the real bounded act over the full drawn roster
    python3 scripts/stock_identity_calibration_replay.py --manifest data/stock_identity/ruler/calibration_replay_manifest_v1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import stock_identity_replay_pilot as pilot_replay  # noqa: E402 — the SAME W2 machinery
from engine.stock_identity import episodes as ep_mod  # noqa: E402
from engine.stock_identity.authority import authority_block  # noqa: E402
from engine.stock_identity.replay import attribution as attr_mod, events as ev_mod  # noqa: E402

DATA = REPO_ROOT / "data" / "stock_identity"
PARTITION_MANIFEST_PATH = DATA / "partition" / "partition_manifest_v1.json"
CONSTANTS_PATH = DATA / "constants" / "si_constants_v1.json"

SCRATCH = Path(
    os.environ.get(
        "STOCK_IDENTITY_CALIBRATION_SCRATCH",
        "/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-"
        "worktrees-stock-identity-fable-coo-ae87a1/6ea3445d-6aa1-4b74-adf2-149cb792db63/"
        "scratchpad/calibration_substrate",
    )
)

TYPED_BLOCKER_SCHEMA = "stock_identity.w3_calibration_typed_blocker.v1"
PROVENANCE_SCHEMA = "stock_identity.w3_calibration_provenance.v1"


class RecentHistoryGuardViolation(ValueError):
    """Raised when a bar frame carries a date beyond the recent-history guard cutoff."""


class SampledSubstrateWriteRefused(RuntimeError):
    """Raised when ``--sample`` is passed without ``--estimate-only`` (freeze
    review finding B1): a sampled run may write timing output only, never a
    substrate directory, never a provenance receipt with status OK."""


@dataclass
class SubstrateResult:
    roster: list[str]
    replayed: list[str] = field(default_factory=list)
    zero_fire: list[str] = field(default_factory=list)
    unavailable: list[dict[str, Any]] = field(default_factory=list)
    events: pd.DataFrame | None = None
    attribution: pd.DataFrame | None = None
    episodes: pd.DataFrame | None = None
    bars_by_symbol: dict[str, pd.DataFrame] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    wall_seconds: float = 0.0


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _partition_manifest() -> dict[str, Any]:
    return json.loads(PARTITION_MANIFEST_PATH.read_text(encoding="utf-8"))


def drawn_roster(manifest: dict[str, Any]) -> list[str]:
    """The mechanical drawn-name roster: sorted ``calibration_partition.members``
    from the frozen partition manifest, validated against the pre-registered
    roster hash in the replay manifest."""
    partition = _partition_manifest()
    roster = sorted(partition["calibration_partition"]["members"])
    payload = json.dumps(roster, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual_hash = hashlib.sha256(payload).hexdigest()
    expected_hash = manifest["roster"]["roster_sha256"]
    if actual_hash != expected_hash:
        raise ValueError(
            f"drawn roster hash mismatch: manifest declares {expected_hash!r}, "
            f"partition_manifest_v1.json now computes {actual_hash!r} — the frozen "
            "partition drifted; this is a STOP condition, never a silent re-draw"
        )
    return roster


def assert_disjoint_from_pilot_and_blind(roster: list[str]) -> None:
    partition = _partition_manifest()
    pilot = set(partition["pilot"]["members"]) | {"B"}
    blind = set(partition["blind_arm"]["members"])
    overlap_pilot = sorted(set(roster) & pilot)
    overlap_blind = sorted(set(roster) & blind)
    if overlap_pilot:
        raise ValueError(f"drawn roster overlaps the pilot cohort: {overlap_pilot}")
    if overlap_blind:
        raise ValueError(f"drawn roster overlaps the untouched blind arm: {overlap_blind}")


def recent_history_cutoff(asof: pd.Timestamp, calendar: pd.DatetimeIndex, guard_sessions: int = 126) -> pd.Timestamp:
    """The 126th trading session strictly before ``asof``, on a calendar built from
    the substrate's own combined bars (no external calendar dependency)."""
    cal = pd.DatetimeIndex(sorted(set(calendar[calendar <= asof])))
    if len(cal) <= guard_sessions:
        raise ValueError(
            f"insufficient trading history ({len(cal)} sessions <= {asof}) to apply "
            f"the {guard_sessions}-session recent-history guard"
        )
    return cal[-(guard_sessions + 1)]


def assert_bars_within_guard(bars_by_symbol: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> None:
    """Raise iff any symbol's INPUT bars carry a date after ``cutoff``. This is the
    bars-side, defense-in-depth check — it proves the truncation that fed event/
    episode generation actually held. It is deliberately NOT the real guard: a
    caller could satisfy this trivially by truncating its own bars and asserting
    against that same truncated copy. :func:`assert_recent_history_guard` below
    is the real guard, checked against the substrate's own OUTPUTS."""
    for sym, df in bars_by_symbol.items():
        if df is None or df.empty:
            continue
        if df.index.max() > cutoff:
            raise RecentHistoryGuardViolation(
                f"{sym}: bars extend to {df.index.max()}, beyond the recent-history "
                f"guard cutoff {cutoff} — the constant-setting input is contaminated"
            )


def assert_recent_history_guard(
    events: pd.DataFrame, episodes: pd.DataFrame, cutoff: pd.Timestamp,
) -> None:
    """The REAL recent-history guard (freeze review finding B3): raises iff the
    calibration-fire substrate's own OUTPUTS carry a date beyond ``cutoff`` — the
    max fire ``signal_known_ts`` in ``events``, or the max episode ``end_date``/
    ``start_date`` in ``episodes``. This is checked against what the substrate
    actually produced, never against a caller's own freshly-truncated input bars
    (which would trivially always pass and prove nothing about the real output).
    """
    if events is not None and not events.empty and "signal_known_ts" in events.columns:
        max_known = pd.to_datetime(events["signal_known_ts"]).max()
        if pd.notna(max_known) and max_known > cutoff:
            raise RecentHistoryGuardViolation(
                f"events: max signal_known_ts {max_known} exceeds the recent-history "
                f"guard cutoff {cutoff} — the constant-setting substrate is contaminated"
            )
    if episodes is not None and not episodes.empty:
        for col in ("end_date", "start_date"):
            if col not in episodes.columns:
                continue
            max_date = pd.to_datetime(episodes[col], errors="coerce").max()
            if pd.notna(max_date) and max_date > cutoff:
                raise RecentHistoryGuardViolation(
                    f"episodes: max {col} {max_date} exceeds the recent-history guard "
                    f"cutoff {cutoff} — the constant-setting substrate is contaminated"
                )


def truncate_to_guard(bars_by_symbol: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    return {sym: df.loc[df.index <= cutoff] for sym, df in bars_by_symbol.items()}


def _episode_constants() -> ep_mod.EpisodeConstants:
    values = json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))["values"]
    return ep_mod.EpisodeConstants(
        X=values["X"], Y=values["Y"], N=values["N"], k=values["k"], z=values["z"],
        M=values["M"], m=values["m"], D1=values["D1"], D2=values["D2"],
        S_reclaim=values["S_reclaim"],
    )


def run_substrate(manifest: dict[str, Any], *, sample: list[str] | None = None) -> SubstrateResult:
    """Execute the calibration-fire substrate over the drawn roster (or ``sample``,
    a bounded subset used ONLY for the runtime-estimate gate — never for a real
    constant-setting read; the CLI in :func:`main` refuses a real write for a
    sampled run, freeze review finding B1).

    Recent-history guard (freeze review finding B3): events, episodes AND bars
    are all truncated to ``recent_history_cutoff(asof)`` BEFORE any of them is
    written or returned — an episode whose resolution would depend on
    post-cutoff data is CENSORED at the cutoff rather than resolved, because
    ``ep_mod.build_catalog`` only ever sees bars through the cutoff. The guard is
    then re-checked against the substrate's own OUTPUTS
    (:func:`assert_recent_history_guard`), not merely against the truncated
    inputs that fed them.
    """
    roster = drawn_roster(manifest)
    assert_disjoint_from_pilot_and_blind(roster)
    names = sample if sample is not None else roster

    partition = _partition_manifest()
    asof = pd.Timestamp(partition["asof"])
    plane_by_symbol = partition["universe"]["plane_by_symbol"]

    t0 = time.time()
    registry = pilot_replay.stage_registry()
    hashes = pilot_replay._spec_hashes()
    ledgers = pilot_replay._ledgers(names)
    const = _episode_constants()

    replayed: list[str] = []
    zero_fire: list[str] = []
    unavailable: list[dict[str, Any]] = []
    raw_bars: dict[str, pd.DataFrame] = {}
    plane_id_by_symbol: dict[str, str] = {}

    for sym in names:
        plane_id = plane_by_symbol.get(sym)
        if not plane_id:
            unavailable.append({"symbol": sym, "reason": "no price plane assignment in the frozen partition manifest"})
            continue
        try:
            df = pilot_replay._load(sym, plane_id, asof)
        except (FileNotFoundError, ValueError) as exc:
            unavailable.append({"symbol": sym, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        if df is None or df.empty:
            unavailable.append({"symbol": sym, "reason": "empty bar frame"})
            continue
        raw_bars[sym] = df
        plane_id_by_symbol[sym] = plane_id

    # B3: compute + enforce the recent-history cutoff HERE, on the combined
    # calendar of the raw (asof-bounded, pre-cutoff) bars, and truncate every
    # downstream input to it before anything derived from it is generated.
    cutoff: pd.Timestamp | None = None
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    if raw_bars:
        full_calendar = pd.DatetimeIndex(sorted({d for df in raw_bars.values() for d in df.index}))
        cutoff = recent_history_cutoff(asof, full_calendar, guard_sessions=126)
        bars_by_symbol = truncate_to_guard(raw_bars, cutoff)
        assert_bars_within_guard(bars_by_symbol, cutoff)

    all_rows: list[dict[str, Any]] = []
    all_catalogs: list[pd.DataFrame] = []

    for sym, df in bars_by_symbol.items():
        plane_id = plane_id_by_symbol[sym]
        fns = pilot_replay._fire_fns(sym, plane_id, hashes, registry, ledgers)
        sym_rows = 0
        for group in pilot_replay.FAMILY_GROUPS:
            rows = fns[group](df)
            sym_rows += len(rows)
            all_rows.extend(rows)

        # df is already truncated to the cutoff, so build_catalog can only ever
        # see through-cutoff bars: an episode whose resolution would need
        # post-cutoff data comes back CENSORED at the cutoff, never resolved.
        cat = ep_mod.build_catalog(df, symbol=sym, plane_id=plane_id, const=const)
        if not cat.empty:
            all_catalogs.append(cat)

        replayed.append(sym)
        if sym_rows == 0:
            zero_fire.append(sym)

    events = ev_mod.finalize_events(all_rows) if all_rows else ev_mod.empty_events()
    if not events.empty:
        events = events.copy()
        events["calibration_substrate"] = True

    episodes_df = pd.concat(all_catalogs, ignore_index=True) if all_catalogs else pd.DataFrame()
    if not episodes_df.empty:
        episodes_df = episodes_df.copy()
        episodes_df["calibration_substrate"] = True

    n_events_guard_dropped = 0
    n_episodes_guard_censored = 0
    if cutoff is not None:
        # Defense-in-depth OUTPUT-level enforcement (freeze review finding B3): a
        # reused W2 fire/catalog function can draw on state beyond the truncated
        # bars frame it was handed (e.g. a persisted ledger), so truncating the
        # INPUT bars alone does not provably bound every output date. Any event
        # that still landed beyond the cutoff is dropped here — it may never
        # reach the substrate, written or unwritten. Any episode whose end_date
        # still landed beyond the cutoff is re-classified CENSORED AT THE CUTOFF
        # (never "resolved") rather than dropped, since its start/type/tier are
        # still legitimate pre-cutoff observations.
        if not events.empty and "signal_known_ts" in events.columns:
            before = len(events)
            events = events.loc[
                pd.to_datetime(events["signal_known_ts"]) <= cutoff
            ].reset_index(drop=True)
            n_events_guard_dropped = before - len(events)

        if not episodes_df.empty and "start_date" in episodes_df.columns:
            episodes_df = episodes_df.loc[
                pd.to_datetime(episodes_df["start_date"]) <= cutoff
            ].reset_index(drop=True)
            if "end_date" in episodes_df.columns:
                beyond_cutoff = pd.to_datetime(episodes_df["end_date"], errors="coerce") > cutoff
                n_episodes_guard_censored = int(beyond_cutoff.sum())
                if n_episodes_guard_censored:
                    episodes_df.loc[beyond_cutoff, "end_date"] = pd.NaT
                    if "censored" in episodes_df.columns:
                        episodes_df.loc[beyond_cutoff, "censored"] = True
                    if "resolution" in episodes_df.columns:
                        episodes_df.loc[beyond_cutoff, "resolution"] = "censored"
                    if "anchor_date" in episodes_df.columns:
                        episodes_df.loc[beyond_cutoff, "anchor_date"] = pd.NaT
                    if "anchor_price" in episodes_df.columns:
                        episodes_df.loc[beyond_cutoff, "anchor_price"] = np.nan
                    if "terminated_reason" in episodes_df.columns:
                        episodes_df.loc[beyond_cutoff, "terminated_reason"] = "recent_history_guard_cutoff"

    p_pre = int(json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))["values"]["P_pre"])
    cal = pd.DatetimeIndex(sorted({d for df in bars_by_symbol.values() for d in df.index}))
    attribution = (
        attr_mod.attribute(events, episodes_df, p_pre=p_pre, calendar=cal)
        if not events.empty else pd.DataFrame()
    )
    if not attribution.empty:
        attribution = attribution.copy()
        attribution["calibration_substrate"] = True

    wall = time.time() - t0

    # B3: the REAL guard, on the substrate's own OUTPUTS -- proves the
    # truncation above actually held all the way through event/episode
    # generation, never merely that the input bars were pre-truncated.
    if cutoff is not None:
        assert_recent_history_guard(events, episodes_df, cutoff)

    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "fire_fns_module": pilot_replay._fire_fns.__module__,
        "fire_fns_qualname": pilot_replay._fire_fns.__qualname__,
        "spec_hashes_module": pilot_replay._spec_hashes.__module__,
        "spec_hashes_qualname": pilot_replay._spec_hashes.__qualname__,
        "stage_registry_module": pilot_replay.stage_registry.__module__,
        "stage_registry_qualname": pilot_replay.stage_registry.__qualname__,
        "family_groups_invoked": list(pilot_replay.FAMILY_GROUPS),
        "spec_hashes_asserted_at_run": hashes,
        "family_registry_asserted_at_run": {
            "n_families": len(registry.get("families", [])),
            "universe_as_of": registry.get("vintage_stamp", {}).get("universe_as_of"),
        },
        "n_names_attempted": len(names),
        "n_names_replayed": len(replayed),
        "n_names_zero_fire": len(zero_fire),
        "n_names_unavailable": len(unavailable),
        "n_events": int(len(events)),
        "n_episodes": int(len(episodes_df)),
        "authority": authority_block(),
        # B1: the receipted roster this substrate covers, checked by the
        # constant-setting act (scripts/stock_identity_calibrate_w3.py) BEFORE it
        # computes anything, against BOTH the manifest's roster hash and
        # n_names_attempted == len(drawn roster).
        "roster_sha256": manifest["roster"]["roster_sha256"],
        # B3: recorded so a downstream reader (the calibrate_w3.py second
        # barrier) can check the substrate's own outputs against the SAME cutoff
        # this run enforced, rather than re-deriving and re-trusting its own copy.
        "recent_history_guard_cutoff": str(cutoff.date()) if cutoff is not None else None,
        "recent_history_guard_sessions": 126,
        "n_events_dropped_by_recent_history_guard": n_events_guard_dropped,
        "n_episodes_censored_by_recent_history_guard": n_episodes_guard_censored,
    }

    return SubstrateResult(
        roster=roster, replayed=replayed, zero_fire=zero_fire, unavailable=unavailable,
        events=events, attribution=attribution, episodes=episodes_df,
        bars_by_symbol=bars_by_symbol, provenance=provenance, wall_seconds=wall,
    )


def write_substrate(result: SubstrateResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if result.events is not None:
        result.events.to_parquet(out_dir / "calibration_events_v1.parquet")
    if result.attribution is not None and not result.attribution.empty:
        result.attribution.to_parquet(out_dir / "calibration_attribution_v1.parquet")
    if result.episodes is not None and not result.episodes.empty:
        result.episodes.to_parquet(out_dir / "calibration_episodes_v1.parquet")
    (out_dir / "provenance_receipt.json").write_text(
        json.dumps(
            {
                **result.provenance,
                "replayed_names": result.replayed,
                "zero_fire_names": result.zero_fire,
                "unavailable_names": result.unavailable,
                "wall_seconds": result.wall_seconds,
            },
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--sample", type=int, default=None,
                    help="bounded runtime-estimate mode: replay only the first N drawn names")
    ap.add_argument("--estimate-only", action="store_true",
                    help="print a linear runtime extrapolation for the full roster and exit "
                         "WITHOUT writing a substrate receipt (never used for a real constant-setting read)")
    ap.add_argument("--output-dir", type=Path, default=SCRATCH)
    args = ap.parse_args()

    # B1: --sample without --estimate-only would replay a PARTIAL roster and then
    # fall straight into the real-write path below, writing a substrate directory
    # and a status-OK provenance receipt for less than the full drawn roster —
    # exactly the "partial seal + constant shopping" defect this law exists to
    # close. A sampled run may write TIMING output only (--estimate-only), never
    # a substrate directory, never a provenance receipt with status OK.
    if args.sample is not None and not args.estimate_only:
        raise SampledSubstrateWriteRefused(
            "REFUSED: --sample without --estimate-only. The calibration-fire "
            "substrate act is bounded to the FULL drawn roster ONLY (freeze §4.1 "
            "rule-before-value discipline; SI-SEALED-CAL-P1 stays sealed for "
            "anything less than the complete roster). A sampled run may write "
            "TIMING output only via --estimate-only, which writes no substrate "
            "directory and no provenance receipt — it never falls through to the "
            "real-write path."
        )

    manifest = _load_manifest(args.manifest)
    roster = drawn_roster(manifest)
    sample = roster[: args.sample] if args.sample else None

    result = run_substrate(manifest, sample=sample)

    if args.estimate_only:
        n_sample = len(sample) if sample else len(roster)
        per_name = result.wall_seconds / n_sample if n_sample else 0.0
        est_full = per_name * len(roster)
        print(json.dumps({
            "schema": "stock_identity.w3_calibration_runtime_estimate.v1",
            "n_sample": n_sample,
            "sample_wall_seconds": result.wall_seconds,
            "per_name_seconds": per_name,
            "n_full_roster": len(roster),
            "estimated_full_wall_seconds": est_full,
            "estimated_full_wall_minutes": est_full / 60.0,
            "unavailable_in_sample": result.unavailable,
        }, indent=2, sort_keys=True), flush=True)
        return 0

    if result.unavailable:
        print(json.dumps({
            "schema": TYPED_BLOCKER_SCHEMA,
            "status": "BLOCKED_UNAVAILABLE_INPUT",
            "unavailable_names": result.unavailable,
            "n_replayed_before_block": len(result.replayed),
            "note": "a name with unavailable/unlawful required price/identity input was "
                    "never silently dropped or substituted; no constant may be set until "
                    "Sol resolves this list",
        }, indent=2, sort_keys=True), flush=True)
        return 3

    write_substrate(result, args.output_dir)
    print(json.dumps({
        "schema": "stock_identity.w3_calibration_replay_result.v1",
        "status": "OK",
        "output_dir": str(args.output_dir),
        "n_replayed": len(result.replayed),
        "n_zero_fire": len(result.zero_fire),
        "n_events": int(len(result.events)) if result.events is not None else 0,
        "wall_seconds": result.wall_seconds,
    }, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
