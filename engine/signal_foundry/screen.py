"""engine.signal_foundry.screen — deterministic 7-gate screen + blocklist.

screen_candidate(candidate, repo_root) → {admit, verdict, reasons}

Gates (SF-R7):
  1. data_path_tracked   — data path is git-tracked (not gitignored/absent)
  2. pit_plan            — PIT plan is stated (not 'unknown' / empty)
  3. sample_5y           — sample >= 5 years (probed from actual file date span)
  4. baseline_named      — a named baseline is present
  5. novelty             — construction_hash not in prior SF specs or REGISTRY/CANDIDATES
  6. orthogonality_noted — orthogonality note present (non-empty)
  7. evidence_noted      — evidence/literature note present

Dedup (SF-R8):
  construction_hash vs all prior specs in data/signal_foundry/candidates.jsonl
  + normalized-name vs engine.signal_lab.REGISTRY names
  + signal_frontier_docket.CANDIDATES names
  + blocklist match → verdict 'forbidden' with reason+source quoted

All logic is deterministic and LLM-free.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from engine.signal_foundry.spec import construction_hash


# ---------------------------------------------------------------------------
# Blocklist loader
# ---------------------------------------------------------------------------

def _load_blocklist(repo_root: Path) -> list[dict]:
    """Load config/signal_foundry_blocklist.yml.  Returns [] if absent."""
    bl_path = repo_root / "config" / "signal_foundry_blocklist.yml"
    if not bl_path.exists():
        return []
    try:
        import yaml  # optional; only needed when file present
        with bl_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("entries", [])
    except Exception:
        return []


def _check_blocklist(candidate: dict, entries: list[dict]) -> tuple[bool, str, str]:
    """Return (hit, reason, source) for the first blocklist match, else (False,'','')."""
    name = str(candidate.get("name", "")).lower()
    thesis = str(candidate.get("thesis", "")).lower()
    mechanism = str(candidate.get("mechanism", "")).lower()
    combined_text = f"{name} {thesis} {mechanism}"

    for entry in entries:
        match_spec = entry.get("match", {})
        patterns = match_spec.get("any_of", [])
        for pat in patterns:
            try:
                if re.search(pat, combined_text, re.IGNORECASE):
                    return True, entry.get("reason", "blocklist match"), entry.get("source", "")
            except re.error:
                # Fall back to simple substring
                if pat.lower() in combined_text:
                    return True, entry.get("reason", "blocklist match"), entry.get("source", "")
    return False, "", ""


# ---------------------------------------------------------------------------
# Prior spec dedup helpers
# ---------------------------------------------------------------------------

def _load_prior_hashes(repo_root: Path) -> set[str]:
    """Load construction_hash values from data/signal_foundry/candidates.jsonl."""
    candidates_path = repo_root / "data" / "signal_foundry" / "candidates.jsonl"
    hashes: set[str] = set()
    if not candidates_path.exists():
        return hashes
    try:
        with candidates_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    h = row.get("construction_hash")
                    if h:
                        hashes.add(str(h))
                except Exception:
                    continue
    except OSError:
        pass
    return hashes


def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation for name-level dedup."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _load_registry_names(repo_root: Path) -> set[str]:
    """Load normalized names from engine.signal_lab.REGISTRY (if importable)."""
    names: set[str] = set()
    try:
        import importlib.util
        spec_path = repo_root / "engine" / "signal_lab.py"
        if not spec_path.exists():
            return names
        spec_mod = importlib.util.spec_from_file_location("_signal_lab_tmp", spec_path)
        if spec_mod is None:
            return names
        mod = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(mod)  # type: ignore[union-attr]
        registry = getattr(mod, "REGISTRY", [])
        for row in registry:
            n = row.get("name", "")
            if n:
                names.add(_normalize_name(str(n)))
    except Exception:
        pass
    return names


def _load_frontier_names(repo_root: Path) -> set[str]:
    """Load normalized names from signal_frontier_docket.CANDIDATES."""
    names: set[str] = set()
    try:
        from engine.signal_frontier_docket import CANDIDATES
        for c in CANDIDATES:
            n = c.get("name", "")
            if n:
                names.add(_normalize_name(str(n)))
    except Exception:
        pass
    return names


def _git_tracked(path_str: str, repo_root: Path) -> bool:
    """Return True iff path is tracked by git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path_str],
            cwd=str(repo_root),
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _probe_file_span_years(path_str: str, repo_root: Path) -> float | None:
    """Probe the actual date span of a parquet/csv file in years.

    Returns None if the file can't be probed.
    Reads only the index (no column data) for speed.
    """
    import pandas as pd
    fpath = Path(path_str)
    if not fpath.is_absolute():
        fpath = repo_root / fpath
    if not fpath.exists():
        return None
    try:
        suffix = fpath.suffix.lower()
        if suffix == ".parquet":
            df = pd.read_parquet(fpath, columns=[])
        elif suffix in {".csv", ".tsv"}:
            sep = "\t" if suffix == ".tsv" else ","
            df = pd.read_csv(fpath, index_col=0, parse_dates=True, sep=sep, usecols=[0])
        else:
            return None
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
        df = df.dropna(how="all")
        if len(df) < 2:
            return None
        span = (df.index.max() - df.index.min()).days / 365.25
        return float(span)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def screen_candidate(
    candidate: dict,
    repo_root: str | Path = ".",
) -> dict:
    """7-gate screen + blocklist + dedup.

    Parameters
    ----------
    candidate : dict
        A proposed spec or pre-spec dict with at least:
        {name, data[{path}], feature.pipeline, target, gates,
         thesis (or mechanism), baseline, orthogonality_note, evidence_note}
    repo_root : Path
        Repo root for git-tracking checks and file probing.

    Returns
    -------
    dict with keys: {admit, verdict, reasons, gates_passed, gates_failed}
    """
    repo_root = Path(repo_root)
    reasons: list[str] = []
    gates_passed: list[str] = []
    gates_failed: list[str] = []

    # ------------------------------------------------------------------ #
    # Blocklist check (forbidden overrides all gates)                      #
    # ------------------------------------------------------------------ #
    blocklist_entries = _load_blocklist(repo_root)
    hit, bl_reason, bl_source = _check_blocklist(candidate, blocklist_entries)
    if hit:
        return {
            "admit": False,
            "verdict": "forbidden",
            "reasons": [
                f"BLOCKLIST HIT: {bl_reason} [source: {bl_source}]"
            ],
            "gates_passed": [],
            "gates_failed": ["blocklist"],
        }

    # ------------------------------------------------------------------ #
    # Gate 1: data_path_tracked                                            #
    # ------------------------------------------------------------------ #
    data_entries = candidate.get("data", [])
    if not data_entries:
        # Try flat field 'data_path' for pre-spec candidates
        dp = candidate.get("data_path") or candidate.get("path")
        data_entries = [{"path": dp}] if dp else []

    all_tracked = True
    if not data_entries:
        all_tracked = False
        reasons.append("Gate 1 FAIL: no data path provided")
        gates_failed.append("data_path_tracked")
    else:
        for entry in data_entries:
            p = entry.get("path", "") if isinstance(entry, dict) else str(entry)
            if not p or not _git_tracked(str(p), repo_root):
                all_tracked = False
                reasons.append(
                    f"Gate 1 FAIL: data path '{p}' is not git-tracked "
                    "(gitignored/absent stores refused — SF-R7)"
                )
                gates_failed.append("data_path_tracked")
                break
    if all_tracked:
        gates_passed.append("data_path_tracked")

    # ------------------------------------------------------------------ #
    # Gate 2: pit_plan_stated                                              #
    # Mirrors validate_spec: pit is required per data[] entry (not       #
    # top-level).  A top-level 'pit' or 'pit_plan' key is accepted as a  #
    # legacy fallback for pre-spec candidates that have not been          #
    # structured into the data[] list yet.                                #
    # ------------------------------------------------------------------ #
    _pit_ok = False
    _checked_entries = [e for e in data_entries if isinstance(e, dict)] if data_entries else []
    if _checked_entries:
        # Per-entry check: every entry must have a non-empty pit key
        _pit_ok = all(
            str(e.get("pit", "")).strip().lower() not in {"", "unknown", "none"}
            for e in _checked_entries
        )
        if not _pit_ok:
            # Legacy top-level fallback (pre-spec candidates)
            pit_top = str(candidate.get("pit") or candidate.get("pit_plan") or "").strip().lower()
            _pit_ok = bool(pit_top and pit_top not in {"", "unknown", "none"})
    else:
        # No data[] entries yet — fall back to top-level pit field
        pit_top = str(candidate.get("pit") or candidate.get("pit_plan") or "").strip().lower()
        _pit_ok = bool(pit_top and pit_top not in {"", "unknown", "none"})

    if _pit_ok:
        gates_passed.append("pit_plan")
    else:
        reasons.append(
            "Gate 2 FAIL: pit plan not stated on data[] entries (or top-level fallback). "
            "Each data entry must carry pit: one of 'clean', 'lagged', 'release_lag', or 'proxy'."
        )
        gates_failed.append("pit_plan")

    # ------------------------------------------------------------------ #
    # Gate 3: sample >= 5 years                                            #
    # ------------------------------------------------------------------ #
    span_ok = False
    # First try explicit history_years field
    history_years = candidate.get("history_years")
    if isinstance(history_years, (int, float)) and float(history_years) >= 5.0:
        span_ok = True
    else:
        # Probe actual file span from the first tracked data path
        for entry in data_entries:
            p = entry.get("path", "") if isinstance(entry, dict) else str(entry)
            if p:
                span = _probe_file_span_years(str(p), repo_root)
                if span is not None and span >= 5.0:
                    span_ok = True
                    break

    if span_ok:
        gates_passed.append("sample_5y")
    else:
        reasons.append(
            "Gate 3 FAIL: sample < 5 years (probed from file span or history_years field)"
        )
        gates_failed.append("sample_5y")

    # ------------------------------------------------------------------ #
    # Gate 4: baseline_named                                               #
    # ------------------------------------------------------------------ #
    baseline = str(candidate.get("baseline") or "").strip()
    if baseline:
        gates_passed.append("baseline_named")
    else:
        reasons.append("Gate 4 FAIL: no baseline declared")
        gates_failed.append("baseline_named")

    # ------------------------------------------------------------------ #
    # Gate 5: novelty (construction_hash dedup + name dedup)               #
    # ------------------------------------------------------------------ #
    prior_hashes = _load_prior_hashes(repo_root)
    registry_names = _load_registry_names(repo_root)
    frontier_names = _load_frontier_names(repo_root)

    # Compute construction_hash if possible
    c_hash = None
    try:
        c_hash = construction_hash(candidate)
    except Exception:
        pass

    name = str(candidate.get("name", "")).strip()
    norm_name = _normalize_name(name) if name else ""

    novelty_ok = True
    if c_hash and c_hash in prior_hashes:
        reasons.append(
            f"Gate 5 FAIL: construction_hash {c_hash!r} already in "
            "data/signal_foundry/candidates.jsonl (SF-R8 dedup)"
        )
        novelty_ok = False
        gates_failed.append("novelty")
    elif norm_name and (norm_name in registry_names or norm_name in frontier_names):
        reasons.append(
            f"Gate 5 FAIL: name '{name}' (normalized: '{norm_name}') already in "
            "REGISTRY or CANDIDATES (SF-R8 dedup)"
        )
        novelty_ok = False
        gates_failed.append("novelty")
    if novelty_ok:
        gates_passed.append("novelty")

    # ------------------------------------------------------------------ #
    # Gate 6: orthogonality_note present                                   #
    # ------------------------------------------------------------------ #
    orth = str(
        candidate.get("orthogonality_note") or candidate.get("orthogonality") or ""
    ).strip()
    if orth and orth != "0":
        gates_passed.append("orthogonality_noted")
    else:
        reasons.append("Gate 6 FAIL: orthogonality note not provided")
        gates_failed.append("orthogonality_noted")

    # ------------------------------------------------------------------ #
    # Gate 7: evidence/literature note present                             #
    # ------------------------------------------------------------------ #
    evid = str(
        candidate.get("evidence_note") or candidate.get("literature") or
        candidate.get("evidence") or ""
    ).strip()
    if evid and evid != "0":
        gates_passed.append("evidence_noted")
    else:
        reasons.append("Gate 7 FAIL: evidence/literature note not provided")
        gates_failed.append("evidence_noted")

    # ------------------------------------------------------------------ #
    # Final admit decision                                                 #
    # ------------------------------------------------------------------ #
    all_passed = len(gates_failed) == 0
    verdict = "admitted" if all_passed else "rejected"

    return {
        "admit": all_passed,
        "verdict": verdict,
        "reasons": reasons,
        "gates_passed": gates_passed,
        "gates_failed": gates_failed,
        "construction_hash": c_hash,
    }
