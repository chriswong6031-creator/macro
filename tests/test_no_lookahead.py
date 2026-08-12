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

# Explicit, reviewed exceptions: "path:line" -> (code fragment, reason).
#
# The FRAGMENT is load-bearing, not decoration. A bare line-number waiver slides
# onto whatever code later occupies that line, so an unrelated leak introduced at
# the same line number would silently inherit the exemption. An entry suppresses a
# finding only while that exact fragment is still on that exact line; any edit that
# moves or rewrites it makes the guard report normally again (fail-closed).
ALLOWLIST: dict[str, tuple[str, str]] = {
    "engine/pick_forward_dist.py:95": (
        ".ffill().bfill().fillna(1.0)",
        "Split-repair back-adjustment factor, not a feature. `factor = raw_close /"
        " adj_close` is the cumulative split multiplier; split_adjust() dropna()s its"
        " input, so factor is NaN exactly where close is NaN. ffill covers interior"
        " and trailing gaps; bfill covers ONLY a LEADING gap, and no split can be"
        " detected before the first valid price — so the first valid bar already"
        " carries the full cumulative factor and bfill propagates that same constant"
        " backwards. Measured (tests/test_pick_forward_dist.py::"
        "test_leading_gap_bfill_is_the_same_constant_not_a_look_ahead): under"
        " truncation a bfilled bar and an ordinary pre-split bar move by an IDENTICAL"
        " ratio, so the bfill adds zero look-ahead beyond the retroactive"
        " back-adjustment the sanctioned splitter applies to every pre-split bar by"
        " design. It is also load-bearing: dropping it fabricates a split-sized gap"
        " at the first valid bar (measured log-return -1.386 vs 0.00067 on a 4:1"
        " fixture) — exactly the false crash split_adjust exists to prevent."
        " Disclosed as REVIEW-10 in research/PICK_FORWARD_DIST_PHASE0.md.",
    ),
    "engine/top_maturation.py:347": (
        ".ffill().bfill()",
        "Split-repair back-adjustment factor, not a feature — the same construction"
        " as engine/pick_forward_dist.py:95 above, in the Winner Health trailing"
        " panel. `factor = close / _split_adjust(close)` is the cumulative split"
        " multiplier; _split_adjust() dropna()s its input, so after the reindex the"
        " factor is NaN at EXACTLY the rows where close is NaN. ffill covers interior"
        " and trailing gaps; bfill covers ONLY a LEADING gap, and no split is"
        " detectable before the first valid price, so the first priced bar already"
        " carries the full cumulative factor and bfill propagates that one constant"
        " backwards. Here the exemption is stronger than the sibling's: the frame ends"
        " `.dropna(subset=['close'])`, and every row the fill touches has a NaN close"
        " by construction — so the bfilled rows are DELETED before anything reads"
        " them. Measured, not asserted (tests/test_top_maturation.py::"
        "test_leading_gap_bfill_rows_never_survive_into_the_panel and"
        " ::test_leading_gap_prefix_parity_bfill_changes_nothing_downstream):"
        " prepending unpriced rows leaves the repaired frame byte-identical, split_day"
        " column included — that flag is the only column read off the FILLED factor"
        " series rather than off close, and it is unchanged. It is also load-bearing"
        " (::test_split_repair_is_load_bearing_no_fabricated_crash_at_the_split):"
        " without the repair a 4:1 split prints as a -75% single-day crash. Display"
        " tier — this panel feeds no score, rank, gate or size."
        " RE-REVIEWED 2026-08-11 (W2b three-tier board): the exemption moved from"
        " line 266 to line 347 because that edit inserted the tier-model constants"
        " and `_atr_distance` above this function and two high/low legs inside it —"
        " the LINE ITSELF is byte-identical to origin/main and carries no `+`/`-` in"
        " the diff, so this is a pure line-number shift and not a new construction."
        " Re-reviewed at the new location rather than relocated on faith: the"
        " backfill still fills only LEADING NaNs with the first known factor, and it"
        " is point-in-time safe because a split-adjustment factor is a"
        " back-adjustment CONSTANT between split events — a property of the corporate"
        " action, not a market observation — so propagating the first priced bar's"
        " factor backwards over unpriced rows cannot import a future price. The two"
        " conditions the argument above rests on were re-checked and both hold: the"
        " frame still ends `.dropna(subset=['close'])` (the newly added high/low"
        " columns ride the same factor and are dropped on the same rows), and all"
        " three measured tests cited above still pass.",
    ),
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
                if not rx.search(line):
                    continue
                exempt = ALLOWLIST.get(f"{rel}:{i}")
                if exempt is not None and exempt[0] in raw[i - 1]:
                    continue
                # report the ORIGINAL line so the violation is readable
                violations.append(f"{rel}:{i}  [{label}]  {raw[i - 1].strip()[:90]}")
    assert not violations, (
        "Look-ahead idiom in feature/engine code (pulls future into a past feature). "
        "Fix the leak, or if genuinely safe add 'path:line' to ALLOWLIST with a reason:\n"
        + "\n".join(violations))


def test_allowlist_entries_are_live_reasoned_and_still_needed():
    """Guard the waivers: a stale exemption is a hole nobody is looking at.

    Every entry must still point at real code, that code must still contain the
    pinned fragment, and it must still trip a banned idiom — otherwise the waiver
    has outlived its cause and belongs deleted, not carried.
    """
    for key, value in ALLOWLIST.items():
        path, _, lineno = key.rpartition(":")
        assert path and lineno.isdigit(), f"malformed ALLOWLIST key {key!r}"
        fragment, reason = value
        assert len(reason) > 120, f"{key}: exemption needs a reviewed reason, got {reason!r}"
        target = ROOT / path
        assert target.exists(), f"{key}: allowlisted file no longer exists"
        lines = target.read_text(encoding="utf-8").splitlines()
        i = int(lineno)
        assert 1 <= i <= len(lines), f"{key}: line {i} past EOF ({len(lines)} lines)"
        assert fragment in lines[i - 1], (
            f"{key}: pinned fragment {fragment!r} is no longer on line {i} "
            f"(found {lines[i - 1].strip()!r}) — re-review the exemption, don't move it"
        )
        assert any(rx.search(lines[i - 1]) for _, rx in BANNED), (
            f"{key}: line {i} no longer trips a banned idiom — drop the exemption"
        )


def test_allowlist_fragment_pin_is_load_bearing():
    """A waiver must not survive the line being rewritten under it.

    Without the fragment check a bare line-number waiver would silently cover
    whatever code later lands on that line — including a genuine leak.
    """
    key = "engine/pick_forward_dist.py:95"
    fragment, _ = ALLOWLIST[key]
    planted = "    x = df.bfill()   # an unrelated leak that moved onto this line"
    assert fragment not in planted, "fixture must not contain the pinned fragment"
    assert any(rx.search(planted) for _, rx in BANNED), "fixture must trip the tripwire"
    exempt = ALLOWLIST.get(key)
    assert exempt is not None and exempt[0] not in planted, (
        "the fragment pin must refuse to cover a rewritten line"
    )


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
