"""BD-4/5/6 control-RNG seeds must be PYTHONHASHSEED-stable.

The frozen Phase-0/0b preregs (research/short_side/BD_PHASE0*_PREREG.md) promise
seeded — i.e. reproducible — random-bar controls.  Until 2026-07-26 the per-ticker
sub-seed was ``hash(ticker) & 0x7FFF_FFFF``, and Python salts ``hash(str)`` per
process (PYTHONHASHSEED), so BD-4/5/6 control draws silently differed on every
run.  Same defect class as chart_render's SVG ids, fixed the same way (#3785):
``zlib.crc32``, which is process-stable.

Two pins, both running the REAL derivation
(``scripts.research.dump_breakdown_events.bd456_control_seed``) in fresh
subprocesses:

1. Identical seeds under PYTHONHASHSEED 0/1/42 — fails if anyone reverts to a
   salted hash.
2. Golden values — fails if the regime itself drifts silently (mask width,
   XOR operator, encoding), which would also break reproducibility of any
   post-fix artifact without anyone noticing.

The subprocess import pulls the module's full top-level import chain
(engine.grading, pandas/numpy, replay_standout_pipeline) — the CI lane installs
exactly the trial-budgets dependency set, verified in a clean venv.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_TICKERS = ["AAPL", "BRK.B", "600519.SS", "9988.HK"]

_SNIPPET = (
    "import json\n"
    "from scripts.research.dump_breakdown_events import (\n"
    "    bd456_control_seed, BD4_CONTROL_RNG_SEED, BD5_CONTROL_RNG_SEED,\n"
    "    BD6_CONTROL_RNG_SEED)\n"
    f"tickers = {_TICKERS!r}\n"
    "consts = [BD4_CONTROL_RNG_SEED, BD5_CONTROL_RNG_SEED, BD6_CONTROL_RNG_SEED]\n"
    "print(json.dumps([[bd456_control_seed(t, c) for c in consts]\n"
    "                  for t in tickers]))\n"
)

# crc32(ticker) & 0x7FFF_FFFF, XOR-ed with the declared constants (7891/13421/19937).
# Computed independently of the module (python3 -c 'import zlib; ...') so this is a
# true golden, not a mirror of the implementation.
_GOLDEN = [
    [912607631, 912614193, 912595645],      # AAPL      (crc31 912611164)
    [1779396223, 1779385537, 1779383629],   # BRK.B     (crc31 1779396780)
    [41848890, 41859716, 41861896],         # 600519.SS (crc31 41848553)
    [1280402111, 1280395265, 1280389517],   # 9988.HK   (crc31 1280408684)
]


def _derive(hash_seed: str) -> list[list[int]]:
    """Run the real seed derivation in a fresh interpreter under one hash seed."""
    env = dict(os.environ, PYTHONHASHSEED=hash_seed)
    proc = subprocess.run(
        [sys.executable, "-c", _SNIPPET],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"seed-derivation subprocess failed under PYTHONHASHSEED={hash_seed}:\n"
        f"{proc.stderr}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_control_seeds_stable_across_hash_seeds():
    """The per-ticker sub-seed must not track the process hash salt."""
    runs = {hs: _derive(hs) for hs in ("0", "1", "42")}
    distinct = {json.dumps(v) for v in runs.values()}
    assert len(distinct) == 1, (
        "BD-4/5/6 control seeds differ across PYTHONHASHSEED values "
        f"(0/1/42): {runs} — control sampling is nondeterministic again; "
        "use zlib.crc32, never builtin hash()"
    )


def test_control_seeds_match_golden():
    """Pin the exact regime: crc32(utf-8 ticker) & 0x7FFF_FFFF, XOR seed const."""
    got = _derive("0")
    assert got == _GOLDEN, (
        f"BD-4/5/6 control-seed regime drifted: got {got}, expected {_GOLDEN} "
        f"for tickers {_TICKERS} — any change here re-rolls every post-fix "
        "control panel and must be a deliberate, documented seeding-contract bump"
    )
