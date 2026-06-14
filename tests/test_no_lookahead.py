"""Look-ahead tripwire (Phase B ops hardening).

Process quality IS the edge here, and the silent killers are FEATURE leaks: a
backward-fill or a centered rolling window pulls FUTURE values into a past feature,
inflating every backtest invisibly. This static guard asserts those idioms never
appear in feature/engine/collector code. It is a TRIPWIRE — the baseline is clean,
so it stays green until someone introduces a leak, then fails loudly with the file.

Deliberately NOT banned: `shift(-N)` — in this repo that is overwhelmingly the
forward-return/-drawdown LABEL used to MEASURE a signal's odds (the house rule that
every band earns a measured forward record), not a feature input. Those live mostly
in scripts/ (calibrators/research) and are audited by name (fwd*/dd*/maxdd/_ret).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["engine", "collectors"]

# idioms that pull future data into a feature; each ( name, compiled regex )
BANNED = [
    ("centered rolling window", re.compile(r"\.rolling\([^)]*center\s*=\s*True")),
    ("standalone center=True", re.compile(r"(?<!\.rolling\()center\s*=\s*True")),
    ("backward-fill (.bfill)", re.compile(r"\.bfill\s*\(")),
    ("backward-fill (method=)", re.compile(r"method\s*=\s*[\"']bfill[\"']")),
    ("backfill (method=)", re.compile(r"method\s*=\s*[\"']backfill[\"']")),
]

# explicit, reviewed exceptions if a legitimate need ever arises: "path::reason"
ALLOWLIST: set[str] = set()


def _py_files():
    for d in SCAN_DIRS:
        yield from (ROOT / d).rglob("*.py")


def test_no_future_leak_idioms_in_feature_code():
    violations = []
    for f in _py_files():
        rel = f.relative_to(ROOT).as_posix()
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                                  # skip comments
            for label, rx in BANNED:
                if rx.search(line) and f"{rel}:{i}" not in ALLOWLIST:
                    violations.append(f"{rel}:{i}  [{label}]  {line.strip()[:90]}")
    assert not violations, (
        "Look-ahead idiom in feature/engine code (pulls future into a past feature). "
        "Fix the leak, or if genuinely safe add 'path:line' to ALLOWLIST with a reason:\n"
        + "\n".join(violations))


def test_tripwire_actually_fires_on_a_planted_leak():
    # guard the guard: the regexes must catch the patterns they claim to
    samples = ["x = s.rolling(20, center=True).mean()", "y = df.bfill()",
               "z = s.fillna(method='bfill')"]
    for s in samples:
        assert any(rx.search(s) for _, rx in BANNED), f"tripwire missed: {s}"
