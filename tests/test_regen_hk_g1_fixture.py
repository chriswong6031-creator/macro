"""tests/test_regen_hk_g1_fixture.py — scripts/regen_hk_g1_fixture.py.

The generator exists so a yahoo dividend adjustment (which rewrites a ticker's
whole price history and hard-fails ``TestG1FixtureIsNotStale``) has a remedy that
is a re-pin WITH a receipt rather than a hand-edit.  Two properties make it safe
to run, and both are guarded here:

  * on an UNCHANGED panel it is a byte-level no-op — running it never churns the
    fixture, so it can be run to ask a question, not only to answer one.  An
    append-only panel advance (new panel sha, identical frozen payload) is the
    same no-op, which is why the sha is stamped on real writes only;
  * on drift it classifies before it writes.  A constant-ratio rewrite prints an
    ADJUSTMENT-SIGNATURE receipt and re-pins; a NON-constant rewrite, calendar
    surgery, a ticker-set change, or verdict/meta movement on a ticker whose
    closes did not move is REFUSED with the file untouched.

Everything runs against a SYNTHETIC three-ticker panel built once per session —
no repo data, no subprocesses.  Each test copies the panel + fixture into its own
tmp dir, so a test that writes cannot leak into the next one.  "Untouched" is
asserted on bytes AND ``st_mtime_ns``: a rewrite with identical content is still
a write, and this suite must be able to tell them apart.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import regen_hk_g1_fixture as regen        # noqa: E402
from scripts.regen_hk_g1_fixture import main            # noqa: E402


AS_OF = "2026-07-31"
TAIL = 90
TICKERS = ("0001.HK", "0002.HK", "0003.HK")
SESSIONS = 300


def _panel_frame() -> "pd.DataFrame":
    """Deterministic, strictly positive closes — no randomness, no NaN."""
    index = pd.bdate_range(end=AS_OF, periods=SESSIONS)
    data = {
        ticker: [10.0 + 0.01 * i + 0.05 * (i % 7) + k
                 for i in range(SESSIONS)]
        for k, ticker in enumerate(TICKERS)
    }
    return pd.DataFrame(data, index=index, dtype="float64")


@pytest.fixture(scope="session")
def template(tmp_path_factory):
    """One built-once panel + bootstrapped fixture; every test copies it.

    The bootstrap is itself the documented first-run flow: against a seed fixture
    with empty sections every ticker is an ADDITION, which is a structural refusal,
    so minting the payload the first time takes ``--force``.
    """
    root = tmp_path_factory.mktemp("regen_g1_template")
    panel_path = root / "closes_deep.parquet"
    _panel_frame().to_parquet(panel_path)

    fixture_path = root / "hk_board_2026_07_31.json"
    fixture_path.write_text(json.dumps({
        "_note": "seed",
        "_source": str(panel_path),
        "_source_sha256_16": "0" * 16,
        "_as_of": AS_OF,
        "_tail_sessions": TAIL,
        "verdicts": {},
        "meta": {},
        "closes": {},
    }))

    assert main(["--fixture", str(fixture_path), "--panel", str(panel_path),
                 "--force"]) == 0
    return {"panel": panel_path, "fixture": fixture_path}


class _Bed:
    """One test's private panel + fixture pair."""

    def __init__(self, panel: Path, fixture: Path):
        self.panel = panel
        self.fixture = fixture

    def run(self, *flags: str) -> int:
        return main(["--fixture", str(self.fixture), "--panel", str(self.panel),
                     *flags])

    def state(self) -> tuple[bytes, int]:
        return self.fixture.read_bytes(), self.fixture.stat().st_mtime_ns

    def payload(self) -> dict:
        return json.loads(self.fixture.read_text())

    def frame(self) -> "pd.DataFrame":
        return pd.read_parquet(self.panel)

    def rewrite(self, frame: "pd.DataFrame") -> None:
        frame.to_parquet(self.panel)

    def restore_clean_panel(self) -> None:
        _panel_frame().to_parquet(self.panel)


@pytest.fixture
def bed(template, tmp_path):
    """A private copy of the bootstrapped pair — a test that writes cannot leak."""
    panel = tmp_path / "closes_deep.parquet"
    fixture = tmp_path / "hk_board_2026_07_31.json"
    shutil.copy2(template["panel"], panel)
    shutil.copy2(template["fixture"], fixture)
    return _Bed(panel=panel, fixture=fixture)


# --------------------------------------------------------------------------- #
# 1. the no-op contract
# --------------------------------------------------------------------------- #
def test_bootstrap_then_byte_idempotent(bed, capsys):
    """Re-running on an unchanged panel writes NOTHING — not even identical bytes."""
    before_bytes, before_mtime = bed.state()
    assert bed.run() == 0
    out = capsys.readouterr().out
    after_bytes, after_mtime = bed.state()

    assert "NO-OP" in out
    assert after_bytes == before_bytes
    assert after_mtime == before_mtime, "an identical rewrite is still a write"

    # the bootstrap really did mint the payload it is now idempotent on
    payload = json.loads(before_bytes)
    assert list(payload["verdicts"]) == list(TICKERS)
    assert list(payload["meta"]) == list(TICKERS)
    assert list(payload["closes"]) == list(TICKERS)
    assert len(payload["closes"]["0001.HK"]["dates"]) == TAIL
    assert payload["_note"] == regen.NOTE
    assert payload["_source_sha256_16"] != "0" * 16


def test_append_only_advance_is_noop(bed, capsys):
    """Sessions appended AFTER the as-of move the panel sha and nothing else."""
    before_bytes, before_mtime = bed.state()
    frame = bed.frame()
    extra = pd.DataFrame(
        {ticker: [float(frame[ticker].iloc[-1]) + 0.1,
                  float(frame[ticker].iloc[-1]) + 0.2] for ticker in TICKERS},
        index=pd.to_datetime(["2026-08-03", "2026-08-04"]))
    bed.rewrite(pd.concat([frame, extra]))

    assert bed.run() == 0
    out = capsys.readouterr().out
    after_bytes, after_mtime = bed.state()

    assert "NO-OP" in out
    assert after_bytes == before_bytes
    assert after_mtime == before_mtime
    assert json.loads(after_bytes)["_source_sha256_16"] == \
        json.loads(before_bytes)["_source_sha256_16"], \
        "the sha is provenance for the last real freeze, not a panel mtime"


# --------------------------------------------------------------------------- #
# 2. adjustment drift — re-pin WITH a receipt
# --------------------------------------------------------------------------- #
def _adjust(bed, ratio: float = 0.987, before_last: int = 50) -> None:
    """Rescale every session strictly older than ``before_last``-from-the-end.

    Mirrors a dividend adjustment's shape: one constant ratio applied to a
    contiguous historical block, leaving the recent sessions alone.
    """
    frame = bed.frame()
    cut = len(frame) - before_last
    frame.iloc[:cut] = frame.iloc[:cut] * ratio
    bed.rewrite(frame)


def test_constant_ratio_adjustment_repins_with_receipt(bed, capsys):
    before = bed.payload()
    _adjust(bed)

    assert bed.run() == 0
    out = capsys.readouterr().out
    after = bed.payload()

    assert "ADJUSTMENT-SIGNATURE" in out
    assert "dates_equal=True" in out
    assert "0.987" in out, "the receipt must carry the measured ratio"
    for ticker in TICKERS:
        assert f"ADJUSTMENT-SIGNATURE {ticker}" in out
    assert "REFUSE" not in out

    assert after["closes"] != before["closes"], "the re-pin must land"
    assert after["closes"]["0001.HK"]["dates"] == before["closes"]["0001.HK"]["dates"]
    assert after["_source_sha256_16"] != before["_source_sha256_16"]

    # ~40 of the 90 stored sessions moved: the block boundary sits inside the tail
    moved = sum(1 for old, new in zip(before["closes"]["0001.HK"]["closes"],
                                      after["closes"]["0001.HK"]["closes"])
                if old != new)
    assert 30 <= moved <= 50, moved


# --------------------------------------------------------------------------- #
# 3. refusals — the file is not touched
# --------------------------------------------------------------------------- #
def _corrupt_one_session(bed) -> None:
    """One session ×1.5 — a re-printed close, not a rescaled history.

    Exactly one stored session moves, which is the shape the constant-ratio test is
    arithmetically incapable of failing on its own (median of one ratio, residual
    zero).  The generator refuses it on that ground, so this is also the guard on
    the guard: a signature that could not fail would let this through.
    """
    frame = bed.frame()
    frame.iloc[-10, 0] = float(frame.iloc[-10, 0]) * 1.5
    bed.rewrite(frame)


def test_non_constant_drift_refuses_untouched(bed, capsys):
    before_bytes, before_mtime = bed.state()
    _corrupt_one_session(bed)

    assert bed.run() == 2
    out = capsys.readouterr().out
    after_bytes, after_mtime = bed.state()

    assert after_bytes == before_bytes
    assert after_mtime == before_mtime
    assert "REFUSE 0001.HK" in out
    assert "human eyes" in out
    assert "--force" in out
    assert "Nothing was written." in out


def test_force_writes_through_refusal(bed, capsys):
    before_bytes, _ = bed.state()
    _corrupt_one_session(bed)

    assert bed.run("--force") == 0
    out = capsys.readouterr().out

    assert "FORCED past" in out
    assert bed.fixture.read_bytes() != before_bytes
    assert bed.payload()["closes"]["0001.HK"]["closes"] != \
        json.loads(before_bytes)["closes"]["0001.HK"]["closes"]


def test_check_never_writes(bed, capsys):
    # a) refusal state — --check reports it and still writes nothing
    _corrupt_one_session(bed)
    before_bytes, before_mtime = bed.state()
    assert bed.run("--check") == 2
    out = capsys.readouterr().out
    assert bed.state() == (before_bytes, before_mtime)
    assert "REFUSE 0001.HK" in out

    # b) clean state — --check on a byte-idempotent pair is a plain no-op
    bed.restore_clean_panel()
    before_bytes, before_mtime = bed.state()
    assert bed.run("--check") == 0
    out = capsys.readouterr().out
    assert bed.state() == (before_bytes, before_mtime)
    assert "NO-OP" in out


def test_derived_only_drift_refuses(bed, capsys, monkeypatch):
    """A verdict that moves while its stored closes do not is never written blind.

    That shape is either a panel rewrite DEEPER than the 90-session tail can see or
    an engine-era change — both need a human, so an engine-change PR re-pins with
    ``--force`` and a data surprise stops here.  Patched at the seam the script
    itself calls, so the refusal is exercised through the real code path.
    """
    real_compact = regen.signal_gate.compact

    def shifted(verdict):
        out = dict(real_compact(verdict))
        if out.get("ticks") is not None:
            out["ticks"] = int(out["ticks"]) + 7
        else:
            out["ticks"] = 7
        return out

    before_bytes, before_mtime = bed.state()
    monkeypatch.setattr(regen.signal_gate, "compact", shifted)

    assert bed.run() == 2
    out = capsys.readouterr().out

    assert bed.state() == (before_bytes, before_mtime)
    assert "REFUSE 0001.HK" in out
    assert "verdict.ticks" in out
    assert "closes did NOT" in out
    assert "human eyes" in out
