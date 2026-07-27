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


# ---------------------------------------------------------------------------
# Contradiction assessment — deterministic scan
# ---------------------------------------------------------------------------
# The operator's question is whether the assistant wrestles contradictory site signals,
# and which kind of conflict it is. The scan is computed at READ time (never stored) so
# widening _CONTRA_PATTERNS re-scores the whole existing corpus.

def _think(text, round_=1, phase="tool", model="deepseek-v4-flash", **kw):
    seg = {"round": round_, "phase": phase, "model": model, "text": text}
    seg.update(kw)
    return seg


def _one(out, rid):
    return next(r for r in out["rows"] if r["id"] == rid)


def test_contra_scan_hits_in_the_answer(tmp_path):
    _seed(tmp_path, [_row("a", a="Breadth and credit contradict each other here.")])
    row = _one(ml.logs(root=tmp_path), "a")
    assert row["contra"]["hit"] is True
    assert row["contra"]["src"] == "answer"
    assert "contradict" in row["contra"]["terms"]


def test_contra_scan_hits_in_the_thinking_only(tmp_path):
    # The failure the doctrine forbids: the model worked a conflict out privately and
    # then shipped a smooth, confident answer. src='thinking' is how it becomes visible.
    _seed(tmp_path, [_row("a", a="Tape is steady. Act.",
                          thinking=[_think("these two readings diverge badly")])])
    row = _one(ml.logs(root=tmp_path), "a")
    assert row["contra"]["hit"] is True
    assert row["contra"]["src"] == "thinking"
    assert "diverg" in row["contra"]["terms"]


def test_contra_scan_src_both(tmp_path):
    _seed(tmp_path, [_row("a", a="The signals conflict.",
                          thinking=[_think("there is a real conflict here")])])
    assert _one(ml.logs(root=tmp_path), "a")["contra"]["src"] == "both"


def test_contra_scan_zh_terms(tmp_path):
    _seed(tmp_path, [
        _row("zh_a", a="两个读数互相矛盾，先观望。"),
        _row("zh_t", a="行情平稳。", thinking=[_think("广度和信用出现分歧")]),
    ])
    out = ml.logs(root=tmp_path)
    assert _one(out, "zh_a")["contra"] == {"hit": True, "terms": ["矛盾"], "src": "answer"}
    assert _one(out, "zh_t")["contra"]["src"] == "thinking"
    assert "分歧" in _one(out, "zh_t")["contra"]["terms"]


def test_contra_scan_misses_a_plain_row(tmp_path):
    _seed(tmp_path, [_row("a", a="Credit is calm and breadth is broad. Act.")])
    row = _one(ml.logs(root=tmp_path), "a")
    assert row["contra"] == {"hit": False, "terms": [], "src": None}


def test_thinking_meta_and_row_keeps_the_trace(tmp_path):
    _seed(tmp_path, [_row("a", thinking=[_think("abc"), _think("de", phase="synthesis")])])
    row = _one(ml.logs(root=tmp_path), "a")
    assert row["thinking_meta"] == {"segments": 2, "chars": 5}
    # The trace itself is NOT stripped — the UI renders it.
    assert [s["text"] for s in row["thinking"]] == ["abc", "de"]


def test_scan_is_read_time_not_stored(tmp_path):
    """Nothing is written back: the ledger stays byte-identical after a logs() call."""
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    p = tmp_path / "data" / "mastermind" / "response_log.jsonl"
    before = p.read_bytes()
    ml.logs(root=tmp_path)
    assert p.read_bytes() == before


# ---------------------------------------------------------------------------
# Filters: has_thinking / contra / verdict
# ---------------------------------------------------------------------------
def test_filter_has_thinking(tmp_path):
    _seed(tmp_path, [_row("with", thinking=[_think("hm")]), _row("without")])
    out = ml.logs(filters={"has_thinking": True}, root=tmp_path)
    assert [r["id"] for r in out["rows"]] == ["with"]


def test_filter_contra(tmp_path):
    _seed(tmp_path, [_row("hit", a="these disagree"), _row("miss", a="all clear")])
    out = ml.logs(filters={"contra": True}, root=tmp_path)
    assert [r["id"] for r in out["rows"]] == ["hit"]


def test_filter_verdict(tmp_path):
    _seed(tmp_path, [_row("a"), _row("b"), _row("c")],
          evals=[{"id": "a", "contra_verdict": "system_error"},
                 {"id": "b", "contra_verdict": "market_divergence"}])
    out = ml.logs(filters={"verdict": "system_error"}, root=tmp_path)
    assert [r["id"] for r in out["rows"]] == ["a"]
    assert ml.logs(filters={"verdict": "all"}, root=tmp_path)["matched"] == 3


def test_stats_count_thinking_contra_and_verdicts(tmp_path):
    _seed(tmp_path, [
        _row("a", a="the readings conflict", thinking=[_think("hm")]),
        _row("b", thinking=[_think("quiet")]),
        _row("c"),
    ], evals=[{"id": "a", "contra_verdict": "system_error"},
              {"id": "b", "contra_verdict": "none"}])
    st = ml.logs(root=tmp_path)["stats"]
    assert st["n_thinking"] == 2
    assert st["n_contra"] == 1
    assert st["verdicts"] == {"system_error": 1, "none": 1}


# ---------------------------------------------------------------------------
# classify_contradictions — LLM tier
# ---------------------------------------------------------------------------
class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _canned(verdict="system_error", signals=("breadth", "credit"), note="one is stale",
            wrap="{}"):
    """A DeepSeek Anthropic-shaped response carrying the classifier's JSON."""
    body = json.dumps({"contradiction": verdict, "signals": list(signals), "note": note})
    return {"content": [{"type": "text", "text": wrap.format(body) if "{}" in wrap else body}]}


def _patch_urlopen(monkeypatch, payload, capture=None):
    def _fake(req, timeout=None):
        if capture is not None:
            capture.append({"url": req.full_url, "headers": dict(req.headers),
                            "body": json.loads(req.data.decode("utf-8"))})
        return _FakeHTTPResponse(payload)
    monkeypatch.setattr(ml.urllib.request, "urlopen", _fake)


def test_classify_no_llm_key_is_fail_soft(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    out = ml.classify_contradictions(limit=5, root=tmp_path)
    assert out == {"ok": False, "error": "no_llm_key", "classified": 0, "skipped": 0,
                   "note": out["note"], "generated_at": out["generated_at"]}
    # Nothing was written.
    assert not (tmp_path / "data" / "mastermind" / "response_eval.jsonl").exists()


def test_classify_writes_a_verdict(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    calls: list = []
    _patch_urlopen(monkeypatch, _canned(), calls)

    out = ml.classify_contradictions(limit=5, root=tmp_path)
    assert out["ok"] and out["classified"] == 1 and out["skipped"] == 0
    assert out["verdicts"] == {"system_error": 1}

    # Request shape: the Anthropic-compatible endpoint, keyed header, thinking off.
    assert calls[0]["url"] == ml._CLASSIFY_URL
    assert calls[0]["headers"]["X-api-key"] == "k"
    assert calls[0]["headers"]["Anthropic-version"] == "2023-06-01"
    assert calls[0]["body"]["thinking"] == {"type": "disabled"}
    assert calls[0]["body"]["model"] == ml._CLASSIFY_MODEL

    ev = _one(ml.logs(root=tmp_path), "a")["eval"]
    assert ev["contra_verdict"] == "system_error"
    assert ev["contra_signals"] == ["breadth", "credit"]
    assert ev["contra_note"] == "one is stale"
    assert ev["contra_model"] == ml._CLASSIFY_MODEL


def test_classify_merge_preserves_an_operator_rating(tmp_path, monkeypatch):
    """The load-bearing one: verdicts and manual grades share ONE latest-wins sidecar,
    so a classification that rewrote the row would silently delete the operator's work."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    _, _, cleaned = ml.validate_rate_body(
        {"id": "a", "grade": 4, "thumb": "up", "star": True, "tags": ["sharp"], "note": "good call"})
    ml.rate(cleaned, evaluator="operator", root=tmp_path)
    before = _one(ml.logs(root=tmp_path), "a")["eval"]

    _patch_urlopen(monkeypatch, _canned(verdict="market_divergence"))
    assert ml.classify_contradictions(limit=5, root=tmp_path)["classified"] == 1

    ev = _one(ml.logs(root=tmp_path), "a")["eval"]
    assert ev["grade"] == 4 and ev["thumb"] == "up" and ev["star"] is True
    assert ev["tags"] == ["sharp"] and ev["note"] == "good call"
    # The human stays the evaluator of record; the machine pass does not restamp it.
    assert ev["evaluator"] == "operator"
    assert ev["updated_ts"] == before["updated_ts"]
    assert ev["contra_verdict"] == "market_divergence"


def test_rating_after_classify_preserves_the_verdict(tmp_path, monkeypatch):
    """The other direction of the merge law: rate() appends a rating-only snapshot, so
    the overlay must fold per FIELD — a full-row latest-wins would let a later manual
    grade silently erase the contra_* verdict."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    _patch_urlopen(monkeypatch, _canned(verdict="system_error"))
    assert ml.classify_contradictions(limit=5, root=tmp_path)["classified"] == 1

    _, _, cleaned = ml.validate_rate_body({"id": "a", "grade": 2, "thumb": "down"})
    ml.rate(cleaned, evaluator="operator", root=tmp_path)

    ev = _one(ml.logs(root=tmp_path), "a")["eval"]
    assert ev["contra_verdict"] == "system_error"
    assert ev["contra_signals"] == ["breadth", "credit"]
    assert ev["grade"] == 2 and ev["thumb"] == "down"
    assert ev["evaluator"] == "operator"  # the human action IS the latest verdict


def test_a_newer_rating_still_resets_an_older_one_under_the_fold(tmp_path):
    """Per-field folding must not resurrect cleared rating fields: every rate() snapshot
    carries the FULL rating set with explicit nulls, so a re-rate that clears the grade
    overwrites it even though the overlay merges rows."""
    _seed(tmp_path, [_row("a", a="steady tape")])
    _, _, first = ml.validate_rate_body({"id": "a", "grade": 5, "star": True, "note": "keep"})
    ml.rate(first, evaluator="operator", root=tmp_path)
    _, _, second = ml.validate_rate_body({"id": "a", "grade": None, "star": False})
    ml.rate(second, evaluator="operator", root=tmp_path)

    ev = _one(ml.logs(root=tmp_path), "a")["eval"]
    assert ev["grade"] is None and ev["star"] is False and ev["note"] == ""


def test_classify_does_not_reclassify_an_already_verdicted_row(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")],
          evals=[{"id": "a", "contra_verdict": "none"}])
    calls: list = []
    _patch_urlopen(monkeypatch, _canned(), calls)
    out = ml.classify_contradictions(limit=5, root=tmp_path)
    assert out["classified"] == 0 and out["candidates"] == 0 and calls == []


def test_classify_takes_rows_with_thinking_even_without_a_keyword_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("quiet", a="steady tape", thinking=[_think("weighing it up")]),
                     _row("plain", a="steady tape")])
    _patch_urlopen(monkeypatch, _canned(verdict="none", signals=[]))
    out = ml.classify_contradictions(limit=5, root=tmp_path)
    assert out["candidates"] == 1 and out["classified"] == 1
    assert _one(ml.logs(root=tmp_path), "quiet")["eval"]["contra_verdict"] == "none"


def test_classify_parses_json_wrapped_in_prose_or_a_fence(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    _patch_urlopen(monkeypatch, _canned(wrap="Here you go:\n```json\n{}\n```\nHope that helps."))
    assert ml.classify_contradictions(limit=5, root=tmp_path)["classified"] == 1
    assert _one(ml.logs(root=tmp_path), "a")["eval"]["contra_verdict"] == "system_error"


def test_classify_unparseable_becomes_an_unclear_verdict(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    _patch_urlopen(monkeypatch, {"content": [{"type": "text", "text": "no json at all"}]})
    out = ml.classify_contradictions(limit=5, root=tmp_path)
    assert out["classified"] == 1
    ev = _one(ml.logs(root=tmp_path), "a")["eval"]
    assert ev["contra_verdict"] == "unclear" and ev["contra_note"] == "unparseable"


def test_classify_unknown_label_falls_back_to_unclear(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict")])
    _patch_urlopen(monkeypatch, _canned(verdict="data_is_haunted"))
    ml.classify_contradictions(limit=5, root=tmp_path)
    assert _one(ml.logs(root=tmp_path), "a")["eval"]["contra_verdict"] == "unclear"


def test_classify_network_error_skips_the_row_not_the_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _seed(tmp_path, [_row("a", a="the readings conflict", ts="2026-07-24T12:00:00+00:00"),
                     _row("b", a="these disagree", ts="2026-07-24T13:00:00+00:00")])
    seen: list = []

    def _flaky(req, timeout=None):
        seen.append(1)
        if len(seen) == 1:
            raise OSError("connection reset")
        return _FakeHTTPResponse(_canned(verdict="market_divergence"))
    monkeypatch.setattr(ml.urllib.request, "urlopen", _flaky)

    out = ml.classify_contradictions(limit=5, root=tmp_path)
    assert out["ok"] and out["classified"] == 1 and out["skipped"] == 1


def test_classify_prompt_carries_question_answer_and_thinking(tmp_path):
    row = _row("a", q="is NVDA a buy?", a="watch, don't chase",
               thinking=[_think("breadth says yes, credit says no")])
    prompt = ml._classify_prompt(row)
    assert "is NVDA a buy?" in prompt
    assert "watch, don't chase" in prompt
    assert "breadth says yes, credit says no" in prompt
    assert "system_error" in prompt and "market_divergence" in prompt
    assert len(prompt) < ml._CLASSIFY_EXCERPT_CHARS + len(ml._CLASSIFY_INSTRUCTIONS) + 200


def test_classify_prompt_clips_a_huge_trace(tmp_path):
    row = _row("a", thinking=[_think("z" * 20000)])
    prompt = ml._classify_prompt(row)
    assert len(prompt) < ml._CLASSIFY_EXCERPT_CHARS + len(ml._CLASSIFY_INSTRUCTIONS) + 200


# ---------------------------------------------------------------------------
# export() carries the contradiction columns
# ---------------------------------------------------------------------------
def test_export_jsonl_carries_thinking_contra_and_verdict(tmp_path):
    _seed(tmp_path, [_row("a", a="the readings conflict", thinking=[_think("hm")])],
          evals=[{"id": "a", "grade": 3, "contra_verdict": "system_error",
                  "contra_signals": ["breadth", "credit"], "contra_note": "stale"}])
    out = ml.export(fmt="jsonl", root=tmp_path)
    line = json.loads(out["content"].splitlines()[0])
    assert line["thinking"][0]["text"] == "hm"
    assert line["contra"]["hit"] is True
    assert line["eval"]["contra_verdict"] == "system_error"
    assert line["eval"]["grade"] == 3


def test_export_csv_has_the_contradiction_columns(tmp_path):
    _seed(tmp_path, [_row("a", a="the readings conflict", thinking=[_think("hmm")])],
          evals=[{"id": "a", "contra_verdict": "market_divergence"}])
    out = ml.export(fmt="csv", root=tmp_path)
    lines = out["content"].splitlines()
    header = lines[0].split(",")
    for col in ("thinking_chars", "contra_hit", "contra_verdict"):
        assert col in header
    cells = lines[1].split(",")
    assert cells[header.index("thinking_chars")] == "3"
    assert cells[header.index("contra_hit")] == "True"
    assert cells[header.index("contra_verdict")] == "market_divergence"


def test_export_respects_the_contra_filter(tmp_path):
    _seed(tmp_path, [_row("a", a="the readings conflict"), _row("b", a="all clear")])
    assert ml.export(fmt="jsonl", filters={"contra": True}, root=tmp_path)["count"] == 1
