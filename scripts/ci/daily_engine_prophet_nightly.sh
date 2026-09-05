#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `engine`, step `Prophet nightly (plan refresh + ledger advancement; R2 after checkpoint)`.
# 2026-08-26 512KB processing-cap headroom diet (tests/test_workflow_file_size.py;
# PR #6499 left ~36 bytes of headroom). Env comes from the step's `env:` block,
# which stays in the YAML.
# Invoked as: bash scripts/ci/daily_engine_prophet_nightly.sh
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

set +e
PROPHET_BASELINE="${RUNNER_TEMP}/prophet-build-${GITHUB_RUN_ID}.before.json"
PROPHET_DELTA="${RUNNER_TEMP}/prophet-build-${GITHUB_RUN_ID}.delta.tsv"
PROPHET_SOURCE_SNAPSHOT="${RUNNER_TEMP}/prophet-source-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT:-1}.json"
PROPHET_SOURCE_BLOB="${RUNNER_TEMP}/prophet-source-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT:-1}.us_standouts.json"
export PROPHET_BASELINE PROPHET_DELTA PROPHET_SOURCE_SNAPSHOT PROPHET_SOURCE_BLOB
# Snapshot exactly the builder-owned publication files before running.
# Correction ledgers are INPUTS, never outputs, and are deliberately
# absent from this closed allowlist. The exact board bytes and the full
# uncapped admitted ordering are also frozen before the build. A compact,
# immutable receipt containing only rows that actually originate is added
# to the same manifest after the builder returns; this preserves first-add
# provenance even if the giant engine tail never reaches its broad commit.
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

from engine.prophet_bridge import _make_id, _normalise_iso_date, select_candidates

root = Path(os.environ["GITHUB_WORKSPACE"])
board_rel = "site/factordata/us_standouts.json"
board_path = root / board_rel
board_bytes = board_path.read_bytes()
board_sha256 = hashlib.sha256(board_bytes).hexdigest()
board = json.loads(board_bytes)
staleness = board.get("staleness")
if not isinstance(staleness, dict):
    staleness = {}
board_asof = str(board.get("as_of") or "")[:10] or None
admitted = select_candidates(board, n=None)
candidates: list[dict] = []
for rank, row in enumerate(admitted, start=1):
    ticker = str(row.get("ticker") or "").strip().upper()
    anchor = (row.get("hold") or {}).get("anchor")
    formation = _normalise_iso_date(anchor if anchor else board_asof)
    plan_id = _make_id(ticker, "BULL", formation) if ticker and formation else None
    canonical_row = json.dumps(
        row, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    candidates.append({
        "admission_rank": rank,
        "expected_plan_id": plan_id,
        "board_row_sha256": hashlib.sha256(canonical_row).hexdigest(),
        "board_row": row,
    })
baseline_plan_ids: list[str] = []
for plan_path in sorted((root / "site/prophet/plans").glob("*.json")):
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        continue
    if plan.get("id"):
        baseline_plan_ids.append(str(plan["id"]))
source_snapshot = {
    "schema": "prophet.origination_source_snapshot/v1",
    "source": {
        "path": board_rel,
        "sha256": board_sha256,
        "size_bytes": len(board_bytes),
        "board_asof": board_asof,
        # price_through is the actual ranked-price watermark; board_asof
        # is publication metadata and must never silently substitute for it.
        "source_asof": str(staleness.get("price_through") or "")[:10] or None,
        "price_through": str(staleness.get("price_through") or "")[:10] or None,
        "source_basis": staleness.get("basis"),
        "basis": staleness.get("basis"),
        "delayed": staleness.get("delayed"),
        "unknown": staleness.get("unknown"),
        "staleness": staleness,
        "gate_go": board.get("gate_go"),
    },
    "admitted_count": len(candidates),
    "admitted_candidates": candidates,
    "baseline_plan_ids": sorted(set(baseline_plan_ids)),
}
snapshot_bytes = json.dumps(
    source_snapshot,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
Path(os.environ["PROPHET_SOURCE_SNAPSHOT"]).write_bytes(snapshot_bytes)
Path(os.environ["PROPHET_SOURCE_BLOB"]).write_bytes(board_bytes)
os.chmod(os.environ["PROPHET_SOURCE_BLOB"], 0o400)

exact = {
    "site/prophet/index.json",
    "site/prophet/showcase.json",
    # G-D board read: the ticker-keyed spark bodies that
    # index.json plans[].board_read.fields.spark reference. Build-owned
    # like showcase.json; without this entry the artifact is
    # runner-local and the references resolve to nothing on main.
    "site/prophet/board_read_sparks.json",
    "data/prophet/ledger.jsonl",
    "data/prophet/ledger_quarantine.json",
    "data/prophet_arena/scoreboard.json",
    "data/prophet_arena/price_basis_trigger_v2/C0_champion_mirror.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C1_buy_soon_first.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C3_door_w_union.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C4_dispersion_cap.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C5_align2_gate.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C6_time_stop_21.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C7_buy_soon_admitted.jsonl",
}
globs = {
    "site/prophet/plans": "*.json",
    "site/prophet/states": "*.json",
    "data/prophet/origination_receipts": "*.json",
    # §6.5 legacy shadow: month-grouped DAY parts
    # (legacy_shadow/YYYY-MM/YYYY-MM-DD.parquet). Build-owned and
    # append-only like the receipts; without this the accrual store
    # is runner-local and dies with the runner.
    "data/prophet/legacy_shadow": "*/*.parquet",
}

def digest(path: Path) -> str:
    if path.is_symlink():
        raise RuntimeError(f"refusing symlinked Prophet output: {path}")
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return f"{path.stat().st_mode & 0o7777:04o}:{h.hexdigest()}"

def snapshot() -> dict[str, str]:
    paths = {root / rel for rel in exact}
    for rel_dir, pattern in globs.items():
        directory = root / rel_dir
        if directory.is_dir():
            paths.update(directory.glob(pattern))
    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(paths)
        if path.is_file()
    }

Path(os.environ["PROPHET_BASELINE"]).write_text(
    json.dumps(snapshot(), sort_keys=True), encoding="utf-8"
)
PY
baseline_rc=$?
if [ "$baseline_rc" -ne 0 ]; then
  echo "succeeded=false" >> "$GITHUB_OUTPUT"
  echo "::warning title=build_prophet manifest::could not snapshot the closed Prophet output allowlist (rc=$baseline_rc); build withheld from early publication"
  exit 0
fi

echo "::group::build_prophet (plan refresh + ledger advancement)"
python -m scripts.build_prophet 2>&1; rc=$?
echo "::endgroup::"
if [ "$rc" -eq 0 ]; then
  # Bind every newly-created plan to the exact admitted board row that
  # originated it. The raw board is hashed before/after the build and an
  # immutable byte copy is independently re-hashed here. Any mismatch or
  # unmappable new plan withholds the ENTIRE early checkpoint.
  python3 - <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ["GITHUB_WORKSPACE"])
snapshot_path = Path(os.environ["PROPHET_SOURCE_SNAPSHOT"])
blob_path = Path(os.environ["PROPHET_SOURCE_BLOB"])
snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
source = snapshot["source"]
expected_sha = str(source["sha256"])
live_bytes = (root / source["path"]).read_bytes()
blob_bytes = blob_path.read_bytes()
live_sha = hashlib.sha256(live_bytes).hexdigest()
blob_sha = hashlib.sha256(blob_bytes).hexdigest()
if live_sha != expected_sha or blob_sha != expected_sha or live_bytes != blob_bytes:
    print(
        "::error title=Prophet origination source changed::"
        "us_standouts bytes did not remain identical across the build; "
        "no output from an ambiguous source snapshot will publish",
        flush=True,
    )
    raise SystemExit(2)

baseline_ids = set(snapshot.get("baseline_plan_ids") or [])
current_plans: dict[str, tuple[Path, dict]] = {}
for plan_path in sorted((root / "site/prophet/plans").glob("*.json")):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_id = str(plan.get("id") or "")
    if plan_id:
        current_plans[plan_id] = (plan_path, plan)
new_ids = sorted(set(current_plans) - baseline_ids)
if not new_ids:
    raise SystemExit(0)

# originate_plans is keep-first for duplicate expected IDs, so mirror
# that exact disposition rather than choosing a later duplicate row.
admitted_by_id: dict[str, dict] = {}
for candidate in snapshot.get("admitted_candidates") or []:
    plan_id = candidate.get("expected_plan_id")
    if plan_id:
        admitted_by_id.setdefault(str(plan_id), candidate)

originations: list[dict] = []
missing: list[str] = []
for plan_id in new_ids:
    candidate = admitted_by_id.get(plan_id)
    if candidate is None:
        missing.append(plan_id)
        continue
    plan_path, plan = current_plans[plan_id]
    plan_bytes = plan_path.read_bytes()
    originations.append({
        "plan_id": plan_id,
        "asset": plan.get("asset"),
        "formation_date": plan.get("formation_date"),
        "plan_path": plan_path.relative_to(root).as_posix(),
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "admission_rank": candidate["admission_rank"],
        "board_row_sha256": candidate["board_row_sha256"],
        "board_row": candidate["board_row"],
    })
if missing:
    print(
        "::error title=Prophet origination receipt incomplete::"
        "new plan(s) do not resolve to the frozen admitted board: "
        + ", ".join(missing),
        flush=True,
    )
    raise SystemExit(3)

run_id = str(os.environ.get("GITHUB_RUN_ID") or "unknown")
run_attempt = str(os.environ.get("GITHUB_RUN_ATTEMPT") or "1")
receipt_id = f"{run_id}-{run_attempt}-{expected_sha[:16]}"
receipt = {
    "schema": "prophet.origination_receipt/v1",
    "receipt_id": receipt_id,
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "run": {
        "id": run_id,
        "attempt": run_attempt,
        "event": os.environ.get("GITHUB_EVENT_NAME"),
        "ref": os.environ.get("GITHUB_REF"),
        "event_sha": os.environ.get("GITHUB_SHA"),
        "source_checkout": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
    },
    # Copy, do not merely reference, the freshness/provenance fields:
    # chronology audits must still resolve the true source after a tail
    # loss even when HEAD's board has already advanced.
    "source": source,
    "selection": {
        "rule": "engine.prophet_bridge.select_candidates(n=None)",
        "admitted_count": snapshot.get("admitted_count"),
        "originated_count": len(originations),
    },
    "originated_plan_ids": new_ids,
    "originations": originations,
}
encoded = (
    json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
).encode("utf-8")
receipt_dir = root / "data/prophet/origination_receipts"
receipt_dir.mkdir(parents=True, exist_ok=True)
receipt_path = receipt_dir / f"{receipt_id}.json"
if receipt_path.exists():
    if receipt_path.read_bytes() != encoded:
        print(
            "::error title=Prophet immutable receipt collision::"
            f"{receipt_path.relative_to(root)} already exists with different bytes",
            flush=True,
        )
        raise SystemExit(4)
else:
    try:
        with receipt_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if receipt_path.read_bytes() != encoded:
            raise SystemExit(4)
print(
    f"Prophet origination receipt: {receipt_path.relative_to(root)} "
    f"({len(originations)} plan(s), source {expected_sha})",
    flush=True,
)
PY
  receipt_rc=$?
  if [ "$receipt_rc" -ne 0 ]; then
    echo "succeeded=false" >> "$GITHUB_OUTPUT"
    echo "::warning title=build_prophet receipt::build returned 0 but exact origination provenance could not be frozen (rc=$receipt_rc); early publication withheld"
    exit 0
  fi
  # Emit an explicit delta manifest: path, pre-build fingerprint
  # (mode + SHA-256, or MISSING), post-build fingerprint. Deletion is
  # not a supported Prophet
  # operation; refusing it prevents a stale run from erasing a newer
  # immutable plan, state, or append-only ledger publication.
  python3 - <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["GITHUB_WORKSPACE"])
exact = {
    "site/prophet/index.json",
    "site/prophet/showcase.json",
    # G-D board read: the ticker-keyed spark bodies that
    # index.json plans[].board_read.fields.spark reference. Build-owned
    # like showcase.json; without this entry the artifact is
    # runner-local and the references resolve to nothing on main.
    "site/prophet/board_read_sparks.json",
    "data/prophet/ledger.jsonl",
    "data/prophet/ledger_quarantine.json",
    "data/prophet_arena/scoreboard.json",
    "data/prophet_arena/price_basis_trigger_v2/C0_champion_mirror.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C1_buy_soon_first.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C3_door_w_union.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C4_dispersion_cap.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C5_align2_gate.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C6_time_stop_21.jsonl",
    "data/prophet_arena/price_basis_trigger_v2/C7_buy_soon_admitted.jsonl",
}
globs = {
    "site/prophet/plans": "*.json",
    "site/prophet/states": "*.json",
    "data/prophet/origination_receipts": "*.json",
    # §6.5 legacy shadow: month-grouped DAY parts
    # (legacy_shadow/YYYY-MM/YYYY-MM-DD.parquet). Build-owned and
    # append-only like the receipts; without this the accrual store
    # is runner-local and dies with the runner.
    "data/prophet/legacy_shadow": "*/*.parquet",
}

def digest(path: Path) -> str:
    if path.is_symlink():
        raise RuntimeError(f"refusing symlinked Prophet output: {path}")
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return f"{path.stat().st_mode & 0o7777:04o}:{h.hexdigest()}"

def snapshot() -> dict[str, str]:
    paths = {root / rel for rel in exact}
    for rel_dir, pattern in globs.items():
        directory = root / rel_dir
        if directory.is_dir():
            paths.update(directory.glob(pattern))
    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(paths)
        if path.is_file()
    }

before = json.loads(
    Path(os.environ["PROPHET_BASELINE"]).read_text(encoding="utf-8")
)
after = snapshot()
deleted = sorted(set(before) - set(after))
if deleted:
    print(
        "::error title=Prophet build deleted owned output::"
        + ", ".join(deleted[:8])
        + " — early checkpoint refuses all deletions",
        flush=True,
    )
    sys.exit(2)
changed = sorted(path for path, sha in after.items() if before.get(path) != sha)
with Path(os.environ["PROPHET_DELTA"]).open("w", encoding="utf-8") as fh:
    for path in changed:
        fh.write(f"{path}\t{before.get(path, 'MISSING')}\t{after[path]}\n")
PY
  manifest_rc=$?
  if [ "$manifest_rc" -eq 0 ]; then
    echo "succeeded=true" >> "$GITHUB_OUTPUT"
    echo "delta_manifest=$PROPHET_DELTA" >> "$GITHUB_OUTPUT"
  else
    echo "succeeded=false" >> "$GITHUB_OUTPUT"
    echo "::warning title=build_prophet manifest::build returned 0 but its owned-output delta could not be proven (rc=$manifest_rc); early publication withheld"
  fi
else
  echo "succeeded=false" >> "$GITHUB_OUTPUT"
  echo "::warning title=build_prophet::rc=$rc (non-fatal — prophet artifacts degrade gracefully)"
fi
exit 0
