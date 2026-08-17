#!/usr/bin/env python3
"""Build a credential-free review ZIP for Sol."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import evidence_root  # noqa: E402
from secrets import scan_tree  # noqa: E402

SKIP_SUFFIX = {".zip"}
SKIP_DIR_NAMES = {"__pycache__"}


def pack(run_id: str, sources: list[Path], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    leaks = []
    for src in sources:
        if src.exists():
            leaks.extend(scan_tree(src))
    if leaks:
        raise SystemExit(f"refusing to pack: secret-scan hits {len(leaks)} ({leaks[0]})")
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in sources:
            if not src.exists():
                continue
            files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
            for p in files:
                if p.suffix in SKIP_SUFFIX or any(part in SKIP_DIR_NAMES for part in p.parts):
                    continue
                if p.name.endswith(".zip"):
                    continue
                arc = p.relative_to(evidence_root()).as_posix()
                zf.write(p, arcname=f"ux-evidence/{arc}")
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    ev = evidence_root()
    dest = ev / f"ux-evidence-review-{args.run_id}.zip"
    sources = [
        ev / "REVIEW_START_HERE.md",
        ev / "CALIBRATION.md",
        ev / "README.md",
        ev / "run-manifest.json",
        ev / "pages",
        ev / "00-product-map",
        ev / "_schema",
        ev / "_config",
    ]
    # Prefer product-map REVIEW if present
    p0 = ev / "00-product-map" / "REVIEW_START_HERE.md"
    if p0.exists() and not (ev / "REVIEW_START_HERE.md").exists():
        (ev / "REVIEW_START_HERE.md").write_text(p0.read_text())
    path = pack(args.run_id, sources, dest)
    print(path)


if __name__ == "__main__":
    main()
