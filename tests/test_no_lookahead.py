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

# Explicit, reviewed exceptions. Keyed "path:line" because that is what the scan
# reports — but a bare line number is a DANGEROUS key on its own: it exempts
# whatever code occupies that line later, so an unrelated edit that shifts the
# file by one line silently hands this exemption to a real leak. Every entry
# therefore PINS THE SOURCE TEXT it was granted for, and
# test_every_allowlist_entry_still_points_at_the_code_it_was_granted_for fails
# the moment the pinned line moves or changes.
#
# The bar for an entry is NOT "this is inconvenient to fix". It is: the idiom is
# inherent to the operation, and every alternative is worse for the reader of the
# data. Anything else gets fixed, not listed.
ALLOWLIST: dict[str, dict[str, str]] = {
    "engine/pick_forward_dist.py:95": {
        "source": "factor = factor.ffill().bfill().fillna(1.0)",
        "reason": (
            "carry_split_factor reconstructs the split back-multiplication factor as "
            "raw_close/adj_close. Split back-adjustment is DEFINITIONALLY a whole-series "
            "operation — a split re-scales every prior bar — so the factor for bars "
            "before the first valid adj_close observation can only come from later data. "
            "Every alternative is worse for the series: ffill+fillna(1.0) alone leaves "
            "pre-adjustment bars un-back-adjusted and manufactures a FAKE DISCONTINUITY "
            "at the split boundary, which is a lie-shaped price series rather than a leak. "
            "The same function already carries a disclosed sibling look-ahead (REVIEW-9, "
            "the split-print stamp) on the same reasoning: it is feature-side only and is "
            "never read by outcome construction. Operator decision 2026-08-06. "
            "SCOPE: this line only — it licenses nothing else, and .bfill() anywhere "
            "outside a split-factor reconstruction is still a leak."
        ),
    },
}


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


def test_every_allowlist_entry_still_points_at_the_code_it_was_granted_for():
    """An allowlist keyed by line number rots into a licence for unrelated code.

    The scan exempts a coordinate, `path:line`. Nothing about that coordinate is
    stable: insert an import forty lines above and the exemption granted to a
    reviewed split-factor reconstruction now covers whatever slid into line 95 —
    a REAL leak, permanently green, with a reassuring reason attached to it.

    So each entry pins its source text and this test re-reads it. A shifted or
    edited line fails HERE, naming the entry, instead of going quiet in the scan
    above. Deliberately a separate test: it must fail even when the scan is green,
    which is exactly the state a rotted exemption produces.
    """
    stale = []
    for key, entry in ALLOWLIST.items():
        rel, _, lineno = key.rpartition(":")
        path = ROOT / rel
        if not path.exists():
            stale.append(f"{key}  [file is gone]")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        i = int(lineno)
        actual = lines[i - 1].strip() if 0 < i <= len(lines) else "<past end of file>"
        if entry["source"] not in actual:
            stale.append(f"{key}\n      granted for: {entry['source']}\n      now holds:   {actual[:100]}")
    assert not stale, (
        "ALLOWLIST entries no longer point at the code they were reviewed for. The "
        "exemption is now covering a DIFFERENT line — re-point it to the new line "
        "number, or drop it if the code it excused is gone:\n  " + "\n  ".join(stale))


def test_allowlist_entries_carry_a_reason():
    """A bare coordinate with no rationale is indistinguishable from a silenced red."""
    for key, entry in ALLOWLIST.items():
        assert entry.get("reason", "").strip(), f"{key} has no reason"
        assert entry.get("source", "").strip(), f"{key} pins no source text"


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
