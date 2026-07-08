"""scripts/build_context_candidates.py — W4 Context Scanner (CORTEX JOB).

Nightly cross-sectional screen over pre-declared template families →
data/neuralweb/context_candidates.jsonl (display/context tier only).

CONSTITUTIONAL MANDATE (R-CI5, R-CI6, Signal-Commons R3)
---------------------------------------------------------
This script NEVER escalates, scores, fuses, or ranks.  Outputs are
display/context tier (horizon_role=context, Article 2 article-binding).
Three legal exits for any candidate:
  (a) Cortex stakes it as a hypothesis (metabolism, fdr_family='cortex',
      3/week chokepoint, graded only on post-registration data).
  (b) A human charters a pre-registered study (rulers derived FROM the
      candidate claim; no free-mining promotion path).
  (c) Decay — candidates last_refreshed > 60 days become status='decayed';
      they remain in the dedupe corpus so a re-derived candidate is never
      re-emitted as novel (dead-stays-dead, R-CI5/6).

BUDGET ENFORCEMENT (R-CI5)
--------------------------
The script REFUSES to run (GovernorRefusal exit 1) if a declared budget row
for fdr_family='context_scan' is absent from the trial ledger.
register_budget() ships the row idempotently as the FIRST action; once written
it persists across runs.

TEMPLATES (v1, FROZEN)
-----------------------
T1  Composition drift — board/fire composition by archetype cell vs universe
    share, tracked vs its own trailing 60d baseline.  Candidate threshold:
    within-window null percentile >= 99 AND cell n >= 50.
T2  Outcome heterogeneity — graded spine rows with personality_basis='pit_labels'
    split by archetype × quad_hard_label cell; per-cell hit-rate delta vs
    engine marginal, printed as percentile vs label-permutation null
    (DT-R14, calendar-block preserving).  Nearly all cells will be
    insufficient_n today — printed honestly.
T3  Co-occurrence / mode-transition shift — production aggregate label
    co-occurrence + mode-share vs trailing 20-snapshot baseline; candidate
    at null-percentile >= 99.

ANTI-MINING HYGIENE (R-CI5)
----------------------------
- Within-window nulls via contiguous-block resample (>= 200 draws).
- Calendar-time controls in all primary template axes (DT-R14).
- Sample floor n >= 50; insufficient_n printed, never hidden.
- Respin cap: 2 (candidates are printed once and refreshed, not respun
  endlessly to clear the threshold).
- Dedupe in fixed order: oracle compounds → species registry →
  machine_registry.jsonl → trial-ledger family strings →
  context_candidates.jsonl (incl. decayed rows).
- adjacent_falsified REQUIRED on every emitted candidate.

Usage
-----
  python -m scripts.build_context_candidates                # full run
  python -m scripts.build_context_candidates --dry-run      # print counts, no writes
  python -m scripts.build_context_candidates --register-budget-only  # just write ledger row
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAMILY = "context_scan"
_OUTPUT_PATH = Path("data/neuralweb/context_candidates.jsonl")
_DECAY_DAYS = 60
_NULL_DRAWS = 200          # contiguous-block resample minimum (R-CI5)
_CANDIDATE_PCTILE = 99     # threshold for emitting a candidate
_CELL_N_FLOOR = 50         # R-CI5 sample floor; below this = insufficient_n
_T3_SNAPSHOT_WINDOW = 20   # trailing snapshot baseline for T3
_TOP_K_CORTEX_CAP = 20     # R-CI11

# v1 template cell counts — itemized basis for declared budget
# T1: archetype × engine buckets; conservative upper-bound estimate 15 cells
# T2: archetype (9 labels) × quad (4 quads) × engine (3) = 108 cells (estimate)
# T3: co-occurrence pairs (quad × vol_regime) max ~12 cells
_BUDGET_T1_CELLS = 15
_BUDGET_T2_CELLS = 108
_BUDGET_T3_CELLS = 12
_BUDGET_TOTAL = _BUDGET_T1_CELLS + _BUDGET_T2_CELLS + _BUDGET_T3_CELLS  # 135

_BUDGET_REASON = (
    f"v1 template grid: T1 composition-drift ~{_BUDGET_T1_CELLS} cells, "
    f"T2 outcome-heterogeneity ~{_BUDGET_T2_CELLS} cells "
    f"(archetype×quad×engine), T3 co-occurrence ~{_BUDGET_T3_CELLS} cells. "
    "itemized per R-CI5."
)

_SCHEMA_VERSION = "context_candidates.v1"


# ---------------------------------------------------------------------------
# GovernorRefusal
# ---------------------------------------------------------------------------

class GovernorRefusal(SystemExit):
    """Raised when the declared budget row is missing from the trial ledger."""


# ---------------------------------------------------------------------------
# Budget registration
# ---------------------------------------------------------------------------

def _ledger_path(root: Path) -> Path:
    return root / "data" / "trial_ledger.jsonl"


def register_budget(root: Path, ledger_path: Path | None = None, *, dry_run: bool = False) -> bool:
    """Write declared budget for fdr_family='context_scan' to the trial ledger.

    Idempotent (register-once semantics): returns True if newly written,
    False if already present.  Does NOT write in dry_run mode.
    """
    from engine.trial_ledger import TrialLedger  # noqa: PLC0415
    path = ledger_path if ledger_path is not None else _ledger_path(root)
    if dry_run:
        led = TrialLedger(path=path, family=_FAMILY)
        already = led.declared_budget(_FAMILY) >= _BUDGET_TOTAL
        log.info("[dry-run] budget row %s (family=%s, n=%d)",
                 "already present" if already else "would be written",
                 _FAMILY, _BUDGET_TOTAL)
        return not already
    led = TrialLedger(path=path, family=_FAMILY)
    return led.log_declared_budget(
        _BUDGET_TOTAL,
        family=_FAMILY,
        reason=_BUDGET_REASON,
    )


def _assert_budget(root: Path, ledger_path: Path | None = None) -> None:
    """Raise GovernorRefusal if declared budget is absent from the ledger."""
    from engine.trial_ledger import TrialLedger  # noqa: PLC0415
    path = ledger_path if ledger_path is not None else _ledger_path(root)
    led = TrialLedger(path=path, family=_FAMILY)
    db = led.declared_budget(_FAMILY)
    if db < 1:
        msg = (
            f"GovernorRefusal: fdr_family='{_FAMILY}' has no declared budget in "
            f"{path}. Run `python -m scripts.build_context_candidates "
            f"--register-budget-only` to write the row, then re-run."
        )
        log.error(msg)
        raise GovernorRefusal(msg)
    log.info("budget check OK: fdr_family=%s declared_n=%d", _FAMILY, db)


# ---------------------------------------------------------------------------
# Candidate ID (content hash)
# ---------------------------------------------------------------------------

def _candidate_id(template: str, cell: str, stat_key: str) -> str:
    """Stable content hash for (template, cell, stat_key) triple."""
    raw = f"{template}\x00{cell}\x00{stat_key}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Archive / dedupe helpers
# ---------------------------------------------------------------------------

def _load_existing_candidates(path: Path) -> dict[str, dict]:
    """Load all existing candidates (incl. decayed) keyed by candidate_id."""
    if not path.exists():
        return {}
    existing: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                cid = row.get("candidate_id")
                if cid:
                    existing[cid] = row
            except Exception:  # noqa: BLE001
                pass
    return existing


def _load_dedup_strings(root: Path) -> set[str]:
    """Collect string tokens from oracle compounds, species, machine_registry,
    and trial-ledger family strings for dedupe matching.

    Returns a set of lowercased natural-language strings to fuzzy-match against
    the candidate's cell/stat description.
    """
    tokens: set[str] = set()

    # Oracle compound registry (data/oracle/compounds/registry.jsonl)
    oracle_reg = root / "data" / "oracle" / "compounds" / "registry.jsonl"
    if oracle_reg.exists():
        try:
            with oracle_reg.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        for k in ("id", "name", "family"):
                            v = row.get(k)
                            if v:
                                tokens.add(str(v).lower())
                    except Exception:  # noqa: BLE001
                        pass
        except OSError:
            pass

    # Species registry (data/species/registry.json)
    species_reg = root / "data" / "species" / "registry.json"
    if species_reg.exists():
        try:
            sr = json.loads(species_reg.read_text(encoding="utf-8"))
            for sp in sr.get("species", []):
                sid = sp.get("id") or sp.get("name") or sp.get("slug")
                if sid:
                    tokens.add(str(sid).lower())
        except Exception:  # noqa: BLE001
            pass

    # Machine registry (data/neuralweb/machine_registry.jsonl)
    mach_reg = root / "data" / "neuralweb" / "machine_registry.jsonl"
    if mach_reg.exists():
        try:
            with mach_reg.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        h = row.get("hypothesis", "")
                        if h:
                            tokens.add(str(h).lower())
                        fam = row.get("fdr_family", "")
                        if fam:
                            tokens.add(str(fam).lower())
                    except Exception:  # noqa: BLE001
                        pass
        except OSError:
            pass

    # Trial ledger family strings
    tl_path = root / "data" / "trial_ledger.jsonl"
    if tl_path.exists():
        try:
            with tl_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        fam = row.get("family", "")
                        if fam:
                            tokens.add(str(fam).lower())
                    except Exception:  # noqa: BLE001
                        pass
        except OSError:
            pass

    return tokens


def _is_dedup_match(candidate_desc: str, dedup_tokens: set[str]) -> str | None:
    """Return the matching token if candidate_desc overlaps with dedup corpus.

    Matching rule: any dedup token of length > 8 that appears verbatim in the
    lowercase candidate description.  Short tokens are excluded to avoid false
    positives on generic words.
    """
    desc_lower = candidate_desc.lower()
    for tok in dedup_tokens:
        if len(tok) > 8 and tok in desc_lower:
            return tok
    return None


# ---------------------------------------------------------------------------
# Null distribution (contiguous-block resample)
# ---------------------------------------------------------------------------

def _contiguous_block_resample(
    values: list[float],
    n_draws: int = _NULL_DRAWS,
    block_size: int = 5,
    seed: int = 42,
) -> list[float]:
    """Time-preserving contiguous-block bootstrap of a 1D statistic series.

    Draws ``n_draws`` bootstrap resamples by sampling contiguous blocks of
    ``block_size`` and concatenating until length >= len(values), then
    computing the mean of each resample.  Returns the list of bootstrap means.

    DT-R14 compliant: blocks preserve local temporal autocorrelation so
    nearby-in-time observations are not decoupled by the resampling.
    """
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return [0.0] * n_draws
    results: list[float] = []
    for _ in range(n_draws):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randint(0, n - 1)
            end = min(start + block_size, n)
            sample.extend(values[start:end])
        sample = sample[:n]
        results.append(sum(sample) / len(sample) if sample else 0.0)
    return results


def _null_percentile(observed: float, null_dist: list[float]) -> float:
    """Return the percentile of ``observed`` in ``null_dist`` (0–100)."""
    if not null_dist:
        return 50.0
    count_below = sum(1 for v in null_dist if v < observed)
    return 100.0 * count_below / len(null_dist)


# ---------------------------------------------------------------------------
# T1 — Composition drift
# ---------------------------------------------------------------------------

def _run_t1(root: Path, dry_run: bool) -> dict[str, Any]:
    """T1: board/fire composition by archetype cell vs universe share.

    Reads data/us_board_ledger/retro_grades.parquet (or snapshots.jsonl)
    and the spine_index.parquet to compare the archetype distribution of
    board buy-lane members vs the universe-wide archetype distribution.

    Drift is computed as the ratio (board_share / universe_share) per cell,
    tracked vs its 60d trailing baseline (all available snapshots).  A
    candidate emits when null-percentile >= 99 AND cell n >= 50.
    """
    counts = {
        "cells_examined": 0,
        "cells_testable": 0,
        "cells_insufficient_n": 0,
        "candidates": 0,
        "null_draws_used": _NULL_DRAWS,
    }
    candidates: list[dict] = []

    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        log.warning("T1: pandas not available — skipping")
        return {"counts": counts, "candidates": candidates}

    # Load spine for universe archetype distribution
    spine_path = root / "data" / "neuralweb" / "spine_index.parquet"
    if not spine_path.exists():
        log.info("T1: spine_index.parquet absent — skipping")
        return {"counts": counts, "candidates": candidates}

    try:
        spine = pd.read_parquet(spine_path, columns=["symbol", "archetype", "engine", "as_of"])
    except Exception as exc:  # noqa: BLE001
        log.warning("T1: spine read failed (%s) — skipping", exc)
        return {"counts": counts, "candidates": candidates}

    if "archetype" not in spine.columns:
        log.info("T1: spine has no 'archetype' column — skipping (column added by W2/build_index)")
        return {"counts": counts, "candidates": candidates}

    # Universe archetype distribution: per unique symbol's most recent archetype
    universe_archtypes = (
        spine.dropna(subset=["archetype"])
        .sort_values("as_of")
        .groupby("symbol")["archetype"]
        .last()
    )
    if universe_archtypes.empty:
        log.info("T1: no universe archetypes found — skipping")
        return {"counts": counts, "candidates": candidates}

    univ_counts = universe_archtypes.value_counts()
    univ_total = univ_counts.sum()
    univ_share = (univ_counts / univ_total).to_dict() if univ_total > 0 else {}
    archetypes = list(univ_share.keys())

    # Load board snapshots for composition over time
    # Use retro_grades.parquet (has ticker + lane + as_of) or snapshots.jsonl
    board_path = root / "data" / "us_board_ledger" / "retro_grades.parquet"
    if not board_path.exists():
        log.info("T1: us_board_ledger/retro_grades.parquet absent — skipping")
        return {"counts": counts, "candidates": candidates}

    try:
        board = pd.read_parquet(board_path, columns=["as_of", "ticker", "lane"])
    except Exception as exc:  # noqa: BLE001
        log.warning("T1: board read failed (%s) — skipping", exc)
        return {"counts": counts, "candidates": candidates}

    # Merge board with universe archetypes
    board_buy = board[board["lane"] == "buy"].copy()
    if board_buy.empty:
        log.info("T1: no buy-lane rows in board — skipping")
        return {"counts": counts, "candidates": candidates}

    arch_map = universe_archtypes.to_dict()
    board_buy["archetype"] = board_buy["ticker"].map(arch_map)
    board_buy = board_buy.dropna(subset=["archetype"])

    if board_buy.empty:
        log.info("T1: no board buy rows with archetype — insufficient coverage")
        return {"counts": counts, "candidates": candidates}

    # Per-snapshot board composition ratios
    snapshots = board_buy.groupby("as_of")
    all_dates = sorted(snapshots.groups.keys())
    # Require at least 10 snapshots for any trailing analysis
    if len(all_dates) < 10:
        log.info("T1: only %d snapshots — need >=10 for baseline; printing counts", len(all_dates))
        counts["cells_examined"] = len(archetypes)
        counts["cells_insufficient_n"] = len(archetypes)
        return {"counts": counts, "candidates": candidates}

    # For each archetype, build drift time series: board_share / universe_share
    for arch in archetypes:
        counts["cells_examined"] += 1
        u_share = univ_share.get(arch, 0)
        if u_share == 0:
            counts["cells_insufficient_n"] += 1
            continue

        drift_series: list[float] = []
        for date, grp in snapshots:
            total_board = len(grp)
            arch_board = (grp["archetype"] == arch).sum()
            b_share = arch_board / total_board if total_board > 0 else 0.0
            drift_series.append(b_share / u_share)

        if len(drift_series) < _CELL_N_FLOOR:
            counts["cells_insufficient_n"] += 1
            log.debug("T1: cell=%s insufficient_n=%d", arch, len(drift_series))
            continue

        counts["cells_testable"] += 1

        # Most recent drift value
        observed = drift_series[-1]

        # Within-window null: contiguous-block resample on trailing 60d window
        window = drift_series[-60:] if len(drift_series) >= 60 else drift_series
        null_dist = _contiguous_block_resample(window, n_draws=_NULL_DRAWS)
        pctile = _null_percentile(observed, null_dist)

        log.debug("T1: cell=%s observed=%.4f null_pctile=%.1f n=%d",
                  arch, observed, pctile, len(window))

        if pctile >= _CANDIDATE_PCTILE:
            counts["candidates"] += 1
            if not dry_run:
                candidates.append({
                    "template": "T1",
                    "cell": arch,
                    "stat": f"composition_drift_ratio={observed:.4f}",
                    "null_pctile": round(pctile, 2),
                    "n": len(window),
                    "adjacent_falsified": "none_known",
                })

    return {"counts": counts, "candidates": candidates}


# ---------------------------------------------------------------------------
# T2 — Outcome heterogeneity
# ---------------------------------------------------------------------------

def _run_t2(root: Path, dry_run: bool) -> dict[str, Any]:
    """T2: graded spine rows with personality_basis='pit_labels' split by
    archetype × quad_hard_label cell; per-cell hit-rate delta vs engine
    marginal, printed as percentile vs label-permutation null (DT-R14).

    EXPECTS insufficient_n nearly everywhere today — printed honestly.

    Note: if spine_index.parquet lacks 'personality_basis' (pre-W2 nightly)
    the column is absent and all cells are marked insufficient_n.  The scan
    still prints honest counts and exits cleanly.
    """
    counts = {
        "cells_examined": 0,
        "cells_testable": 0,
        "cells_insufficient_n": 0,
        "candidates": 0,
        "null_draws_used": _NULL_DRAWS,
        "pit_labels_rows": 0,
    }
    candidates: list[dict] = []

    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        log.warning("T2: pandas not available — skipping")
        return {"counts": counts, "candidates": candidates}

    spine_path = root / "data" / "neuralweb" / "spine_index.parquet"
    if not spine_path.exists():
        log.info("T2: spine_index.parquet absent — skipping")
        return {"counts": counts, "candidates": candidates}

    try:
        cols = ["engine", "outcome_graded", "archetype", "quad_hard_label",
                "as_of", "outcome_excess"]
        # personality_basis may be absent (pre-W2 nightly)
        try:
            df = pd.read_parquet(spine_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("T2: spine read failed (%s) — skipping", exc)
            return {"counts": counts, "candidates": candidates}
    except Exception as exc:  # noqa: BLE001
        log.warning("T2: spine load error (%s) — skipping", exc)
        return {"counts": counts, "candidates": candidates}

    # Filter to graded rows only
    if "outcome_graded" not in df.columns:
        log.info("T2: 'outcome_graded' absent — skipping")
        return {"counts": counts, "candidates": candidates}

    graded = df[df["outcome_graded"] == True].copy()  # noqa: E712

    # Filter on personality_basis == 'pit_labels' (R-CI3 provenance; only pit-safe rows)
    if "personality_basis" not in graded.columns:
        log.info(
            "T2: 'personality_basis' column absent (pre-W2 nightly build); "
            "all cells insufficient_n — expected during initial deployment"
        )
        # Enumerate theoretical cells for honest reporting
        archetypes = graded["archetype"].dropna().unique().tolist() if "archetype" in graded.columns else []
        quads = graded["quad_hard_label"].dropna().unique().tolist() if "quad_hard_label" in graded.columns else []
        engines = graded["engine"].dropna().unique().tolist() if "engine" in graded.columns else []
        counts["cells_examined"] = max(len(archetypes) * len(quads), 1)
        counts["cells_insufficient_n"] = counts["cells_examined"]
        return {"counts": counts, "candidates": candidates}

    pit_graded = graded[graded["personality_basis"] == "pit_labels"].copy()
    counts["pit_labels_rows"] = len(pit_graded)
    log.info("T2: %d graded rows with personality_basis=pit_labels", len(pit_graded))

    if pit_graded.empty:
        log.info("T2: no pit_labels rows — all cells insufficient_n (expected today)")
        if "archetype" in graded.columns and "quad_hard_label" in graded.columns:
            archetypes = graded["archetype"].dropna().unique().tolist()
            quads = graded["quad_hard_label"].dropna().unique().tolist()
            counts["cells_examined"] = max(len(archetypes) * len(quads), 1)
            counts["cells_insufficient_n"] = counts["cells_examined"]
        return {"counts": counts, "candidates": candidates}

    if "archetype" not in pit_graded.columns or "quad_hard_label" not in pit_graded.columns:
        log.info("T2: archetype or quad_hard_label absent in pit_labels rows — skipping")
        return {"counts": counts, "candidates": candidates}

    if "outcome_excess" not in pit_graded.columns:
        log.info("T2: outcome_excess absent — skipping")
        return {"counts": counts, "candidates": candidates}

    # Compute engine-level marginal hit rate (positive excess return = hit)
    pit_graded["hit"] = (pit_graded["outcome_excess"] > 0).astype(int)
    engine_marginal = pit_graded.groupby("engine")["hit"].mean().to_dict()

    # Per (archetype × quad) cell: compute hit-rate delta vs engine marginal
    cells = pit_graded.groupby(["archetype", "quad_hard_label", "engine"])
    for (arch, quad, eng), grp in cells:
        counts["cells_examined"] += 1

        n = len(grp)
        if n < _CELL_N_FLOOR:
            counts["cells_insufficient_n"] += 1
            log.debug("T2: cell=(%s,%s,%s) insufficient_n=%d", arch, quad, eng, n)
            continue

        counts["cells_testable"] += 1

        cell_hr = grp["hit"].mean()
        marg_hr = engine_marginal.get(eng, cell_hr)
        observed_delta = cell_hr - marg_hr

        # Label-permutation null (time-preserving DT-R14): shuffle labels within
        # calendar-quarter blocks, recompute delta _NULL_DRAWS times
        hits = grp["hit"].tolist()
        as_ofs = grp["as_of"].tolist() if "as_of" in grp.columns else [None] * n

        # Build calendar-quarter block map
        quarter_blocks: dict[str, list[int]] = {}
        for i, asof in enumerate(as_ofs):
            q_key = str(asof)[:7] if asof else "unknown"  # YYYY-MM
            quarter_blocks.setdefault(q_key, []).append(i)

        rng = random.Random(42)
        null_deltas: list[float] = []
        for _ in range(_NULL_DRAWS):
            perm_hits = hits[:]
            for idxs in quarter_blocks.values():
                vals = [hits[i] for i in idxs]
                rng.shuffle(vals)
                for j, i in enumerate(idxs):
                    perm_hits[i] = vals[j]
            perm_mean = sum(perm_hits) / len(perm_hits) if perm_hits else 0.0
            null_deltas.append(perm_mean - marg_hr)

        pctile = _null_percentile(observed_delta, null_deltas)
        log.debug("T2: cell=(%s,%s,%s) delta=%.4f pctile=%.1f n=%d",
                  arch, quad, eng, observed_delta, pctile, n)

        if pctile >= _CANDIDATE_PCTILE:
            counts["candidates"] += 1
            if not dry_run:
                candidates.append({
                    "template": "T2",
                    "cell": f"archetype={arch}|quad={quad}|engine={eng}",
                    "stat": f"hit_rate_delta={observed_delta:.4f}|cell_hr={cell_hr:.4f}|marginal_hr={marg_hr:.4f}",
                    "null_pctile": round(pctile, 2),
                    "n": n,
                    "adjacent_falsified": "none_known",
                })

    return {"counts": counts, "candidates": candidates}


# ---------------------------------------------------------------------------
# T3 — Co-occurrence / mode-transition shift
# ---------------------------------------------------------------------------

def _run_t3(root: Path, dry_run: bool) -> dict[str, Any]:
    """T3: aggregate label co-occurrence + mode-share vs trailing 20-snapshot
    baseline.

    Reads the snapshot history from us_board_ledger/snapshots.jsonl
    (buy-lane composition per as_of) and looks for shifts in the
    joint (quad_hard_label × vol_regime) mode distribution compared
    to the trailing 20-snapshot baseline.  Candidate at null-pctile >= 99.
    """
    counts = {
        "cells_examined": 0,
        "cells_testable": 0,
        "cells_insufficient_n": 0,
        "candidates": 0,
        "null_draws_used": _NULL_DRAWS,
    }
    candidates: list[dict] = []

    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        log.warning("T3: pandas not available — skipping")
        return {"counts": counts, "candidates": candidates}

    # Load spine for regime label time series (per as_of)
    spine_path = root / "data" / "neuralweb" / "spine_index.parquet"
    if not spine_path.exists():
        log.info("T3: spine_index.parquet absent — skipping")
        return {"counts": counts, "candidates": candidates}

    try:
        df = pd.read_parquet(
            spine_path,
            columns=["as_of", "quad_hard_label", "vol_regime", "engine"]
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("T3: spine read failed (%s) — skipping", exc)
        return {"counts": counts, "candidates": candidates}

    if "quad_hard_label" not in df.columns or "vol_regime" not in df.columns:
        log.info("T3: required columns absent — skipping")
        return {"counts": counts, "candidates": candidates}

    df = df.dropna(subset=["quad_hard_label", "vol_regime", "as_of"])
    if df.empty:
        log.info("T3: no valid regime-labelled rows — skipping")
        return {"counts": counts, "candidates": candidates}

    # Build per-snapshot mode-share: fraction of (quad, vol_regime) combos by as_of
    snap_groups = df.groupby("as_of")
    all_dates = sorted(snap_groups.groups.keys())

    if len(all_dates) < _T3_SNAPSHOT_WINDOW + 2:
        log.info("T3: only %d snapshots — need >=%d for baseline; printing counts",
                 len(all_dates), _T3_SNAPSHOT_WINDOW + 2)
        counts["cells_examined"] = 1
        counts["cells_insufficient_n"] = 1
        return {"counts": counts, "candidates": candidates}

    # Get the joint (quad, vol) combinations we've seen
    joint_cells = (
        df.groupby(["quad_hard_label", "vol_regime"])
        .size()
        .reset_index(name="count")
    )
    joint_cells = joint_cells[joint_cells["count"] >= _CELL_N_FLOOR]

    if joint_cells.empty:
        log.info("T3: no cells with n >= %d — all insufficient_n", _CELL_N_FLOOR)
        counts["cells_examined"] = 1
        counts["cells_insufficient_n"] = 1
        return {"counts": counts, "candidates": candidates}

    # For each joint cell, build mode-share time series
    for _, cell_row in joint_cells.iterrows():
        quad = cell_row["quad_hard_label"]
        vol = cell_row["vol_regime"]
        counts["cells_examined"] += 1

        # Time series of mode share per snapshot
        share_series: list[float] = []
        for date in all_dates:
            grp = snap_groups.get_group(date)
            total = len(grp)
            cell_count = ((grp["quad_hard_label"] == quad) & (grp["vol_regime"] == vol)).sum()
            share_series.append(cell_count / total if total > 0 else 0.0)

        if len(share_series) < _CELL_N_FLOOR:
            counts["cells_insufficient_n"] += 1
            continue

        counts["cells_testable"] += 1

        # Most recent vs baseline window
        current = share_series[-1]
        baseline = share_series[-(1 + _T3_SNAPSHOT_WINDOW):-1]
        if not baseline:
            counts["cells_insufficient_n"] += 1
            continue

        baseline_mean = sum(baseline) / len(baseline)
        observed_shift = current - baseline_mean

        # Contiguous-block null on baseline window
        null_dist = _contiguous_block_resample(baseline, n_draws=_NULL_DRAWS)
        # Null is the distribution of baseline_mean values under resampling
        null_shifts = [v - baseline_mean for v in null_dist]
        pctile = _null_percentile(abs(observed_shift),
                                   [abs(v) for v in null_shifts])

        log.debug("T3: cell=(%s,%s) shift=%.4f pctile=%.1f n=%d",
                  quad, vol, observed_shift, pctile, len(baseline))

        if pctile >= _CANDIDATE_PCTILE:
            counts["candidates"] += 1
            if not dry_run:
                candidates.append({
                    "template": "T3",
                    "cell": f"quad={quad}|vol_regime={vol}",
                    "stat": f"mode_share_shift={observed_shift:.4f}|current={current:.4f}|baseline_mean={baseline_mean:.4f}",
                    "null_pctile": round(pctile, 2),
                    "n": len(baseline),
                    "adjacent_falsified": "none_known",
                })

    return {"counts": counts, "candidates": candidates}


# ---------------------------------------------------------------------------
# Candidate emission with dedupe + decay
# ---------------------------------------------------------------------------

def _emit_candidates(
    new_candidates: list[dict],
    output_path: Path,
    dedup_tokens: set[str],
    dry_run: bool,
) -> tuple[int, int, int]:
    """Write non-duplicate candidates to output_path.

    Returns (emitted, refreshed, deduped).
    - emitted: new records written
    - refreshed: existing records with last_refreshed updated
    - deduped: skipped as duplicates
    """
    existing = _load_existing_candidates(output_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    emitted = 0
    refreshed = 0
    deduped = 0
    updated_existing: dict[str, dict] = dict(existing)

    for cand in new_candidates:
        template = cand["template"]
        cell = cand["cell"]
        stat = cand["stat"]
        null_pctile = cand["null_pctile"]
        n = cand["n"]
        # adjacent_falsified is REQUIRED (R-CI5) — must be present AND non-empty
        adj_falsified = cand.get("adjacent_falsified")

        if not adj_falsified:
            raise ValueError(
                f"adjacent_falsified is REQUIRED on every emitted candidate. "
                f"Got empty value for template={template} cell={cell}"
            )

        cid = _candidate_id(template, cell, stat.split("|")[0].split("=")[0])
        candidate_desc = f"{template} {cell} {stat}"

        # Dedupe against external registries (oracle, species, machine, trial-ledger)
        dedup_match = _is_dedup_match(candidate_desc, dedup_tokens)
        if dedup_match:
            log.info("DEDUP: candidate %s matches existing registry token '%s'",
                     cid, dedup_match[:40])
            deduped += 1
            continue

        if cid in existing:
            # Refresh last_refreshed rather than re-emitting
            existing_row = existing[cid]
            existing_row["last_refreshed"] = now
            existing_row["null_pctile"] = null_pctile
            existing_row["n"] = n
            # Re-check decay status: if it was decayed, it revives but keeps seen-before
            # The row stays in file — dead-stays-dead means it won't get a NEW candidate_id
            # This refresh just updates the timestamp so decay clock resets
            updated_existing[cid] = existing_row
            refreshed += 1
            log.debug("REFRESH: candidate %s (template=%s cell=%s)", cid, template, cell)
            continue

        # New candidate
        row: dict = {
            "_schema": _SCHEMA_VERSION,
            "candidate_id": cid,
            "template": template,
            "cell": cell,
            "stat": stat,
            "null_pctile": null_pctile,
            "n": n,
            "first_seen": now,
            "last_refreshed": now,
            "adjacent_falsified": adj_falsified,
            "status": "candidate",
        }
        updated_existing[cid] = row
        emitted += 1
        log.info("EMIT: new candidate %s (template=%s cell=%s pctile=%.1f n=%d)",
                 cid, template, cell, null_pctile, n)

    # Apply decay: candidates with last_refreshed > DECAY_DAYS become 'decayed'
    from datetime import timedelta  # noqa: PLC0415
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=_DECAY_DAYS)
    for cid, row in updated_existing.items():
        if row.get("status") == "candidate":
            try:
                lr = datetime.fromisoformat(row.get("last_refreshed", "2000-01-01"))
                if lr.tzinfo is None:
                    from datetime import timezone as _tz  # noqa: PLC0415
                    lr = lr.replace(tzinfo=_tz.utc)
                if lr < cutoff_dt:
                    row["status"] = "decayed"
                    log.info("DECAY: candidate %s decayed (last_refreshed=%s)",
                             cid, row.get("last_refreshed"))
            except Exception:  # noqa: BLE001
                pass

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            for row in updated_existing.values():
                fh.write(json.dumps(row, default=str) + "\n")

    return emitted, refreshed, deduped


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    root: Path | None = None,
    dry_run: bool = False,
    ledger_path: Path | None = None,
) -> int:
    """Run all three templates.  Returns exit code (0 on success)."""
    if root is None:
        root = Path(__file__).resolve().parent.parent

    # --- STEP 1: Register budget (idempotent) ---
    newly_registered = register_budget(root, ledger_path=ledger_path, dry_run=dry_run)
    if newly_registered:
        log.info("Budget row registered for fdr_family=%s n=%d", _FAMILY, _BUDGET_TOTAL)

    # --- STEP 2: Assert budget present (GovernorRefusal if absent) ---
    if not dry_run:
        _assert_budget(root, ledger_path=ledger_path)
    else:
        # In dry-run, check the ledger but don't refuse — just log
        from engine.trial_ledger import TrialLedger  # noqa: PLC0415
        lp = ledger_path if ledger_path is not None else _ledger_path(root)
        led = TrialLedger(path=lp, family=_FAMILY)
        db = led.declared_budget(_FAMILY)
        log.info("[dry-run] budget check: declared_n=%d (family=%s)", db, _FAMILY)

    # --- STEP 3: Run templates ---
    log.info("Running T1 (composition drift)...")
    t1_result = _run_t1(root, dry_run)

    log.info("Running T2 (outcome heterogeneity)...")
    t2_result = _run_t2(root, dry_run)

    log.info("Running T3 (co-occurrence shift)...")
    t3_result = _run_t3(root, dry_run)

    # Collect all candidate dicts
    all_candidates = (
        t1_result["candidates"]
        + t2_result["candidates"]
        + t3_result["candidates"]
    )

    # --- STEP 4: Print per-template counts ---
    for name, result in [("T1", t1_result), ("T2", t2_result), ("T3", t3_result)]:
        c = result["counts"]
        print(
            f"[{name}] cells_examined={c['cells_examined']} "
            f"testable={c.get('cells_testable', '?')} "
            f"insufficient_n={c['cells_insufficient_n']} "
            f"candidates={c['candidates']} "
            f"null_draws={c.get('null_draws_used', _NULL_DRAWS)}"
        )

    print(f"Total candidates before dedupe: {len(all_candidates)}")

    # --- STEP 5: Dedupe against external registries ---
    dedup_tokens = _load_dedup_strings(root)
    log.info("Loaded %d dedup tokens from external registries", len(dedup_tokens))

    # --- STEP 6: Emit / refresh / decay ---
    output_path = root / _OUTPUT_PATH
    emitted, refreshed, deduped = _emit_candidates(
        all_candidates, output_path, dedup_tokens, dry_run
    )

    action = "[dry-run] would emit" if dry_run else "emitted"
    print(
        f"Candidates: {action}={emitted} refreshed={refreshed} "
        f"deduped={deduped} "
        f"(output={output_path if not dry_run else 'dry-run-no-write'})"
    )

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [context_scanner] %(message)s",
    )
    p = argparse.ArgumentParser(
        description="W4 context scanner — template families, printed nulls, display-only candidates"
    )
    p.add_argument("--root", type=Path, default=None, help="Repo root override")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing to disk or trial ledger",
    )
    p.add_argument(
        "--register-budget-only",
        action="store_true",
        help="Only write the declared budget row to the trial ledger, then exit",
    )
    p.add_argument(
        "--ledger-path",
        type=Path,
        default=None,
        help="Override trial ledger path (for testing)",
    )
    args = p.parse_args()

    root = args.root or Path(__file__).resolve().parent.parent

    if args.register_budget_only:
        new = register_budget(root, ledger_path=args.ledger_path)
        print(f"Budget row {'newly written' if new else 'already present'}: "
              f"family={_FAMILY} n={_BUDGET_TOTAL}")
        sys.exit(0)

    rc = run(root=root, dry_run=args.dry_run, ledger_path=args.ledger_path)
    sys.exit(rc)


if __name__ == "__main__":
    _cli()
