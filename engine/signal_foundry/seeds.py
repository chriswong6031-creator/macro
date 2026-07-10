"""engine.signal_foundry.seeds — harvest structured brainstorm seeds.

harvest_seeds(repo_root) → list[{source, ref, summary, data_hint, kind}]

Sources (all absent → skip with note, never crash):
  1. data/neuralweb/causal_mechanisms.jsonl  (screened_candidate-ish entries)
  2. data/neuralweb/causal_frontier.json     (top rows)
  3. data/neuralweb/causal_surprise_queue.jsonl
  4. engine/signal_lab.py REGISTRY (tier=killed: name+why = open-search-space seeds)
  5. research-factory candidates file (engine/research_factory/ grep for candidates.jsonl)
     filtered by alpha_family type

Returns list of seed dicts; each has:
  source  : str  — which source file / registry
  ref     : str  — row id or name
  summary : str  — short description of the seed
  data_hint : str — what data file/store it references (if known)
  kind    : str  — 'causal_edge', 'frontier_candidate', 'killed_construction',
                   'surprise_queue', 'alpha_family', 'unknown'
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, tolerating torn final lines."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return rows


def _read_json(path: Path) -> Any:
    """Read a JSON file.  Returns None on any error."""
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def harvest_seeds(repo_root: str | Path = ".") -> list[dict]:
    """Collect brainstorm seeds from all available sources.

    Parameters
    ----------
    repo_root : Path
        Repository root.

    Returns
    -------
    List of seed dicts: [{source, ref, summary, data_hint, kind}].
    Missing sources are skipped with a note in the list (source='meta', kind='note').
    """
    repo_root = Path(repo_root)
    seeds: list[dict] = []

    # ------------------------------------------------------------------ #
    # Source 1: data/neuralweb/causal_mechanisms.jsonl                     #
    # ------------------------------------------------------------------ #
    mech_path = repo_root / "data" / "neuralweb" / "causal_mechanisms.jsonl"
    mech_rows = _read_jsonl(mech_path)
    if not mech_rows:
        seeds.append({
            "source": "causal_mechanisms.jsonl",
            "ref": "absent",
            "summary": "causal_mechanisms.jsonl not found or empty — skip",
            "data_hint": "",
            "kind": "note",
        })
    else:
        for row in mech_rows:
            verdict = str(row.get("verdict", "")).lower()
            # Only keep screened_candidate-ish entries (positive signals)
            if verdict not in {"screened_candidate", "pass_candidate", "candidate"}:
                # Also include rows with strong evidence even without explicit verdict
                support = row.get("causal_support", {})
                if not any(v == "strong" for v in support.values()):
                    continue
            cause = row.get("cause_id") or row.get("cause") or row.get("edge_id", "")
            target = row.get("target_id") or row.get("target", "")
            seeds.append({
                "source": "data/neuralweb/causal_mechanisms.jsonl",
                "ref": str(row.get("edge_id") or cause or ""),
                "summary": (
                    f"Causal edge: {cause} → {target} "
                    f"(verdict={row.get('verdict', 'unknown')})"
                ),
                "data_hint": str(row.get("data_path") or row.get("cause_path") or ""),
                "kind": "causal_edge",
            })

    # ------------------------------------------------------------------ #
    # Source 2: data/neuralweb/causal_frontier.json                        #
    # ------------------------------------------------------------------ #
    frontier_path = repo_root / "data" / "neuralweb" / "causal_frontier.json"
    frontier_data = _read_json(frontier_path)
    if frontier_data is None:
        seeds.append({
            "source": "causal_frontier.json",
            "ref": "absent",
            "summary": "causal_frontier.json not found — skip",
            "data_hint": "",
            "kind": "note",
        })
    else:
        # frontier_data may be a list or a dict with 'candidates'/'edges' key
        if isinstance(frontier_data, list):
            rows = frontier_data
        elif isinstance(frontier_data, dict):
            rows = (
                frontier_data.get("candidates") or
                frontier_data.get("edges") or
                frontier_data.get("rows") or
                list(frontier_data.values()) if all(isinstance(v, dict) for v in frontier_data.values()) else []
            )
        else:
            rows = []

        for row in rows[:50]:  # top 50 rows at most
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("edge_id") or row.get("id") or "")
            seeds.append({
                "source": "data/neuralweb/causal_frontier.json",
                "ref": name,
                "summary": str(
                    row.get("thesis") or row.get("summary") or
                    row.get("description") or name
                ),
                "data_hint": str(row.get("data_path") or row.get("path") or ""),
                "kind": "frontier_candidate",
            })

    # ------------------------------------------------------------------ #
    # Source 3: data/neuralweb/causal_surprise_queue.jsonl                 #
    # ------------------------------------------------------------------ #
    sq_path = repo_root / "data" / "neuralweb" / "causal_surprise_queue.jsonl"
    sq_rows = _read_jsonl(sq_path)
    if not sq_rows:
        seeds.append({
            "source": "causal_surprise_queue.jsonl",
            "ref": "absent",
            "summary": "causal_surprise_queue.jsonl not found or empty — skip",
            "data_hint": "",
            "kind": "note",
        })
    else:
        for row in sq_rows[:30]:
            name = str(row.get("name") or row.get("edge_id") or row.get("id") or "")
            seeds.append({
                "source": "data/neuralweb/causal_surprise_queue.jsonl",
                "ref": name,
                "summary": str(
                    row.get("thesis") or row.get("summary") or
                    row.get("surprise_note") or name
                ),
                "data_hint": str(row.get("data_path") or row.get("path") or ""),
                "kind": "surprise_queue",
            })

    # ------------------------------------------------------------------ #
    # Source 4: engine/signal_lab.py REGISTRY (killed rows)                #
    # ------------------------------------------------------------------ #
    try:
        import importlib.util
        sl_path = repo_root / "engine" / "signal_lab.py"
        if sl_path.exists():
            spec_obj = importlib.util.spec_from_file_location("_signal_lab_seed", sl_path)
            if spec_obj is not None:
                mod = importlib.util.module_from_spec(spec_obj)
                spec_obj.loader.exec_module(mod)  # type: ignore[union-attr]
                registry = getattr(mod, "REGISTRY", [])
                killed = [r for r in registry if str(r.get("tier", "")).lower() == "killed"]
                if not killed:
                    seeds.append({
                        "source": "engine/signal_lab.py REGISTRY",
                        "ref": "no_killed_rows",
                        "summary": "REGISTRY has no tier=killed rows — nothing to seed",
                        "data_hint": "",
                        "kind": "note",
                    })
                else:
                    for row in killed:
                        name = str(row.get("name", ""))
                        why = str(row.get("why") or row.get("note") or row.get("kill_reason") or "")
                        seeds.append({
                            "source": "engine/signal_lab.py REGISTRY",
                            "ref": name,
                            "summary": (
                                f"Killed construction '{name}' — kill is construction-specific; "
                                f"a different construction on the same theme is admissible. "
                                f"Kill reason: {why}"
                            ),
                            "data_hint": str(row.get("data_path") or ""),
                            "kind": "killed_construction",
                        })
        else:
            seeds.append({
                "source": "engine/signal_lab.py REGISTRY",
                "ref": "absent",
                "summary": "engine/signal_lab.py not found — skip",
                "data_hint": "",
                "kind": "note",
            })
    except Exception as exc:
        seeds.append({
            "source": "engine/signal_lab.py REGISTRY",
            "ref": "error",
            "summary": f"Could not import signal_lab.REGISTRY: {exc}",
            "data_hint": "",
            "kind": "note",
        })

    # ------------------------------------------------------------------ #
    # Source 5: research-factory candidates.jsonl (alpha_family type)      #
    # ------------------------------------------------------------------ #
    rf_candidates: list[dict] = []
    rf_found_path: str = ""
    # Search engine/research_factory/ for candidates.jsonl
    rf_base = repo_root / "engine" / "research_factory"
    if rf_base.exists():
        for p in rf_base.rglob("candidates.jsonl"):
            rows_tmp = _read_jsonl(p)
            if rows_tmp:
                rf_candidates = rows_tmp
                rf_found_path = str(p.relative_to(repo_root))
                break
    # Also check data/ path
    if not rf_candidates:
        for p in (repo_root / "data").rglob("research_factory*candidates*.jsonl"):
            rows_tmp = _read_jsonl(p)
            if rows_tmp:
                rf_candidates = rows_tmp
                rf_found_path = str(p.relative_to(repo_root))
                break

    if not rf_candidates:
        seeds.append({
            "source": "research_factory/candidates.jsonl",
            "ref": "absent",
            "summary": "research-factory candidates.jsonl not found or empty — skip",
            "data_hint": "",
            "kind": "note",
        })
    else:
        alpha_rows = [r for r in rf_candidates if str(r.get("type", "")).lower() == "alpha_family"]
        if not alpha_rows:
            seeds.append({
                "source": rf_found_path,
                "ref": "no_alpha_family",
                "summary": f"Found {len(rf_candidates)} candidates but none with type=alpha_family",
                "data_hint": "",
                "kind": "note",
            })
        else:
            for row in alpha_rows:
                name = str(row.get("name") or row.get("id") or "")
                seeds.append({
                    "source": rf_found_path,
                    "ref": name,
                    "summary": str(
                        row.get("thesis") or row.get("summary") or
                        row.get("description") or name
                    ),
                    "data_hint": str(row.get("data_path") or row.get("path") or ""),
                    "kind": "alpha_family",
                })

    return seeds
