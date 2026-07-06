"""scripts/build_covariance_spine.py — CLI wrapper for engine.neuralweb.covariance_spine.

Builds the R-ORTH covariance spine artifact (RUL-ORTH-1..11, display-only).

Writes:
  data/neuralweb/covariance_spine.json         (primary; git-committed)
  site/neuralwebdata/covariance_spine.json     (site mirror; same content)
  data/neuralweb/covariance_spine_history.parquet  (headline scalar history)

All writes are atomic (temp+rename).  Always exits 0.

Usage:
    python -m scripts.build_covariance_spine [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_covariance_spine")


def _repo_root(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    return Path(__file__).resolve().parent.parent


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".tmp_{path.name}_",
        suffix=".json",
        delete=False,
    ) as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    tmp_path.replace(path)


def _update_history(root: Path, payload: dict) -> None:
    """Append/replace one summary row in covariance_spine_history.parquet."""
    import pandas as pd  # noqa: PLC0415

    out_path = root / "data" / "neuralweb" / "covariance_spine_history.parquet"
    as_of = payload.get("as_of", "")

    blocks = payload.get("blocks", {})
    lobes = blocks.get("lobes", {})
    rates = blocks.get("rates", {})
    factors = blocks.get("factors", {})
    disp = blocks.get("dispersion", {})

    new_row = {
        "as_of": as_of,
        "effective_independent_lobes": lobes.get("effective_independent_lobes"),
        "n_lobes_measurable": lobes.get("n_lobes_measurable"),
        "rates_dominant_pc_share": rates.get("dominant_pc_share"),
        "factors_effective_bets": factors.get("effective_factor_bets_pr"),
        "dispersion_state": disp.get("state"),
        "same_bet_warning": bool(
            lobes.get("same_bet_warning", {}).get("active", False)
        ),
    }

    new_df = pd.DataFrame([new_row])

    if out_path.exists():
        try:
            existing = pd.read_parquet(out_path)
            # Replace row with same as_of (idempotent)
            existing = existing[existing["as_of"] != as_of]
            combined = pd.concat([existing, new_df], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("build_covariance_spine: history read failed (%s); starting fresh", exc)
            combined = new_df
    else:
        combined = new_df

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=out_path.parent,
        prefix=f".tmp_{out_path.name}_",
        suffix=".parquet",
        delete=False,
    ) as tf:
        tmp_path = Path(tf.name)
    combined.to_parquet(tmp_path, index=False)
    tmp_path.replace(out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build R-ORTH covariance spine (display-only, RUL-ORTH-1..11)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    try:
        from engine.neuralweb.covariance_spine import build_state  # noqa: PLC0415

        payload = build_state(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("build_covariance_spine: build_state failed — %s", exc)
        return 0  # non-fatal per house law

    # Write primary + site mirror
    data_path = root / "data" / "neuralweb" / "covariance_spine.json"
    site_path = root / "site" / "neuralwebdata" / "covariance_spine.json"

    try:
        _atomic_write_json(data_path, payload)
        log.info("build_covariance_spine: wrote %s", data_path)
    except Exception as exc:  # noqa: BLE001
        log.error("build_covariance_spine: write to data path failed — %s", exc)
        return 0  # non-fatal

    try:
        _atomic_write_json(site_path, payload)
        log.info("build_covariance_spine: wrote %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_covariance_spine: site mirror write failed — %s", exc)

    # Update history parquet
    try:
        _update_history(root, payload)
        log.info("build_covariance_spine: history parquet updated")
    except Exception as exc:  # noqa: BLE001
        log.warning("build_covariance_spine: history update failed — %s", exc)

    # One-line summary
    blocks = payload.get("blocks", {})
    lobes = blocks.get("lobes", {})
    eil = lobes.get("effective_independent_lobes")
    n_meas = lobes.get("n_lobes_measurable", 0)
    n_tot = lobes.get("n_lobes_total", 0)
    null_ref = lobes.get("null_reference") or {}
    pctile = null_ref.get("pctile_vs_null")
    missing = payload.get("missing_inputs", [])

    print(
        f"covariance-spine: as_of={payload.get('as_of')} | "
        f"eil={eil} | lobes={n_meas}/{n_tot} measurable | "
        f"pctile_vs_null={pctile} | "
        f"missing={len(missing)} | "
        f"→ {data_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
