"""W5 replay runner PROGRESS HEARTBEAT — stderr-only liveness for the long loops.

WHY THIS SUITE EXISTS.  Measured 2026-08-15: a Panel-B replay went ~2 wall-hours
silent between the post-gather census line and the results write, and the only
liveness evidence the operator had was ``ps`` CPU-time forensics — made worse
because the macOS spawn workers do not match a ``pgrep`` on the script name.
The heartbeat is the fix; these tests pin the two properties that make it worth
having and the one that would make it harmful:

  * it PRINTS — on both the time threshold and the item threshold, independently;
  * it prints to STDERR, never stdout, because stdout carries the receipt/JSON
    contract this runner's consumers parse;
  * it can never raise out of a loop it is merely watching.

The last of the source-level tests pins the five instrumented phases BY NAME:
an instrument that silently loses a call site is exactly the failure it exists
to prevent, and a deleted ``_Heartbeat(...)`` would otherwise leave every
behavioural test above still green.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import entry_radar_replay as runner  # noqa: E402

_LINE = re.compile(r"^\[(?P<phase>[^\]]+)\] (?P<k>\d+)/(?P<n>\d+) "
                   r"\(elapsed (?P<elapsed>\d+)s\)$")

#: Item thresholds only — a huge time budget so nothing fires on the clock.
_ITEMS_ONLY = {"every_seconds": 1e9}
#: Time threshold only — every tick is due on the clock, item step unreachable.
_TIME_ONLY = {"every_seconds": 0.0, "every_fraction": 10.0}


def _lines(stream: io.StringIO) -> list[str]:
    return [ln for ln in stream.getvalue().splitlines() if ln]


def test_line_shape_is_phase_k_of_n_and_elapsed():
    buf = io.StringIO()
    beat = runner._Heartbeat("gather:B", 40, stream=buf, **_ITEMS_ONLY)
    for _ in range(40):
        beat.tick()
    beat.done()

    parsed = [_LINE.match(ln) for ln in _lines(buf)]
    assert all(parsed), f"unparseable heartbeat line(s): {_lines(buf)}"
    assert {m["phase"] for m in parsed} == {"gather:B"}
    assert {m["n"] for m in parsed} == {"40"}
    assert [m["k"] for m in parsed][0] == "0"   # the phase announces itself
    assert [m["k"] for m in parsed][-1] == "40"  # ...and closes on the full count


def test_opening_line_prints_before_any_work_including_an_empty_loop():
    """A phase with nothing to do still proves it was ENTERED.

    This is the silent-gather case: without the opening line, "0 items" and
    "hung before the first item" are the same observation.
    """
    buf = io.StringIO()
    beat = runner._Heartbeat("featurize:A", 0, stream=buf)
    assert _lines(buf) == ["[featurize:A] 0/0 (elapsed 0s)"]
    beat.done()
    assert len(_lines(buf)) == 1, "done() must not repeat a count already printed"


def test_item_threshold_fires_every_five_percent():
    buf = io.StringIO()
    beat = runner._Heartbeat("attach+match:B", 100, stream=buf, **_ITEMS_ONLY)
    for _ in range(100):
        beat.tick()
    beat.done()
    # 5% of 100 => a line every 5 items: the opening line plus 20.
    assert len(_lines(buf)) == 21
    assert [int(_LINE.match(ln)["k"]) for ln in _lines(buf)] == list(range(0, 101, 5))


def test_time_threshold_fires_independently_of_the_item_threshold():
    """The clock branch alone must be able to print.

    ``every_fraction=10.0`` puts the item threshold at 10x the item count — it
    can never come due — so every line here is the time branch's work.  This is
    the branch that matters for a slow loop over few items, which is precisely
    the Panel-B shape that went silent.
    """
    buf = io.StringIO()
    beat = runner._Heartbeat("fs_grid:B", 3, stream=buf, **_TIME_ONLY)
    for _ in range(3):
        beat.tick()
    beat.done()
    assert [int(_LINE.match(ln)["k"]) for ln in _lines(buf)] == [0, 1, 2, 3]


def test_a_quiet_loop_stays_quiet_until_a_threshold_is_due():
    buf = io.StringIO()
    beat = runner._Heartbeat("finalize:A", 1000, stream=buf, **_ITEMS_ONLY)
    for _ in range(49):  # step is 50 — nothing is due yet
        beat.tick()
    assert len(_lines(buf)) == 1
    beat.tick()
    assert [int(_LINE.match(ln)["k"]) for ln in _lines(buf)] == [0, 50]


def test_done_closes_a_partial_tail_exactly_once():
    buf = io.StringIO()
    beat = runner._Heartbeat("gather:A", 100, stream=buf, **_ITEMS_ONLY)
    for _ in range(7):  # step is 5: one line at 5, then a 2-item tail
        beat.tick()
    assert [int(_LINE.match(ln)["k"]) for ln in _lines(buf)] == [0, 5]
    beat.done()
    beat.done()
    assert [int(_LINE.match(ln)["k"]) for ln in _lines(buf)] == [0, 5, 7]


def test_heartbeat_defaults_to_stderr_and_writes_nothing_to_stdout(capsys):
    """stdout is the contract channel; the heartbeat may never touch it."""
    beat = runner._Heartbeat("gather:B", 10, **_ITEMS_ONLY)
    for _ in range(10):
        beat.tick()
    beat.done()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert all(_LINE.match(ln) for ln in captured.err.splitlines() if ln)
    assert "[gather:B] 10/10" in captured.err


def test_a_broken_stream_cannot_kill_the_run_it_watches():
    """An hour into a loop, a closed stderr must cost the LINE, not the work."""
    class _Broken(io.StringIO):
        def write(self, _s):  # noqa: D401 — stand-in for a closed pipe
            raise ValueError("I/O operation on closed file")

    beat = runner._Heartbeat("attach+match:A", 10, stream=_Broken(),
                             **_TIME_ONLY)
    for _ in range(10):
        beat.tick()
    beat.done()  # no exception is the assertion


def test_closed_stream_is_also_survived():
    buf = io.StringIO()
    beat = runner._Heartbeat("attach+match:A", 4, stream=buf, **_TIME_ONLY)
    buf.close()
    for _ in range(4):
        beat.tick()
    beat.done()


@pytest.mark.parametrize("phase", ["gather:", "finalize:", "featurize:",
                                   "attach+match:", "fs_grid"])
def test_every_long_loop_is_still_instrumented(phase):
    """The five phases are named in the runner source, by construction site.

    A behavioural test cannot notice a call site that was deleted, and a phase
    that stops reporting is indistinguishable from a hang — which is the whole
    defect this instrument was added for.
    """
    src = (ROOT / "scripts" / "entry_radar_replay.py").read_text(encoding="utf-8")
    assert f'_Heartbeat(f"{phase}' in src or f'_Heartbeat("{phase}' in src, (
        f"no _Heartbeat construction found for phase {phase!r} — a long loop "
        "lost its liveness line")


def test_the_real_finalize_loop_is_wired_and_keeps_stdout_clean(tmp_path, capsys):
    """Real call site, no fixtures: an empty candidate list still announces."""
    refusals: list[dict] = []
    out = runner._finalize_candidates([], panel="B", cache_dir=tmp_path,
                                      spy_close=None, sectors={},
                                      refusals=refusals)
    captured = capsys.readouterr()
    assert out == [] and refusals == []
    assert captured.out == ""
    assert captured.err.splitlines() == ["[finalize:B] 0/0 (elapsed 0s)"]
