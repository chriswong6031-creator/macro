"""engine/provider_health.py — per-rung waterfall telemetry.

WHY THIS LEDGER EXISTS. On 2026-08-08 the marketing estate's evidence for
"which model wrote tonight" was `data/ai_costs/usage.jsonl`, and that ledger
books a row only on SUCCESS. So a lane whose first three rungs failed every
call recorded a ledger reading 100% DeepSeek and contained no trace that codex,
oauth or anthropic had ever been asked, on a config that pins codex FIRST.
Three very different outages (rung absent on the host / rung refused the call /
rung struck off by an earlier item's 429) produced one indistinguishable
symptom. These tests pin the rows that separate them.
"""
from __future__ import annotations

import json

import pytest

from engine import llm_auth, provider_health as ph


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    """Every test writes to its own file. The real ledger is never touched."""
    path = tmp_path / "provider_health.jsonl"
    monkeypatch.setenv("PROVIDER_HEALTH_PATH", str(path))
    monkeypatch.delenv("PROVIDER_HEALTH_DISABLED", raising=False)
    return path


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ── classify_error: the operator's decision tree, not the SDK's taxonomy ──────

@pytest.mark.parametrize(("message", "expected"), [
    ("429 Codex usage limit reached", "usage_limit"),
    ("quota exceeded for this org", "usage_limit"),
    ("401 Codex authentication failed", "auth"),
    ("403 Forbidden", "auth"),
    ("Codex provider timeout", "timeout"),
    ("Codex provider not installed", "not_installed"),
    ("400 unsupported request feature: inline image input", "unsupported"),
    ("529 overloaded", "transport"),
    ("something nobody has seen before", "error"),
])
def test_every_failure_class_the_waterfall_can_see_is_named(message, expected):
    assert ph.classify_error(RuntimeError(message)) == expected


def test_a_spent_window_is_never_misread_as_a_dead_credential():
    """ORDER IS LOAD-BEARING. The Codex CLI's usage-limit message also carries
    the word 'login' in its remediation sentence, and misreading a spent 5h
    window as a dead credential is what marks a HEALTHY rung dead for the rest
    of the process (llm_auth.mark_dead is process-lifetime)."""
    exc = RuntimeError(
        "429 usage limit reached. To sign in again, run codex login")
    assert ph.classify_error(exc) == "usage_limit"


def test_no_exception_classifies_as_empty():
    assert ph.classify_error(None) == ""


# ── the ledger rows ──────────────────────────────────────────────────────────

def test_an_attempt_row_carries_the_lane_the_rung_and_the_class(_isolated_ledger):
    ph.record_attempt(lane="marketing-copywriter", context="marketing_copy_v2",
                      rung="codex", cap_id="codex_account", model="gpt-5.6-sol",
                      ok=False, latency_ms=1234, error_class="usage_limit",
                      detail="429 Codex usage limit reached")
    row, = _rows(_isolated_ledger)
    assert row["event"] == "attempt"
    assert row["lane"] == "marketing-copywriter"
    assert row["rung"] == "codex"
    assert row["cap_id"] == "codex_account"
    assert row["ok"] is False
    assert row["error_class"] == "usage_limit"
    assert row["latency_ms"] == 1234
    assert row["ts"].endswith("Z")


def test_detail_is_truncated_so_the_ledger_cannot_carry_a_reply(_isolated_ledger):
    ph.record_attempt(lane="l", context="c", rung="codex", ok=False,
                      latency_ms=1, error_class="error", detail="x" * 5000)
    row, = _rows(_isolated_ledger)
    assert len(row["detail"]) <= 200


def test_a_waterfall_row_names_the_rungs_the_host_could_build(_isolated_ledger):
    """THE ROW THAT ANSWERS 'was codex even a candidate'. An absent rung and a
    failing rung need different remedies and used to leave identical evidence."""
    ph.record_waterfall(lane="marketing-copywriter", context="",
                        rungs=[{"name": "codex", "cap_id": "codex_account",
                                "model": "gpt-5.6-sol"},
                               {"name": "deepseek", "model": "deepseek-v4-pro"}])
    row, = _rows(_isolated_ledger)
    assert row["event"] == "waterfall"
    assert row["n_rungs"] == 2
    assert [r["rung"] for r in row["rungs"]] == ["codex", "deepseek"]


def test_an_empty_waterfall_still_writes_a_row(_isolated_ledger):
    """Armed-but-mute is an outage worth a row: 'no rung was built' is a
    different fact from 'nothing was recorded'."""
    ph.record_waterfall(lane="marketing-copywriter", context="", rungs=[])
    row, = _rows(_isolated_ledger)
    assert row["n_rungs"] == 0


def test_the_disable_switch_writes_nothing(_isolated_ledger, monkeypatch):
    monkeypatch.setenv("PROVIDER_HEALTH_DISABLED", "1")
    ph.record_attempt(lane="l", context="c", rung="codex", ok=True, latency_ms=1)
    assert _rows(_isolated_ledger) == []


def test_an_unwritable_path_never_raises(monkeypatch):
    """Telemetry must never be able to cost a model call."""
    monkeypatch.setenv("PROVIDER_HEALTH_PATH", "/dev/null/nope/health.jsonl")
    ph.record_attempt(lane="l", context="c", rung="codex", ok=True, latency_ms=1)
    ph.record_waterfall(lane="l", context="c", rungs=[])
    assert ph.read_rows() == []


def test_summarize_folds_rows_into_a_per_rung_verdict():
    rows = [
        {"event": "attempt", "rung": "codex", "ok": False,
         "error_class": "usage_limit"},
        {"event": "attempt", "rung": "codex", "ok": False,
         "error_class": "usage_limit"},
        {"event": "attempt", "rung": "deepseek", "ok": True},
        {"event": "waterfall", "rung": "ignored"},
        "not a dict",
    ]
    out = ph.summarize_attempts(rows)
    assert out["codex"] == {"ok": 0, "fail": 2, "usage_limit": 2}
    assert out["deepseek"] == {"ok": 1, "fail": 0}
    assert "ignored" not in out


def test_read_rows_can_filter_to_one_lane(_isolated_ledger):
    ph.record_attempt(lane="marketing-copywriter", context="c", rung="codex",
                      ok=True, latency_ms=1)
    ph.record_attempt(lane="hot-tape-wire", context="c", rung="codex",
                      ok=True, latency_ms=1)
    assert len(ph.read_rows()) == 2
    assert len(ph.read_rows(lane="hot-tape-wire")) == 1


# ── the llm_auth integration: make_call is what actually fills the ledger ─────

class _Resp:
    def __init__(self):
        self.usage = None


def _provider(name, fn, *, lane="marketing-copywriter"):
    """A synthetic rung descriptor, deliberately WITHOUT a `cap_id`.

    NO cap_id ON PURPOSE. `make_call` routes a descriptor that carries one into
    the key-pool bookkeeping (`_note_pool_success` on success, `_cool_pool_key`
    on a 429/401), and that writes the repo's REAL
    data/metabolism/key_ledger.jsonl as a call-time side effect. With a
    plausible-looking `cap_id` these tests passed and then failed the session on
    the MM_DATA_GUARD tripwire, which is the correct verdict: a test must never
    write a production ledger. Dropping the key also exercises the `cap_id or
    env_var` fallback in the health row, pinned below.
    """
    return {"name": name, "env_var": f"ENV_{name.upper()}", "cred": "tok",
            "client": object(), "model": f"model-{name}", "usage_lane": lane,
            "_fn": fn}


def test_make_call_records_one_row_per_rung_it_walks(_isolated_ledger):
    """The whole point: the rungs make_call walked PAST are now on the record."""
    llm_auth.clear_dead()
    calls: list[str] = []

    def call_fn(client, model):
        calls.append(model)
        if model == "model-codex":
            raise RuntimeError("429 Codex usage limit reached")
        return "text", None, _Resp()

    attempts: list[dict] = []
    text, reason, served = llm_auth.make_call(
        [_provider("codex", None), _provider("deepseek", None)],
        call_fn, context="marketing_copy_v2", attempts=attempts)

    assert (text, reason, served) == ("text", None, "deepseek")
    assert [(a["rung"], a["ok"], a["error_class"]) for a in attempts] == [
        ("codex", False, "usage_limit"), ("deepseek", True, "")]

    rows = [r for r in _rows(_isolated_ledger) if r["event"] == "attempt"]
    assert [(r["rung"], r["ok"], r["error_class"]) for r in rows] == [
        ("codex", False, "usage_limit"), ("deepseek", True, "")]
    assert all(r["lane"] == "marketing-copywriter" for r in rows)
    # A rung with no pool cap_id still identifies itself: the row falls back to
    # the env-var NAME (never its value, which is a credential).
    assert rows[0]["cap_id"] == "ENV_CODEX"
    llm_auth.clear_dead()


def test_a_rung_skipped_because_it_was_struck_off_is_recorded_as_such(
        _isolated_ledger):
    """`mark_dead` lasts the whole PROCESS, so ONE 429 on item 3 of a 900-item
    nightly removes that rung from items 4..900 — and the only trace used to be
    a debug line. A skip is a rung outcome and it is the one that hid longest."""
    llm_auth.clear_dead()
    llm_auth.mark_dead("codex", "ENV_CODEX", reason="test")

    attempts: list[dict] = []
    llm_auth.make_call(
        [_provider("codex", None), _provider("deepseek", None)],
        lambda client, model: ("text", None, _Resp()),
        context="marketing_copy_v2", attempts=attempts)

    assert attempts[0]["rung"] == "codex"
    assert attempts[0]["skipped"] == "dead"
    assert attempts[0]["ok"] is False
    row = next(r for r in _rows(_isolated_ledger)
               if r["event"] == "attempt" and r["rung"] == "codex")
    assert row["error_class"] == "skipped_dead"
    llm_auth.clear_dead()


def test_the_attempts_out_param_is_optional(_isolated_ledger):
    """Every existing caller unpacks a 3-tuple and passes no `attempts`; the
    keyword must be invisible to them."""
    llm_auth.clear_dead()
    out = llm_auth.make_call(
        [_provider("deepseek", None)],
        lambda client, model: ("text", None, _Resp()),
        context="whatever")
    assert out == ("text", None, "deepseek")
