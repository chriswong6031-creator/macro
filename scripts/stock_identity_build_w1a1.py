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
import fcntl
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
    W1A1_ASOF,
    W1A1_IDENTITY_RECEIPT,
    W1A1_PARTITION_TREATMENT,
    W1A1_PROCEDURAL_DEVIATION,
    W1A1_RECEIPT_SCHEMA,
    W1A1_REFERENCE_SHA256,
    W1A1_SEALED_W1_SHA256,
    W1A1_TRIAL_BUDGET,
    W1_SEALED_MINER_PROBE,
    W1A1_EFFECTIVE_MINER_PROBE,
    W1A1_GOLD_ANNOTATION_BEGIN,
    W1A1_GOLD_ANNOTATION_END,
    W1A1_GOLD_DISCLOSURE_PATH,
    W1A1_GITHUB_REPOSITORY,
    W1A1_INITIAL_REGISTRATION_COMMIT,
    W1A1_PR_BASE_REF,
    W1A1_PR_HEAD_REF,
    W1A1_PR_URL,
    W1A1_PREREQUISITE_MERGES,
    W1A1_PREREQUISITE_SOURCE_HEADS,
    W1A1_PULL_REQUEST,
    W1A1_REGISTERED_OUTPUT_PATHS,
    current_miner_probe,
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
DISCLOSURE_ONLY_PATH = W1A1_GOLD_DISCLOSURE_PATH

# Machine-checked in tests.  No frozen W1 path belongs here.
OUTPUT_PATHS: tuple[str, ...] = W1A1_REGISTERED_OUTPUT_PATHS
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

if str(ASOF.date()) != W1A1_ASOF:
    raise RuntimeError("builder/pilot A1 asof constants diverged")
if REFERENCE_SHA256 != W1A1_REFERENCE_SHA256:
    raise RuntimeError("builder/pilot A1 reference hashes diverged")
if FROZEN_SHA256 != W1A1_SEALED_W1_SHA256:
    raise RuntimeError("builder/pilot A1 sealed hashes diverged")

# The #5632 seed container itself was sha256 dc126c36..., but this curated store is
# advanced nightly. A durable A1 input receipt therefore pins the logical OHLCV prefix
# through ASOF, not mutable parquet container bytes or post-ASOF appends.
#
# Post-ASOF appends are NOT the only nightly mutation, which is what the original
# registration assumed. `scripts/fetch_basket_ohlcv.py` re-downloads the full
# auto-adjusted history every collection night and lets the new vendor frame win, so
# the already-elapsed 2014..ASOF prefix is re-derived nightly and lands at a slightly
# different float: measured 2026-08-18, two collections 21 minutes apart moved 2,214
# then 2,341 of the 3,172 prefix rows. An exact-equality digest over the LIVE plane
# therefore reds the fleet on every collection night by construction. The prefix the
# A1 result was computed from is consequently frozen as a program-owned immutable
# snapshot, and the live plane is checked by a revision tripwire (see below) instead.
B_SOURCE_SEED_CONTAINER_SHA256 = (
    "dc126c36c6fa07b37ca212051d2a194758725330bfed9c5b6112701b12be6b5f"
)
B_SOURCE_PREFIX_SHA256 = "6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db"

#: Immutable 2014-01-02..ASOF prefix the A1 artifacts were built from, extracted from
#: the #5632 seed container (commit 6d04e9b3, `data/baskets/ohlcv/B.parquet`, container
#: sha256 dc126c36...) under the `plane.load_symbol` normalization. Its logical digest
#: is B_SOURCE_PREFIX_SHA256 unchanged — freezing the bytes re-anchored the registered
#: receipt, it did not restamp it.
B_SOURCE_SNAPSHOT_RELATIVE_PATH = (
    "data/stock_identity/sources/w1a1_b_ohlcv_prefix_v0.parquet"
)
B_SOURCE_SNAPSHOT_PATH = REPO_ROOT / B_SOURCE_SNAPSHOT_RELATIVE_PATH
B_SOURCE_SNAPSHOT_SHA256 = (
    "ba200fe4eb0b881eec4f7a2962c949dea4450d0ffbc1713ab465f440b008d878"
)
B_SOURCE_SNAPSHOT_PROVENANCE_COMMIT = "6d04e9b3100af7afaf834ceb2c9c307a48808f0b"

# Revision-tripwire bands. Measured seed->live over the 3,172-row prefix on 2026-08-18:
#   * O/H/L/C move by a single per-row multiplicative factor, coherent across the four
#     columns to 4.4e-16 (machine epsilon) — the signature of adjustment arithmetic,
#     not of a restated print.
#   * normalized by the window-wide median factor, that per-row factor stays within
#     8.63e-07 of uniform (worst row, 2014; 8.8e-08 by 2026) and does NOT accumulate:
#     seed->mid and mid->live were each ~8.5e-07, seed->live 8.63e-07.
#   * volume is byte-identical on all 3,171 settled rows across three collections
#     spanning four days; only the ASOF row itself moved (10,621,100 -> 10,625,700,
#     4.33e-04), the final session's tape still consolidating when the seed was cut.
#
# The band is on UNIFORMITY, not on the level, because the level is not the thing that
# can invalidate A1. `auto_adjust=True` rescales the whole elapsed history on every
# future dividend — a routine ~$0.10 Barrick quarterly on a ~$41 tape is a ~2.4e-3
# coherent shift, 240x any noise band — but a uniform rescale leaves every return,
# drawdown and percentage gap identical, so it cannot move an A1 conclusion. Banding
# the level would therefore re-red the fleet on the next ordinary dividend, which is
# the exact failure this heal exists to end. What does invalidate A1 is a change in
# RELATIVE prices, which is what the residual-vs-median test sees. Splits stay covered
# through the volume channel: split adjustment rescales share counts too, and settled
# volume must match exactly.
#
# The coherence band is NOT set at the observed 4.4e-16. Coherence holds that tightly
# only because the vendor derives O/H/L from one float64 ratio per row and sets
# close=adjclose, so the common factor cancels — but the underlying raw prints are
# float32-quantized (values arrive as 40.79999923706055), a grid of ~6e-8 relative. A
# single raw print re-quantizing by one ULP, or a yfinance bump that re-derives O/H/L
# differently (requirements.txt pins no upper bound), would then blow a machine-epsilon
# band and be reported as a "print revision" — re-reding the fleet on vendor noise,
# which is the defect this heal exists to end. 1e-6 sits ~16x above that grid and still
# catches any single-column restatement large enough to mean anything: 1e-6 of a $41
# tape is $0.00004. Coherence is the ONLY detector of a one-column move, because a
# lone outlier among four leaves the median — and therefore the residual — untouched.
B_LIVE_PRICE_COHERENCE_BAND = 1e-6
B_LIVE_PRICE_REVISION_BAND = 1e-5
B_LIVE_ASOF_VOLUME_BAND = 1e-2
#: Sanity bound on the gross rescale. Not a corporate-action test — corporate actions
#: are caught on the volume channel, which is why this is checked only after it.
B_LIVE_GROSS_RESCALE_BOUNDS = (0.2, 5.0)
GOLD_ANNOTATION_BEGIN = W1A1_GOLD_ANNOTATION_BEGIN
GOLD_ANNOTATION_END = W1A1_GOLD_ANNOTATION_END

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

_GENERIC_PERCENTILE_PROSE = (
    "Percentiles are PIT ranks against the contemporaneous evaluated universe."
)
_B_PERCENTILE_PROSE = (
    "Percentiles are B's hypothetical insertion ranks against the frozen 2,780-name "
    "W1 reference; only B was ranked and no W1 row was recomputed or rewritten."
)
_GENERIC_B_GAP_PROSE = (
    "Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs "
    "the whole session's move, not just the overnight jump, so cross-plane comparisons "
    "of the dislocation share carry that caveat."
)
_B_GAP_PROSE = (
    "Gap basis on this plane: `open_vs_prev_close` — the opening print is compared "
    "with the previous close, isolating the overnight jump."
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ohlcv_prefix_sha256(frame: pd.DataFrame) -> str:
    """Versioned, parquet-container-independent digest of normalized OHLCV rows."""
    columns = ["open", "high", "low", "close", "volume"]
    if list(frame.columns) != columns:
        raise SystemExit(f"B prefix columns drifted: {list(frame.columns)}")
    if not isinstance(frame.index, pd.DatetimeIndex) or not frame.index.is_unique:
        raise SystemExit("B prefix index must be a unique DatetimeIndex")
    if not frame.index.is_monotonic_increasing:
        raise SystemExit("B prefix index must be ascending")

    digest = hashlib.sha256()
    digest.update(b"stock_identity.w1a1.ohlcv_prefix.v1\n")
    digest.update(b"Date\x1fopen\x1fhigh\x1flow\x1fclose\x1fvolume\n")
    for stamp, values in zip(frame.index, frame[columns].to_numpy(dtype="float64")):
        if not bool(np.isfinite(values).all()):
            raise SystemExit(f"B prefix has non-finite OHLCV at {stamp}")
        row = [pd.Timestamp(stamp).strftime("%Y-%m-%d"), *(float(v).hex() for v in values)]
        digest.update("\x1f".join(row).encode("ascii") + b"\n")
    return digest.hexdigest()


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"B dossier {label} boundary is ambiguous")
    return text.replace(old, new, 1)


def _apply_b_dossier_disclosures(markdown: str) -> str:
    """Correct A1-only prose without changing the frozen W1 dossier renderer."""
    markdown = _replace_once(
        markdown,
        "# B — Identity Atlas v0 dossier",
        "# B — Identity Atlas v0 dossier (W1-A1 addendum)",
        label="title",
    )
    markdown = _replace_once(
        markdown,
        _GENERIC_PERCENTILE_PROSE,
        _B_PERCENTILE_PROSE,
        label="percentile",
    )
    return _replace_once(
        markdown,
        _GENERIC_B_GAP_PROSE,
        _B_GAP_PROSE,
        label="gap-basis",
    )


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


def _gh_pr_view(number: int) -> dict[str, Any]:
    gh = shutil.which("gh")
    if gh is None:
        raise SystemExit("GitHub provenance gate requires the gh CLI on PATH")
    proc = subprocess.run(
        [
            gh,
            "pr",
            "view",
            str(number),
            "--repo",
            W1A1_GITHUB_REPOSITORY,
            "--json",
            (
                "number,state,baseRefName,headRefName,headRefOid,mergeCommit,"
                "isCrossRepository,isDraft,url"
            ),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(
            f"GitHub provenance lookup failed for PR #{number}: "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"GitHub provenance lookup for PR #{number} was not JSON") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"GitHub provenance lookup for PR #{number} was malformed")
    return payload


def _validate_prerequisites() -> None:
    origin_main = _git("rev-parse", "origin/main")
    for number, key in ((5613, "pr_5613"), (5632, "pr_5632")):
        pr = _gh_pr_view(number)
        merge = pr.get("mergeCommit") or {}
        expected = {
            "number": number,
            "state": "MERGED",
            "baseRefName": "main",
            "headRefOid": W1A1_PREREQUISITE_SOURCE_HEADS[key],
            "isCrossRepository": False,
        }
        if any(pr.get(field) != value for field, value in expected.items()):
            raise SystemExit(f"PR #{number} source-head provenance does not match registration")
        if merge.get("oid") != W1A1_PREREQUISITE_MERGES[key]:
            raise SystemExit(f"PR #{number} squash-merge provenance does not match registration")
        _require_ancestor(
            W1A1_PREREQUISITE_MERGES[key],
            origin_main,
            f"PR #{number} merge receipt",
        )

    if not B_SOURCE_PATH.exists():
        raise SystemExit(f"missing prerequisite B input {B_SOURCE_PATH}")
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


def _validate_current_pull_request(registration_commit: str) -> dict[str, Any]:
    branch = _git("branch", "--show-current")
    if branch != W1A1_PR_HEAD_REF:
        raise SystemExit(
            f"A1 run branch is {branch!r}; expected exact PR head {W1A1_PR_HEAD_REF!r}"
        )
    pr = _gh_pr_view(W1A1_PULL_REQUEST)
    expected = {
        "number": W1A1_PULL_REQUEST,
        "state": "OPEN",
        "baseRefName": W1A1_PR_BASE_REF,
        "headRefName": W1A1_PR_HEAD_REF,
        "headRefOid": registration_commit,
        "isCrossRepository": False,
        "isDraft": True,
        "url": W1A1_PR_URL,
    }
    if any(pr.get(field) != value for field, value in expected.items()):
        raise SystemExit("A1 pull-request provenance does not match the registration")
    return {
        "repository": W1A1_GITHUB_REPOSITORY,
        "base_ref": W1A1_PR_BASE_REF,
        "head_ref": W1A1_PR_HEAD_REF,
        "head_oid_at_run": registration_commit,
        "url": W1A1_PR_URL,
        "draft_at_run": True,
    }


def _validate_registration() -> dict[str, Any]:
    text = REGISTRATION.read_text(encoding="utf-8")
    required = (
        AMENDMENT_ID,
        "before the only artifact-producing A1 run",
        "Procedural-deviation ledger",
        "effective analytical miner probe",
        B_SOURCE_PREFIX_SHA256,
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


def _validate_compute_hygiene(symbol: str, first_date: pd.Timestamp) -> dict[str, Any]:
    """Run masterplan §9.6 before any history for ``symbol`` is consumed."""
    verdict = dict(
        hyg_mod.check_symbol(symbol, repo_root=REPO_ROOT, first_date=first_date)
    )
    flags = set(verdict.get("flags") or ())
    blocked_flags = {"compute_blocklisted", "reused_ticker_unacked"}
    if (
        symbol in hyg_mod.COMPUTE_BLOCKLIST
        or verdict.get("compute_eligible") is not True
        or flags & blocked_flags
    ):
        raise SystemExit(
            f"{symbol} fails the registered pre-read compute hygiene gate: "
            f"flags={sorted(flags)}, notes={verdict.get('notes') or {}}"
        )
    return verdict


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
    _validate_compute_hygiene(SYMBOL, pd.Timestamp("2014-01-02"))
    return snapshot


def _load_b_prefix_snapshot() -> pd.DataFrame:
    """The frozen A1 input prefix, checked at both the byte and the logical layer."""
    if not B_SOURCE_SNAPSHOT_PATH.exists():
        raise SystemExit(
            f"frozen A1 B prefix snapshot is absent: {B_SOURCE_SNAPSHOT_RELATIVE_PATH}"
        )
    container = _sha256(B_SOURCE_SNAPSHOT_PATH)
    if container != B_SOURCE_SNAPSHOT_SHA256:
        raise SystemExit(
            f"frozen A1 B prefix snapshot container drifted: {container}"
        )
    frame = pd.read_parquet(B_SOURCE_SNAPSHOT_PATH)
    if len(frame) != 3172:
        raise SystemExit(f"frozen A1 B prefix snapshot row receipt drifted: {len(frame)}")
    if frame.index.min() != pd.Timestamp("2014-01-02") or frame.index.max() != ASOF:
        raise SystemExit("frozen A1 B prefix snapshot date receipt drifted")
    actual = _ohlcv_prefix_sha256(frame)
    if actual != B_SOURCE_PREFIX_SHA256:
        raise SystemExit(
            f"frozen A1 B prefix snapshot logical digest differs from registration: {actual}"
        )
    return frame


def _tripwire_b_live_plane(snapshot: pd.DataFrame) -> dict[str, Any]:
    """Fire when the LIVE curated plane revises the frozen A1 evidence window.

    The live plane is re-derived from the vendor every collection night, so equality
    is not the question — whether the re-derivation is adjustment arithmetic or a real
    revision is. Prices must move as ONE UNIFORM rescale of the whole window (any
    uniform rescale is return-preserving, so it cannot move an A1 conclusion); settled
    volume must not move at all.
    """
    live = load_symbol(SYMBOL, PRICE_PLANE_ID, REPO_ROOT)
    if live.index.min() != pd.Timestamp("2014-01-02") or ASOF not in live.index:
        raise SystemExit("B source does not contain the registered 2014-01-02..ASOF prefix")
    prefix = live.loc[live.index <= ASOF]
    if len(prefix) != len(snapshot) or not prefix.index.equals(snapshot.index):
        raise SystemExit(
            "B live prefix no longer spans the frozen A1 session index "
            f"({len(prefix)} rows vs {len(snapshot)}) — a session was added, dropped or "
            "restamped inside the sealed window; adjudicate before rebuilding A1"
        )
    if list(prefix.columns) != list(snapshot.columns):
        raise SystemExit(f"B live prefix columns drifted: {list(prefix.columns)}")

    prices = ["open", "high", "low", "close"]
    base = snapshot[prices].to_numpy(dtype="float64")
    live_prices = prefix[prices].to_numpy(dtype="float64")
    if not bool(np.isfinite(live_prices).all()):
        raise SystemExit("B live prefix carries non-finite OHLC")
    if not bool((base > 0).all()):
        raise SystemExit("frozen A1 B prefix snapshot carries a non-positive price")

    ratio = live_prices / base
    coherence = np.abs(ratio.max(axis=1) - ratio.min(axis=1))
    worst_coherence = float(coherence.max())
    if worst_coherence > B_LIVE_PRICE_COHERENCE_BAND:
        stamp = snapshot.index[int(coherence.argmax())].date()
        raise SystemExit(
            f"B live prefix restated an individual price at {stamp}: O/H/L/C moved by "
            f"different factors (spread {worst_coherence:.3e} > "
            f"{B_LIVE_PRICE_COHERENCE_BAND:.0e}). Auto-adjustment rescales the four "
            "together, so this is a print revision, not vendor noise — adjudicate "
            "against the sealed A1 result before rebuilding"
        )

    row_factor = np.median(ratio, axis=1)
    gross = float(np.median(row_factor))
    residual = np.abs(row_factor / gross - 1.0)
    worst_price = float(residual.max())
    if worst_price > B_LIVE_PRICE_REVISION_BAND:
        stamp = snapshot.index[int(residual.argmax())].date()
        raise SystemExit(
            f"B live prefix moved NON-UNIFORMLY at {stamp}: residual against the "
            f"window rescale {gross:.9g} is {worst_price:.3e} > "
            f"{B_LIVE_PRICE_REVISION_BAND:.0e}. A dividend or split rescales the whole "
            "window and preserves every return; this changed relative prices, so it is "
            "a restatement inside the frozen A1 window — adjudicate against the sealed "
            "A1 result before rebuilding"
        )

    # Volume runs BEFORE the gross-rescale bound: a real corporate action rescales share
    # counts, so it must be diagnosed as one rather than as a broken vendor frame.
    settled = snapshot.index < ASOF
    base_volume = snapshot["volume"].to_numpy(dtype="float64")
    live_volume = prefix["volume"].to_numpy(dtype="float64")
    if not bool(np.isfinite(live_volume).all()):
        raise SystemExit("B live prefix carries non-finite volume")
    moved = settled & (base_volume != live_volume)
    settled_moved = int(moved.sum())
    if settled_moved:
        stamps = [str(s.date()) for s in snapshot.index[moved][:5]]
        raise SystemExit(
            f"B live prefix restated settled volume on {settled_moved} session(s) "
            f"({', '.join(stamps)}) — settled share counts are stable under "
            "re-adjustment, so this is a split or a vendor restatement; adjudicate "
            "against the sealed A1 result before rebuilding"
        )
    asof_base = float(base_volume[-1])
    asof_live = float(live_volume[-1])
    if asof_base <= 0:
        raise SystemExit("frozen A1 B prefix snapshot has no ASOF-session volume")
    asof_dev = abs(asof_live / asof_base - 1.0)
    if asof_dev > B_LIVE_ASOF_VOLUME_BAND:
        raise SystemExit(
            f"B live prefix moved ASOF-session volume by {asof_dev:.3e} > "
            f"{B_LIVE_ASOF_VOLUME_BAND:.0e} ({asof_base:.0f} -> {asof_live:.0f}); that "
            "exceeds late tape consolidation — adjudicate before rebuilding"
        )

    low, high = B_LIVE_GROSS_RESCALE_BOUNDS
    if not low <= gross <= high:
        raise SystemExit(
            f"B live prefix rescaled the whole window by {gross:.6g}, outside "
            f"[{low}, {high}], with settled volume unchanged — no corporate action "
            "rescales prices that far and leaves share counts intact, so this is a "
            "broken vendor frame; adjudicate before rebuilding"
        )

    return {
        "checked_path": B_SOURCE_RELATIVE_PATH,
        "rows_compared": int(len(prefix)),
        "live_prefix_sha256": _ohlcv_prefix_sha256(prefix),
        "max_price_coherence_spread": worst_coherence,
        "gross_window_rescale": gross,
        "max_nonuniform_residual": worst_price,
        "price_coherence_band": B_LIVE_PRICE_COHERENCE_BAND,
        "price_revision_band": B_LIVE_PRICE_REVISION_BAND,
        "settled_volume_rows_moved": settled_moved,
        "asof_volume_relative_deviation": asof_dev,
        "asof_volume_band": B_LIVE_ASOF_VOLUME_BAND,
        "gross_rescale_note": (
            "a gross rescale away from 1.0 is post-asof dividend/split adjustment; it "
            "is return-preserving and disclosed here rather than treated as a revision"
        ),
        "verdict": "adjustment arithmetic only; no revision to the frozen A1 window",
    }


#: Set by ``_validate_b_source`` so the receipt records the SAME live-plane reading the
#: run validated. Recomputing it during staging would re-read a file the nightly may
#: have rewritten in between, turning a receipt line into a mid-publish SystemExit.
_LIVE_REVISION_RECEIPT: dict[str, Any] | None = None


def _validate_b_source() -> pd.DataFrame:
    """Return the frozen A1 prefix, having tripwired the live curated plane.

    A1 math reads the snapshot, never the live file: the nightly re-adjustment means
    the live plane can no longer reproduce the sealed A1 outputs, and a result whose
    inputs move every night is not a sealed result.
    """
    global _LIVE_REVISION_RECEIPT
    snapshot = _load_b_prefix_snapshot()
    _LIVE_REVISION_RECEIPT = _tripwire_b_live_plane(snapshot)
    return snapshot


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
        if column not in frame.columns:
            raise SystemExit(f"{label}: {column} is missing")
        values = frame[column]
        if values.isna().any() or not pd.api.types.is_bool_dtype(values.dtype):
            raise SystemExit(f"{label}: {column} must be non-null boolean")
        if not values.eq(False).all():  # noqa: E712 - identity authority is literal false
            raise SystemExit(f"{label}: {column} is missing or not all-false")


def _validate_schema_like(
    frame: pd.DataFrame, frozen: pd.DataFrame, label: str
) -> None:
    frozen_columns = list(frozen.columns)
    missing = [c for c in frozen_columns if c not in frame.columns]
    extra = [c for c in frame.columns if c not in frozen_columns]
    if missing or extra:
        raise SystemExit(f"{label} schema drift: missing={missing}, extra={extra}")
    type_drift = {
        column: (str(frame[column].dtype), str(frozen[column].dtype))
        for column in frozen_columns
        if not pd.api.types.is_dtype_equal(frame[column].dtype, frozen[column].dtype)
    }
    if type_drift:
        raise SystemExit(f"{label} logical-type drift: {type_drift}")


def _schema_like(frame: pd.DataFrame, frozen_path: Path, label: str) -> pd.DataFrame:
    """Normalize one additive row set to the sealed combined-artifact schema."""
    frozen = pd.read_parquet(frozen_path)
    frozen_columns = list(frozen.columns)
    missing = [c for c in frozen_columns if c not in frame.columns]
    extra = [c for c in frame.columns if c not in frozen_columns]
    if missing or extra:
        raise SystemExit(f"{label} schema drift: missing={missing}, extra={extra}")
    out = frame[frozen_columns].copy()
    for column, target_dtype in frozen.dtypes.items():
        try:
            out[column] = out[column].astype(target_dtype)
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                f"{label}: cannot normalize {column} to {target_dtype}: {exc}"
            ) from exc
    _validate_schema_like(out, frozen, label)
    return out


def _validate_parquet_schema_like(
    path: Path, frozen_path: Path, label: str
) -> None:
    """Require the reopened logical data schema to match W1.

    The frozen episode parquet accidentally persisted pandas' RangeIndex as a physical
    ``__index_level_0__`` Arrow field.  That storage accident is not a program column
    and A1 deliberately writes ``index=False``.  Conversely, an all-null W1 column has
    Arrow type ``null`` even though its logical pandas dtype is ``object``.  Comparing
    reopened data columns/dtypes therefore pins the consumer-visible contract without
    elevating either serialization accident into a new amendment requirement.
    """
    candidate = pd.read_parquet(path)
    frozen = pd.read_parquet(frozen_path)
    _validate_schema_like(candidate, frozen, f"{label} serialized")


def _gold_markdown_with_annotation() -> str:
    path = REPO_ROOT / DISCLOSURE_ONLY_PATH
    original = path.read_text(encoding="utf-8")
    if _sha256(path) != FROZEN_SHA256[DISCLOSURE_ONLY_PATH]:
        raise SystemExit("GOLD.md no longer matches the registered pre-annotation hash")
    if GOLD_ANNOTATION_BEGIN in original or GOLD_ANNOTATION_END in original:
        raise SystemExit("GOLD.md already carries an A1 marker")
    # Match the complete heading, not the later ``## Identity-episode`` prefix.
    anchor = "\n\n## Identity\n"
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
    svg, substitutions = re.subn(
        r"<dc:date>.*?</dc:date>",
        "<dc:date>2026-08-14T00:00:00+00:00</dc:date>",
        svg,
        flags=re.S,
    )
    if substitutions != 1:
        raise SystemExit(f"B.svg must carry exactly one normalized dc:date; got {substitutions}")
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
    markdown = _apply_b_dossier_disclosures(markdown)
    # Match the complete heading, not its prefix: the generic dossier also contains
    # ``## Identity-episode catalog`` later in the document.
    identity = "\n## Identity\n"
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
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        # A failed copy/replace must not poison the next registered attempt.
        temporary.unlink(missing_ok=True)


def _build_and_stage(
    *,
    stage_root: Path,
    frame: pd.DataFrame,
    raw_reference: pd.DataFrame,
    factor_returns: pd.Series,
    manifest: dict[str, Any],
    registration_commit: str,
    pull_request_context: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    ec, sc, constants = _load_constants()
    states = state_mod.tag_states(frame, PRICE_PLANE_ID, sc)
    catalog = ep_mod.build_catalog(
        frame,
        symbol=SYMBOL,
        plane_id=PRICE_PLANE_ID,
        const=ec,
        states=states["state"],
        # The tape is active. The sealed builder supplies a termination reason only
        # when a tape actually ended; right-censoring remains disclosed in the dossier
        # and receipt, not fabricated into the per-episode termination field.
        terminated_reason=None,
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
    if len(raw_reference) != 2780 or not raw_reference.index.is_unique:
        raise SystemExit("frozen percentile reference must contain 2,780 unique rows")
    percentile_row = fp_mod.candidate_percentiles_against_reference(
        raw_reference[numeric], raw_b.loc[SYMBOL], numeric
    )
    percentiles = pd.DataFrame([percentile_row], index=[SYMBOL])
    unstable = fp_mod.unstable_flags(percentiles)

    raw_row = raw_b.loc[SYMBOL]
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
        "source_prefix_asof": str(ASOF.date()),
        "source_prefix_sha256": B_SOURCE_PREFIX_SHA256,
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
    source_at_run = load_symbol(SYMBOL, PRICE_PLANE_ID, REPO_ROOT)
    receipt = {
        "schema": W1A1_RECEIPT_SCHEMA,
        "amendment_id": AMENDMENT_ID,
        "registered_date": BUILD_DATE,
        "asof": str(ASOF.date()),
        "pull_request": W1A1_PULL_REQUEST,
        "pull_request_context": pull_request_context,
        "initial_registration_commit": W1A1_INITIAL_REGISTRATION_COMMIT,
        "registration_commit": registration_commit,
        "prerequisite_source_heads": W1A1_PREREQUISITE_SOURCE_HEADS,
        "prerequisite_merges": W1A1_PREREQUISITE_MERGES,
        "identity_receipt": W1A1_IDENTITY_RECEIPT,
        "miner_probe_roster": {
            "sealed_w1": list(W1_SEALED_MINER_PROBE),
            "effective_w1a1": list(W1A1_EFFECTIVE_MINER_PROBE),
        },
        "partition_treatment": W1A1_PARTITION_TREATMENT,
        "procedural_deviation": W1A1_PROCEDURAL_DEVIATION,
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
            "price_plane_id": PRICE_PLANE_ID,
            "prefix_asof": str(ASOF.date()),
            "prefix_sha256": B_SOURCE_PREFIX_SHA256,
            "seed_container_sha256": B_SOURCE_SEED_CONTAINER_SHA256,
            "snapshot_path": B_SOURCE_SNAPSHOT_RELATIVE_PATH,
            "snapshot_sha256": B_SOURCE_SNAPSHOT_SHA256,
            "snapshot_provenance_commit": B_SOURCE_SNAPSHOT_PROVENANCE_COMMIT,
            "snapshot_read_note": (
                "A1 math reads the frozen snapshot; `path` names the curated plane it "
                "was cut from and is re-checked by the live revision tripwire"
            ),
            "live_plane_revision": _LIVE_REVISION_RECEIPT,
            "file_sha256_at_run": _sha256(B_SOURCE_PATH),
            "file_rows_at_run": int(len(source_at_run)),
            "file_last_date_at_run": str(source_at_run.index.max().date()),
            "rows_used": int(len(frame)),
            "first_date": str(frame.index.min().date()),
            "last_date_used": str(frame.index.max().date()),
            "history_caveat": (
                "2014-01-02 is a curated data floor, not issuer/listing birth; no "
                "pre-2014 portion of the 2011-2015 gold bear is covered"
            ),
        },
        "sealed_w1_sha256": FROZEN_SHA256,
        "registered_output_paths": list(OUTPUT_PATHS),
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
        "trial_budget": W1A1_TRIAL_BUDGET,
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

    reopened_receipt = json.loads(
        (stage_root / RECEIPT_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    if reopened_receipt != receipt or reopened_receipt.get("authority") != authority_block():
        raise SystemExit("serialized amendment receipt differs from its validated object")
    episode_json = json.loads((stage_root / OUTPUT_PATHS[4]).read_text(encoding="utf-8"))
    if episode_json.get("authority") != authority_block() or episode_json.get("symbol") != SYMBOL:
        raise SystemExit("serialized B episode JSON lacks B-only/all-false closure")

    for relative, label in (
        (OUTPUT_PATHS[1], "B fingerprint"),
        (OUTPUT_PATHS[2], "B states"),
        (OUTPUT_PATHS[3], "B episodes"),
    ):
        frozen_path = {
            OUTPUT_PATHS[1]: DATA / "fingerprints" / "pilot_fingerprint_v0.parquet",
            OUTPUT_PATHS[2]: DATA / "state" / "pilot_state_daily.parquet",
            OUTPUT_PATHS[3]: DATA / "episodes" / "pilot_episode_catalog_v0.parquet",
        }[relative]
        _validate_parquet_schema_like(stage_root / relative, frozen_path, label)
        reopened = pd.read_parquet(stage_root / relative)
        _assert_zero_authority_frame(reopened, label)
        if set(reopened["symbol"].astype(str)) != {SYMBOL}:
            raise SystemExit(f"{label}: serialized rows are not B-only")
        if "price_plane_id" in reopened.columns and set(
            reopened["price_plane_id"].astype(str)
        ) != {PRICE_PLANE_ID}:
            raise SystemExit(f"{label}: serialized price plane drifted")


def _validate_published(receipt: dict[str, Any]) -> None:
    _validate_frozen_hashes(skip_gold_markdown=True)
    for relative, expected in receipt["generated_output_sha256"].items():
        if _sha256(REPO_ROOT / relative) != expected:
            raise SystemExit(f"published output hash drift: {relative}")
    published_receipt = json.loads(
        (REPO_ROOT / RECEIPT_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    if published_receipt != receipt:
        raise SystemExit("published amendment receipt differs from the staged receipt")
    published_gold = REPO_ROOT / DISCLOSURE_ONLY_PATH
    disclosure = receipt["disclosure_only"]
    if _sha256(published_gold) != disclosure["after_sha256"]:
        raise SystemExit("published GOLD annotation hash drifted")
    gold_text = published_gold.read_text(encoding="utf-8")
    if gold_text.count(GOLD_ANNOTATION_BEGIN) != 1 or gold_text.count(GOLD_ANNOTATION_END) != 1:
        raise SystemExit("published GOLD annotation markers are absent or ambiguous")
    restored = gold_text.replace(f"\n\n{GOLD_ANNOTATION}\n\n", "\n\n", 1)
    if hashlib.sha256(restored.encode("utf-8")).hexdigest() != disclosure["before_sha256"]:
        raise SystemExit("published GOLD annotation does not restore the sealed dossier")
    try:
        effective = current_miner_probe(REPO_ROOT)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"published amendment consumer closure failed: {exc}") from exc
    if effective != W1A1_EFFECTIVE_MINER_PROBE:
        raise SystemExit("published amendment consumer returned the wrong effective roster")


def _publish(stage_root: Path, staged_gold: Path, receipt: dict[str, Any]) -> None:
    lock_key = hashlib.sha256(str(REPO_ROOT.resolve()).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"stock-identity-w1a1-{lock_key}.lock"
    lock_handle = lock_path.open("a+", encoding="utf-8")
    lock_acquired = False
    try:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_acquired = True
        except BlockingIOError as exc:
            raise SystemExit("another W1-A1 publication is already in progress") from exc
        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write(f"pid={os.getpid()}\nrepo={REPO_ROOT.resolve()}\n")
        lock_handle.flush()

        _validate_outputs_absent()
        _validate_frozen_hashes()
        gold_path = REPO_ROOT / DISCLOSURE_ONLY_PATH
        original_gold = gold_path.read_bytes()
        try:
            for relative in OUTPUT_PATHS[1:]:
                _publish_file(stage_root / relative, REPO_ROOT / relative)
            _publish_file(staged_gold, gold_path)
            # Receipt last: its presence means every governed output and disclosure landed.
            _publish_file(stage_root / RECEIPT_RELATIVE_PATH, REPO_ROOT / RECEIPT_RELATIVE_PATH)
            # Closure remains inside the transaction. A failure here rolls everything back.
            _validate_published(receipt)
        except BaseException:
            # Every registered additive target was absent at preflight, so removing them
            # is a true rollback, never deletion of a pre-existing user artifact.
            for relative in OUTPUT_PATHS:
                (REPO_ROOT / relative).unlink(missing_ok=True)
                (REPO_ROOT / relative).with_name(
                    (REPO_ROOT / relative).name + ".w1a1.tmp"
                ).unlink(missing_ok=True)
            rollback_source = gold_path.with_name("GOLD.md.w1a1.rollback-source")
            rollback_source.write_bytes(original_gold)
            try:
                _publish_file(rollback_source, gold_path)
            finally:
                rollback_source.unlink(missing_ok=True)
            raise
    finally:
        try:
            if lock_acquired:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
            # Keep the stable per-repository inode. Unlinking after unlock lets a
            # waiter acquire the old inode while a third process creates and locks a
            # new one at the same path, defeating mutual exclusion.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w1-reference-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    registration_commit = _validate_clean_pushed_registration()
    pull_request_context = _validate_current_pull_request(registration_commit)
    _validate_prerequisites()
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
    if "reused_ticker_acked" not in gold["flags"] or {
        "reused_ticker_unacked", "compute_blocklisted"
    } & set(gold["flags"]):
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
            pull_request_context=pull_request_context,
        )
        staged_gold = Path(staged_gold_raw)
        _validate_staged(stage_root, receipt, staged_gold)
        _validate_frozen_hashes()
        _publish(stage_root, staged_gold, receipt)
    print(
        f"[W1-A1] published B-only amendment: {receipt['result_counts']} · "
        "GOLD measured rows unchanged · receipt written last",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
