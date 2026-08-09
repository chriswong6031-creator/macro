"""tests/test_admin_program_watch.py — the seasonality program watch on the admin console.

The artifact is built nightly and its alerts previously reached the operator only
through a GitHub annotation and the raw JSON. This suite pins the admin-side reader:
it never raises, every failure mode is a *stated* one (an unread watch must not look
like a quiet one), and `fired` sorts first.

Two things this suite deliberately does NOT do:

* it does not assert WHICH tripwire is currently on fire in the committed artifact.
  That artifact is rebuilt and committed every night, so a content assertion turns
  red the day the operator does the work the panel exists to prompt — the feature
  succeeding would break CI. The real-artifact test pins the *dialect* instead.
* it does not treat the market `asof` as a build timestamp. `resolve_asof` stamps it
  from site/seasonalitydata/index.json's trading `as_of`, which legitimately sits 2-4
  days behind the wall clock over a weekend; the freshness verdict is tested against
  both clocks and against the calendar-sized thresholds.

Tests
-----
1.  panel happy path / operator prompt exposure
2.  every failure branch is a stated state (absent, bad JSON, schema, size, shape)
3.  ordering: fired → unavailable → unknown → waiting, stable inside a state
4.  counts: recomputed from rows, every row lands in a bucket (incl. "other")
5.  clocks: stale_days (market as-of) vs built_days (file write), offsets honoured
6.  freshness: ok / stale / unknown — a healthy weekend lag never reads as an alarm
7.  the COMMITTED artifact, read for dialect only
8.  server wiring: summary payload key, GET /api/program_watch, and its auth wall
9.  the console source contracts app.js must keep (freshness-driven, no false cause)
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest.mock
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from admin import program_watch  # noqa: E402
from admin.server import Handler  # noqa: E402

APP_JS = REPO_ROOT / "admin" / "static" / "app.js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    return urllib.request.urlopen(req, timeout=10)


def _tripwire(key: str, state: str = "waiting", **over) -> dict:
    row = {
        "key": key,
        "state": state,
        "headline": f"{key} headline",
        "why": f"{key} matters because …",
        "operator_prompt": f"Do the {key} thing. Context: research/DOC.md.",
        "handoff_doc": "research/DOC.md",
        "evidence": {"path": f"data/seasonality/{key}.jsonl", "n": 3},
    }
    row.update(over)
    return row


def _doc(tripwires: list[dict], asof: str = "2026-08-05",
         schema: str = program_watch.WATCH_SCHEMA) -> dict:
    counts = {"fired": 0, "waiting": 0, "unavailable": 0}
    for t in tripwires:
        state = t.get("state")
        if isinstance(state, str) and state in counts:
            counts[state] += 1
    return {"asof": asof, "schema": schema, "counts": counts, "tripwires": tripwires}


def _write(tmp_path: Path, payload, name: str = "program_watch.json") -> Path:
    p = tmp_path / name
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return p


def _panel_at(path: Path) -> dict:
    with unittest.mock.patch("admin.program_watch._watch_path", return_value=path):
        return program_watch.panel()


def _age_file(path: Path, days: float) -> None:
    """Backdate the artifact's mtime — the reader's only producer-run proxy."""
    when = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    os.utime(path, (when, when))


def _days_ago(days: float, fmt: str = "%Y-%m-%d") -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime(fmt)


# ---------------------------------------------------------------------------
# 1: happy path
# ---------------------------------------------------------------------------

def test_panel_happy_path(tmp_path):
    p = _write(tmp_path, _doc([_tripwire("alpha", "fired"), _tripwire("beta")]))
    r = _panel_at(p)
    assert r["available"] is True
    assert r["note"] is None
    assert r["asof"] == "2026-08-05"
    assert [t["key"] for t in r["tripwires"]] == ["alpha", "beta"]
    assert r["counts"] == {"fired": 1, "waiting": 1, "unavailable": 0, "other": 0}
    first = r["tripwires"][0]
    for field in ("key", "state", "headline", "why", "operator_prompt", "handoff_doc", "evidence"):
        assert field in first, field
    assert first["evidence"]["n"] == 3
    assert r["truncated"] is False


def test_panel_exposes_operator_prompt(tmp_path):
    """The whole feature: the operator copies this and pastes it into a new session.

    Shown verbatim because this is the operator surface — module names, PRs and
    research/ docs are its vocabulary. NOT a secrecy claim: the artifact is committed
    to a public repo, so nothing genuinely private may be put in it.
    """
    p = _write(tmp_path, _doc([_tripwire("alpha", "fired")]))
    r = _panel_at(p)
    row = r["tripwires"][0]
    assert row["operator_prompt"] == "Do the alpha thing. Context: research/DOC.md."
    assert row["handoff_doc"] == "research/DOC.md"


# ---------------------------------------------------------------------------
# 2: every failure is a STATED state, never an empty "all clear"
# ---------------------------------------------------------------------------

def test_panel_absent(tmp_path):
    r = _panel_at(tmp_path / "nope.json")
    assert r["available"] is False
    assert r["tripwires"] == []
    assert r["counts"] == {"fired": 0, "waiting": 0, "unavailable": 0, "other": 0}
    assert r["note"] and "nightly" in r["note"]
    assert "build_program_watch.py" in r["note"]
    # the unavailable payload carries the same shape the renderer reads, and its
    # freshness is "unknown" — never an implicit ok
    assert r["freshness"]["level"] == "unknown"
    assert r["freshness"]["note"] == r["note"]


def test_panel_bad_json(tmp_path):
    p = _write(tmp_path, "{not valid json")
    r = _panel_at(p)
    assert r["available"] is False
    assert r["tripwires"] == []
    # names the failure mode rather than rendering a silent empty panel
    assert "JSON" in r["note"]
    assert "not an all-clear" in r["note"].lower()


def test_panel_wrong_schema(tmp_path):
    p = _write(tmp_path, _doc([_tripwire("alpha", "fired")],
                              schema="seasonality.program_watch.v9"))
    r = _panel_at(p)
    assert r["available"] is False
    assert r["tripwires"] == []          # refuses rather than rendering fields it may misread
    assert "seasonality.program_watch.v9" in r["note"]
    assert program_watch.WATCH_SCHEMA in r["note"]


def test_panel_oversized(tmp_path):
    """A file over the byte cap is refused BY SIZE — not parsed and not rendered.

    The padding keeps the file valid JSON, so a pass here cannot come from the
    parse branch firing instead of the size guard.
    """
    doc = _doc([_tripwire("alpha", "fired")])
    doc["padding"] = "x" * (program_watch._MAX_BYTES + 1000)
    p = _write(tmp_path, doc)
    assert p.stat().st_size > program_watch._MAX_BYTES
    assert json.loads(p.read_text()) is not None   # still parseable — the size gate is what fires
    r = _panel_at(p)
    assert r["available"] is False
    assert r["tripwires"] == []
    assert "bytes" in r["note"]
    assert f"{p.stat().st_size:,}" in r["note"]


def test_panel_not_an_object(tmp_path):
    p = _write(tmp_path, [1, 2, 3])
    r = _panel_at(p)
    assert r["available"] is False
    assert "top level" in r["note"]


def test_panel_missing_tripwire_list(tmp_path):
    p = _write(tmp_path, {"asof": "2026-08-05", "schema": program_watch.WATCH_SCHEMA})
    r = _panel_at(p)
    assert r["available"] is False
    assert "tripwire" in r["note"]


# ---------------------------------------------------------------------------
# 3: ordering is load-bearing
# ---------------------------------------------------------------------------

def test_panel_fired_first_ordering(tmp_path):
    """fired → unavailable → waiting, and the artifact's own order holds inside a state.

    The operator must not scroll past quiet rows to reach the one that needs them.
    """
    rows = [
        _tripwire("w1", "waiting"),
        _tripwire("u1", "unavailable"),
        _tripwire("w2", "waiting"),
        _tripwire("f1", "fired"),
        _tripwire("w3", "waiting"),
        _tripwire("f2", "fired"),
    ]
    r = _panel_at(_write(tmp_path, _doc(rows)))
    assert [t["key"] for t in r["tripwires"]] == ["f1", "f2", "u1", "w1", "w2", "w3"]


def test_unknown_state_outranks_waiting_and_is_counted(tmp_path):
    """A state this console does not know is NEWS: shown, counted, above the quiet rows.

    The producer can add a state (`escalated`, `overdue`) without touching the schema
    string, so a reader that files it behind `waiting` and counts it nowhere prints
    "0 fired · 0 no-read · 0 waiting" above a row headlined "needs you now".
    """
    rows = [_tripwire("w1", "waiting"), _tripwire("x1", "escalated"),
            _tripwire("f1", "fired"), _tripwire("weird", ["fired"])]
    r = _panel_at(_write(tmp_path, _doc(rows)))
    assert [t["key"] for t in r["tripwires"]] == ["f1", "x1", "weird", "w1"]
    assert r["counts"] == {"fired": 1, "waiting": 1, "unavailable": 0, "other": 2}
    # every row lands in a bucket — the header can never read all-quiet above a row
    assert sum(r["counts"].values()) == len(r["tripwires"])


def test_panel_counts_all_states(tmp_path):
    """Counts are recomputed from the rows shown, not copied from the artifact's claim."""
    rows = [_tripwire("f1", "fired"), _tripwire("u1", "unavailable"),
            _tripwire("w1", "waiting"), _tripwire("w2", "waiting")]
    doc = _doc(rows)
    doc["counts"] = {"fired": 99, "waiting": 0, "unavailable": 0}   # a lying artifact
    r = _panel_at(_write(tmp_path, doc))
    assert r["counts"] == {"fired": 1, "waiting": 2, "unavailable": 1, "other": 0}


def test_panel_truncates_oversized_list(tmp_path):
    n = program_watch._MAX_TRIPWIRES + 5
    rows = [_tripwire(f"w{i}", "waiting") for i in range(n)]
    r = _panel_at(_write(tmp_path, _doc(rows)))
    assert len(r["tripwires"]) == program_watch._MAX_TRIPWIRES
    assert r["truncated"] is True
    assert r["counts"]["waiting"] == n    # the count is of ALL rows, not the shown slice


# ---------------------------------------------------------------------------
# 5: the two clocks
# ---------------------------------------------------------------------------

def test_panel_stale_days_is_the_market_asof_age(tmp_path):
    old = _days_ago(5)
    r = _panel_at(_write(tmp_path, _doc([_tripwire("a", "fired")], asof=old)))
    assert r["available"] is True
    assert r["stale_days"] == pytest.approx(5.0, abs=1.5)

    fresh = _days_ago(0)
    r2 = _panel_at(_write(tmp_path, _doc([_tripwire("a", "fired")], asof=fresh), name="b.json"))
    assert 0 <= r2["stale_days"] < 1.5


def test_panel_built_days_is_the_file_write_age(tmp_path):
    """built_days ages the FILE, not the market as-of — the only producer-run proxy.

    The two must not be confused: a freshly written artifact whose as-of is Friday's
    trading date is healthy, and a panel that reads the as-of as a build stamp calls
    that a stopped nightly.
    """
    p = _write(tmp_path, _doc([_tripwire("a", "fired")], asof=_days_ago(3)))
    r = _panel_at(p)
    assert r["built_days"] == pytest.approx(0.0, abs=0.01)
    assert r["built_at"] and r["built_at"].startswith(_days_ago(0))
    assert r["stale_days"] == pytest.approx(3.0, abs=1.5)

    _age_file(p, 9)
    r2 = _panel_at(p)
    assert r2["built_days"] == pytest.approx(9.0, abs=0.05)


def test_panel_stale_days_unparseable(tmp_path):
    r = _panel_at(_write(tmp_path, _doc([_tripwire("a", "fired")], asof="last tuesday")))
    assert r["available"] is True          # an unreadable date does not sink the panel
    assert r["stale_days"] is None
    assert r["asof"] == "last tuesday"


@pytest.mark.parametrize("stamp,expected", [
    ("%Y-%m-%dT%H:%M:%SZ", 3.0),
    ("%Y-%m-%dT%H:%M:%S+00:00", 3.0),
    ("%Y-%m-%d %H:%M:%S", 3.0),
    ("%Y-%m-%d", 3.0),
])
def test_age_honours_iso_dialects(stamp, expected):
    ts = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(stamp)
    assert program_watch._age_days(ts) == pytest.approx(expected, abs=1.05)


def test_age_does_not_discard_a_utc_offset():
    """An offset-bearing stamp used to be sliced away and read as UTC — up to 14h wrong."""
    dt = datetime.now(timezone(timedelta(hours=-4))) - timedelta(days=3)
    got = program_watch._age_days(dt.strftime("%Y-%m-%dT%H:%M:%S-04:00"))
    assert got == pytest.approx(3.0, abs=0.01)


@pytest.mark.parametrize("bad", [None, "", 12345, True, {"a": 1}, [1], "not a date"])
def test_age_returns_none_for_junk(bad):
    assert program_watch._age_days(bad) is None


# ---------------------------------------------------------------------------
# 6: freshness — an alarm that is lit on ordinary Tuesdays is an alarm nobody reads
# ---------------------------------------------------------------------------

def test_a_weekend_lagged_asof_on_a_freshly_written_file_is_not_an_alarm(tmp_path):
    """The false alarm this panel shipped with: as_of is a TRADING date.

    Friday's as_of read on Monday is ~3 days behind on a nightly that ran hours ago.
    That must render ok, or the operator learns to ignore the one banner meant to be
    believed.
    """
    p = _write(tmp_path, _doc([_tripwire("a", "fired")], asof=_days_ago(3)))
    r = _panel_at(p)
    assert r["freshness"]["level"] == "ok"
    assert r["freshness"]["note"] is None


def test_an_asof_further_behind_than_the_calendar_explains_is_stale(tmp_path):
    p = _write(tmp_path, _doc([_tripwire("a", "fired")],
                              asof=_days_ago(program_watch._ASOF_LAG_DAYS + 3)))
    r = _panel_at(p)
    assert r["freshness"]["level"] == "stale"
    note = r["freshness"]["note"]
    assert "behind" in note
    # states what was observed; never diagnoses a cause it cannot see
    assert "has probably stopped" not in note
    assert "weekend" in note or "holiday" in note


def test_an_unwritten_artifact_file_is_stale_even_with_a_fresh_asof(tmp_path):
    p = _write(tmp_path, _doc([_tripwire("a", "fired")], asof=_days_ago(0)))
    _age_file(p, program_watch._BUILD_STALE_DAYS + 2)
    r = _panel_at(p)
    assert r["freshness"]["level"] == "stale"
    assert "rewritten" in r["freshness"]["note"]
    assert "build_program_watch.py" in r["freshness"]["note"]


def test_an_unreadable_asof_states_that_freshness_is_unknown(tmp_path):
    """Not silence. `stale_days is None` used to render exactly like a fresh watch."""
    r = _panel_at(_write(tmp_path, _doc([_tripwire("a", "fired")], asof=None)))
    assert r["available"] is True
    assert r["stale_days"] is None
    assert r["freshness"]["level"] == "unknown"
    assert "unknown, not fresh" in r["freshness"]["note"]


def test_a_future_dated_asof_is_not_laundered_into_extra_fresh(tmp_path):
    future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
    r = _panel_at(_write(tmp_path, _doc([_tripwire("a", "fired")], asof=future)))
    assert r["stale_days"] < 0
    assert r["freshness"]["level"] == "unknown"
    assert "future" in r["freshness"]["note"]


# ---------------------------------------------------------------------------
# never raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    None,                                   # absent file
    "{not valid json",
    "",
    "null",
    '"a bare string"',
    "[1,2,3]",
    '{"schema": "wrong.v1"}',
    '{"schema": "seasonality.program_watch.v1"}',
    '{"schema": "seasonality.program_watch.v1", "tripwires": "not a list"}',
    '{"schema": "seasonality.program_watch.v1", "tripwires": [1, "two", null]}',
    '{"schema": "seasonality.program_watch.v1", "tripwires": [{}], "asof": 12345}',
    '{"schema": "seasonality.program_watch.v1", "tripwires": [{"state": {"a": 1}}]}',
    '{"schema": "seasonality.program_watch.v1", "tripwires": [{"state": "escalated"}],'
    ' "asof": "2026-13-45"}',
])
def test_panel_never_raises(tmp_path, payload):
    """key_alerts.panel's discipline: every failure mode is a returned state."""
    if payload is None:
        r = _panel_at(tmp_path / "absent.json")
    else:
        r = _panel_at(_write(tmp_path, payload))
    assert isinstance(r, dict)
    assert set(r) >= {"available", "note", "asof", "stale_days", "built_at", "built_days",
                      "freshness", "counts", "tripwires"}
    assert isinstance(r["tripwires"], list)
    assert isinstance(r["counts"], dict)
    assert r["freshness"]["level"] in {"ok", "unknown", "stale"}
    assert sum(r["counts"].values()) == len(r["tripwires"])
    if not r["available"]:
        assert r["note"], "an unavailable panel must always say WHY"


def test_panel_survives_a_broken_path_resolve():
    with unittest.mock.patch("admin.program_watch._watch_path",
                             side_effect=RuntimeError("no data root")):
        r = program_watch.panel()
    assert r["available"] is False
    assert "no data root" in r["note"]


# ---------------------------------------------------------------------------
# 7: the REAL committed artifact — DIALECT only, never its current contents
# ---------------------------------------------------------------------------

def test_real_artifact_reads_in_this_consoles_dialect():
    """Against the committed data/seasonality/program_watch.json, not a fixture.

    A synthetic-only suite would pass while the reader misread the real dialect. What
    is asserted is everything the renderer depends on — schema accepted, rows present,
    every row a known-or-counted state, fired block contiguous and first, the copy
    button's payload present. What is NOT asserted is WHICH tripwire is fired: that
    artifact is rebuilt nightly, so pinning its content makes the panel's own success
    (the operator clearing the follow-ups) turn main red.
    """
    data_root = REPO_ROOT / "data"
    real = data_root / "seasonality" / "program_watch.json"
    if not real.exists():
        # A skip only for a checkout with no data/ tree at all. If data/ IS here and
        # the artifact is not, that is a producer failure, not a reason to pass.
        if data_root.exists():
            pytest.fail("data/ is present but data/seasonality/program_watch.json is not — "
                        "scripts/build_program_watch.py did not write/commit its artifact")
        pytest.skip("checkout carries no data/ tree")
    r = _panel_at(real)
    assert r["available"] is True, r["note"]
    assert r["tripwires"], "the committed artifact carries tripwires"
    assert sum(r["counts"].values()) == len(r["tripwires"])
    assert r["counts"]["other"] == 0, (
        "the committed artifact uses a tripwire state this console does not know: "
        f"{sorted({t['state'] for t in r['tripwires']})}")
    assert r["stale_days"] is not None, f"unreadable asof in the real artifact: {r['asof']!r}"
    for t in r["tripwires"]:
        assert t["key"] and isinstance(t["key"], str)
        assert t["headline"], f"{t['key']} carries no headline"
        assert t["operator_prompt"], f"{t['key']} carries no operator_prompt to copy"
    # the fired block, whatever is in it, is contiguous and first
    seen_non_fired = False
    for t in r["tripwires"]:
        if t["state"] != "fired":
            seen_non_fired = True
        else:
            assert not seen_non_fired, "a fired tripwire sorted after a quiet one"


# ---------------------------------------------------------------------------
# 8: server wiring + the auth wall
# ---------------------------------------------------------------------------

def test_summary_payload_carries_program_watch():
    """app.js reads s.program_watch on the landing — the payload must carry it."""
    from admin import server
    payload = server._summary_payload()
    assert "program_watch" in payload
    assert isinstance(payload["program_watch"], dict)


def test_http_get_program_watch(tmp_path):
    p = _write(tmp_path, _doc([_tripwire("alpha", "fired"), _tripwire("beta")]))
    httpd, port = _server()
    try:
        with unittest.mock.patch("admin.program_watch._watch_path", return_value=p):
            data = json.loads(_get(port, "/api/program_watch?force=1").read())
        assert data["available"] is True
        assert [t["key"] for t in data["tripwires"]] == ["alpha", "beta"]
        assert data["tripwires"][0]["operator_prompt"]
        assert data["freshness"]["level"] in {"ok", "unknown", "stale"}
    finally:
        httpd.shutdown(); httpd.server_close()


def test_http_get_program_watch_absent(tmp_path):
    httpd, port = _server()
    try:
        with unittest.mock.patch("admin.program_watch._watch_path",
                                 return_value=tmp_path / "missing.json"):
            data = json.loads(_get(port, "/api/program_watch?force=1").read())
        assert data["available"] is False
        assert data["note"]
        assert data["tripwires"] == []
    finally:
        httpd.shutdown(); httpd.server_close()


def test_program_watch_route_refuses_an_unauthenticated_read(monkeypatch, tmp_path):
    """RUL-8 is the module's stated law; nothing pinned it until now.

    The route sits below do_GET's session gate today. A refactor that hoisted it above
    that gate would have shipped green — this test is what sees it.
    """
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password")
    from admin import settings
    assert settings.auth_enabled() is True
    httpd, port = _server()
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(port, "/api/program_watch")
        assert excinfo.value.code == 401
        assert json.loads(excinfo.value.read())["error"] == "authentication required"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_program_watch_route_is_registered_below_the_auth_gate():
    """Source-level twin of the test above: ordering inside do_GET is the auth."""
    src = (REPO_ROOT / "admin" / "server.py").read_text(encoding="utf-8")
    body = src.split("def do_GET", 1)[1]
    assert body.index('"authentication required"') < body.index('"/api/program_watch"')
    assert "/api/program_watch" not in str(Handler._PUBLIC_GET)


# ---------------------------------------------------------------------------
# 9: the console-side contracts (app.js is not importable; its source is the pin)
# ---------------------------------------------------------------------------

def test_app_js_renders_the_panel_from_the_servers_freshness_verdict():
    src = APP_JS.read_text(encoding="utf-8")
    assert "renderProgramWatch(s.program_watch)" in src
    assert "wireProgramWatch(s.program_watch)" in src
    assert "pw.freshness" in src, "the panel must read the server's verdict, not re-derive it"
    # the false-cause copy this panel shipped with, and the client-side threshold that
    # aged a TRADING date against the wall clock — both gone for good
    assert "The nightly that refreshes it has probably stopped" not in src
    assert "PW_STALE_DAYS" not in src
    # both clocks are printed, so the operator can see which one is behind
    assert "pw.built_days" in src and "pw.stale_days" in src


def test_app_js_never_resolves_a_producer_state_off_object_prototype():
    src = APP_JS.read_text(encoding="utf-8")
    assert "Object.prototype.hasOwnProperty.call(map, k)" in src
    assert "pwOwn(PW_PILL, st" in src and "pwOwn(PW_LABEL, st" in src


def test_app_js_copy_button_carries_the_nested_open_prompts():
    """The fired tripwire's instruction lives in evidence[*].prompt.

    A copy that drops it sends the operator to the JSON this panel replaces.
    """
    src = APP_JS.read_text(encoding="utf-8")
    assert "function pwOpenItems(" in src
    assert "pwOpenItems(it.evidence)" in src
    assert "Context doc:" in src and "Source: data/seasonality/program_watch.json" in src


def test_app_js_states_the_missing_key_case_instead_of_vanishing():
    src = APP_JS.read_text(encoding="utf-8")
    block = src.split("function renderProgramWatch(", 1)[1].split("\nfunction wireProgramWatch", 1)[0]
    assert "did not send it" in block
    assert "return \"\"" not in block, "a silently empty panel is the failure this rail exists to prevent"


def test_app_js_recheck_button_bypasses_both_caches():
    src = APP_JS.read_text(encoding="utf-8")
    assert 'api("/api/program_watch?force=1")' in src
    assert 'id="pwRecheck"' in src
