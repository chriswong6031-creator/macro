"""engine.signal_foundry.results — load results, promotion docket, forward accrual.

Functions
---------
load_results(repo_root)
    Return list of result dicts from data/signal_foundry/results/*.json.

promotion_docket(repo_root)
    pass_candidates minus any with human adjudication marks in
    data/signal_foundry/promotions.jsonl.

accrue_forward(repo_root, asof)
    For each spec in candidates.jsonl with status=registered and asof > registered_at,
    append that date's realized feature/target row to data/signal_foundry/forward/<id>.jsonl.
    Idempotent per (id, date).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, tolerating absent file and torn lines."""
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


def load_results(repo_root: str | Path = ".") -> list[dict]:
    """Load all result records from data/signal_foundry/results/*.json.

    Missing directory → returns [].
    Malformed JSON files are skipped silently.
    """
    repo_root = Path(repo_root)
    results_dir = repo_root / "data" / "signal_foundry" / "results"
    results: list[dict] = []
    if not results_dir.exists():
        return results
    for p in sorted(results_dir.glob("*.json")):
        try:
            with p.open(encoding="utf-8") as fh:
                results.append(json.load(fh))
        except Exception:
            continue
    return results


def promotion_docket(repo_root: str | Path = ".") -> list[dict]:
    """Return pass_candidate results not yet human-adjudicated.

    Loads all results, filters to verdict == 'pass_candidate', then removes
    any whose spec.id appears in data/signal_foundry/promotions.jsonl
    (the human adjudication log written by Fable/operator).

    Returns a list of result dicts ready for human promotion review.
    """
    repo_root = Path(repo_root)
    all_results = load_results(repo_root)
    pass_candidates = [r for r in all_results if r.get("verdict") == "pass_candidate"]

    # Load adjudicated promotions
    prom_path = repo_root / "data" / "signal_foundry" / "promotions.jsonl"
    adjudicated_ids: set[str] = set()
    for row in _load_jsonl(prom_path):
        sid = row.get("spec_id") or row.get("id") or ""
        if sid:
            adjudicated_ids.add(str(sid))

    # Remove already-adjudicated
    docket = [
        r for r in pass_candidates
        if str((r.get("spec") or {}).get("id", "")) not in adjudicated_ids
    ]
    return docket


def accrue_forward(
    repo_root: str | Path = ".",
    asof: str | date | None = None,
) -> dict[str, int]:
    """Append realized (feature, target) rows for registered specs where asof > registered_at.

    For each spec in data/signal_foundry/candidates.jsonl with status=registered:
      - Skip if asof <= registered_at (forward evidence only — SF-R4).
      - Load the spec's feature series and target series up to asof.
      - Append the row for `asof` to data/signal_foundry/forward/<id>.jsonl.
      - Idempotent: skip if (id, date) row already present.

    Parameters
    ----------
    repo_root : Path
    asof : str or date
        The date for which to accrue evidence.  Defaults to today.

    Returns
    -------
    dict: {spec_id: rows_written} for each spec processed.
    """
    import pandas as pd
    from engine.signal_foundry.spec import load_spec
    from engine.signal_foundry.transforms import apply_pipeline

    repo_root = Path(repo_root)
    if asof is None:
        asof = date.today()
    if isinstance(asof, str):
        asof = date.fromisoformat(asof)
    asof_ts = pd.Timestamp(asof)

    candidates_path = repo_root / "data" / "signal_foundry" / "candidates.jsonl"
    candidates = _load_jsonl(candidates_path)
    registered = [c for c in candidates if c.get("status") == "registered"]

    forward_dir = repo_root / "data" / "signal_foundry" / "forward"
    forward_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, int] = {}

    for candidate in registered:
        spec_id = str(candidate.get("id") or candidate.get("spec_id") or "")
        if not spec_id:
            continue

        # SF-R4: forward evidence only on asof > registered_at
        registered_at_str = str(candidate.get("registered_at") or "")
        if not registered_at_str:
            continue
        try:
            registered_at = date.fromisoformat(registered_at_str)
        except (ValueError, TypeError):
            continue
        if asof <= registered_at:
            continue

        # Load the full spec (from candidates.jsonl row itself or a spec file)
        spec: dict[str, Any] = {}
        spec_file = repo_root / "data" / "signal_foundry" / "specs" / f"{spec_id}.json"
        if spec_file.exists():
            try:
                spec = load_spec(spec_file)
            except Exception:
                spec = candidate
        else:
            spec = candidate

        # Load forward append file and check idempotency
        fwd_path = forward_dir / f"{spec_id}.jsonl"
        existing_dates: set[str] = set()
        for row in _load_jsonl(fwd_path):
            dt = row.get("date") or row.get("asof")
            if dt:
                existing_dates.add(str(dt))

        asof_str = asof.isoformat()
        if asof_str in existing_dates:
            written[spec_id] = 0
            continue

        # Compute feature value at asof
        try:
            data_entries = spec.get("data", [])
            if not data_entries:
                continue
            pipeline = (spec.get("feature") or {}).get("pipeline", [])
            if not pipeline:
                continue

            series_list = []
            for entry in data_entries:
                p = Path(entry.get("path", ""))
                if not p.is_absolute():
                    p = repo_root / p
                if not p.exists():
                    break
                suffix = p.suffix.lower()
                if suffix == ".parquet":
                    df = pd.read_parquet(p)
                else:
                    df = pd.read_csv(p, index_col=0, parse_dates=True)
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                df = df[~df.index.duplicated(keep="last")]
                col = entry.get("column")
                if col and col in df.columns:
                    s = df.loc[:asof_ts, col].dropna()
                else:
                    continue
                series_list.append(s)

            if len(series_list) != len(data_entries):
                continue

            if len(series_list) == 1:
                inputs: Any = series_list[0]
            else:
                aligned_pair = pd.concat(series_list, axis=1).dropna()
                inputs = (aligned_pair.iloc[:, 0], aligned_pair.iloc[:, 1])

            feature_series = apply_pipeline(inputs, pipeline)
            feature_series = feature_series.dropna()

            # Get feature value at asof (use last available if exact date missing)
            feat_at_asof = feature_series.reindex(
                feature_series.index[feature_series.index <= asof_ts]
            ).iloc[-1] if len(feature_series) > 0 else float("nan")

            # Try to get target value
            tgt_spec = spec.get("target", {})
            tgt_path = Path(tgt_spec.get("path", ""))
            if not tgt_path.is_absolute():
                tgt_path = repo_root / tgt_path
            tgt_val = None
            if tgt_path.exists():
                suffix = tgt_path.suffix.lower()
                if suffix == ".parquet":
                    tdf = pd.read_parquet(tgt_path)
                else:
                    tdf = pd.read_csv(tgt_path, index_col=0, parse_dates=True)
                if not isinstance(tdf.index, pd.DatetimeIndex):
                    tdf.index = pd.to_datetime(tdf.index)
                tdf = tdf.sort_index()
                tdf = tdf[~tdf.index.duplicated(keep="last")]
                tgt_col = tgt_spec.get("column", "Close")
                for col_name in ([tgt_col] if tgt_col else []) + ["Adj Close", "Close", "close", "value"]:
                    if col_name in tdf.columns:
                        tgt_at = tdf.loc[:asof_ts, col_name]
                        if len(tgt_at) > 0:
                            tgt_val = float(tgt_at.iloc[-1])
                        break

            row_out = {
                "date": asof_str,
                "spec_id": spec_id,
                "feature": float(feat_at_asof) if feat_at_asof == feat_at_asof else None,
                "target_raw": tgt_val,
                "registered_at": registered_at_str,
            }

            with fwd_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row_out) + "\n")
            written[spec_id] = 1

        except Exception:
            written[spec_id] = 0
            continue

    return written
