"""tests/test_marketing_liveness_tripwire.py — the alarm that ends "green and dark".

WHAT IS BEING PINNED. Between 2026-08-06 and 2026-08-10 the marketing publisher
posted NOTHING and every 30-minute sweep concluded GREEN. Buffer's plan locked
(429s) on 08-06, ``MARKETING_PUBLISH_ENABLED`` went to 0 on 08-08 while the
backend refused, Buffer was fixed, and nobody re-armed it. A dry-run sweep is a
successful sweep, so the workflow had nothing to fail on.

``scripts/marketing_liveness_tripwire.py`` is the observer for that shape. Its
decision is factored into ``evaluate(now, armed, last_live_post_at, cfg)`` — a
pure function — precisely so the rules can be pinned here without a process, an
env var or a real ledger. The properties that matter:

  * armed + silent + deep in the posting window is a RED sweep, not a warning;
  * armed + silent at 11:30Z is NOT — the ladder's overnight gap is normal, and
    an alarm that cries every morning is an alarm nobody reads;
  * disarmed is allowed, being disarmed for a DAY has to be re-decided out loud:
    a warning on every sweep and one red at 13:00Z;
  * an unknown last-post time reads as very old, never as fine (no receipts is
    the state a five-day outage ends in);
  * a dry-run row is not a post, and a truncated row is not a crash.

Every annotation is asserted to START with ``::`` — the house law this lane broke
once already (CLAUDE.md, "GitHub annotations must START the line": a ``::warning``
handed to a logger is dropped by GitHub, which is how the publisher's disarmed
downgrade shipped invisible). tests/test_gh_annotation_line_start.py guards the
emitter side; this file guards that the strings themselves stay well-formed.

Sparse worktrees: every file this suite reads is built under ``tmp_path``. It
never touches repo ``data/``.

Run: TZ=UTC python3 -m pytest tests/test_marketing_liveness_tripwire.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import marketing_liveness_tripwire as tw


CFG = {"stale_post_alarm_hours": 8.0, "disarmed_alarm_hours": 24.0}

# 20:00Z — inside [17:00Z..23:59Z], the back half of the 11:00Z–00:30Z ladder.
IN_WINDOW = datetime(2026, 8, 10, 20, 0, tzinfo=timezone.utc)
# 11:30Z — the second rung of the day; "nothing since yesterday" is expected here.
OUT_OF_WINDOW = datetime(2026, 8, 10, 11, 30, tzinfo=timezone.utc)
# 13:20Z — the once-daily slot where a long-dark lane turns red.
DAILY_FAIL_SLOT = datetime(2026, 8, 10, 13, 20, tzinfo=timezone.utc)


def _ago(now: datetime, hours: float) -> datetime:
    return now - timedelta(hours=hours)


def _assert_annotations_well_formed(annotations: list[str]) -> None:
    """Every annotation starts its line, or GitHub never sees it."""
    assert annotations, "the tripwire must always say something"
    for line in annotations:
        assert line.startswith("::"), f"annotation does not start the line: {line!r}"
        assert "\n" not in line, f"multi-line annotation would break parsing: {line!r}"


def _kinds(annotations: list[str]) -> list[str]:
    """['error', 'warning', 'notice', ...] in emission order."""
    return [line[2:].split(" ", 1)[0] for line in annotations]


# ── 1. ARMED AND SILENT — the outage the incident actually was ───────────────

def test_armed_and_stale_inside_the_window_is_a_red_sweep():
    code, annotations = tw.evaluate(IN_WINDOW, True, _ago(IN_WINDOW, 30), CFG)

    assert code == 1
    _assert_annotations_well_formed(annotations)
    assert _kinds(annotations) == ["error"]
    assert "marketing-liveness" in annotations[0]
    assert "30.0h" in annotations[0]
    assert "threshold 8h" in annotations[0]


def test_armed_and_stale_outside_the_window_is_ok():
    """11:30Z with nothing since yesterday afternoon is the ladder's normal gap.

    Same inputs as the test above but two rungs into the morning: the alarm must
    hold its fire, or it fires every single day and stops being read.
    """
    code, annotations = tw.evaluate(OUT_OF_WINDOW, True, _ago(OUT_OF_WINDOW, 30), CFG)

    assert code == 0
    _assert_annotations_well_formed(annotations)
    assert _kinds(annotations) == ["notice"]
    assert "armed=True" in annotations[0]


def test_armed_and_fresh_inside_the_window_is_ok():
    code, annotations = tw.evaluate(IN_WINDOW, True, _ago(IN_WINDOW, 2), CFG)

    assert code == 0
    _assert_annotations_well_formed(annotations)
    assert _kinds(annotations) == ["notice"]
    assert "2.0h ago" in annotations[0]


def test_the_armed_threshold_is_a_boundary_not_a_vibe():
    """Exactly at the threshold is not yet stale; a minute past it is."""
    at = tw.evaluate(IN_WINDOW, True, _ago(IN_WINDOW, 8), CFG)
    past = tw.evaluate(IN_WINDOW, True, _ago(IN_WINDOW, 8.02), CFG)

    assert at[0] == 0, "an alarm must not fire one second early"
    assert past[0] == 1


def test_config_moves_the_armed_threshold():
    cfg = {"stale_post_alarm_hours": 3.0, "disarmed_alarm_hours": 24.0}
    code, annotations = tw.evaluate(IN_WINDOW, True, _ago(IN_WINDOW, 4), cfg)

    assert code == 1
    assert "threshold 3h" in annotations[0]


# ── 2. DISARMED — allowed, but not allowed to become permanent quietly ───────

def test_disarmed_and_fresh_is_ok():
    """The operator disarmed an hour ago. That is a decision, not an incident."""
    code, annotations = tw.evaluate(IN_WINDOW, False, _ago(IN_WINDOW, 3), CFG)

    assert code == 0
    _assert_annotations_well_formed(annotations)
    assert _kinds(annotations) == ["notice"]
    assert "armed=False" in annotations[0]


def test_disarmed_over_a_day_warns_on_an_ordinary_sweep():
    code, annotations = tw.evaluate(IN_WINDOW, False, _ago(IN_WINDOW, 96), CFG)

    assert code == 0, "a warning must not red all ~30 sweeps a day"
    _assert_annotations_well_formed(annotations)
    assert _kinds(annotations) == ["warning"]
    assert "marketing-dark" in annotations[0]
    assert "posts are OFF" in annotations[0]
    assert "96.0h" in annotations[0]


def test_disarmed_over_a_day_reds_the_daily_slot():
    """13:00Z is where "temporarily dark" has to be re-decided out loud.

    Five days of green is exactly what happens when nothing ever forces the
    question, so once a day the dark lane fails its own sweep.
    """
    code, annotations = tw.evaluate(DAILY_FAIL_SLOT, False, _ago(DAILY_FAIL_SLOT, 96), CFG)

    assert code == 1
    _assert_annotations_well_formed(annotations)
    assert _kinds(annotations) == ["warning", "error"], \
        "the daily red must ALSO carry the plain warning"
    assert "13:00Z" in annotations[1]
    assert "disarmed >24h" in annotations[1]


def test_disarmed_but_fresh_does_not_red_the_daily_slot():
    """The 13:00Z red is about darkness, not about the hour."""
    code, annotations = tw.evaluate(DAILY_FAIL_SLOT, False, _ago(DAILY_FAIL_SLOT, 2), CFG)

    assert code == 0
    assert _kinds(annotations) == ["notice"]


def test_the_disarmed_window_gate_does_not_apply():
    """The posting-window gate is the ARMED rule's, not the dark rule's.

    A lane that has been off for four days is off at 11:30Z too, and the whole
    point of the dark rule is that it keeps speaking while the ladder is idle.
    """
    code, annotations = tw.evaluate(OUT_OF_WINDOW, False, _ago(OUT_OF_WINDOW, 96), CFG)

    assert code == 0
    assert _kinds(annotations) == ["warning"]


# ── 3. UNKNOWN AGE — no receipts is the state an outage ends in ──────────────

def test_missing_publications_file_reads_as_very_old(tmp_path):
    assert tw.read_last_live_post(tmp_path / "publications.jsonl") is None

    code, annotations = tw.evaluate(IN_WINDOW, True, None, CFG)
    assert code == 1, "unknown must never read as fine"
    assert _kinds(annotations) == ["error"]

    dark_code, dark_ann = tw.evaluate(DAILY_FAIL_SLOT, False, None, CFG)
    assert dark_code == 1
    assert _kinds(dark_ann) == ["warning", "error"]


def test_empty_publications_file_reads_as_unknown(tmp_path):
    path = tmp_path / "publications.jsonl"
    path.write_text("", encoding="utf-8")

    assert tw.read_last_live_post(path) is None
    assert tw.age_hours(IN_WINDOW, None) == tw.UNKNOWN_AGE_HOURS


# ── 4. THE LEDGER READER — what counts as evidence of a post ─────────────────

def _write_rows(tmp_path, rows: list[str]):
    path = tmp_path / "publications.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_reader_takes_the_newest_live_receipt(tmp_path):
    """MAX, not last line: the ledger is union-merged, so file order is not time
    order (.gitattributes merge=union across the nightly + sweep lanes)."""
    path = _write_rows(tmp_path, [
        json.dumps({"mode": "live", "published_at": "2026-08-10T18:15:00Z"}),
        json.dumps({"mode": "live", "published_at": "2026-08-10T12:00:00Z"}),
    ])

    assert tw.read_last_live_post(path) == datetime(2026, 8, 10, 18, 15, tzinfo=timezone.utc)


def test_reader_ignores_rows_that_are_not_live(tmp_path):
    """A dry-run row is not a post. Counting one is how a dark lane looks alive."""
    path = _write_rows(tmp_path, [
        json.dumps({"mode": "live", "published_at": "2026-08-05T20:46:42Z"}),
        json.dumps({"mode": "dry_run", "published_at": "2026-08-10T19:00:00Z"}),
        json.dumps({"published_at": "2026-08-10T19:30:00Z"}),  # no mode at all
    ])

    assert tw.read_last_live_post(path) == datetime(2026, 8, 5, 20, 46, 42, tzinfo=timezone.utc)


def test_reader_skips_malformed_rows_without_crashing(tmp_path):
    """The ledger is appended to by a job that can be cancelled mid-write."""
    path = _write_rows(tmp_path, [
        "not json at all",
        '{"mode": "live", "published_at": "2026-08-10T16:00:00Z"}',
        '{"mode": "live", "published_at": "yesterday-ish"}',   # unparseable stamp
        '{"mode": "live"}',                                     # no stamp
        '["mode", "live"]',                                     # not an object
        "",                                                     # blank line
        '{"mode": "live", "published_at": "2026-08-10T17:0',    # truncated tail
    ])

    assert tw.read_last_live_post(path) == datetime(2026, 8, 10, 16, 0, tzinfo=timezone.utc)


def test_reader_normalises_stamps_to_utc(tmp_path):
    """Offset stamps and naive stamps both land on the same instant."""
    path = _write_rows(tmp_path, [
        json.dumps({"mode": "live", "published_at": "2026-08-10T14:00:00+02:00"}),
    ])
    assert tw.read_last_live_post(path) == datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    assert tw.parse_iso("2026-08-10T12:00:00") == datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert tw.parse_iso("") is None
    assert tw.parse_iso(None) is None


def test_a_future_stamp_is_clock_skew_not_negative_age():
    assert tw.age_hours(IN_WINDOW, IN_WINDOW + timedelta(hours=3)) == 0.0


# ── 5. WINDOW + ARM PARSING ──────────────────────────────────────────────────

@pytest.mark.parametrize("hour,minute,expected", [
    (0, 0, True), (0, 30, True), (0, 31, False),
    (1, 0, False), (11, 0, False), (16, 59, False),
    (17, 0, True), (20, 0, True), (23, 59, True),
])
def test_evaluation_window_covers_the_back_half_of_the_ladder(hour, minute, expected):
    now = datetime(2026, 8, 10, hour, minute, tzinfo=timezone.utc)
    assert tw.in_evaluation_window(now) is expected


@pytest.mark.parametrize("raw,expected", [
    ("1", True), (" 1 ", True),
    ("0", False), ("", False), ("true", False), ("yes", False),
])
def test_arm_variable_is_read_the_way_the_workflow_writes_it(raw, expected):
    """`== "1"`, matching marketing-publish.yml's own ledger-commit guard.

    A non-"1" truthy value reads DISARMED here, which errs LOUD (the dark rule
    fires after a quiet day) and can never silence a real outage.
    """
    assert tw.armed_from_env({"MARKETING_PUBLISH_ENABLED": raw}) is expected


def test_arm_variable_absent_is_disarmed():
    assert tw.armed_from_env({}) is False


# ── 6. CONFIG — thresholds are overridable and the loader never crashes ──────

def _cfg_file(tmp_path, body: str):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "marketing.yml").write_text(body, encoding="utf-8")
    return tmp_path


def test_config_block_overrides_the_defaults(tmp_path):
    pytest.importorskip("yaml")
    root = _cfg_file(tmp_path, "publish:\n  liveness:\n"
                               "    stale_post_alarm_hours: 4\n"
                               "    disarmed_alarm_hours: 12\n")

    cfg = tw.load_config(root)
    assert cfg == {"stale_post_alarm_hours": 4.0, "disarmed_alarm_hours": 12.0}


def test_absent_block_absent_file_and_junk_all_fall_back_to_defaults(tmp_path):
    pytest.importorskip("yaml")
    defaults = {
        "stale_post_alarm_hours": tw.DEFAULT_STALE_POST_ALARM_HOURS,
        "disarmed_alarm_hours": tw.DEFAULT_DISARMED_ALARM_HOURS,
    }

    # no file at all
    assert tw.load_config(tmp_path / "nowhere") == defaults
    # a config with no liveness block
    assert tw.load_config(_cfg_file(tmp_path, "publish:\n  backend: buffer\n")) == defaults
    # liveness present but not a mapping
    assert tw.load_config(_cfg_file(tmp_path, "publish:\n  liveness: off\n")) == defaults
    # unusable values are refused one by one, never adopted
    assert tw.load_config(_cfg_file(
        tmp_path,
        "publish:\n  liveness:\n"
        "    stale_post_alarm_hours: soon\n"
        "    disarmed_alarm_hours: 0\n",
    )) == defaults
    # unparseable YAML
    assert tw.load_config(_cfg_file(tmp_path, "publish: [unclosed\n")) == defaults


def test_the_shipped_config_carries_the_block():
    """The knobs are documented in config/marketing.yml, not only in code.

    A loader that silently defaults is indistinguishable from a config nobody
    wired, so this pins the block's presence rather than the loader's output.
    """
    yaml = pytest.importorskip("yaml")
    payload = yaml.safe_load((tw.ROOT / tw.CONFIG_REL).read_text(encoding="utf-8"))
    block = (payload.get("publish") or {}).get("liveness")

    assert isinstance(block, dict), "publish.liveness is missing from config/marketing.yml"
    assert float(block["stale_post_alarm_hours"]) > 0
    assert float(block["disarmed_alarm_hours"]) > 0
    assert tw.load_config()["stale_post_alarm_hours"] == float(block["stale_post_alarm_hours"])


# ── 7. END TO END through main() — annotations reach stdout, code is the exit ─

def test_main_prints_the_annotation_at_column_zero(tmp_path, capsys, monkeypatch):
    """capsys, not caplog: an annotation that goes through logging is invisible
    to GitHub, and that is the defect this whole module exists to end."""
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "marketing" / "publications.jsonl").write_text(
        json.dumps({"mode": "live", "published_at": "2026-08-05T20:46:42Z"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")

    code = tw.main(["--root", str(tmp_path), "--now", "2026-08-10T20:00:00Z"])
    out = capsys.readouterr().out.splitlines()
    emitted = [ln for ln in out if "::" in ln]

    assert code == 1
    assert emitted, "no annotation reached stdout"
    for line in emitted:
        assert line.startswith("::"), f"annotation is not at column 0: {line!r}"
    assert any(ln.startswith("::error title=marketing-liveness::") for ln in emitted)


def test_main_is_green_and_quiet_when_the_lane_is_healthy(tmp_path, capsys, monkeypatch):
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "marketing" / "publications.jsonl").write_text(
        json.dumps({"mode": "live", "published_at": "2026-08-10T19:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")

    code = tw.main(["--root", str(tmp_path), "--now", "2026-08-10T20:00:00Z"])
    out = capsys.readouterr().out

    assert code == 0
    assert out.startswith("::notice title=marketing-liveness::ok")


def test_main_refuses_an_unparseable_now(tmp_path):
    assert tw.main(["--root", str(tmp_path), "--now", "whenever"]) == 2
