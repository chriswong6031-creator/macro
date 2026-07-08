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
register_budget() is OPERATOR-ONLY via --register-budget-only.
run() calls _assert_budget() FIRST and refuses when no declared-budget row
pre-exists — it never auto-registers.

TEMPLATES (v1, FROZEN)
-----------------------
T1  Composition drift — board/fire composition by archetype cell vs universe
    share, tracked vs its own trailing 60d baseline.  Candidate threshold:
    within-window null percentile >= 99 AND cell n >= 50.
    Observed and null use the SAME functional: recent-window mean (last 5
    snapshots) vs block-resampled same-length-window means from baseline.
T2  Outcome heterogeneity — graded spine rows with personality_basis='pit_labels'
    split by archetype × quad_hard_label cell; per-cell hit-rate delta vs
    engine marginal, printed as percentile vs time-block-preserving
    MEMBERSHIP null (DT-R14): draw cell-sized subset from ENGINE-MARGINAL pool
    preserving calendar-block composition.  Nearly all cells will be
    insufficient_n today — printed honestly.
T3  Co-occurrence / mode-transition shift — production aggregate label
    co-occurrence + mode-share vs trailing 20-snapshot baseline; candidate
    at null-percentile >= 99.  Observed and null use the SAME functional:
    recent-window mean vs block-resampled same-length-window means.

ANTI-MINING HYGIENE (R-CI5)
----------------------------
- Same observed/null functional (window mean, not point-vs-mean).
- Calendar-time controls in all primary template axes (DT-R14).
- Sample floor n >= 50; insufficient_n printed, never hidden.
- Respin cap: 2 (candidates are printed once and refreshed, not respun
  endlessly to clear the threshold).
- Dedupe in fixed order: oracle compounds → species registry →
  machine_registry.jsonl → trial-ledger family strings →
  context_candidates.jsonl (incl. decayed rows).
  Structured matching: BOTH the candidate's cell-key tokens AND the stat-
  family word must appear in the registry string (no raw substring sweep).
- adjacent_falsified REQUIRED on every emitted candidate; consulted from
  species registry for matching archetype/cell tokens.

Usage
-----
  python -m scripts.build_context_candidates                # full run
  python -m scripts.build_context_candidates --dry-run      # print counts, no writes
  python -m scripts.build_context_candidates --register-budget-only  # operator: write ledger row
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
_T1_RECENT_WINDOW = 5      # recent-window size for T1 observed mean
_T3_RECENT_WINDOW = 5      # recent-window size for T3 observed mean
_TOP_K_CORTEX_CAP = 20     # R-CI11

# v1 template cell counts — estimated basis (basis='estimated')
# T1: archetype × engine buckets; conservative upper-bound ~15 cells
# T2: archetype (9 labels) × quad (4 quads) × engine (3) ≈ 108 cells
# T3: co-occurrence pairs (quad × vol_regime) max ~12 cells
_BUDGET_T1_CELLS = 15
_BUDGET_T2_CELLS = 108
_BUDGET_T3_CELLS = 12
_BUDGET_TOTAL = _BUDGET_T1_CELLS + _BUDGET_T2_CELLS + _BUDGET_T3_CELLS  # 135

_BUDGET_REASON = (
    f"v1 template grid: T1 composition-drift ~{_BUDGET_T1_CELLS} cells (estimated), "
    f"T2 outcome-heterogeneity ~{_BUDGET_T2_CELLS} cells "
    f"(archetype×quad×engine, estimated), T3 co-occurrence ~{_BUDGET_T3_CELLS} cells "
    f"(estimated). basis=estimated (frozen vocabulary tallied at runtime)."
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

    This function is OPERATOR-ONLY — called via --register-budget-only.
    run() does NOT call it.
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
    """Raise GovernorRefusal if declared budget is absent from the ledger.

    This MUST be the FIRST call in run() — run() never auto-registers.
    """
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


def _load_dedup_corpus(root: Path) -> list[dict]:
    """Collect structured dedup entries from oracle compounds, species, machine_registry,
    and trial-ledger family strings.

    Each entry is a dict with:
      - 'source': which registry (oracle/species/machine/ledger)
      - 'id': the id/family/slug string
      - 'family_words': frozenset of stat-family words extracted from the id/description
        (e.g. 'composition', 'hit-rate', 'co-occurrence', 'drift')
      - 'archetype_tokens': frozenset of archetype-like tokens from the id/description
    """
    corpus: list[dict] = []

    def _extract_tokens(s: str) -> frozenset[str]:
        """Lowercased space/underscore/dash split tokens."""
        import re
        return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)

    _STAT_FAMILY_WORDS = frozenset([
        "composition", "drift", "hit", "rate", "delta", "cooccurrence",
        "co-occurrence", "co_occurrence", "mode", "share", "shift",
        "heterogeneity", "transition",
    ])

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
                                s = str(v).lower()
                                corpus.append({
                                    "source": "oracle",
                                    "id": s,
                                    "tokens": _extract_tokens(s),
                                    "family_words": _STAT_FAMILY_WORDS & _extract_tokens(s),
                                })
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
                for field in ("species_id", "id", "name", "slug"):
                    v = sp.get(field)
                    if v:
                        s = str(v).lower()
                        corpus.append({
                            "source": "species",
                            "id": s,
                            "tokens": _extract_tokens(s),
                            "family_words": _STAT_FAMILY_WORDS & _extract_tokens(s),
                            "raw": sp,
                        })
                        break
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
                            s = str(h).lower()
                            corpus.append({
                                "source": "machine",
                                "id": s,
                                "tokens": _extract_tokens(s),
                                "family_words": _STAT_FAMILY_WORDS & _extract_tokens(s),
                            })
                        fam = row.get("fdr_family", "")
                        if fam:
                            s = str(fam).lower()
                            corpus.append({
                                "source": "machine",
                                "id": s,
                                "tokens": _extract_tokens(s),
                                "family_words": _STAT_FAMILY_WORDS & _extract_tokens(s),
                            })
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
                            s = str(fam).lower()
                            corpus.append({
                                "source": "ledger",
                                "id": s,
                                "tokens": _extract_tokens(s),
                                "family_words": _STAT_FAMILY_WORDS & _extract_tokens(s),
                            })
                    except Exception:  # noqa: BLE001
                        pass
        except OSError:
            pass

    return corpus


def _is_dedup_match(
    cell_key_tokens: frozenset[str],
    stat_family_tokens: frozenset[str],
    corpus: list[dict],
) -> str | None:
    """Return the matching id if the candidate matches against the dedup corpus.

    Structured matching (F6 fix): a match requires BOTH:
      1. At least one of the candidate's cell-key tokens appears in the
         corpus entry's token set (archetype/cell match), AND
      2. At least one of the candidate's stat-family words appears in the
         corpus entry's token set (stat family match), OR an exact
         family-string match (entry id == one of the stat_family_tokens).

    This prevents false-positive dedup where a species entry merely mentions
    the same archetype without being semantically comparable.
    """
    for entry in corpus:
        entry_tokens = entry.get("tokens", frozenset())
        # Condition 1: archetype/cell overlap
        cell_overlap = cell_key_tokens & entry_tokens
        if not cell_overlap:
            continue
        # Condition 2: stat-family overlap OR exact id match
        family_overlap = stat_family_tokens & entry_tokens
        exact_match = entry["id"] in stat_family_tokens
        if family_overlap or exact_match:
            return entry["id"]
    return None


# ---------------------------------------------------------------------------
# Species adjacent_falsified lookup (F8)
# ---------------------------------------------------------------------------

def _lookup_adjacent_falsified(
    root: Path,
    archetype_tokens: frozenset[str],
    cell_tokens: frozenset[str],
) -> str:
    """Consult species registry for adjacent_falsified entries matching candidate.

    Checks species entries' adjacent_falsified list and archetype_scope.hostile
    for entries mentioning the candidate's archetype/cell tokens.  Returns the
    first matching species_id:idea string, or 'none_known' if no match.
    """
    species_reg = root / "data" / "species" / "registry.json"
    if not species_reg.exists():
        return "none_known"

    try:
        sr = json.loads(species_reg.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "none_known"

    import re
    def _tok(s: str) -> frozenset[str]:
        return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)

    combined_tokens = archetype_tokens | cell_tokens

    for sp in sr.get("species", []):
        sp_id = sp.get("species_id") or sp.get("id") or sp.get("name", "")

        # Check archetype_scope.hostile
        hostile = sp.get("archetype_scope", {}).get("hostile", [])
        if isinstance(hostile, list):
            for h in hostile:
                h_tokens = _tok(str(h))
                if combined_tokens & h_tokens:
                    return f"{sp_id}:hostile_scope"

        # Check adjacent_falsified entries
        adj = sp.get("adjacent_falsified", [])
        if isinstance(adj, list):
            for entry in adj:
                if isinstance(entry, dict):
                    idea = entry.get("idea", "")
                    source = entry.get("source", "")
                    idea_tokens = _tok(idea)
                    if combined_tokens & idea_tokens:
                        return f"{sp_id}:{source or idea[:40]}"
                elif isinstance(entry, str):
                    entry_tokens = _tok(entry)
                    if combined_tokens & entry_tokens:
                        return f"{sp_id}:{entry[:40]}"

    return "none_known"


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
    tracked vs its 60d trailing baseline.  Observed = recent-window mean
    (last _T1_RECENT_WINDOW snapshots).  Null = block-resampled same-length
    window means from the baseline window (same functional, F3 fix).
    A candidate emits when null-percentile >= 99 AND cell n >= 50.
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
    # Require at least _CELL_N_FLOOR snapshots for null distribution
    if len(all_dates) < _CELL_N_FLOOR:
        log.info("T1: only %d snapshots — need >=%d for null; printing counts",
                 len(all_dates), _CELL_N_FLOOR)
        counts["cells_examined"] = len(archetypes)
        counts["cells_insufficient_n"] = len(archetypes)
        return {"counts": counts, "candidates": candidates}

    # Load species corpus for adjacent_falsified lookup
    import re  # noqa: PLC0415
    def _tok(s: str) -> frozenset[str]:
        return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)

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

        # Use baseline window (all but last _T1_RECENT_WINDOW) for the null
        if len(drift_series) < _CELL_N_FLOOR + _T1_RECENT_WINDOW:
            counts["cells_insufficient_n"] += 1
            log.debug("T1: cell=%s insufficient_n=%d", arch, len(drift_series))
            continue

        counts["cells_testable"] += 1

        # F3 fix: observed = mean of the last _T1_RECENT_WINDOW snapshots
        recent_window = drift_series[-_T1_RECENT_WINDOW:]
        observed = sum(recent_window) / len(recent_window)

        # Baseline window: trailing 60d (excluding the recent window used as observed)
        baseline_end = len(drift_series) - _T1_RECENT_WINDOW
        baseline_start = max(0, baseline_end - 60)
        baseline = drift_series[baseline_start:baseline_end]
        if len(baseline) < _T1_RECENT_WINDOW:
            counts["cells_insufficient_n"] += 1
            continue

        # Null: block-resample baseline; each draw produces a _T1_RECENT_WINDOW-sized
        # sub-window mean — same functional as observed (window mean)
        null_dist = _null_draw_window_means(
            baseline, window_size=_T1_RECENT_WINDOW, n_draws=_NULL_DRAWS
        )
        pctile = _null_percentile(observed, null_dist)

        log.debug("T1: cell=%s observed_mean=%.4f null_pctile=%.1f n_baseline=%d",
                  arch, observed, pctile, len(baseline))

        if pctile >= _CANDIDATE_PCTILE:
            counts["candidates"] += 1
            if not dry_run:
                arch_tokens = _tok(arch)
                adj_falsified = _lookup_adjacent_falsified(root, arch_tokens, arch_tokens)
                candidates.append({
                    "template": "T1",
                    "cell": arch,
                    "stat": f"composition_drift_mean={observed:.4f}",
                    "null_pctile": round(pctile, 2),
                    "n": len(baseline),
                    "adjacent_falsified": adj_falsified,
                })

    return {"counts": counts, "candidates": candidates}


def _null_draw_window_means(
    baseline: list[float],
    window_size: int,
    n_draws: int = _NULL_DRAWS,
    seed: int = 42,
) -> list[float]:
    """Draw n_draws window means from the baseline via block resampling.

    For each draw:
    1. Block-resample the baseline to length >= len(baseline).
    2. Take the last window_size values and compute their mean.

    This produces a null distribution of window means — same functional as
    the observed (mean of the last window_size snapshots in the live series).
    """
    rng = random.Random(seed)
    n = len(baseline)
    block_size = 5
    results: list[float] = []
    for _ in range(n_draws):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randint(0, n - 1)
            end = min(start + block_size, n)
            sample.extend(baseline[start:end])
        sample = sample[:n]
        # Take last window_size values as the "recent window" in the resample
        w = sample[-window_size:]
        results.append(sum(w) / len(w) if w else 0.0)
    return results


# ---------------------------------------------------------------------------
# T2 — Outcome heterogeneity
# ---------------------------------------------------------------------------

def _run_t2(root: Path, dry_run: bool) -> dict[str, Any]:
    """T2: graded spine rows with personality_basis='pit_labels' split by
    archetype × quad_hard_label cell; per-cell hit-rate delta vs engine
    marginal, printed as percentile vs time-block-preserving MEMBERSHIP null
    (DT-R14, F2 fix).

    NULL (F2 fix): for each of _NULL_DRAWS draws, resample a cell-sized
    subset from the ENGINE-MARGINAL pool preserving calendar-block
    composition (same number of rows per month-block as the cell has in
    that block, from the marginal pool's rows of that block), compute the
    draw's hit-rate delta vs marginal.

    EXPECTS insufficient_n nearly everywhere today — printed honestly.
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
        df = pd.read_parquet(spine_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("T2: spine read failed (%s) — skipping", exc)
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
    pit_graded = pit_graded.copy()
    pit_graded["hit"] = (pit_graded["outcome_excess"] > 0).astype(int)
    engine_marginal = pit_graded.groupby("engine")["hit"].mean().to_dict()

    import re  # noqa: PLC0415
    def _tok(s: str) -> frozenset[str]:
        return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)

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

        # F2 fix: time-block-preserving MEMBERSHIP null
        # For each draw, resample a cell-sized subset from the engine-marginal pool
        # preserving calendar-block composition.
        #
        # Engine-marginal pool = all pit_graded rows for this engine
        eng_pool = pit_graded[pit_graded["engine"] == eng].copy()

        # Build month-block map for the CELL rows
        as_ofs = grp["as_of"].tolist() if "as_of" in grp.columns else [None] * n
        cell_block_counts: dict[str, int] = {}
        for asof in as_ofs:
            q_key = str(asof)[:7] if asof else "unknown"  # YYYY-MM
            cell_block_counts[q_key] = cell_block_counts.get(q_key, 0) + 1

        # Build month-block index for the engine-marginal pool
        eng_block_hits: dict[str, list[int]] = {}
        for idx, row_asof in zip(eng_pool.index, eng_pool["as_of"].tolist() if "as_of" in eng_pool.columns else [None] * len(eng_pool)):
            q_key = str(row_asof)[:7] if row_asof else "unknown"
            eng_block_hits.setdefault(q_key, []).append(eng_pool.loc[idx, "hit"])

        rng = random.Random(42)
        null_deltas: list[float] = []
        for _ in range(_NULL_DRAWS):
            draw_hits: list[int] = []
            for q_key, count_needed in cell_block_counts.items():
                pool_hits = eng_block_hits.get(q_key, [])
                if not pool_hits:
                    # Fall back to global pool for this block
                    pool_hits = [v for vlist in eng_block_hits.values() for v in vlist]
                if not pool_hits:
                    # No marginal data at all — skip this draw
                    break
                # Sample with replacement from the pool's block
                sample = [rng.choice(pool_hits) for _ in range(count_needed)]
                draw_hits.extend(sample)
            else:
                if draw_hits:
                    draw_hr = sum(draw_hits) / len(draw_hits)
                    null_deltas.append(draw_hr - marg_hr)

        if not null_deltas:
            counts["cells_insufficient_n"] += 1
            log.debug("T2: cell=(%s,%s,%s) null_deltas empty — no marginal pool data",
                      arch, quad, eng)
            continue

        pctile = _null_percentile(observed_delta, null_deltas)
        log.debug("T2: cell=(%s,%s,%s) delta=%.4f pctile=%.1f n=%d",
                  arch, quad, eng, observed_delta, pctile, n)

        if pctile >= _CANDIDATE_PCTILE:
            counts["candidates"] += 1
            if not dry_run:
                arch_tokens = _tok(arch)
                cell_tokens = _tok(f"quad={quad}|engine={eng}")
                adj_falsified = _lookup_adjacent_falsified(root, arch_tokens, cell_tokens)
                candidates.append({
                    "template": "T2",
                    "cell": f"archetype={arch}|quad={quad}|engine={eng}",
                    "stat": f"hit_rate_delta={observed_delta:.4f}|cell_hr={cell_hr:.4f}|marginal_hr={marg_hr:.4f}",
                    "null_pctile": round(pctile, 2),
                    "n": n,
                    "adjacent_falsified": adj_falsified,
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

    F3 fix: observed = mean of last _T3_RECENT_WINDOW snapshots;
    null = block-resampled same-length window means from baseline
    (same functional as observed).
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

    # Need at least _CELL_N_FLOOR + _T3_RECENT_WINDOW snapshots total
    min_snapshots = _CELL_N_FLOOR + _T3_RECENT_WINDOW
    if len(all_dates) < min_snapshots:
        log.info("T3: only %d snapshots — need >=%d for null; printing counts",
                 len(all_dates), min_snapshots)
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

    import re  # noqa: PLC0415
    def _tok(s: str) -> frozenset[str]:
        return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)

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

        if len(share_series) < _CELL_N_FLOOR + _T3_RECENT_WINDOW:
            counts["cells_insufficient_n"] += 1
            continue

        counts["cells_testable"] += 1

        # F3 fix: observed = mean of last _T3_RECENT_WINDOW snapshots
        recent_window = share_series[-_T3_RECENT_WINDOW:]
        observed_mean = sum(recent_window) / len(recent_window)

        # Baseline window: exclude the recent window
        baseline_end = len(share_series) - _T3_RECENT_WINDOW
        baseline_start = max(0, baseline_end - _T3_SNAPSHOT_WINDOW)
        baseline = share_series[baseline_start:baseline_end]
        if len(baseline) < _T3_RECENT_WINDOW:
            counts["cells_insufficient_n"] += 1
            continue

        # Null: block-resample baseline to get window means — same functional as observed
        null_window_means = _null_draw_window_means(
            baseline, window_size=_T3_RECENT_WINDOW, n_draws=_NULL_DRAWS
        )
        # Shift relative to baseline mean
        baseline_mean = sum(baseline) / len(baseline)
        observed_shift = observed_mean - baseline_mean
        null_shifts = [v - baseline_mean for v in null_window_means]

        pctile = _null_percentile(abs(observed_shift), [abs(v) for v in null_shifts])

        log.debug("T3: cell=(%s,%s) shift=%.4f pctile=%.1f n_baseline=%d",
                  quad, vol, observed_shift, pctile, len(baseline))

        if pctile >= _CANDIDATE_PCTILE:
            counts["candidates"] += 1
            if not dry_run:
                cell_tokens = _tok(f"quad={quad}|vol_regime={vol}")
                adj_falsified = _lookup_adjacent_falsified(root, frozenset(), cell_tokens)
                candidates.append({
                    "template": "T3",
                    "cell": f"quad={quad}|vol_regime={vol}",
                    "stat": f"mode_share_shift={observed_shift:.4f}|observed_mean={observed_mean:.4f}|baseline_mean={baseline_mean:.4f}",
                    "null_pctile": round(pctile, 2),
                    "n": len(baseline),
                    "adjacent_falsified": adj_falsified,
                })

    return {"counts": counts, "candidates": candidates}


# ---------------------------------------------------------------------------
# Candidate emission with dedupe + decay
# ---------------------------------------------------------------------------

def _emit_candidates(
    new_candidates: list[dict],
    output_path: Path,
    dedup_corpus: list[dict] | set[str],
    dry_run: bool,
) -> tuple[int, int, int]:
    """Write non-duplicate candidates to output_path.

    Returns (emitted, refreshed, deduped).
    - emitted: new records written
    - refreshed: existing active records with last_refreshed updated
    - deduped: skipped as duplicates

    ``dedup_corpus`` accepts either the structured list[dict] from
    _load_dedup_corpus() (preferred) or a bare set[str] of tokens
    (legacy / test compatibility).
    """
    existing = _load_existing_candidates(output_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    emitted = 0
    refreshed = 0
    deduped = 0
    updated_existing: dict[str, dict] = dict(existing)

    import re  # noqa: PLC0415
    def _tok(s: str) -> frozenset[str]:
        return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)

    _STAT_FAMILY_WORDS = frozenset([
        "composition", "drift", "hit", "rate", "delta", "cooccurrence",
        "co-occurrence", "co_occurrence", "mode", "share", "shift",
        "heterogeneity", "transition",
    ])

    # Normalise dedup_corpus for legacy callers that pass a set[str]
    if isinstance(dedup_corpus, set):
        # Convert bare string set to structured corpus (for test back-compat)
        _corpus: list[dict] = []
        for tok in dedup_corpus:
            s = tok.lower()
            _corpus.append({
                "source": "legacy",
                "id": s,
                "tokens": _tok(s),
                "family_words": _STAT_FAMILY_WORDS & _tok(s),
            })
        corpus = _corpus
    else:
        corpus = dedup_corpus

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

        # Structured dedup (F6 fix): require cell-key AND stat-family overlap
        cell_key_tokens = _tok(cell)
        stat_key = stat.split("|")[0].split("=")[0]
        stat_family_tokens = _tok(stat_key) & _STAT_FAMILY_WORDS
        dedup_match = _is_dedup_match(cell_key_tokens, stat_family_tokens, corpus)
        if dedup_match:
            log.info("DEDUP: candidate %s matches existing registry token '%s'",
                     cid, str(dedup_match)[:40])
            deduped += 1
            continue

        if cid in existing:
            # Refresh or update based on decay status
            existing_row = existing[cid]
            if existing_row.get("status") == "decayed":
                # F7 fix: do NOT bump last_refreshed on decayed rows
                # Record last_seen_while_decayed instead
                existing_row["last_seen_while_decayed"] = now
                existing_row["null_pctile"] = null_pctile
                existing_row["n"] = n
            else:
                # Active candidate: refresh timestamps
                existing_row["last_refreshed"] = now
                existing_row["null_pctile"] = null_pctile
                existing_row["n"] = n
            updated_existing[cid] = existing_row
            refreshed += 1
            log.debug("REFRESH: candidate %s (template=%s cell=%s status=%s)",
                      cid, template, cell, existing_row.get("status", "candidate"))
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
    """Run all three templates.  Returns exit code (0 on success).

    IMPORTANT: run() NEVER auto-registers the budget.  It calls _assert_budget()
    FIRST — if no declared-budget row pre-exists, it raises GovernorRefusal
    (non-zero exit, zero screening).  Use --register-budget-only to register.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent

    # --- STEP 1: Assert budget present (FIRST — no auto-register) ---
    # GovernorRefusal if absent; run() is operator-gated.
    _assert_budget(root, ledger_path=ledger_path)

    # --- STEP 2: Run templates ---
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

    # --- STEP 3: Print per-template counts ---
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

    # --- STEP 4: Dedupe against external registries ---
    dedup_corpus = _load_dedup_corpus(root)
    log.info("Loaded %d dedup corpus entries from external registries", len(dedup_corpus))

    # --- STEP 5: Emit / refresh / decay ---
    output_path = root / _OUTPUT_PATH
    emitted, refreshed, deduped = _emit_candidates(
        all_candidates, output_path, dedup_corpus, dry_run
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
        help="OPERATOR: write the declared budget row to the trial ledger, then exit",
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
