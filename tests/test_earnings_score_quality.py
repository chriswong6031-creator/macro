"""The degeneration tripwire must separate the two corpora we actually have.

Thresholds here are not guesses. Both sides were measured on the real store on
2026-08-14, on the SAME schema, so the tripwire is calibrated against a healthy
baseline rather than against an opinion:

    local Qwen  (n=64)     2 of 10 tone words | 70% top-2 sentiment | 34% perf >= 9
    metered     (n=1,234)  9 of 10 tone words | 23% top-2 sentiment |  8% perf >= 9

A tripwire that cannot pass the healthy corpus is noise, and a tripwire that
cannot fail the degenerate one is decoration. Both directions are pinned.
"""
from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from engine.earnings_qual import TONE_WORDS
from scripts.audit_earnings_score_quality import (
    EarningsScoreQualityError,
    audit_frame,
    main,
)


def _frame(tones: list[str], sentiments: list[float], performances: list[float]) -> pd.DataFrame:
    n = max(len(tones), len(sentiments), len(performances))

    def _fill(values, filler):
        return (values * n)[:n] if values else [filler] * n

    return pd.DataFrame(
        {
            "tone_word": _fill(tones, "steady"),
            "sentiment": _fill(sentiments, 0.0),
            "performance": _fill(performances, 5.0),
            "scored_at": ["2026-08-14T00:00:00+00:00"] * n,
            "prompt_version": ["equal-v3+abcdef12"] * n,
        }
    )


def _healthy(n: int = 64) -> pd.DataFrame:
    """Shaped like the measured metered corpus, which must grade `ok`."""
    tones = list(TONE_WORDS[:9])
    sentiments = [round(-0.8 + 0.15 * i, 2) for i in range(12)]
    performances = [2.0, 3.5, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.5]
    frame = _frame(tones, sentiments, performances)
    return pd.concat([frame] * (n // len(frame) + 1), ignore_index=True).head(n)


def _degenerate(n: int = 64) -> pd.DataFrame:
    """The measured local-Qwen shape: two tone words, two sentiments, top-heavy."""
    tones = ["confident"] * 42 + ["cautious"] * 22
    sentiments = [0.85] * 29 + [-0.15] * 16 + [0.65] * 12 + [0.75] * 7
    performances = [9.2] * 22 + [6.2] * 20 + [4.2] * 12 + [7.2] * 10
    return _frame(tones, sentiments, performances).head(n)


def test_the_healthy_corpus_grades_ok() -> None:
    report = audit_frame(_healthy())
    assert report["level"] == "ok", report["checks"]
    assert report["ok"] is True


def test_the_measured_degenerate_corpus_grades_error() -> None:
    report = audit_frame(_degenerate())
    assert report["level"] == "error"
    assert report["checks"]["tone_vocabulary_share"]["level"] == "error"
    assert report["checks"]["sentiment_top2_share"]["level"] == "error"
    assert report["checks"]["high_performance_share"]["level"] == "error"


@pytest.mark.parametrize(
    "check,frame",
    [
        ("tone_vocabulary_share", _frame(["confident", "cautious"],
                                         [round(-0.8 + 0.15 * i, 2) for i in range(12)],
                                         [2.0, 4.0, 5.0, 6.0, 7.0, 8.0])),
        ("sentiment_top2_share", _frame(list(TONE_WORDS[:9]),
                                        [0.85] * 9 + [-0.15],
                                        [2.0, 4.0, 5.0, 6.0, 7.0, 8.0])),
        ("high_performance_share", _frame(list(TONE_WORDS[:9]),
                                          [round(-0.8 + 0.15 * i, 2) for i in range(12)],
                                          [9.5] * 5 + [5.0] * 5)),
    ],
)
def test_each_check_fires_on_its_own_defect(check: str, frame: pd.DataFrame) -> None:
    """One collapsed dimension must be enough — the three are independent failures."""
    report = audit_frame(pd.concat([frame] * 12, ignore_index=True))
    assert report["checks"][check]["level"] == "error", report["checks"]


def test_an_undersampled_window_is_reported_but_never_graded() -> None:
    """A share over 12 rows says nothing, and a false alarm gets a tripwire muted."""
    report = audit_frame(_degenerate(12), min_rows=30)
    assert report["level"] == "insufficient_data"
    assert report["ok"] is True
    assert report["rows"] == 12


def test_an_empty_window_raises_rather_than_reporting_health() -> None:
    with pytest.raises(EarningsScoreQualityError):
        audit_frame(_frame([], [], []).head(0))


def test_cli_emits_a_line_start_error_and_strict_exits_nonzero(tmp_path, capsys) -> None:
    path = tmp_path / "scores.parquet"
    _degenerate().to_parquet(path)
    rc = main(["--scores", str(path), "--window-days", "0", "--strict"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "earnings-scorer-degenerated" in ln)
    # Through a logger the level name would prefix this and GitHub would drop it.
    assert line.startswith("::error title=earnings-scorer-degenerated::")
    assert "2 of 10 tone words used" in line
    assert rc == 1


def test_cli_is_quiet_and_zero_on_a_healthy_store(tmp_path, capsys) -> None:
    path = tmp_path / "scores.parquet"
    _healthy().to_parquet(path)
    rc = main(["--scores", str(path), "--window-days", "0", "--strict"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "::error" not in out and "::warning" not in out


def test_a_missing_store_warns_instead_of_reporting_health(tmp_path, capsys) -> None:
    rc = main(["--scores", str(tmp_path / "nope.parquet"), "--strict"])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.splitlines()[0].startswith("::warning title=earnings-score-quality::")


def test_json_out_records_the_three_measurements(tmp_path) -> None:
    import json

    path = tmp_path / "scores.parquet"
    _degenerate().to_parquet(path)
    dest = tmp_path / "q" / "score_quality.json"
    main(["--scores", str(path), "--window-days", "0", "--json-out", str(dest)])
    report = json.loads(dest.read_text(encoding="utf-8"))
    assert report["schema"] == "macro.earnings_score_quality/v1"
    assert report["level"] == "error"
    assert set(report["checks"]) == {
        "tone_vocabulary_share",
        "sentiment_top2_share",
        "high_performance_share",
    }
