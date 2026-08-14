#!/usr/bin/env python3
"""Build the registered W1-A1 B-only Stock Identity amendment.

This is intentionally not a stage of ``stock_identity_build_atlas.py``.  The W1
universe, pilot, partitions, constants, combined artifacts, census, and GOLD chart
are sealed.  A1 reads those objects, computes one design-touched Barrick row against
the frozen W1 context, and writes only its registered append-only paths plus one
reversible disclosure block in the existing GOLD markdown dossier.

The command has no collection fallback, parameter sweep, repartition, recalibration,
or universe rebuild.  ``--validate-only`` performs every available preflight without
writing.  The normal run computes into an OS temporary directory, validates the full
staged result, publishes the governing receipt last, and refuses any overwrite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity import dossier as dossier_mod  # noqa: E402
from engine.stock_identity import episodes as ep_mod  # noqa: E402
from engine.stock_identity import fingerprint as fp_mod  # noqa: E402
from engine.stock_identity import hygiene as hyg_mod  # noqa: E402
from engine.stock_identity import partition as part_mod  # noqa: E402
from engine.stock_identity import state as state_mod  # noqa: E402
from engine.stock_identity.authority import AUTHORITY_KEYS, authority_block  # noqa: E402
from engine.stock_identity.pilot import (  # noqa: E402
    AMENDMENT_ID,
    W1_SEALED_MINER_PROBE,
    W1A1_EFFECTIVE_MINER_PROBE,
)
from engine.stock_identity.plane import (  # noqa: E402
    PLANE_BASKETS,
    load_symbol,
    primary_planes,
)

ASOF = pd.Timestamp("2026-08-13")
BUILD_DATE = "2026-08-14"
SYMBOL = "B"
PRICE_PLANE_ID = PLANE_BASKETS

DATA = REPO_ROOT / "data" / "stock_identity"
RESEARCH = REPO_ROOT / "research" / "stock_identity"
REGISTRATION = RESEARCH / "W1_IDENTITY_ATLAS_V0_REGISTRATION.md"
MANIFEST_PATH = DATA / "partition" / "partition_manifest_v1.json"
CONSTANTS_PATH = DATA / "constants" / "si_constants_v1.json"
B_SOURCE_RELATIVE_PATH = "data/baskets/ohlcv/B.parquet"
B_SOURCE_PATH = REPO_ROOT / B_SOURCE_RELATIVE_PATH
DISCLOSURE_ONLY_PATH = "research/stock_identity/dossiers/GOLD.md"

# Machine-checked in tests.  No frozen W1 path belongs here.
OUTPUT_PATHS: tuple[str, ...] = (
    "data/stock_identity/amendments/w1a1_gold_wrong_issuer.json",
    "data/stock_identity/fingerprints/amendments/w1a1_b_fingerprint_v0.parquet",
    "data/stock_identity/state/amendments/w1a1_b_state_daily.parquet",
    "data/stock_identity/episodes/amendments/w1a1_b_episode_catalog_v0.parquet",
    "data/stock_identity/episodes/amendments/B.json",
    "research/stock_identity/dossiers/B.md",
    "research/stock_identity/dossiers/B.svg",
)
RECEIPT_RELATIVE_PATH = OUTPUT_PATHS[0]

FROZEN_SHA256: dict[str, str] = {
    "data/stock_identity/partition/partition_manifest_v1.json":
        "b1f82f842350e39ac7a73214fd8ebd58b175b52fdf42b3a0fb5a2d03143a5d48",
    "data/stock_identity/partition/universe_snapshot_v1.parquet":
        "9f22807e7cb6ba570f1963de945b7be77461a1788608754e25db6235f4fe3730",
    "data/stock_identity/constants/si_constants_v1.json":
        "276d4ad267ab8711942943e306e844bfdff1f17a051bd17a9d460c1e428fc648",
    "data/stock_identity/fingerprints/fingerprint_spec.json":
        "bbefcd5b72915435acb8714d7892b79e010cb49d394b3222d89575c7b022dee0",
    "data/stock_identity/fingerprints/pilot_fingerprint_v0.parquet":
        "2bdef8763b0c73a6df3f27e8307246887b7b9dc982f66331ba4d96ff09d72ba3",
    "data/stock_identity/state/pilot_state_daily.parquet":
        "e2c43f8761431c62506311e61fa387c70433f82bde8143b564fdf87da7ee485e",
    "data/stock_identity/episodes/pilot_episode_catalog_v0.parquet":
        "3216f6cbbf539584dba31caf30e09b6e76e0297ca34698fcb0235cf6e0d6bc0f",
    "data/stock_identity/episodes/pilot/GOLD.json":
        "be8a1d053c6fc9f639017abb4cf7f3063e7bde8229d9a1622dedd38a02ff16d1",
    "data/stock_identity/census/coverage_census_v0.parquet":
        "d64d37c0ab8e0729aa732f2a68a183dd08e0ca3336e9a4a71975772f28c0b4cd",
    "data/stock_identity/census/coverage_census_v0.md":
        "cf1a818749802bf6143656cfc06efa8ad95d3e87570a011726766c461bf371bb",
    DISCLOSURE_ONLY_PATH:
        "2675b5be60cc09a37324e697bb62c20679b8f21cfe4d268f5082ce0730861558",
    "research/stock_identity/dossiers/GOLD.svg":
        "e4e6466f2b4535b97d2fae4eb3eb7e39c1a40600343d955f0e0fe843d7df49db",
}

REFERENCE_SHA256: dict[str, str] = {
    "raw_all.parquet": "ca9c5e5ac78c9a1913a145f8763a2bea84cd80a4a10d6fd2f4d095377f021a08",
    "univ_ew.parquet": "80f5ab3c80aa44da26e17ca58d8a14db930e5d3c03e45031c4c9505c3edba70a",
    "strata.parquet": "67ae54370dfd2279583f99a16475865796542b786cd983a1e94da27edb33f769",
}

B_SOURCE_SHA256 = "dc126c36c6fa07b37ca212051d2a194758725330bfed9c5b6112701b12be6b5f"
GOLD_ANNOTATION_BEGIN = "<!-- SI-W1-A1-GOLD-WRONG-ISSUER:BEGIN -->"
GOLD_ANNOTATION_END = "<!-- SI-W1-A1-GOLD-WRONG-ISSUER:END -->"

GOLD_ANNOTATION = "\n".join(
    (
        GOLD_ANNOTATION_BEGIN,
        "> **Post-seal identity annotation — W1-A1, 2026-08-14.** The sealed figures",
        "> below describe **Gold.com, Inc.** (fka A-Mark Precious Metals; EDGAR CIK",
        "> **1591588**), a bullion dealer whose A-Mark tape begins 2014-03-17 and moved",
        "> from `AMRK` to NYSE `GOLD` on 2025-12-02. They do **not** describe Barrick",
        "> and are not miner-neighborhood evidence. **Barrick Mining Corporation**",
        "> (EDGAR CIK **756894**) has traded as NYSE `B` since 2025-05-09; the registered",
        "> B-only W1-A1 addendum is the effective miner-probe record.",
        ">",
        "> Preregistration discipline: the historical `miner neighborhood probe` row",
        "> and false `continuous Barrick history` hygiene row below remain byte-for-byte",
        "> as superseded sealed output. No measured GOLD row, value, episode, state,",
        "> percentile, census cell, or chart was changed. Removing this marked envelope",
        "> reconstructs the original dossier exactly; `GOLD.svg` is unchanged.",
        GOLD_ANNOTATION_END,
    )
)

B_DOSSIER_PROLOGUE = (
    "**Registered W1-A1 addendum (2026-08-14).** This is the design-touched Barrick "
    "Mining Corporation instrument (EDGAR CIK 756894), added as the effective miner "
    "probe after the sealed W1 `GOLD` row was verified as Gold.com/A-Mark dealer "
    "behavior. It is an additive dossier, not a retroactive substitution: B remains "
    "outside the frozen W1 universe, pilot manifest, blind arm, sealed calibration "
    "partition, every future blind extension, and every confirmatory grade. Percentiles "
    "are a B-only hypothetical insertion into the frozen 2,780-name W1 reference; no "
    "existing rank changed. Frozen UNIV_EW includes GOLD's dealer context as one small "
    "component and is retained only for comparability, never as miner evidence. The "
    "curated `baskets_ohlcv_v1` tape begins **2014-01-02**; that is a data floor, not "
    "Barrick's birth, and it cannot cover the pre-2014 portion of the 2011-2015 gold bear."
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False
    )
    if check and proc.returncode:
        raise SystemExit(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def _require_ancestor(ancestor: str, descendant: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", ancestor):
        raise SystemExit(f"{label}: expected a full 40-character lowercase commit SHA")
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"{label}: {ancestor} is not an ancestor of {descendant}")


def _validate_clean_pushed_registration() -> str:
    status = _git("status", "--porcelain=v1")
    if status:
        raise SystemExit(
            "REFUSING: registration run requires a clean worktree; commit and push the "
            "registration before computing\n" + status
        )
    head = _git("rev-parse", "HEAD")
    upstream = _git("rev-parse", "@{u}")
    if head != upstream:
        raise SystemExit(
            f"REFUSING: HEAD {head} is not the pushed upstream registration {upstream}"
        )
    _require_ancestor(_git("rev-parse", "origin/main"), head, "fresh-main gate")
    registration_at_head = _git("show", f"{head}:{REGISTRATION.relative_to(REPO_ROOT)}")
    if AMENDMENT_ID not in registration_at_head:
        raise SystemExit("REFUSING: pushed HEAD does not contain the A1 registration")
    return head


def _validate_prerequisites(pr_5613_merge: str, pr_5632_merge: str) -> None:
    origin_main = _git("rev-parse", "origin/main")
    _require_ancestor(pr_5613_merge, origin_main, "PR #5613 merge receipt")
    _require_ancestor(pr_5632_merge, origin_main, "PR #5632 merge receipt")

    if not B_SOURCE_PATH.exists():
        raise SystemExit(f"missing prerequisite B input {B_SOURCE_PATH}")
    if _sha256(B_SOURCE_PATH) != B_SOURCE_SHA256:
        raise SystemExit("B input hash differs from the registered PR #5632 receipt")

    cfg = yaml.safe_load((REPO_ROOT / "config.yml").read_text(encoding="utf-8")) or {}
    ack = str((((cfg.get("quality") or {}).get("reused_ticker_acks") or {}).get("GOLD", "")))
    required = ("Gold.com", "1591588", "756894", "2025-12-02", "2025-05-09", "PR #5632")
    if any(token not in ack for token in required):
        raise SystemExit("config.yml GOLD acknowledgement lacks the registered identity receipts")
    if "KNOWN CONSUMER DEFECT" in ack or "NO store file under 'B'" in ack:
        raise SystemExit("config.yml GOLD acknowledgement still carries the pre-#5632 status tail")

    breaks = yaml.safe_load(
        (REPO_ROOT / "config" / "theme_graph_identity_breaks.yml").read_text(encoding="utf-8")
    ) or {}
    rows = [r for r in breaks.get("breaks", []) if r.get("symbol") == "GOLD"]
    if len(rows) != 1 or "1591588" not in str(rows[0]) or "756894" not in str(rows[0]):
        raise SystemExit("ratified GOLD identity-break receipt is missing or ambiguous")


def _validate_registration() -> dict[str, Any]:
    text = REGISTRATION.read_text(encoding="utf-8")
    required = (
        AMENDMENT_ID,
        "before the only artifact-producing A1 run",
        "Procedural-deviation ledger",
        "effective analytical miner probe",
        B_SOURCE_SHA256,
        REFERENCE_SHA256["raw_all.parquet"],
        "measured_rows_mutated: false",
    )
    if any(token not in text for token in required):
        raise SystemExit("A1 registration is incomplete or does not pin the declared run")
    for relative in OUTPUT_PATHS:
        if f"`{relative}`" not in text:
            raise SystemExit(f"A1 registration does not name output {relative}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    procedure_hash, _ = part_mod.partition_procedure_sha256(REGISTRATION)
    if procedure_hash != manifest["partition_procedure_sha256"]:
        raise SystemExit("appending A1 moved the sealed §4 procedure hash")
    if pd.Timestamp(manifest["asof"]) != ASOF:
        raise SystemExit("W1 manifest asof differs from the registered A1 asof")
    return manifest


def _validate_frozen_hashes(*, skip_gold_markdown: bool = False) -> None:
    for relative, expected in FROZEN_SHA256.items():
        if skip_gold_markdown and relative == DISCLOSURE_ONLY_PATH:
            continue
        path = REPO_ROOT / relative
        if not path.exists() or _sha256(path) != expected:
            raise SystemExit(f"frozen W1 artifact drift: {relative}")


def _validate_outputs_absent() -> None:
    present = [relative for relative in OUTPUT_PATHS if (REPO_ROOT / relative).exists()]
    png = REPO_ROOT / "research/stock_identity/dossiers/B.png"
    if png.exists():
        present.append(str(png.relative_to(REPO_ROOT)))
    if present:
        raise SystemExit("REFUSING to overwrite A1 output(s): " + ", ".join(present))


def _validate_b_membership(manifest: dict[str, Any]) -> pd.DataFrame:
    snapshot_path = DATA / "partition" / "universe_snapshot_v1.parquet"
    snapshot = pd.read_parquet(snapshot_path)
    snapshot_symbols = set(snapshot["symbol"].astype(str))
    if "GOLD" not in snapshot_symbols or SYMBOL in snapshot_symbols:
        raise SystemExit("sealed snapshot membership does not match the A1 registration")
    if "GOLD" not in set(manifest["pilot"]["members"]) or SYMBOL in set(
        manifest["pilot"]["members"]
    ):
        raise SystemExit("sealed pilot membership does not match the A1 registration")
    if SYMBOL in set(manifest["blind_arm"]["members"]):
        raise SystemExit("B unexpectedly appears in the sealed blind arm")
    if SYMBOL in set(manifest["calibration_partition"]["members"]):
        raise SystemExit("B unexpectedly appears in the sealed calibration partition")

    planes = primary_planes(REPO_ROOT)
    if planes.get(SYMBOL) != PRICE_PLANE_ID:
        raise SystemExit(f"B primary plane must be {PRICE_PLANE_ID}, got {planes.get(SYMBOL)}")
    duplicate = DATA / "ohlcv" / "B.parquet"
    if duplicate.exists():
        raise SystemExit(f"prohibited duplicate program-owned B plane exists: {duplicate}")
    if "GOLD" in hyg_mod.COMPUTE_BLOCKLIST:
        raise SystemExit("GOLD must not be compute-blocked: its dealer tape is valid")
    return snapshot


def _validate_b_source() -> pd.DataFrame:
    frame = load_symbol(SYMBOL, PRICE_PLANE_ID, REPO_ROOT)
    if len(frame) != 3172:
        raise SystemExit(f"B source row count drifted: expected 3172, got {len(frame)}")
    if frame.index.min() != pd.Timestamp("2014-01-02") or frame.index.max() != ASOF:
        raise SystemExit("B source date range differs from the registered receipt")
    if list(frame.columns) != ["open", "high", "low", "close", "volume"]:
        raise SystemExit(f"B source columns drifted: {list(frame.columns)}")
    return frame.loc[frame.index <= ASOF]


def _validate_reference(reference_dir: Path) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    for name, expected in REFERENCE_SHA256.items():
        path = reference_dir / name
        if not path.exists() or _sha256(path) != expected:
            raise SystemExit(f"frozen W1 reference checkpoint drift: {path}")

    raw = pd.read_parquet(reference_dir / "raw_all.parquet")
    if "symbol" in raw.columns:
        raw = raw.set_index("symbol")
    if raw.shape != (2780, 64) or not raw.index.is_unique:
        raise SystemExit(f"raw W1 reference shape/index drifted: {raw.shape}")
    symbols = set(raw.index.astype(str))
    if "GOLD" not in symbols or SYMBOL in symbols:
        raise SystemExit("raw W1 reference must contain GOLD and exclude B")

    factor_frame = pd.read_parquet(reference_dir / "univ_ew.parquet")
    if list(factor_frame.columns) != ["UNIV_EW"]:
        raise SystemExit("UNIV_EW reference schema drifted")
    if not factor_frame.index.is_unique or not factor_frame.index.is_monotonic_increasing:
        raise SystemExit("UNIV_EW reference index is not unique and sorted")
    if pd.Timestamp(factor_frame.index.max()) != ASOF:
        raise SystemExit("UNIV_EW reference does not end at the frozen asof")

    strata = pd.read_parquet(reference_dir / "strata.parquet")
    strata_symbols = set(strata["symbol"].astype(str))
    if "GOLD" not in strata_symbols or SYMBOL in strata_symbols:
        raise SystemExit("frozen strata checkpoint must contain GOLD and exclude B")
    return raw, factor_frame["UNIV_EW"], strata


def _load_constants() -> tuple[ep_mod.EpisodeConstants, state_mod.StateConstants, dict[str, Any]]:
    payload = json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))
    v = payload["values"]
    ec = ep_mod.EpisodeConstants(
        X=float(v["X"]), Y=float(v["Y"]), N=int(v["N"]), k=float(v["k"]),
        z=float(v["z"]), M=int(v["M"]), m=int(v["m"]), D1=int(v["D1"]),
        D2=int(v["D2"]), S_reclaim=int(v["S_reclaim"]),
    )
    sc = state_mod.StateConstants(
        g=float(v["g"]), theta_dw=float(v["theta_dw"]),
        theta_bd=float(v["theta_bd"]), theta_pb=float(v["theta_pb"]),
        theta_up=float(v["theta_up"]), J=float(v["J"]), V=int(v["V"]),
        E=int(v["E"]), R=int(v["R"]),
    )
    return ec, sc, payload


def _stamp_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for key, value in authority_block().items():
        out[f"authority_{key}"] = value
    return out


def _assert_zero_authority_frame(frame: pd.DataFrame, label: str) -> None:
    for key in AUTHORITY_KEYS:
        column = f"authority_{key}"
        if column not in frame.columns or bool(frame[column].any()):
            raise SystemExit(f"{label}: {column} is missing or not all-false")


def _schema_like(frame: pd.DataFrame, frozen_path: Path, label: str) -> pd.DataFrame:
    frozen_columns = list(pd.read_parquet(frozen_path).columns)
    missing = [c for c in frozen_columns if c not in frame.columns]
    extra = [c for c in frame.columns if c not in frozen_columns]
    if missing or extra:
        raise SystemExit(f"{label} schema drift: missing={missing}, extra={extra}")
    return frame[frozen_columns]


def _gold_markdown_with_annotation() -> str:
    path = REPO_ROOT / DISCLOSURE_ONLY_PATH
    original = path.read_text(encoding="utf-8")
    if _sha256(path) != FROZEN_SHA256[DISCLOSURE_ONLY_PATH]:
        raise SystemExit("GOLD.md no longer matches the registered pre-annotation hash")
    if GOLD_ANNOTATION_BEGIN in original or GOLD_ANNOTATION_END in original:
        raise SystemExit("GOLD.md already carries an A1 marker")
    anchor = "\n\n## Identity"
    if original.count(anchor) != 1:
        raise SystemExit("GOLD.md standing authority/Identity boundary is ambiguous")
    annotated = original.replace(anchor, f"\n\n{GOLD_ANNOTATION}{anchor}", 1)
    restored = annotated.replace(f"\n\n{GOLD_ANNOTATION}\n\n", "\n\n", 1)
    if hashlib.sha256(restored.encode("utf-8")).hexdigest() != FROZEN_SHA256[
        DISCLOSURE_ONLY_PATH
    ]:
        raise SystemExit("GOLD annotation is not mechanically reversible")
    return annotated


def _render_b_chart(
    *, stage_path: Path, frame: pd.DataFrame, states: pd.Series, catalog: pd.DataFrame
) -> None:
    try:
        import matplotlib
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "matplotlib is required for the registered B.svg output; rerun with the "
            "workspace plotting runtime"
        ) from exc
    matplotlib.rcParams["svg.hashsalt"] = "SI-W1-A1-B-2026-08-14"
    written = dossier_mod.render_chart(
        symbol="B · curated tape floor 2014-01-02",
        df=frame,
        states=states,
        catalog=catalog,
        out_path=stage_path,
    )
    if written.suffix != ".svg" or written != stage_path:
        raise SystemExit(
            "registered B.svg exceeded the renderer limit; no PNG fallback is authorized"
        )
    svg = stage_path.read_text(encoding="utf-8")
    svg = re.sub(
        r"<dc:date>.*?</dc:date>",
        "<dc:date>2026-08-14T00:00:00+00:00</dc:date>",
        svg,
        count=1,
        flags=re.S,
    )
    if "2014-01-02" not in svg:
        raise SystemExit("B.svg is missing the registered visible tape-floor watermark")
    stage_path.write_text(svg, encoding="utf-8")


def _build_dossier(
    *,
    frame: pd.DataFrame,
    states: pd.DataFrame,
    catalog: pd.DataFrame,
    raw_row: pd.Series,
    percentile_row: pd.Series,
    unstable_row: pd.Series,
    constants: dict[str, Any],
    manifest: dict[str, Any],
    chart_relative_path: str,
) -> str:
    hygiene = dict(
        hyg_mod.check_symbol(SYMBOL, repo_root=REPO_ROOT, first_date=frame.index.min())
    )
    flags = list(hygiene.get("flags") or [])
    notes = dict(hygiene.get("notes") or {})
    flags.append("lineage_receipt")
    notes["lineage_receipt"] = (
        "Barrick Mining Corporation, EDGAR CIK 756894; NYSE B since 2025-05-09. "
        "The curated B tape is the registered W1-A1 input. Retired NYSE GOLD is now "
        "Gold.com/A-Mark and is a different instrument."
    )
    hygiene["flags"] = flags
    hygiene["notes"] = notes

    shares = state_mod.state_share_by_year(states["state"])
    snapshot_row = {
        "symbol": SYMBOL,
        "price_plane_id": PRICE_PLANE_ID,
        "first_date": frame.index.min(),
        "last_date": frame.index.max(),
        "n_rows": int(len(frame)),
        "has_open": "open" in frame.columns,
        "sector": "NOT_STRATIFIED — absent from frozen W1 snapshot",
        "cap_bucket": "NOT_STRATIFIED",
        "vol_tercile": "NOT_STRATIFIED",
        "tape_ended": False,
        "terminated_reason": "right_censored_at_asof (tape active through asof)",
    }
    markdown = dossier_mod.render_markdown(
        symbol=SYMBOL,
        plane_id=PRICE_PLANE_ID,
        snapshot_row=snapshot_row,
        hygiene=hygiene,
        raw=raw_row.to_dict(),
        percentiles=percentile_row.to_dict(),
        coverage={name: bool(pd.notna(value)) for name, value in raw_row.items()},
        unstable=unstable_row.to_dict(),
        catalog=catalog,
        state_shares=shares,
        constants_meta={
            "gap_basis": str(states["gap_basis"].iloc[0]),
            "constants_sha256": constants.get("calibration_sha256", "n/a"),
            "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
            "partition_procedure_sha256": manifest["partition_procedure_sha256"],
            "asof": manifest["asof"],
        },
        chart_rel=chart_relative_path,
        pilot_role=(
            "miner neighborhood probe — Barrick Mining (W1-A1 amendment; outside "
            "the sealed W1 pilot)"
        ),
    )
    markdown = markdown.replace(
        "# B — Identity Atlas v0 dossier",
        "# B — Identity Atlas v0 dossier (W1-A1 addendum)",
        1,
    )
    identity = "\n## Identity"
    if markdown.count(identity) != 1:
        raise SystemExit("B dossier Identity boundary is ambiguous")
    return markdown.replace(identity, f"\n{B_DOSSIER_PROLOGUE}\n{identity}", 1)


def _staged_path(stage_root: Path, relative: str) -> Path:
    path = stage_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _publish_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".w1a1.tmp")
    if temporary.exists():
        raise SystemExit(f"stale publication temporary exists: {temporary}")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def _build_and_stage(
    *,
    stage_root: Path,
    frame: pd.DataFrame,
    raw_reference: pd.DataFrame,
    factor_returns: pd.Series,
    manifest: dict[str, Any],
    registration_commit: str,
    pr_5613_merge: str,
    pr_5632_merge: str,
    pull_request: int,
) -> tuple[dict[str, Any], str]:
    ec, sc, constants = _load_constants()
    states = state_mod.tag_states(frame, PRICE_PLANE_ID, sc)
    catalog = ep_mod.build_catalog(
        frame,
        symbol=SYMBOL,
        plane_id=PRICE_PLANE_ID,
        const=ec,
        states=states["state"],
        terminated_reason="right_censored_at_asof (tape active through asof)",
    )
    raw = fp_mod.compute_raw(
        frame,
        plane_id=PRICE_PLANE_ID,
        asof=ASOF,
        factor_returns=factor_returns,
        catalog_stats=ep_mod.catalog_f3_stats(catalog),
    )
    raw["symbol"] = SYMBOL
    raw_b = pd.DataFrame([raw]).set_index("symbol")

    numeric = list(fp_mod.METRIC_NAMES) + list(fp_mod.DIAGNOSTIC_NUMERIC)
    missing_reference = [name for name in numeric if name not in raw_reference.columns]
    if missing_reference or len(numeric) != 57:
        raise SystemExit(f"frozen percentile field set drifted: missing={missing_reference}")
    joint = pd.concat(
        [raw_reference[numeric], raw_b.reindex(columns=numeric)],
        axis=0,
    )
    if len(joint) != 2781 or not joint.index.is_unique:
        raise SystemExit("B hypothetical insertion did not produce 2,781 unique rows")
    percentiles = fp_mod.cross_sectional_percentiles(joint, numeric)
    unstable = fp_mod.unstable_flags(percentiles)

    raw_row = raw_b.loc[SYMBOL]
    percentile_row = percentiles.loc[SYMBOL]
    unstable_row = unstable.loc[SYMBOL]

    fingerprint_row: dict[str, Any] = {
        "symbol": SYMBOL,
        "asof": str(ASOF.date()),
        "epoch_key": "epoch_0",
        "epoch_detector": "none/provisional",
        "price_plane_id": raw_row.get("d_price_plane_id"),
        "n_sessions": int(raw_row.get("_n_sessions", 0)),
        "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
    }
    for name in fp_mod.METRIC_NAMES + fp_mod.DIAGNOSTIC_NAMES:
        fingerprint_row[name] = raw_row.get(name)
        if name in numeric:
            value = percentile_row.get(name)
            fingerprint_row[f"{name}__pct"] = float(value) if pd.notna(value) else None
            fingerprint_row[f"{name}__covered"] = bool(pd.notna(raw_row.get(name)))
            fingerprint_row[f"{name}__unstable"] = bool(unstable_row.get(name, False))
    for key, value in authority_block().items():
        fingerprint_row[f"authority_{key}"] = value
    fingerprint = pd.DataFrame([fingerprint_row])
    fingerprint = _schema_like(
        fingerprint,
        DATA / "fingerprints" / "pilot_fingerprint_v0.parquet",
        "B fingerprint",
    )
    _assert_zero_authority_frame(fingerprint, "B fingerprint")

    state_frame = states.reset_index().rename(columns={"Date": "date", "index": "date"})
    state_frame.insert(0, "symbol", SYMBOL)
    state_frame.insert(1, "price_plane_id", PRICE_PLANE_ID)
    state_frame = _stamp_frame(state_frame)
    state_frame = _schema_like(
        state_frame,
        DATA / "state" / "pilot_state_daily.parquet",
        "B states",
    )
    _assert_zero_authority_frame(state_frame, "B states")

    episode_frame = _stamp_frame(catalog)
    episode_frame = _schema_like(
        episode_frame,
        DATA / "episodes" / "pilot_episode_catalog_v0.parquet",
        "B episodes",
    )
    _assert_zero_authority_frame(episode_frame, "B episodes")

    fingerprint_path = _staged_path(stage_root, OUTPUT_PATHS[1])
    state_path = _staged_path(stage_root, OUTPUT_PATHS[2])
    episode_path = _staged_path(stage_root, OUTPUT_PATHS[3])
    episode_json_path = _staged_path(stage_root, OUTPUT_PATHS[4])
    dossier_path = _staged_path(stage_root, OUTPUT_PATHS[5])
    chart_path = _staged_path(stage_root, OUTPUT_PATHS[6])

    fingerprint.to_parquet(fingerprint_path, index=False)
    state_frame.to_parquet(state_path, index=False)
    episode_frame.to_parquet(episode_path, index=False)
    episode_payload = {
        "schema": "stock_identity.episode_catalog.amendment.v1",
        "amendment_id": AMENDMENT_ID,
        "symbol": SYMBOL,
        "issuer": "Barrick Mining Corporation",
        "edgar_cik": "756894",
        "asof": str(ASOF.date()),
        "price_plane_id": PRICE_PLANE_ID,
        "source_path": B_SOURCE_RELATIVE_PATH,
        "source_sha256": B_SOURCE_SHA256,
        "constants_values": constants["values"],
        "atr_basis": ep_mod.ATR_BASIS,
        "labeling_note": (
            "episode resolution labels use future data by design — a research-time "
            "labeling instrument, never a live signal"
        ),
        "episodes": json.loads(episode_frame.to_json(orient="records", date_format="iso")),
        "authority": authority_block(),
    }
    _write_json(episode_json_path, episode_payload)

    _render_b_chart(
        stage_path=chart_path,
        frame=frame,
        states=states["state"],
        catalog=catalog,
    )
    dossier_markdown = _build_dossier(
        frame=frame,
        states=states,
        catalog=catalog,
        raw_row=raw_row,
        percentile_row=percentile_row,
        unstable_row=unstable_row,
        constants=constants,
        manifest=manifest,
        chart_relative_path=chart_path.name,
    )
    dossier_path.write_text(dossier_markdown, encoding="utf-8")

    gold_markdown = _gold_markdown_with_annotation()
    staged_gold = stage_root / "GOLD.annotated.md"
    staged_gold.write_text(gold_markdown, encoding="utf-8")

    generated_hashes = {
        relative: _sha256(stage_root / relative)
        for relative in OUTPUT_PATHS[1:]
    }
    gold_post_sha = _sha256(staged_gold)
    receipt = {
        "schema": "stock_identity.w1_amendment.v1",
        "amendment_id": AMENDMENT_ID,
        "registered_date": BUILD_DATE,
        "asof": str(ASOF.date()),
        "pull_request": pull_request,
        "registration_commit": registration_commit,
        "prerequisite_merges": {
            "pr_5613": pr_5613_merge,
            "pr_5632": pr_5632_merge,
        },
        "identity_receipt": {
            "GOLD": {
                "issuer": "Gold.com, Inc. (fka A-Mark Precious Metals)",
                "edgar_cik": "1591588",
                "role": "bullion dealer instrument; frozen W1 miner interpretation withdrawn",
                "effective_symbol_date": "2025-12-02",
                "store_first_print": "2014-03-17",
            },
            "B": {
                "issuer": "Barrick Mining Corporation",
                "edgar_cik": "756894",
                "role": "design-touched W1-A1 miner-probe addendum",
                "effective_symbol_date": "2025-05-09",
                "curated_tape_floor": "2014-01-02",
            },
        },
        "miner_probe_roster": {
            "sealed_w1": list(W1_SEALED_MINER_PROBE),
            "effective_w1a1": list(W1A1_EFFECTIVE_MINER_PROBE),
        },
        "partition_treatment": {
            "B_design_touched": True,
            "B_absent_from_w1_universe": True,
            "B_absent_from_w1_pilot": True,
            "B_excluded_from_blind": True,
            "B_excluded_from_calibration": True,
            "B_excluded_from_future_blind_extension": True,
            "B_excluded_from_confirmatory_grading": True,
        },
        "procedural_deviation": {
            "status": "DISCLOSED_PRE_REGISTRATION_IMPLEMENTATION_EXPOSURE",
            "write_scope": "no repository artifacts written; independent git status/diff clean",
            "observed_scope": (
                "B tape shape/edge rows plus in-memory state, episode, fingerprint, "
                "percentile and instability outputs were printed before registration"
            ),
            "consequence": (
                "observations cannot choose outputs, thresholds, constants, acceptance "
                "rules or interpretations; B is permanently design-touched"
            ),
        },
        "rank_context": {
            "method": (
                "B-only hypothetical insertion into the frozen W1 raw reference; pandas "
                "average-tie empirical ranks over each field's non-null denominator"
            ),
            "frozen_reference_rows": 2780,
            "hypothetical_joint_rows": 2781,
            "only_B_persisted": True,
            "w1_percentiles_rewritten": False,
            "univ_ew_recomputed": False,
            "dealer_context_disclosure": (
                "frozen UNIV_EW and ranks include GOLD dealer context as one small "
                "component; retained for comparability, never miner evidence"
            ),
            "reference_sha256": REFERENCE_SHA256,
        },
        "price_input": {
            "path": B_SOURCE_RELATIVE_PATH,
            "sha256": B_SOURCE_SHA256,
            "price_plane_id": PRICE_PLANE_ID,
            "rows": int(len(frame)),
            "first_date": str(frame.index.min().date()),
            "last_date": str(frame.index.max().date()),
            "history_caveat": (
                "2014-01-02 is a curated data floor, not issuer/listing birth; no "
                "pre-2014 portion of the 2011-2015 gold bear is covered"
            ),
        },
        "sealed_w1_sha256": FROZEN_SHA256,
        "generated_output_sha256": generated_hashes,
        "disclosure_only": {
            "path": DISCLOSURE_ONLY_PATH,
            "before_sha256": FROZEN_SHA256[DISCLOSURE_ONLY_PATH],
            "after_sha256": gold_post_sha,
            "marker_begin": GOLD_ANNOTATION_BEGIN,
            "marker_end": GOLD_ANNOTATION_END,
            "restores_original_when_removed": True,
            "gold_svg_unchanged": True,
        },
        "result_counts": {
            "fingerprint_rows": int(len(fingerprint)),
            "state_rows": int(len(state_frame)),
            "episode_rows": int(len(episode_frame)),
        },
        "measured_rows_mutated": False,
        "trial_budget": (
            "not applicable: one deterministic descriptive configuration, no sweep, "
            "outcome attachment, graded question, or result-contingent choice"
        ),
        "authority": authority_block(),
    }
    _write_json(_staged_path(stage_root, RECEIPT_RELATIVE_PATH), receipt)
    return receipt, str(staged_gold)


def _validate_staged(stage_root: Path, receipt: dict[str, Any], staged_gold: Path) -> None:
    for relative in OUTPUT_PATHS:
        if not (stage_root / relative).exists():
            raise SystemExit(f"staged output missing: {relative}")
    if not staged_gold.exists():
        raise SystemExit("staged GOLD annotation is missing")
    for relative, expected in receipt["generated_output_sha256"].items():
        if _sha256(stage_root / relative) != expected:
            raise SystemExit(f"staged output hash drift: {relative}")
    if receipt["authority"] != authority_block():
        raise SystemExit("receipt authority is not all-false")
    if receipt["measured_rows_mutated"] is not False:
        raise SystemExit("receipt does not preserve measured rows")
    if staged_gold.read_text(encoding="utf-8").count(GOLD_ANNOTATION_BEGIN) != 1:
        raise SystemExit("staged GOLD annotation marker is not unique")


def _publish(stage_root: Path, staged_gold: Path) -> None:
    _validate_outputs_absent()
    _validate_frozen_hashes()
    for relative in OUTPUT_PATHS[1:]:
        _publish_file(stage_root / relative, REPO_ROOT / relative)
    _publish_file(staged_gold, REPO_ROOT / DISCLOSURE_ONLY_PATH)
    # Receipt last: its presence means every governed output and disclosure landed.
    _publish_file(stage_root / RECEIPT_RELATIVE_PATH, REPO_ROOT / RECEIPT_RELATIVE_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w1-reference-dir", type=Path, required=True)
    parser.add_argument("--pr-5613-merge", required=True)
    parser.add_argument("--pr-5632-merge", required=True)
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    registration_commit = _validate_clean_pushed_registration()
    _validate_prerequisites(args.pr_5613_merge, args.pr_5632_merge)
    manifest = _validate_registration()
    _validate_frozen_hashes()
    _validate_outputs_absent()
    _validate_b_membership(manifest)
    frame = _validate_b_source()
    raw_reference, factor_returns, _ = _validate_reference(args.w1_reference_dir.resolve())

    gold = hyg_mod.check_symbol(
        "GOLD", repo_root=REPO_ROOT, first_date=pd.Timestamp("2014-03-17")
    )
    if not gold["compute_eligible"] or gold["blind_eligible"]:
        raise SystemExit("GOLD must be compute-eligible and blind-ineligible after acknowledgement")
    if "reused_ticker_acked" not in gold["flags"] or "reused_ticker_unacked" in gold["flags"]:
        raise SystemExit("GOLD acknowledgement flags are contradictory")

    if args.validate_only:
        print(
            "[validate-only] W1-A1 registration, ancestry, frozen hashes, B plane, "
            "partition exclusions and reference checkpoint: PASS",
            flush=True,
        )
        return 0

    with tempfile.TemporaryDirectory(prefix="stock-identity-w1a1-") as tmp:
        stage_root = Path(tmp)
        receipt, staged_gold_raw = _build_and_stage(
            stage_root=stage_root,
            frame=frame,
            raw_reference=raw_reference,
            factor_returns=factor_returns,
            manifest=manifest,
            registration_commit=registration_commit,
            pr_5613_merge=args.pr_5613_merge,
            pr_5632_merge=args.pr_5632_merge,
            pull_request=args.pull_request,
        )
        staged_gold = Path(staged_gold_raw)
        _validate_staged(stage_root, receipt, staged_gold)
        _validate_frozen_hashes()
        _publish(stage_root, staged_gold)

    _validate_frozen_hashes(skip_gold_markdown=True)
    for relative, expected in receipt["generated_output_sha256"].items():
        if _sha256(REPO_ROOT / relative) != expected:
            raise SystemExit(f"published output hash drift: {relative}")
    print(
        f"[W1-A1] published B-only amendment: {receipt['result_counts']} · "
        "GOLD measured rows unchanged · receipt written last",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
