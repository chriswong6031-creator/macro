"""End-of-collection size tripwire for tracked data stores.

Guards against runaway growth in stores that are git-committed daily.
Currently watches:

  data/signal_archive/track_record.parquet
      WARN  > 20 MB
      FAIL  > 50 MB

Exits with code 1 on any FAIL.  Warnings are printed to stdout but do not
fail the run.  Writes data/quality/sizes_audit.json (observability only;
never modifies the audited stores).

Run as a module:  ``python -m scripts.audit_sizes``
Importable as:     ``from scripts import audit_sizes``
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("audit.sizes")

# ---------------------------------------------------------------------------
# Thresholds (frozen; change requires §8 status row)
# ---------------------------------------------------------------------------
_TRACK_RECORD_WARN_MB = 20
_TRACK_RECORD_FAIL_MB = 50

# ---------------------------------------------------------------------------
# Store definitions: (relative_path, warn_mb, fail_mb)
# ---------------------------------------------------------------------------
_STORES = [
    ("data/signal_archive/track_record.parquet", _TRACK_RECORD_WARN_MB, _TRACK_RECORD_FAIL_MB),
]


def _mb(n_bytes: int) -> float:
    return round(n_bytes / (1024 * 1024), 3)


def _row_count(path: Path) -> int | None:
    """Return row count for parquet files; None on any error."""
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415
        pf = pq.read_metadata(str(path))
        return pf.num_rows
    except Exception:  # noqa: BLE001
        try:
            import pandas as pd  # noqa: PLC0415
            return len(pd.read_parquet(path))
        except Exception:  # noqa: BLE001
            return None


def run(repo_root: str | Path | None = None) -> dict:
    """Run size checks; return audit report dict.

    Returns
    -------
    dict with keys:
      checks    — list of per-store result dicts
      n_fail    — count of FAILed stores
      n_warn    — count of WARNed stores (excl. fails)
      pass_all  — True iff n_fail == 0
    """
    if repo_root is None:
        repo_root = ROOT
    repo_root = Path(repo_root)

    checks = []
    n_fail = 0
    n_warn = 0

    for rel, warn_mb, fail_mb in _STORES:
        p = repo_root / rel
        entry: dict = {"path": rel, "exists": p.exists(), "warn_mb": warn_mb, "fail_mb": fail_mb}

        if not p.exists():
            entry["verdict"] = "ABSENT"
            entry["size_mb"] = None
            entry["row_count"] = None
            log.info("sizes: %s ABSENT (not yet created — first CI run will create it)", rel)
            checks.append(entry)
            continue

        size_bytes = p.stat().st_size
        size_mb = _mb(size_bytes)
        row_count = _row_count(p)
        entry["size_mb"] = size_mb
        entry["row_count"] = row_count

        if size_mb > fail_mb:
            verdict = "FAIL"
            n_fail += 1
            log.error(
                "sizes: %s FAIL — %.3f MB > %.0f MB hard limit (rows: %s)",
                rel, size_mb, fail_mb, row_count,
            )
            print(
                f"FAIL  {rel}: {size_mb:.3f} MB > {fail_mb:.0f} MB hard limit"
                f"  (rows={row_count})",
            )
        elif size_mb > warn_mb:
            verdict = "WARN"
            n_warn += 1
            log.warning(
                "sizes: %s WARN — %.3f MB > %.0f MB warn threshold (rows: %s)",
                rel, size_mb, warn_mb, row_count,
            )
            print(
                f"WARN  {rel}: {size_mb:.3f} MB > {warn_mb:.0f} MB warn threshold"
                f"  (rows={row_count})",
            )
        else:
            verdict = "OK"
            log.info("sizes: %s OK — %.3f MB (rows: %s)", rel, size_mb, row_count)
            print(f"OK    {rel}: {size_mb:.3f} MB  (rows={row_count})")

        entry["verdict"] = verdict
        checks.append(entry)

    report = {
        "checks": checks,
        "n_fail": n_fail,
        "n_warn": n_warn,
        "pass_all": n_fail == 0,
    }

    # Write observability JSON
    out_path = repo_root / "data" / "quality" / "sizes_audit.json"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2))
    except Exception as exc:  # noqa: BLE001
        log.warning("sizes: could not write audit JSON: %s", exc)

    return report


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    report = run()
    if not report["pass_all"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
