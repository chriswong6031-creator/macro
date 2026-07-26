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

import io
import re
import tokenize
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


def _code_lines(src: str) -> dict[int, str]:
    """Line-number -> source line with comments and string literals blanked out.

    The banned idioms are CODE patterns.  Scanning raw text also matches prose
    that documents their ABSENCE — every module whose docstring promises "no
    center=True" tripped its own tripwire, which is why this guard sat red.
    Blanking comment/string tokens keeps line numbers stable for the report
    while leaving real ``center=True`` keyword arguments fully visible.
    """
    lines = {i: line for i, line in enumerate(src.splitlines(), 1)}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return lines                                       # scan raw; fail loud, not open
    for tok in tokens:
        if tok.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (r1, c1), (r2, c2) = tok.start, tok.end
        for row in range(r1, r2 + 1):
            line = lines.get(row)
            if line is None:
                continue
            lo = c1 if row == r1 else 0
            hi = c2 if row == r2 else len(line)
            lines[row] = line[:lo] + " " * (hi - lo) + line[hi:]
    return lines


def test_no_future_leak_idioms_in_feature_code():
    violations = []
    for f in _py_files():
        rel = f.relative_to(ROOT).as_posix()
        src = f.read_text(encoding="utf-8")
        raw = src.splitlines()
        scan = _code_lines(src)
        for i, line in scan.items():
            if line.lstrip().startswith("#"):
                continue                                  # skip comments
            for label, rx in BANNED:
                if rx.search(line) and f"{rel}:{i}" not in ALLOWLIST:
                    # report the ORIGINAL line so the violation is readable
                    violations.append(f"{rel}:{i}  [{label}]  {raw[i - 1].strip()[:90]}")
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


def test_comment_stripping_does_not_blind_the_tripwire():
    """Blanking strings/comments must hide PROSE only, never real code."""
    planted = (
        '"""Docstring promising no center=True and never .bfill()."""\n'
        "import pandas as pd\n"
        "# a comment mentioning center=True\n"
        "def f(s):\n"
        "    note = 'we avoid center=True here'\n"
        "    return s.rolling(20, center=True).mean()\n"
    )
    scan = _code_lines(planted)
    hit_rows = {i for i, line in scan.items()
                if not line.lstrip().startswith("#")
                and any(rx.search(line) for _, rx in BANNED)}
    # line 6 is the only real leak; docstring (1), comment (3) and the string
    # literal on line 5 must all be invisible to the scan.
    assert hit_rows == {6}, f"expected only the real leak on line 6, got {sorted(hit_rows)}"
