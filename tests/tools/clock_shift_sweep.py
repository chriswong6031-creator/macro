"""Batch driver for the clock-shift plugin (tests/tools/clock_shift.py).

Runs a list of test files under the plugin at one shift, in batches, and folds
the per-test outcomes of every batch into a single results JSON.  `diff` then
reports which node ids went pass -> fail between two shifts: those are the
fixture clock bombs, and the bracketing shifts are the fire-date window.

  # from the repo root
  python3 tests/tools/clock_shift_sweep.py run  --files files.txt --shift 0    --out /tmp/cs/s0
  python3 tests/tools/clock_shift_sweep.py run  --files files.txt --shift 3650 --out /tmp/cs/s3650
  python3 tests/tools/clock_shift_sweep.py diff /tmp/cs/s0/results.json /tmp/cs/s3650/results.json

`--files` is a newline-separated list of pytest targets (paths, or path::nodeid).
Shift 0 is the BASELINE and must be run under the plugin too — a plain pytest run
is a different lens, so a plain-vs-shifted diff attributes plugin artifacts to
the clock.  Read BASELINE RED before FLIPPED: a test already red at shift 0 is
not evidence of anything about time.

`--out` should be OUTSIDE the repo (a scratch dir): the junit XML and results
JSON are working files, not artifacts, and writing them into the tree turns a
sweep into worktree litter.
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PLUGIN_DIR = str(Path(__file__).resolve().parent)
BATCH = 40


def _assert_repo_root() -> Path:
    """Refuse to run from anywhere but a repo root holding tests/.

    The plugin resolves the repo boundary from CLOCK_SHIFT_REPO_ROOT or the CWD,
    and pytest resolves relative targets against the CWD as well.  Run from the
    wrong directory and the sweep silently scopes the name-swap to a foreign
    tree — every module reads as third-party, nothing is shifted, and the whole
    sweep comes back clean for the wrong reason.
    """
    cwd = Path.cwd().resolve()
    if not (cwd / "tests").is_dir():
        raise SystemExit(
            f"clock_shift_sweep: cwd {cwd} is not a repo root (no tests/ dir). "
            "Run this from the checkout you are sweeping."
        )
    return cwd


def parse_junit(path: Path) -> dict:
    out = {}
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return out
    for tc in root.iter("testcase"):
        nodeid = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        file_attr = tc.get("file") or ""
        if file_attr:
            nodeid = f"{file_attr}::{tc.get('name', '')}"
        outcome = "passed"
        for child in tc:
            if child.tag == "failure":
                outcome = "failed"
            elif child.tag == "error":
                outcome = "error"
            elif child.tag == "skipped":
                outcome = "skipped"
        out[nodeid] = outcome
    return out


def cmd_run(args):
    repo_root = _assert_repo_root()
    files = [f.strip() for f in Path(args.files).read_text().splitlines() if f.strip()]
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["TZ"] = "UTC"
    env["CLOCK_SHIFT_DAYS"] = str(args.shift)
    env["CLOCK_SHIFT_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = PLUGIN_DIR + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    results = {}
    batch_meta = []
    for i in range(0, len(files), BATCH):
        chunk = files[i : i + BATCH]
        xml_path = outdir / f"batch_{i // BATCH:03d}.xml"
        cmd = [
            sys.executable, "-m", "pytest", "-p", args.plugin,
            "-q", "--tb=no", "-p", "no:cacheprovider",
            "--continue-on-collection-errors",
            f"--junitxml={xml_path}",
            *chunk,
        ]
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=args.timeout
        )
        tail = "\n".join(proc.stdout.strip().splitlines()[-2:])
        batch_meta.append(
            {"batch": i // BATCH, "rc": proc.returncode, "tail": tail,
             "n_files": len(chunk)}
        )
        print(f"[shift +{args.shift}] batch {i // BATCH}: rc={proc.returncode} {tail}",
              flush=True)
        results.update(parse_junit(xml_path))
    (outdir / "results.json").write_text(json.dumps(results, indent=0, sort_keys=True))
    (outdir / "batches.json").write_text(json.dumps(batch_meta, indent=1))
    counts = {}
    for v in results.values():
        counts[v] = counts.get(v, 0) + 1
    print(f"[shift +{args.shift}] TOTAL {counts}", flush=True)


def cmd_diff(args):
    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())
    flipped = sorted(
        k for k, v in b.items()
        if v in ("failed", "error") and a.get(k) == "passed"
    )
    missing_in_b = sorted(k for k in a if k not in b)
    base_red = sorted(k for k, v in a.items() if v in ("failed", "error"))
    print(f"BASELINE RED ({len(base_red)}):")
    for k in base_red:
        print(f"  {k}")
    print(f"FLIPPED pass->fail ({len(flipped)}):")
    for k in flipped:
        print(f"  {k}")
    if missing_in_b:
        print(f"MISSING in shifted run ({len(missing_in_b)}) — first 10:")
        for k in missing_in_b[:10]:
            print(f"  {k}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--files", required=True,
                   help="file holding newline-separated pytest targets")
    r.add_argument("--shift", type=int, required=True,
                   help="CLOCK_SHIFT_DAYS for this run (0 = instrumented baseline)")
    r.add_argument("--out", required=True,
                   help="output dir for junit XML + results.json (keep it out of the repo)")
    r.add_argument("--plugin", default="clock_shift",
                   help="plugin module name passed to pytest -p (default: clock_shift)")
    r.add_argument("--timeout", type=int, default=3600,
                   help="per-batch subprocess timeout in seconds (default: 3600)")
    r.set_defaults(func=cmd_run)
    d = sub.add_parser("diff")
    d.add_argument("a", help="baseline results.json (normally the shift-0 run)")
    d.add_argument("b", help="shifted results.json")
    d.set_defaults(func=cmd_diff)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
