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


def assert_recent_history_guard(bars_by_symbol: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> None:
    """Raise iff any symbol's bars carry a date after ``cutoff``. Defense-in-depth
    check called immediately before any PR-3 value is computed — the guard is
    enforced by TRUNCATION upstream, and this call proves the truncation held."""
    for sym, df in bars_by_symbol.items():
        if df is None or df.empty:
            continue
        if df.index.max() > cutoff:
            raise RecentHistoryGuardViolation(
                f"{sym}: bars extend to {df.index.max()}, beyond the recent-history "
                f"guard cutoff {cutoff} — the constant-setting input is contaminated"
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
    constant-setting read)."""
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
    all_rows: list[dict[str, Any]] = []
    all_catalogs: list[pd.DataFrame] = []
    bars_by_symbol: dict[str, pd.DataFrame] = {}

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

        bars_by_symbol[sym] = df
        fns = pilot_replay._fire_fns(sym, plane_id, hashes, registry, ledgers)
        sym_rows = 0
        for group in pilot_replay.FAMILY_GROUPS:
            rows = fns[group](df)
            sym_rows += len(rows)
            all_rows.extend(rows)

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
