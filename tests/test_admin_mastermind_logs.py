"""Tests for admin/mastermind_logs.py — the operator read + eval view over the
Mastermind AI response log corpus."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from admin import mastermind_logs as ml


def _seed(root, rows, evals=None):
    d = root / "data" / "mastermind"
    d.mkdir(parents=True, exist_ok=True)
    (d / "response_log.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    if evals:
        (d / "response_eval.jsonl").write_text(
            "\n".join(json.dumps(e) for e in evals) + "\n", encoding="utf-8")


def _row(rid, surface="macro", model="claude-opus-4-8", lane="pro",
         q="question text", a="answer text", ts="2026-07-24T12:00:00+00:00", **kw):
    base = {
        "id": rid, "schema": ml.__dict__.get("_SCHEMA", "mastermind.response_log.v1"),
        "ts": ts, "surface": surface, "lane": lane, "model": model,
        "provider": "claude_api", "question": q, "answer": a,
        "input_tokens": 5, "output_tokens": 7, "flags": {"error": False},
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# logs() — read + stats
# ---------------------------------------------------------------------------
def test_logs_empty_root_is_valid(tmp_path):
    out = ml.logs(root=tmp_path)
    assert out["rows"] == []
    assert out["stats"]["total"] == 0


def test_logs_reads_and_counts(tmp_path):
    _seed(tmp_path, [
        _row("a", surface="macro"),
        _row("b", surface="terminal", model="deepseek-chat", provider="deepseek"),
    ])
    out = ml.logs(root=tmp_path)
    assert out["stats"]["total"] == 2
    assert out["stats"]["by_surface"] == {"macro": 1, "terminal": 1}
    ids = {r["id"] for r in out["rows"]}
    assert ids == {"a", "b"}
    # each row carries an eval overlay stub
    assert all("eval" in r for r in out["rows"])


def test_logs_sorted_newest_first(tmp_path):
    _seed(tmp_path, [
        _row("old", ts="2026-07-20T00:00:00+00:00"),
        _row("new", ts="2026-07-24T00:00:00+00:00"),
    ])
    out = ml.logs(root=tmp_path)
    assert [r["id"] for r in out["rows"]] == ["new", "old"]


def test_logs_filter_by_surface(tmp_path):
    _seed(tmp_path, [_row("a", surface="macro"), _row("b", surface="terminal")])
    out = ml.logs(filters={"surface": "terminal"}, root=tmp_path)
    assert [r["id"] for r in out["rows"]] == ["b"]
    assert out["matched"] == 1
    # stats stay whole-window even when filtered
    assert out["stats"]["total"] == 2


def test_logs_filter_search_and_model(tmp_path):
    _seed(tmp_path, [
        _row("a", q="tell me about NVDA", model="claude-opus-4-8"),
        _row("b", q="what about bonds", model="deepseek-chat"),
    ])
    assert [r["id"] for r in ml.logs(filters={"q": "nvda"}, root=tmp_path)["rows"]] == ["a"]
    assert [r["id"] for r in ml.logs(filters={"model": "deepseek"}, root=tmp_path)["rows"]] == ["b"]


def test_logs_filter_graded_overlay(tmp_path):
    _seed(tmp_path,
          [_row("a"), _row("b")],
          evals=[{"id": "a", "grade": 5, "updated_ts": "2026-07-24T12:05:00+00:00"}])
    graded = ml.logs(filters={"graded": "yes"}, root=tmp_path)
    ungraded = ml.logs(filters={"graded": "no"}, root=tmp_path)
    assert [r["id"] for r in graded["rows"]] == ["a"]
    assert [r["id"] for r in ungraded["rows"]] == ["b"]
    assert graded["stats"]["graded"] == 1
    assert graded["rows"][0]["eval"]["grade"] == 5


# ---------------------------------------------------------------------------
# validate_rate_body
# ---------------------------------------------------------------------------
def test_validate_rate_body_ok():
    ok, err, cleaned = ml.validate_rate_body(
        {"id": "abc", "grade": 4, "thumb": "up", "star": True,
         "tags": ["great", " concise "], "note": "solid"})
    assert ok and err is None
    assert cleaned["id"] == "abc"
    assert cleaned["grade"] == 4
    assert cleaned["thumb"] == "up"
    assert cleaned["star"] is True
    assert cleaned["tags"] == ["great", "concise"]
    assert cleaned["note"] == "solid"


def test_validate_rate_body_requires_id():
    ok, err, _ = ml.validate_rate_body({"grade": 3})
    assert not ok and "id" in err


def test_validate_rate_body_grade_range():
    ok, err, _ = ml.validate_rate_body({"id": "x", "grade": 9})
    assert not ok and "range" in err


def test_validate_rate_body_bad_thumb():
    ok, err, _ = ml.validate_rate_body({"id": "x", "thumb": "sideways"})
    assert not ok and "thumb" in err


# ---------------------------------------------------------------------------
# rate() writeback + overlay latest-wins
# ---------------------------------------------------------------------------
def test_rate_appends_and_overlays(tmp_path):
    _seed(tmp_path, [_row("a")])
    ok, _, cleaned = ml.validate_rate_body({"id": "a", "grade": 2, "thumb": "down"})
    assert ok
    res = ml.rate(cleaned, evaluator="operator", root=tmp_path)
    assert res["ok"] and res["eval"]["grade"] == 2
    # subsequent read reflects the verdict
    out = ml.logs(root=tmp_path)
    row = next(r for r in out["rows"] if r["id"] == "a")
    assert row["eval"]["grade"] == 2 and row["eval"]["thumb"] == "down"


def test_rate_latest_wins(tmp_path):
    _seed(tmp_path, [_row("a")])
    _, _, c1 = ml.validate_rate_body({"id": "a", "grade": 1})
    ml.rate(c1, root=tmp_path)
    _, _, c2 = ml.validate_rate_body({"id": "a", "grade": 5})
    ml.rate(c2, root=tmp_path)
    out = ml.logs(root=tmp_path)
    row = next(r for r in out["rows"] if r["id"] == "a")
    assert row["eval"]["grade"] == 5


# ---------------------------------------------------------------------------
# export()
# ---------------------------------------------------------------------------
def test_export_jsonl(tmp_path):
    _seed(tmp_path, [_row("a"), _row("b")])
    out = ml.export(fmt="jsonl", root=tmp_path)
    assert out["ok"] and out["count"] == 2
    assert out["filename"].endswith(".jsonl")
    lines = [json.loads(x) for x in out["content"].splitlines()]
    assert {l["id"] for l in lines} == {"a", "b"}


def test_export_csv_has_header_and_eval_cols(tmp_path):
    _seed(tmp_path, [_row("a")], evals=[{"id": "a", "grade": 4, "updated_ts": "t"}])
    out = ml.export(fmt="csv", root=tmp_path)
    assert out["ok"] and out["filename"].endswith(".csv")
    header = out["content"].splitlines()[0]
    for col in ("id", "surface", "question", "answer", "grade", "thumb", "tags"):
        assert col in header


def test_export_respects_filter(tmp_path):
    _seed(tmp_path, [_row("a", surface="macro"), _row("b", surface="terminal")])
    out = ml.export(fmt="jsonl", filters={"surface": "macro"}, root=tmp_path)
    assert out["count"] == 1


# ---------------------------------------------------------------------------
# refresh() — graceful no-op without R2 creds
# ---------------------------------------------------------------------------
def test_refresh_noop_without_creds(tmp_path, monkeypatch):
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(k, raising=False)
    out = ml.refresh(root=tmp_path)
    assert out["ok"] is False
    assert out["ingested"] == 0
    assert "note" in out


# ---------------------------------------------------------------------------
# ingest_health() — is the R2 → ledger ingest still running?
# ---------------------------------------------------------------------------
def _ago(days: float) -> str:
    """An ISO ts `days` in the past — never hardcode dates in a staleness test."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def test_ingest_health_empty_ledger_is_dark(tmp_path):
    # The exact July-2026 production state: nothing ever ingested, panel silent.
    ing = ml.logs(root=tmp_path)["ingest"]
    assert ing["dark"] is True
    assert ing["last_ts"] is None


def test_ingest_health_fresh_row_not_dark(tmp_path):
    ts = _ago(0)
    _seed(tmp_path, [_row("a", ts=ts)])
    ing = ml.logs(root=tmp_path)["ingest"]
    assert ing["dark"] is False
    assert ing["last_by_surface"]["macro"] == ts
    assert ing["threshold_days"] == 2


def test_ingest_health_stale_ledger_is_dark(tmp_path):
    ts = _ago(5)
    _seed(tmp_path, [_row("a", ts=ts)])
    ing = ml.logs(root=tmp_path)["ingest"]
    assert ing["dark"] is True
    assert ing["dark_days"] >= 4
    assert ing["last_ts"].startswith(ts[:10])


def test_ingest_health_one_day_old_not_dark(tmp_path):
    _seed(tmp_path, [_row("a", ts=_ago(1))])
    assert ml.logs(root=tmp_path)["ingest"]["dark"] is False


def test_ingest_health_tracks_newest_per_surface(tmp_path):
    # One surface still writing keeps the ledger overall-live — per-surface is the tell.
    old, recent, mid = _ago(5), _ago(1), _ago(3)
    _seed(tmp_path, [
        _row("m_old", surface="macro", ts=old),
        _row("m_new", surface="macro", ts=recent),
        _row("t_mid", surface="terminal", ts=mid),
    ])
    ing = ml.logs(root=tmp_path)["ingest"]
    assert ing["dark"] is False
    assert ing["last_by_surface"]["macro"] == recent
    assert ing["last_by_surface"]["terminal"] == mid
