"""Tests for engine/neuralweb/brain_market_intel.py — the Mastermind retrieval pair.

All offline: stdlib only, no network, no LLM, no API key, no gateway import.

TWO DELIBERATE ISOLATIONS, both guarding documented house traps:

  1. THE CLOCK IS FROZEN AND THREADED. Every fixture timestamp is derived from
     `NOW` and passed to the function under test as `now=NOW`. Fixtures with
     hard-coded ISO dates aged against the wall clock have detonated twice here
     as scheduled CI reds (see scripts/marketing_fastlane_daemon._merge_wires_window
     and tests/test_marketing_press_copy.py); a relative-to-NOW fixture cannot.

  2. THE HOST RUNG OF THE PATH LADDER IS NEUTRALISED. /var/lib/macro-live/public/live
     genuinely exists on the VPS and may exist on a self-hosted runner, so a test
     that let the ladder fall through to it would read PRODUCTION wires and pass
     or fail depending on which machine ran it. The autouse fixture repoints that
     constant at a nonexistent path and clears MACRO_LIVE_DIR, so every test pins
     repo-relative behaviour only.

Coverage:
   1-8   live wire: salience/recency ordering, window filter, limit clamp, symbol
         preference + backfill, ticker-list matching, word boundaries, zh passthrough,
         unparseable ts skipped
   9-10  path ladder: MACRO_LIVE_DIR wins; fallback used when the live dir is empty
  11-14  merge: nightly top-up, cross-source dedupe, notes, `rejected` never served
  15-16  TI-R5 OUTPUT WHITELIST — the epistemics law, pinned mechanically
  17-25  research search: scoring, recency decay, top_pick, truncation, short query,
         corrupt/missing catalog, real-catalog smoke
  26-27  tool schemas
  28-35  W2 ranked-wire sidecar: ladder, freshness gate, permutation, unknown ids,
         nightly pool untouched, output whitelist unchanged, never written
  36-46  W2 street clusters: convergence admission, one-house exclusion, dead
         fields ignored, determinism, ambient words, honest empty, real catalog
  47-62  W4 full-report escalation (mode='report'): the three content layers, the
         12k exposure cap + its marker, the rights note, the excerpt-only
         fallback charging NOTHING, one debit per served body, the per-user ip
         bucket proved against the REAL limiter, every honest error (pro_required
         / report_not_found / vault_unavailable / view_limit_reached), and the
         proof that search and clusters still touch neither corpus nor ledger
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_market_intel as bmi  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The one instant this whole module lives at.
NOW = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_ladder(monkeypatch):
    """Make BOTH path ladders host-independent (see this module's docstring).

    The ranked-wire sidecar (W2) adds a second ladder on the STATE dir, which is
    just as real on a deployed host as the public live dir — an unneutralised
    /var/lib/macro-live/state/wire_rank.json would silently reorder the wire pool
    in every ordering test on that machine and nowhere else.
    """
    monkeypatch.delenv("MACRO_LIVE_DIR", raising=False)
    monkeypatch.setattr(bmi, "_VPS_LIVE_DIR", "/nonexistent/macro-live/public/live")
    monkeypatch.delenv("MACRO_LIVE_STATE_DIR", raising=False)
    monkeypatch.setattr(bmi, "_VPS_STATE_DIR", "/nonexistent/macro-live/state")


# --------------------------------------------------------------------------- #
# Fixture builders — every timestamp is relative to NOW
# --------------------------------------------------------------------------- #
def _ago(hours: float) -> str:
    """ISO stamp `hours` before NOW, in the wire's "…Z" form."""
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_ago(days: float) -> str:
    """ISO stamp `days` before NOW (research vault's published_at form)."""
    return (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wire(iid: str, headline: str, hours_ago: float = 1.0, **over) -> dict:
    """One wires.v1 rail item, shaped like engine/marketing/press_lane._build_rail_item."""
    item = {
        "id": iid,
        "ts": _ago(hours_ago),
        "class": "policy",
        "label_en": "Washington",
        "label_zh": "政策",
        "register": "markets",
        "en": headline,
        "attribution": "",
        "corroboration": "reports",
    }
    item.update(over)
    return item


def _write_wires(directory: pathlib.Path, items: list[dict], *, bare_list: bool = False) -> None:
    """Publish a wires.json payload into `directory` (dict form, or a bare list)."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = items if bare_list else {
        "schema": "wires.v1",
        "updated_at": _ago(0),
        "items": items,
    }
    (directory / "wires.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_nightly(
    root: pathlib.Path,
    *,
    headlines: list[dict] | None = None,
    market: list[dict] | None = None,
    rejected: list[dict] | None = None,
    by_ticker: dict | None = None,
) -> None:
    """Write site/news/macro.json + site/news/financial.json in their real shapes."""
    news = root / "site" / "news"
    news.mkdir(parents=True, exist_ok=True)
    (news / "macro.json").write_text(json.dumps({
        "schema": "macro_news.v1",
        "fetched_at": _ago(0),
        "headlines": headlines or [],
        "rejected": rejected or [],
    }), encoding="utf-8")
    (news / "financial.json").write_text(json.dumps({
        "schema": "financial_news.v1",
        "fetched_at": _ago(0),
        "market": market or [],
        "by_ticker": by_ticker or {},
    }), encoding="utf-8")


def _nightly_item(title: str, hours_ago: float = 1.0, **over) -> dict:
    """One site/news item (macro `headlines` / financial `market` shape)."""
    item = {
        "title": title,
        "url": "https://example.com/x",
        "domain": "example.com",
        "seendate": _ago(hours_ago),
        "importance_score": 70,
        "tickers": [],
    }
    item.update(over)
    return item


def _events(root, **kw) -> list[dict]:
    """get_market_events at the frozen clock, returning just the event list."""
    return bmi.get_market_events(root, now=NOW, **kw)["events"]


# --------------------------------------------------------------------------- #
# 1-8  Live wire behaviour
# --------------------------------------------------------------------------- #
def test_wire_orders_by_salience_then_recency(tmp_path):
    """Salience desc first; among equal (or absent) salience, newest first."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("a", "Middling item", hours_ago=1, salience=50),
        _wire("b", "Top item", hours_ago=5, salience=90),
        _wire("c", "Second item", hours_ago=3, salience=70),
    ])
    assert [e["headline"] for e in _events(tmp_path)] == [
        "Top item", "Second item", "Middling item",
    ]


def test_unscored_wire_items_rank_by_recency_after_scored_ones(tmp_path):
    """The published rail carries NO `salience` (it lives on the daemon's scored
    item), so this is the ordinary production path: rank by ts, and never invent
    a score — the emitted salience stays None."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("a", "Older unscored", hours_ago=4),
        _wire("b", "Newer unscored", hours_ago=1),
        _wire("c", "Scored", hours_ago=9, salience=10),
    ])
    events = _events(tmp_path)
    assert [e["headline"] for e in events] == ["Scored", "Newer unscored", "Older unscored"]
    assert events[1]["salience"] is None and events[2]["salience"] is None


def test_window_filters_out_stale_wire_items(tmp_path):
    """An item older than window_h is dropped, not shown as current."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("fresh", "Two hours old", hours_ago=2),
        _wire("stale", "Thirty hours old", hours_ago=30),
    ])
    assert [e["headline"] for e in _events(tmp_path, window_h=12)] == ["Two hours old"]
    # Widening the window admits it — the filter is the window, not a hidden cap.
    assert len(_events(tmp_path, window_h=48)) == 2


def test_limit_is_clamped_to_the_documented_bounds(tmp_path):
    """1..10, and unusable input falls back to the default rather than raising."""
    _write_wires(tmp_path / "site" / "live", [
        _wire(f"i{n}", f"Item {n}", hours_ago=1 + n * 0.1) for n in range(12)
    ])
    assert len(_events(tmp_path, limit=3)) == 3
    assert len(_events(tmp_path, limit=99)) == 10      # capped at 10
    assert len(_events(tmp_path, limit=0)) == 1        # floored at 1
    assert len(_events(tmp_path, limit="nonsense")) == 5   # default


def test_window_h_is_clamped_too(tmp_path):
    """window_h outside 1..48 clamps; the returned window_h reports what was USED."""
    _write_wires(tmp_path / "site" / "live", [_wire("a", "Item", hours_ago=1)])
    assert bmi.get_market_events(tmp_path, window_h=500, now=NOW)["window_h"] == 48.0
    assert bmi.get_market_events(tmp_path, window_h=0.1, now=NOW)["window_h"] == 1.0
    assert bmi.get_market_events(tmp_path, window_h=None, now=NOW)["window_h"] == 12.0


def test_symbol_prefers_matching_items_then_backfills(tmp_path):
    """A symbol reorders — it never truncates to nothing. A quiet ticker still
    returns the broad tape, which is the honest answer to 'what about NVDA'."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("g1", "General macro item one", hours_ago=1, salience=95),
        _wire("g2", "General macro item two", hours_ago=2, salience=94),
        _wire("m1", "NVDA lifts its outlook", hours_ago=6, salience=10),
        _wire("g3", "General macro item three", hours_ago=3, salience=93),
    ])
    events = _events(tmp_path, limit=3, symbol="NVDA")
    assert events[0]["headline"] == "NVDA lifts its outlook", "match leads despite low salience"
    assert len(events) == 3, "general items backfill to the limit"
    assert [e["headline"] for e in events[1:]] == [
        "General macro item one", "General macro item two",
    ]


def test_symbol_matches_the_ticker_list_not_only_the_text(tmp_path):
    """The brief's contract is text OR tickers; the ticker list is the only signal
    when the headline names the company but not the symbol."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("g", "Broad tape moves", hours_ago=1, salience=99),
        _wire("m", "Apple ships a new laptop", hours_ago=8, salience=1, tickers=["AAPL"]),
    ])
    assert _events(tmp_path, limit=2, symbol="AAPL")[0]["headline"] == "Apple ships a new laptop"


@pytest.mark.parametrize(
    "symbol, decoy, real",
    [
        ("BA", "BABA earnings beat", "BA wins a defense contract"),
        ("C", "CPI prints hot", "C reports earnings"),
    ],
)
def test_symbol_matching_respects_word_boundaries(tmp_path, symbol, decoy, real):
    """'BA' must not hit 'BABA' and 'C' must not hit 'CPI' — a substring match
    would silently mis-attribute every headline to a short ticker.

    The decoy is the NEWER item, so it would lead on recency alone; the genuine
    match must still be promoted past it. That ordering is what makes this test
    bite — asserting 'order unchanged' would pass even if both items matched.
    """
    _write_wires(tmp_path / "site" / "live", [
        _wire("decoy", decoy, hours_ago=1),
        _wire("real", real, hours_ago=5),
    ])
    events = _events(tmp_path, symbol=symbol)
    assert [e["headline"] for e in events] == [real, decoy], (
        f"{symbol!r} matched the decoy {decoy!r} as a substring"
    )


def test_zh_passes_through_and_is_absent_when_untranslated(tmp_path):
    """An untranslated item must NOT carry headline_zh — the rail's own honest
    disclosure rule (英文原文), never English passed off as translated."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("t", "Fed holds rates steady", hours_ago=1, salience=90, zh="美联储维持利率不变"),
        _wire("u", "Dollar slips", hours_ago=2, salience=80),
    ])
    translated, plain = _events(tmp_path)
    assert translated["headline_zh"] == "美联储维持利率不变"
    assert "headline_zh" not in plain


def test_unparseable_ts_is_skipped(tmp_path):
    """An event with no trustworthy timestamp cannot be placed in a freshness
    window, and guessing one would be inventing a fact."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("ok", "Parseable", hours_ago=1),
        _wire("bad", "Garbage stamp", ts="not-a-date"),
        _wire("empty", "Blank stamp", ts=""),
        _wire("none", "Null stamp", ts=None),
    ])
    assert [e["headline"] for e in _events(tmp_path)] == ["Parseable"]


def test_a_bare_top_level_list_payload_is_accepted(tmp_path):
    """Defensive shape handling: dev/ad-hoc files are sometimes a bare list."""
    _write_wires(tmp_path / "site" / "live", [_wire("a", "Bare list item")], bare_list=True)
    assert [e["headline"] for e in _events(tmp_path)] == ["Bare list item"]


# --------------------------------------------------------------------------- #
# 9-10  Path ladder
# --------------------------------------------------------------------------- #
def test_env_macro_live_dir_wins_over_repo_paths(tmp_path, monkeypatch):
    """MACRO_LIVE_DIR is the top rung: the deployed host's live dir must beat a
    stale repo copy, matching scripts/notify_turn_events.py:93."""
    live = tmp_path / "hostlive"
    _write_wires(live, [_wire("env", "From the env dir")])
    _write_wires(tmp_path / "site" / "live", [_wire("repo", "From site/live")])
    monkeypatch.setenv("MACRO_LIVE_DIR", str(live))

    assert bmi._resolve_wires_path(tmp_path) == live / "wires.json"
    assert [e["headline"] for e in _events(tmp_path)] == ["From the env dir"]


def test_fallback_file_is_used_when_the_live_dir_is_empty(tmp_path, monkeypatch):
    """A present-but-EMPTY live dir must fall through, not blank the read.

    This is where a reader must diverge from the daemon's writer ladder
    (_wires_sink_target picks the first candidate whose PARENT exists): on a dev
    box the live dir exists and is empty while the gitignored dev sink under
    data/marketing/press/ holds the real window.
    """
    empty_live = tmp_path / "hostlive"
    empty_live.mkdir(parents=True)
    monkeypatch.setenv("MACRO_LIVE_DIR", str(empty_live))
    _write_wires(tmp_path / "data" / "marketing" / "press", [_wire("dev", "From the dev sink")])

    assert bmi._resolve_wires_path(tmp_path) == tmp_path / "data/marketing/press/wires.json"
    assert [e["headline"] for e in _events(tmp_path)] == ["From the dev sink"]


def test_site_live_outranks_the_dev_sink(tmp_path):
    """Ladder order between the two repo-relative rungs."""
    _write_wires(tmp_path / "site" / "live", [_wire("s", "From site/live")])
    _write_wires(tmp_path / "data" / "marketing" / "press", [_wire("d", "From the dev sink")])
    assert [e["headline"] for e in _events(tmp_path)] == ["From site/live"]


def test_no_wire_anywhere_resolves_to_none_and_never_raises(tmp_path):
    assert bmi._resolve_wires_path(tmp_path) is None
    result = bmi.get_market_events(tmp_path, now=NOW)
    assert result["events"] == [] and result["note"] == "no fresh events in window"


def test_corrupt_wire_json_degrades_to_the_nightly(tmp_path):
    """Corrupt live artifact must not take the turn down — it falls to the digest."""
    live = tmp_path / "site" / "live"
    live.mkdir(parents=True)
    (live / "wires.json").write_text("{not json", encoding="utf-8")
    _write_nightly(tmp_path, headlines=[_nightly_item("Nightly still works")])

    result = bmi.get_market_events(tmp_path, now=NOW)
    assert [e["headline"] for e in result["events"]] == ["Nightly still works"]
    assert result["note"] == "nightly digest only"


# --------------------------------------------------------------------------- #
# 11-14  Merge, dedupe, notes
# --------------------------------------------------------------------------- #
def test_nightly_tops_up_a_thin_wire(tmp_path):
    """Ordering is SOURCE-MAJOR: the wire's items first, then the top-up. The two
    pools are never sorted against each other — press salience and the news
    desk's importance score share a 0..100 range and nothing else."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("w1", "Wire item one", hours_ago=4, salience=20),
        _wire("w2", "Wire item two", hours_ago=5, salience=10),
    ])
    _write_nightly(
        tmp_path,
        headlines=[_nightly_item("Macro digest item", hours_ago=1, importance_score=99)],
        market=[_nightly_item("Financial digest item", hours_ago=2, quality=100)],
    )
    events = _events(tmp_path, limit=5)
    assert [e["source_kind"] for e in events] == [
        "live_wire", "live_wire", "nightly", "nightly",
    ]
    assert [e["headline"] for e in events[:2]] == ["Wire item one", "Wire item two"]
    assert {e["headline"] for e in events[2:]} == {"Macro digest item", "Financial digest item"}
    # The digest's 99/100 desk scores do NOT outrank a salience-20 wire item:
    # source-major ordering is what stops that cross-pool comparison happening.
    assert events[0]["salience"] == 20.0


def test_nightly_is_not_even_read_when_the_wire_fills_the_limit(tmp_path, monkeypatch):
    """"Only to top up" is literal — the digest files are not opened at all.

    Asserted with a SPY, not by inspecting the output: source-major ordering means
    a needlessly-merged digest item gets truncated away anyway, so an output-only
    assertion passes whether or not the guard exists. (Verified by mutation: making
    the merge unconditional left every output assertion green.)
    """
    calls: list[tuple] = []
    real = bmi._collect_nightly_events
    monkeypatch.setattr(
        bmi, "_collect_nightly_events",
        lambda root, cutoff: (calls.append((root, cutoff)), real(root, cutoff))[1],
    )
    _write_wires(tmp_path / "site" / "live", [
        _wire(f"w{n}", f"Wire item {n}", hours_ago=1 + n * 0.1) for n in range(3)
    ])
    _write_nightly(tmp_path, headlines=[_nightly_item("Should not appear", importance_score=100)])

    events = _events(tmp_path, limit=3)
    assert calls == [], "the digest was read despite a full wire"
    assert all(e["source_kind"] == "live_wire" for e in events)
    assert "Should not appear" not in {e["headline"] for e in events}

    # …and it IS read when the wire comes up short.
    assert len(_events(tmp_path, limit=5)) == 4 and len(calls) == 1


def test_a_nightly_twin_of_a_wire_story_is_deduped(tmp_path):
    """press_lane composes rail text as '<headline> -- <attribution> · <stamp>',
    so the tails must come off for the dedupe key or the same story shows twice."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("w", "Fed holds rates steady -- Reuters · SPY +0.3%", hours_ago=1),
    ])
    _write_nightly(tmp_path, headlines=[
        _nightly_item("Fed holds rates steady", hours_ago=2),
        _nightly_item("Dollar slips after the decision", hours_ago=3),
    ])
    events = _events(tmp_path, limit=5)
    assert len(events) == 2, "the twin was deduped"
    assert events[0]["source_kind"] == "live_wire", "the wire copy wins (chip + zh + composed text)"
    assert events[0]["headline"].startswith("Fed holds rates steady -- Reuters")
    assert events[1]["headline"] == "Dollar slips after the decision"


def test_notes_report_which_source_actually_answered(tmp_path):
    """Three states, three honest notes."""
    assert bmi.get_market_events(tmp_path, now=NOW)["note"] == "no fresh events in window"

    _write_nightly(tmp_path, headlines=[_nightly_item("Digest only")])
    assert bmi.get_market_events(tmp_path, now=NOW)["note"] == "nightly digest only"

    _write_wires(tmp_path / "site" / "live", [_wire("w", "Wire is up")])
    assert bmi.get_market_events(tmp_path, now=NOW)["note"] == "live wire"


def test_stale_nightly_digest_is_not_served_as_current(tmp_path):
    """The window binds the digest too — a day-old macro.json must not answer
    'what happened today' just because it is the only file present."""
    _write_nightly(tmp_path, headlines=[_nightly_item("Yesterday's news", hours_ago=30)])
    result = bmi.get_market_events(tmp_path, window_h=12, now=NOW)
    assert result["events"] == [] and result["note"] == "no fresh events in window"


def test_rejected_headlines_are_never_returned(tmp_path):
    """site/news/*.json also carries a `rejected` list — headlines the desk
    filtered OUT. Serving those would present rejected material as news, which is
    why the container keys are a whitelist rather than 'every list-valued key'."""
    _write_nightly(
        tmp_path,
        headlines=[],
        rejected=[_nightly_item("Rejected junk headline", hours_ago=1)],
    )
    assert _events(tmp_path) == []


def test_financial_by_ticker_bucket_is_read(tmp_path):
    """financial.json keeps per-ticker items in a dict-of-lists bucket; a symbol
    question is exactly where those matter."""
    _write_nightly(tmp_path, by_ticker={"NVDA": [_nightly_item("NVDA guidance raised", hours_ago=1)]})
    assert [e["headline"] for e in _events(tmp_path, symbol="NVDA")] == ["NVDA guidance raised"]


def test_nightly_items_carry_no_manufactured_corroboration(tmp_path):
    """The digest makes no corroboration decision, so the field is None — never a
    fabricated 'reports' chip that would imply a sourcing judgement we never made."""
    _write_nightly(tmp_path, headlines=[_nightly_item("Digest item")])
    assert _events(tmp_path)[0]["corroboration"] is None


# --------------------------------------------------------------------------- #
# 15-16  TI-R5 output whitelist — the epistemics law, pinned mechanically
# --------------------------------------------------------------------------- #
def test_event_items_carry_exactly_the_documented_keys(tmp_path):
    """Every event key is in EVENT_FIELDS, and every required field is present.

    This is the mechanical form of the module's epistemics law: the output is a
    whitelist, so no upstream field can reach the model's context without an
    edit here.
    """
    _write_wires(tmp_path / "site" / "live", [
        _wire("t", "Translated item", hours_ago=1, salience=90, zh="翻译"),
        _wire("p", "Plain item", hours_ago=2),
    ])
    _write_nightly(tmp_path, headlines=[_nightly_item("Digest item", hours_ago=3)])

    events = _events(tmp_path, limit=10)
    assert len(events) == 3
    for event in events:
        extra = set(event) - set(bmi.EVENT_FIELDS)
        assert not extra, f"undocumented output field(s): {sorted(extra)}"
        missing = set(bmi.EVENT_FIELDS_REQUIRED) - set(event)
        assert not missing, f"missing required field(s): {sorted(missing)}"


def test_forbidden_effect_fields_never_reach_the_output(tmp_path):
    """TI-R5 / A7: no predicted effect, no beneficiary or casualty list, no
    invented probability — NOT EVEN IF an upstream lane starts publishing them.

    The shock→beneficiary/'shelter' map is a standing house KILL
    (research/DO_NOT_REBUILD.md §1). This test feeds every forbidden shape
    through the reader and asserts none of it survives the projection.
    """
    poisoned = _wire("x", "Tariffs raised on imports", hours_ago=1, salience=88)
    poisoned.update({
        "beneficiaries": ["XLU", "GLD"],
        "casualties": ["XLK"],
        "shelter": "gold",
        "probability": 0.72,
        "expected_move": 1.4,
        "predicted_effect": "semis sell off",
        "front_run": True,
        "impact_score": 9,
    })
    _write_wires(tmp_path / "site" / "live", [poisoned])

    result = bmi.get_market_events(tmp_path, now=NOW)
    event = result["events"][0]
    assert event["headline"] == "Tariffs raised on imports", "the FACT still comes through"
    for banned in ("beneficiaries", "casualties", "shelter", "probability",
                   "expected_move", "predicted_effect", "front_run", "impact_score"):
        assert banned not in event, f"{banned} leaked into the output"

    # Belt and braces: none of the forbidden VALUES appear anywhere in the payload,
    # so nothing slipped through under a different key either.
    blob = json.dumps(result, ensure_ascii=False)
    for value in ("XLU", "GLD", "XLK", "gold", "0.72", "semis sell off"):
        assert value not in blob, f"forbidden value {value!r} survived projection"


# --------------------------------------------------------------------------- #
# 17-25  Research-vault search
# --------------------------------------------------------------------------- #
def _catalog(root: pathlib.Path, items: list[dict]) -> None:
    """Write a research_vault.catalog.v1 file."""
    directory = root / "data" / "research_vault"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "catalog.json").write_text(json.dumps({
        "schema": "research_vault.catalog.v1",
        "generated_at": _ago(0),
        "count": len(items),
        "items": items,
    }), encoding="utf-8")


def _note(iid: str, title: str, *, days: float = 0.0, points=(), institution="Citi",
          top_pick=False, side="sell") -> dict:
    """One catalog item in its committed shape."""
    return {
        "id": iid,
        "title": title,
        "institution": institution,
        "side": side,
        "desk": "",
        "published_at": _days_ago(days),
        "summary_points": list(points),
        "tags": [],
        "tickers": [],
        "top_pick": top_pick,
        "pages": 9,
        "language": "en",
    }


def _search(root, query, **kw) -> dict:
    return bmi.search_research(root, query, now=NOW, **kw)


def test_a_title_hit_outranks_a_summary_hit(tmp_path):
    """3.0 per title token vs 1.5 per summary token, same date → title wins."""
    _catalog(tmp_path, [
        _note("s", "Unrelated Wrapper Note", points=["momentum crowding is extreme"]),
        _note("t", "Momentum Crowding Risk", points=["nothing relevant here"]),
    ])
    results = _search(tmp_path, "momentum crowding")["results"]
    assert [r["id"] for r in results] == ["t", "s"]


def test_recency_decay_demotes_a_stale_exact_match(tmp_path):
    """Explicitly constructed: a 60-day-old TWO-token title match must lose to a
    same-day ONE-token title match.

        stale: 2 title hits × 3.0 = 6.0, factor max(0.35, 1-60/45) = 0.35 → 2.10
        fresh: 1 title hit  × 3.0 = 3.0, factor 1.0                     → 3.00
    """
    _catalog(tmp_path, [
        _note("stale", "Momentum Crowding Unwind", days=60),
        _note("fresh", "Momentum Only Note", days=0),
    ])
    results = _search(tmp_path, "momentum crowding")["results"]
    assert [r["id"] for r in results] == ["fresh", "stale"], (
        "the recency factor must outweigh the extra exact-match token"
    )


def test_recency_factor_floors_at_035_and_never_goes_negative(tmp_path):
    """A very old note is demoted, never erased or negated (a negative factor
    would invert the ranking and put the oldest research on top)."""
    assert bmi._recency_factor(_days_ago(0), NOW) == pytest.approx(1.0)
    assert bmi._recency_factor(_days_ago(45), NOW) == pytest.approx(bmi._RECENCY_FLOOR)
    assert bmi._recency_factor(_days_ago(4000), NOW) == pytest.approx(bmi._RECENCY_FLOOR)
    assert bmi._recency_factor(None, NOW) == pytest.approx(bmi._RECENCY_FLOOR)
    # A future stamp is clock skew, not extra freshness.
    assert bmi._recency_factor((NOW + timedelta(days=5)).isoformat(), NOW) == pytest.approx(1.0)


def test_top_pick_breaks_a_tie(tmp_path):
    """+1.0, applied to two otherwise identical notes."""
    _catalog(tmp_path, [
        _note("plain", "Momentum Crowding Alpha", days=1),
        _note("picked", "Momentum Crowding Beta", days=1, top_pick=True),
    ])
    results = _search(tmp_path, "momentum crowding")["results"]
    assert [r["id"] for r in results] == ["picked", "plain"]
    assert results[0]["top_pick"] is True and results[1]["top_pick"] is False


def test_top_pick_alone_never_admits_an_irrelevant_note(tmp_path):
    """The bonus is a tiebreak among relevant research, not a ticket into every
    result set — otherwise the 8 committed top picks would answer every query."""
    _catalog(tmp_path, [
        _note("irrelevant", "Japanese Government Bond Supply", top_pick=True),
        _note("relevant", "Momentum Crowding Risk"),
    ])
    assert [r["id"] for r in _search(tmp_path, "momentum crowding")["results"]] == ["relevant"]


def test_an_institution_word_hit_scores(tmp_path):
    """2.0 for an institution word — 'what does Goldman think' is a real ask."""
    _catalog(tmp_path, [
        _note("gs", "Rates Outlook Update", institution="Goldman Sachs"),
        _note("other", "Rates Outlook Update Two", institution="Nuveen"),
    ])
    results = _search(tmp_path, "goldman rates")["results"]
    assert results[0]["id"] == "gs" and results[0]["institution"] == "Goldman Sachs"


def test_summary_points_are_capped_at_four_and_truncated_to_220(tmp_path):
    _catalog(tmp_path, [
        _note("long", "Momentum Crowding Deep Dive",
              points=["A" * 400, "second", "third", "fourth", "fifth", "sixth"]),
    ])
    points = _search(tmp_path, "momentum crowding")["results"][0]["summary_points"]
    assert len(points) == 4, "first four only"
    assert all(len(p) <= 220 for p in points)
    assert len(points[0]) == 220 and points[0].endswith("…"), (
        "the ellipsis is inside the budget — a 221-char result would break a "
        "caller sizing a context window off the documented cap"
    )
    assert points[1:] == ["second", "third", "fourth"]


def test_result_items_carry_the_documented_keys(tmp_path):
    _catalog(tmp_path, [_note("r", "Momentum Crowding Risk", points=["p1"])])
    result = _search(tmp_path, "momentum crowding")
    assert set(result) == {"query", "results", "count_scanned", "note"}
    assert set(result["results"][0]) == {
        "id", "title", "institution", "side", "published_at", "summary_points", "top_pick",
    }
    assert result["count_scanned"] == 1
    assert "third-party" in result["note"] and "not the desk's own signals" in result["note"]


def test_limit_is_clamped_to_one_through_eight(tmp_path):
    _catalog(tmp_path, [_note(f"n{i}", f"Momentum Crowding Note {i}") for i in range(10)])
    assert len(_search(tmp_path, "momentum crowding", limit=3)["results"]) == 3
    assert len(_search(tmp_path, "momentum crowding", limit=99)["results"]) == 8
    assert len(_search(tmp_path, "momentum crowding", limit=0)["results"]) == 1
    assert len(_search(tmp_path, "momentum crowding", limit=None)["results"]) == 5


def test_a_short_query_says_so_rather_than_faking_a_search(tmp_path):
    """One bare token against hundreds of notes ranks essentially by recency and
    would read as a search that worked."""
    _catalog(tmp_path, [_note("r", "Momentum Crowding Risk")])
    for query in ("momentum", "", "   ", "a", None):
        result = _search(tmp_path, query)
        assert result["results"] == [] and result["note"] == "query too short", query


def test_qualified_tickers_survive_tokenisation(tmp_path):
    """Splitting on non-alnum would shred 600036.SH into '600036' + 'sh'."""
    assert "600036.sh" in bmi._tokenize("600036.SH outlook")
    _catalog(tmp_path, [_note("cn", "600036.SH Deposit Repricing Outlook")])
    assert _search(tmp_path, "600036.SH outlook")["results"][0]["id"] == "cn"


def test_a_repeated_query_word_does_not_buy_a_double_weight(tmp_path):
    """Distinct-token counting: 'momentum momentum crowding' must score exactly as
    'momentum crowding', or a user could inflate a match by repeating himself."""
    items = [_note("a", "Momentum Crowding Risk"), _note("b", "Momentum Only")]
    _catalog(tmp_path, items)
    once = [r["id"] for r in _search(tmp_path, "momentum crowding")["results"]]
    twice = [r["id"] for r in _search(tmp_path, "momentum momentum crowding")["results"]]
    assert once == twice


def test_a_corrupt_catalog_reports_unavailable_and_never_raises(tmp_path):
    directory = tmp_path / "data" / "research_vault"
    directory.mkdir(parents=True)
    (directory / "catalog.json").write_text("{not json", encoding="utf-8")
    result = _search(tmp_path, "hedge fund momentum")
    assert result["results"] == [] and result["note"] == "research vault unavailable"


def test_a_missing_catalog_reports_unavailable(tmp_path):
    result = _search(tmp_path, "hedge fund momentum")
    assert result["results"] == [] and result["note"] == "research vault unavailable"


def test_an_unexpected_container_shape_reports_unavailable(tmp_path):
    """Valid JSON, wrong shape — the same honest answer, not a crash."""
    directory = tmp_path / "data" / "research_vault"
    directory.mkdir(parents=True)
    (directory / "catalog.json").write_text('{"schema": "x", "items": "not a list"}', encoding="utf-8")
    assert _search(tmp_path, "hedge fund momentum")["note"] == "research vault unavailable"


def test_no_match_is_not_the_same_as_no_vault(tmp_path):
    """An empty result over a HEALTHY vault keeps the third-party note, so the
    model can say 'the vault has nothing on this' rather than 'it is broken'."""
    _catalog(tmp_path, [_note("r", "Japanese Government Bond Supply")])
    result = _search(tmp_path, "momentum crowding")
    assert result["results"] == []
    assert result["note"] != "research vault unavailable"
    assert result["count_scanned"] == 1


# --------------------------------------------------------------------------- #
# Smoke test against the REAL committed catalog
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not (ROOT / "data" / "research_vault" / "catalog.json").exists(),
    reason="data/research_vault/catalog.json not present in this checkout",
)
def test_real_catalog_search_returns_usable_results():
    """The committed vault (~346 institutional notes), searched at the WALL clock
    on purpose: this is the one test that proves the function works against real
    data as it ages, so it must not be pinned to NOW."""
    result = bmi.search_research(ROOT, "hedge fund momentum")
    assert result["count_scanned"] > 100, "the real catalog was scanned"
    assert result["results"], "a plain thematic query must return something"
    top = result["results"][0]
    assert top["title"] and isinstance(top["title"], str)
    assert top["summary_points"] and all(p.strip() for p in top["summary_points"])
    assert all(len(p) <= 220 for r in result["results"] for p in r["summary_points"])
    assert len(result["results"]) <= 5


@pytest.mark.skipif(
    not (ROOT / "site" / "news" / "macro.json").exists(),
    reason="site/news/macro.json not present in this checkout",
)
def test_real_repo_events_read_never_raises():
    """get_market_events against the real checkout: whatever the freshness of the
    committed digests, it returns a well-formed envelope with an honest note."""
    result = bmi.get_market_events(ROOT, window_h=48, limit=5)
    assert set(result) == {"asof", "window_h", "events", "note"}
    assert result["note"] in {"live wire", "nightly digest only", "no fresh events in window"}
    for event in result["events"]:
        assert not set(event) - set(bmi.EVENT_FIELDS)


# --------------------------------------------------------------------------- #
# 26-27  Tool schemas
# --------------------------------------------------------------------------- #
def test_events_tool_schema_shape_and_bounds():
    schema = bmi.EVENTS_TOOL_SCHEMA
    assert schema["name"] == "get_market_events"
    props = schema["input_schema"]["properties"]
    assert schema["input_schema"]["type"] == "object"
    assert set(props) == {"window_h", "limit", "symbol"}
    assert props["window_h"]["type"] == "number"
    assert props["limit"]["type"] == "integer"
    assert props["symbol"]["type"] == "string"
    assert schema["input_schema"]["required"] == [], "every argument is optional"
    # The bounds the code enforces must be the bounds the model is told.
    assert "1..48" in props["window_h"]["description"] and "default 12" in props["window_h"]["description"]
    assert "1..10" in props["limit"]["description"] and "default 5" in props["limit"]["description"]
    # WHEN to call, and the epistemics fence.
    description = schema["description"]
    assert "why is the market moving" in description
    assert "FACTS ONLY" in description
    assert "beneficiary" in description, "the TI-R5 fence is stated to the model too"


def test_research_tool_schema_shape_and_attribution_instruction():
    schema = bmi.RESEARCH_TOOL_SCHEMA
    assert schema["name"] == "search_research"
    props = schema["input_schema"]["properties"]
    # `mode` joined query/limit with the W2 street-clusters build and `report_id`
    # with the W4 full-report escalation; `required` did NOT change either time,
    # so the gateway's existing query=… call site keeps working.
    assert set(props) == {"query", "limit", "mode", "report_id"}
    assert props["query"]["type"] == "string" and props["limit"]["type"] == "integer"
    assert props["report_id"]["type"] == "string"
    assert schema["input_schema"]["required"] == ["query"]
    assert "1..8" in props["limit"]["description"] and "default 5" in props["limit"]["description"]
    description = schema["description"]
    assert "third-party" in description
    assert "institution" in description, "views must be attributed, never absorbed"
    assert "never present" in description


def test_research_tool_schema_offers_every_mode_and_fences_convergence():
    """The model must be able to reach clusters mode, and must be told what a
    convergence count is NOT — many desks agreeing is a crowding fact, not
    evidence the view is right."""
    props = bmi.RESEARCH_TOOL_SCHEMA["input_schema"]["properties"]
    assert props["mode"]["type"] == "string"
    assert props["mode"]["enum"] == ["search", "clusters", "report"]
    description = bmi.RESEARCH_TOOL_SCHEMA["description"]
    assert "clusters" in description, "the mode is unreachable if never mentioned"
    assert "crowding" in description
    assert "not evidence" in description.lower()


def test_research_tool_schema_teaches_the_report_mode_and_its_rights_fence():
    """mode='report' is reachable, and the model is told the three things that
    keep it honest: ids come from results (never invented), it is metered, and
    the material is somebody else's copyrighted work."""
    schema = bmi.RESEARCH_TOOL_SCHEMA
    description = schema["description"]
    assert "mode='report'" in description, "the mode is unreachable if never mentioned"
    assert "metered" in description
    assert "attribute" in description.lower()
    assert "synthesize" in description.lower()
    report_id = schema["input_schema"]["properties"]["report_id"]
    assert "mode='report'" in report_id["description"]
    assert "never invent" in report_id["description"].lower()
    assert "pro" in report_id["description"].lower(), "the tier gate is stated"


def test_both_schemas_are_json_serialisable():
    """They are handed to the Anthropic SDK verbatim."""
    for schema in (bmi.EVENTS_TOOL_SCHEMA, bmi.RESEARCH_TOOL_SCHEMA):
        assert json.loads(json.dumps(schema)) == schema


# --------------------------------------------------------------------------- #
# 28-35  W2 — the ranked-wire sidecar
# --------------------------------------------------------------------------- #
# WHY A SIDECAR AT ALL: the news desk DECLINED salience on the public wires.v1
# payload (their leak law — internal ranking numbers never ride a user-fetchable
# file, ruled 2026-07-30). So the desk's ordering arrives out-of-band on a
# NON-public state path, as ids in best-first order and no numbers at all. There
# is nothing to leak and nothing an LLM could re-present as a desk probability.
def _write_rank(directory: pathlib.Path, ids, *, minutes_ago: float = 1.0,
                schema: str = "wire_rank.v1", updated_at: object = None,
                omit_ids: bool = False) -> pathlib.Path:
    """Publish a wire_rank.v1 sidecar into `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    payload: dict = {"schema": schema}
    payload["updated_at"] = (
        updated_at if updated_at is not None
        else (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    if not omit_ids:
        payload["ids"] = ids
    path = directory / "wire_rank.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _three_wires(root: pathlib.Path) -> None:
    """Three wire items whose RECENCY order is c, b, a (newest first)."""
    _write_wires(root / "site" / "live", [
        _wire("a", "Oldest item", hours_ago=3),
        _wire("b", "Middle item", hours_ago=2),
        _wire("c", "Newest item", hours_ago=1),
    ])


def test_a_fresh_sidecar_reorders_the_wire_pool(tmp_path):
    """Position, not score: the sidecar names ids best-first and that becomes the
    order. Recency here would be c, b, a — so an unchanged order would prove
    nothing, which is why the fixture inverts it."""
    _three_wires(tmp_path)
    _write_rank(tmp_path / "data" / "marketing" / "press", ["a", "b", "c"])
    assert [e["headline"] for e in _events(tmp_path)] == [
        "Oldest item", "Middle item", "Newest item",
    ]


def test_a_stale_sidecar_is_ignored_in_favour_of_honest_recency(tmp_path):
    """A wire window turns over in minutes, so an hour-old ranking would pin a
    dead lead story to the top of a live tape. Past the age bound it is dropped."""
    _three_wires(tmp_path)
    press = tmp_path / "data" / "marketing" / "press"
    _write_rank(press, ["a", "b", "c"], minutes_ago=bmi._WIRE_RANK_MAX_AGE_MIN + 1)
    assert [e["headline"] for e in _events(tmp_path)] == [
        "Newest item", "Middle item", "Oldest item",
    ]
    # Just inside the bound it applies again — the gate is the age, not the file.
    _write_rank(press, ["a", "b", "c"], minutes_ago=bmi._WIRE_RANK_MAX_AGE_MIN - 1)
    assert [e["headline"] for e in _events(tmp_path)][0] == "Oldest item"


def test_no_sidecar_leaves_the_recency_order_untouched(tmp_path):
    """The default state today: the desk publishes no sidecar, and the honest
    answer is recency."""
    _three_wires(tmp_path)
    assert bmi._resolve_wire_rank_path(tmp_path) is None
    assert [e["headline"] for e in _events(tmp_path)] == [
        "Newest item", "Middle item", "Oldest item",
    ]


def test_ids_absent_from_the_sidecar_keep_their_order_after_the_ranked_ones(tmp_path):
    """A partial ranking is normal — the desk ranks what it scored. Unnamed items
    must not be dropped or shuffled; they fall in behind, still newest-first."""
    _write_wires(tmp_path / "site" / "live", [
        _wire("a", "Oldest item", hours_ago=4),
        _wire("b", "Middle item", hours_ago=3),
        _wire("c", "Newer item", hours_ago=2),
        _wire("d", "Newest item", hours_ago=1),
    ])
    _write_rank(tmp_path / "data" / "marketing" / "press", ["b"])
    assert [e["headline"] for e in _events(tmp_path, limit=10)] == [
        "Middle item",                      # the one ranked id leads
        "Newest item", "Newer item", "Oldest item",   # the rest, still by recency
    ]


def test_unknown_and_malformed_ids_are_ignored(tmp_path):
    """Ids for items outside the window (or plain junk) must not reorder anything
    they do not name, and must not crash the read."""
    _three_wires(tmp_path)
    _write_rank(tmp_path / "data" / "marketing" / "press",
                ["ghost-1", None, 42, {"id": "b"}, "", "  ", "b"])
    assert [e["headline"] for e in _events(tmp_path)] == [
        "Middle item",                            # the only real id
        "Newest item", "Oldest item",
    ]


@pytest.mark.parametrize("kwargs, why", [
    ({"omit_ids": True}, "no ids list at all"),
    ({"updated_at": "not-a-date"}, "an unparseable stamp cannot be shown fresh"),
    ({"updated_at": ""}, "a blank stamp cannot be shown fresh"),
])
def test_a_malformed_sidecar_degrades_to_recency(tmp_path, kwargs, why):
    """Every degraded case falls back to the honest order rather than erroring.

    An unstamped ranking is treated as UNUSABLE, not as fresh: assuming freshness
    is exactly how a dead daemon's last ordering outlives it.
    """
    _three_wires(tmp_path)
    _write_rank(tmp_path / "data" / "marketing" / "press", ["a", "b", "c"], **kwargs)
    assert [e["headline"] for e in _events(tmp_path)] == [
        "Newest item", "Middle item", "Oldest item",
    ], why


def test_corrupt_sidecar_json_degrades_to_recency(tmp_path):
    _three_wires(tmp_path)
    press = tmp_path / "data" / "marketing" / "press"
    press.mkdir(parents=True, exist_ok=True)
    (press / "wire_rank.json").write_text("{not json", encoding="utf-8")
    assert [e["headline"] for e in _events(tmp_path)][0] == "Newest item"


def test_a_renamed_schema_still_ranks(tmp_path):
    """Loose schema check, matching _wire_items: a reader that hard-failed on a
    rename would go dark on a schema bump, and every field access is defensive."""
    _three_wires(tmp_path)
    _write_rank(tmp_path / "data" / "marketing" / "press", ["a"],
                schema="wire_rank.v2")
    assert [e["headline"] for e in _events(tmp_path)][0] == "Oldest item"


def test_the_state_dir_env_wins_over_the_dev_sink(tmp_path, monkeypatch):
    """MACRO_LIVE_STATE_DIR is the deployed override (app/deploy/live-setup.sh:80,
    scripts/vps_live_orchestrator.py:459) — the STATE dir, never the public one."""
    _three_wires(tmp_path)
    state = tmp_path / "hoststate"
    _write_rank(state, ["a"])
    _write_rank(tmp_path / "data" / "marketing" / "press", ["c"])
    monkeypatch.setenv("MACRO_LIVE_STATE_DIR", str(state))

    assert bmi._resolve_wire_rank_path(tmp_path) == state / "wire_rank.json"
    assert [e["headline"] for e in _events(tmp_path)][0] == "Oldest item"


def test_an_empty_state_dir_falls_through_to_the_dev_sink(tmp_path, monkeypatch):
    """File-exists, not dir-exists — the same divergence from the writer ladder
    that _resolve_wires_path makes: on a dev box the state dir exists and is empty
    while the dev sink holds the real file."""
    _three_wires(tmp_path)
    empty = tmp_path / "hoststate"
    empty.mkdir(parents=True)
    monkeypatch.setenv("MACRO_LIVE_STATE_DIR", str(empty))
    _write_rank(tmp_path / "data" / "marketing" / "press", ["a"])

    assert bmi._resolve_wire_rank_path(tmp_path) == tmp_path / "data/marketing/press/wire_rank.json"
    assert [e["headline"] for e in _events(tmp_path)][0] == "Oldest item"


def test_the_sidecar_never_reorders_the_nightly_pool(tmp_path):
    """Source-major ordering is untouched: the desk ranks the intraday tape, not
    last night's digest, so a sidecar naming a digest id changes nothing and the
    wire items still come first."""
    _write_wires(tmp_path / "site" / "live", [_wire("w1", "Wire item", hours_ago=5)])
    _write_nightly(tmp_path, headlines=[
        _nightly_item("Digest one", hours_ago=1),
        _nightly_item("Digest two", hours_ago=2),
    ])
    _write_rank(tmp_path / "data" / "marketing" / "press", ["Digest two", "w1"])
    events = _events(tmp_path, limit=5)
    assert [e["source_kind"] for e in events] == ["live_wire", "nightly", "nightly"]
    assert [e["headline"] for e in events] == ["Wire item", "Digest one", "Digest two"]


def test_the_sidecar_adds_no_output_field_and_leaks_no_value(tmp_path):
    """The sidecar's ONLY effect is a permutation. EVENT_FIELDS is unchanged, so
    no id, position or ranking artefact can reach the model's context — the same
    mechanical guarantee as the TI-R5 whitelist tests above."""
    _three_wires(tmp_path)
    _write_rank(tmp_path / "data" / "marketing" / "press", ["c", "a", "b"])
    result = bmi.get_market_events(tmp_path, now=NOW)

    for event in result["events"]:
        assert not set(event) - set(bmi.EVENT_FIELDS)
        assert event["salience"] is None, "a position is not a score"
    blob = json.dumps(result, ensure_ascii=False)
    for banned in ("wire_rank", "rank", "position", "\"ids\"", "\"id\""):
        assert banned not in blob, f"{banned!r} leaked into the payload"


def test_reading_the_sidecar_never_writes_it(tmp_path):
    """This module is a READER. The daemon owns the file."""
    _three_wires(tmp_path)
    press = tmp_path / "data" / "marketing" / "press"
    path = _write_rank(press, ["a", "b", "c"])
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    _events(tmp_path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert sorted(p.name for p in press.iterdir()) == ["wire_rank.json"]


def test_the_wire_rank_helper_returns_positions_not_scores(tmp_path):
    """Unit-level: the reader hands back {id: position} and nothing numeric from
    the file, because the file deliberately contains no numbers to hand back."""
    _write_rank(tmp_path / "data" / "marketing" / "press", ["x", "y", "z"])
    assert bmi._wire_rank_order(tmp_path, NOW) == {"x": 0, "y": 1, "z": 2}
    # A duplicated id keeps its FIRST (best) position.
    _write_rank(tmp_path / "data" / "marketing" / "press", ["x", "y", "x"])
    assert bmi._wire_rank_order(tmp_path, NOW) == {"x": 0, "y": 1}
    # An empty ids list is not a ranking.
    _write_rank(tmp_path / "data" / "marketing" / "press", [])
    assert bmi._wire_rank_order(tmp_path, NOW) is None


def test_a_future_stamped_sidecar_is_clock_skew_not_staleness(tmp_path):
    """Same rule _recency_factor applies to research dates: a stamp ahead of the
    caller's instant is a skewed writer, not a stale file."""
    _three_wires(tmp_path)
    _write_rank(tmp_path / "data" / "marketing" / "press", ["a"], minutes_ago=-30)
    assert [e["headline"] for e in _events(tmp_path)][0] == "Oldest item"


# --------------------------------------------------------------------------- #
# 36-46  W2 — street clusters
# --------------------------------------------------------------------------- #
def _clusters(root, **kw) -> dict:
    return bmi.search_research(root, "", mode="clusters", now=NOW, **kw)


def test_a_convergent_theme_is_reported_with_its_houses(tmp_path):
    """Three notes on one subject from three different houses IS the street
    converging, and the houses are named so the user can weigh them."""
    _catalog(tmp_path, [
        _note("t1", "Iran Oil Supply Shock", institution="Goldman Sachs"),
        _note("t2", "Iran Escalation And Crude", institution="J.P. Morgan"),
        _note("t3", "The Iran Premium In Brent", institution="ING"),
        _note("x1", "Japanese Government Bond Supply", institution="MUFG"),
    ])
    result = _clusters(tmp_path)
    assert result["schema"] == "brain.research_clusters.v1"
    assert result["count_scanned"] == 4
    themes = {c["theme"]: c for c in result["clusters"]}
    assert "iran" in themes, f"no iran theme in {list(themes)}"
    iran = themes["iran"]
    assert iran["n_reports"] == 3
    assert iran["n_institutions"] == 3
    assert iran["institutions"] == ["Goldman Sachs", "ING", "J.P. Morgan"]
    assert [r["id"] for r in iran["reports"]] == ["t1", "t2", "t3"]
    assert "not consensus-as-authority" in result["note"]


def test_one_house_repeating_itself_is_not_convergence(tmp_path):
    """The institution count is the ONLY thing separating "the street is focused
    on X" from "one desk published three notes on its own idea"."""
    _catalog(tmp_path, [
        _note("a1", "Tariff Escalation Risk", institution="Citi"),
        _note("a2", "Tariff Deadline Preview", institution="Citi"),
        _note("a3", "Tariff Pass Through", institution="Citi"),
    ])
    assert _clusters(tmp_path)["clusters"] == []


def test_a_theme_below_the_report_floor_is_excluded(tmp_path):
    """Two notes is a coincidence, not a theme."""
    _catalog(tmp_path, [
        _note("a1", "Copper Squeeze Deepens", institution="Citi"),
        _note("a2", "Copper Inventories Fall", institution="UBS"),
    ])
    assert _clusters(tmp_path)["clusters"] == []
    # A third house tips it over the bar.
    _catalog(tmp_path, [
        _note("a1", "Copper Squeeze Deepens", institution="Citi"),
        _note("a2", "Copper Inventories Fall", institution="UBS"),
        _note("a3", "Copper And The Grid", institution="ING"),
    ])
    assert [c["theme"] for c in _clusters(tmp_path)["clusters"]] == ["copper"]


def test_the_dead_tags_and_tickers_fields_are_never_read(tmp_path):
    """`tags`/`tickers`/`desk` are filled 0/374 in the committed catalog. A theme
    keyed off one would return nothing forever; a theme keyed off a POPULATED one
    in some future vintage still must not appear until that is a deliberate build.
    """
    items = [
        _note("g1", "Unrelated Alpha", institution="Citi"),
        _note("g2", "Unrelated Beta", institution="UBS"),
        _note("g3", "Unrelated Gamma", institution="ING"),
    ]
    for item in items:
        item["tags"] = ["semiconductors", "semiconductors"]
        item["tickers"] = ["NVDA"]
        item["desk"] = "equities"
    _catalog(tmp_path, items)
    blob = json.dumps(_clusters(tmp_path), ensure_ascii=False)
    assert "semiconductors" not in blob and "NVDA" not in blob
    assert "equities" not in blob


def test_clusters_are_deterministic_under_catalog_reordering(tmp_path):
    """A catalog rebuild reorders `items`; the themes must not move. An unstable
    convergence read would look like the street changed its mind overnight."""
    items = [
        _note("i1", "Iran Oil Supply Shock", days=0.5, institution="Goldman Sachs"),
        _note("i2", "Iran Escalation And Crude", days=1.0, institution="J.P. Morgan"),
        _note("i3", "The Iran Premium In Brent", days=1.5, institution="ING"),
        _note("c1", "Credit Spreads Widen", days=0.2, institution="Natixis"),
        _note("c2", "Credit Issuance Surge", days=0.8, institution="Morgan Stanley"),
        _note("c3", "Private Credit Stress", days=2.0, institution="UBS"),
    ]
    _catalog(tmp_path, items)
    first = _clusters(tmp_path)
    _catalog(tmp_path, list(reversed(items)))
    second = _clusters(tmp_path)
    assert first == second
    # Both themes clear the bar, and the order between them is total.
    assert [c["theme"] for c in first["clusters"]] == ["credit", "iran"]


def test_reports_are_the_newest_three_and_carry_no_summary_text(tmp_path):
    """A convergence answer needs WHO and WHEN, not five bullet points per note —
    the model can call search mode for the content of any one of them."""
    # 6 tariff notes inside a 30-note window: a term carried by EVERY note in the
    # catalog is ambient by definition, so the fixture has to look like a real
    # window rather than a single-subject slab.
    items = [
        _note(f"n{i}", f"Tariff Escalation {i}", days=i,
              institution=f"House {i}", points=["a bullet that must not ship"])
        for i in range(6)
    ]
    items += [_note(f"f{i}", f"Unrelated Subject{i} Coverage", days=i * 0.1,
                    institution=f"Filler {i}") for i in range(24)]
    _catalog(tmp_path, items)
    cluster = _clusters(tmp_path)["clusters"][0]
    assert cluster["theme"].startswith("tariff") or "tariff" in cluster["theme"]
    assert cluster["n_reports"] == 6
    assert [r["id"] for r in cluster["reports"]] == ["n0", "n1", "n2"], "newest three"
    assert set(cluster["reports"][0]) == {"id", "title", "institution", "published_at"}
    assert "a bullet that must not ship" not in json.dumps(cluster)


def test_window_days_is_the_theme_s_own_span(tmp_path):
    """"6 houses inside a day" and "6 houses across a fortnight" are different
    facts about convergence; the catalog's rolling window cannot express either."""
    _catalog(tmp_path, [
        _note("a", "Tariff One", days=0.0, institution="Citi"),
        _note("b", "Tariff Two", days=1.0, institution="UBS"),
        _note("c", "Tariff Three", days=2.5, institution="ING"),
    ])
    assert _clusters(tmp_path)["clusters"][0]["window_days"] == 2.5


def test_top_pick_count_is_carried(tmp_path):
    _catalog(tmp_path, [
        _note("a", "Tariff One", institution="Citi", top_pick=True),
        _note("b", "Tariff Two", institution="UBS"),
        _note("c", "Tariff Three", institution="ING", top_pick=True),
    ])
    assert _clusters(tmp_path)["clusters"][0]["top_pick_count"] == 2


def test_report_furniture_never_becomes_a_theme(tmp_path):
    """"JPM GLOBAL MARKET INTELLIGENCE" and "DB Research Europe" are recurring
    PUBLICATION SERIES names. A theme called "market" or "research" would be the
    vague glance-tier copy the design doctrine bans, and it is not a subject."""
    _catalog(tmp_path, [
        _note("a", "Global Market Intelligence Weekly Update", institution="J.P. Morgan"),
        _note("b", "Daily Market Research Note", institution="UBS"),
        _note("c", "Weekly Market Commentary Update", institution="Nuveen"),
    ])
    themes = {c["theme"] for c in _clusters(tmp_path)["clusters"]}
    for furniture in ("market", "research", "weekly", "update", "daily", "global"):
        assert furniture not in themes, f"{furniture!r} was reported as a theme"


def test_an_ambient_word_is_not_reported_as_a_theme(tmp_path):
    """A term in more than a quarter of the window is the week's vocabulary. Its
    "N houses wrote about it" reads as convergence when it is just weather."""
    items = [_note(f"r{i}", f"Risk Assessment Subject{i}", institution=f"House {i}")
             for i in range(20)]
    items += [_note(f"i{i}", f"Iran Escalation Take{i}", institution=f"Bank {i}")
              for i in range(4)]
    _catalog(tmp_path, items)
    themes = {c["theme"] for c in _clusters(tmp_path)["clusters"]}
    assert "risk" not in themes, "an ambient word was sold as convergence"
    assert "assessment" not in themes
    # The real subject survives. Its label carries both terms that cover the same
    # four notes ("escalation iran") — that is the doc-set merge folding one
    # subject said two ways into a single theme, not two themes.
    assert any("iran" in theme for theme in themes), themes
    assert len(themes) == 1


def test_an_empty_catalog_is_honest_rather_than_broken(tmp_path):
    """`clusters: []` over a HEALTHY vault means nothing cleared the bar — the
    model can say so instead of claiming the read failed."""
    _catalog(tmp_path, [])
    result = _clusters(tmp_path)
    assert result["clusters"] == [] and result["count_scanned"] == 0
    assert result["note"] != "research vault unavailable"
    assert "not consensus-as-authority" in result["note"]


def test_a_missing_or_corrupt_catalog_reports_unavailable_in_clusters_mode(tmp_path):
    result = _clusters(tmp_path)
    assert result["schema"] == "brain.research_clusters.v1"
    assert result["clusters"] == [] and result["note"] == "research vault unavailable"

    directory = tmp_path / "data" / "research_vault"
    directory.mkdir(parents=True)
    (directory / "catalog.json").write_text("{not json", encoding="utf-8")
    assert _clusters(tmp_path)["note"] == "research vault unavailable"


def test_max_clusters_caps_the_reported_themes(tmp_path):
    items = []
    for n, subject in enumerate(("iran", "copper", "tariff", "vietnam", "cocoa", "lithium")):
        for house in ("Citi", "UBS", "ING"):
            items.append(_note(f"{subject}-{house}", f"{subject.title()} Outlook Note",
                               institution=house, days=n * 0.1))
    _catalog(tmp_path, items)
    assert len(_clusters(tmp_path)["clusters"]) == 5, "default max_clusters"
    raw = bmi._research_clusters(bmi._catalog_items(tmp_path), now=NOW, max_clusters=2)
    assert len(raw["clusters"]) == 2


def test_clusters_carry_no_score_or_confidence_key(tmp_path):
    """Counts and a day-span are facts. A score would be an authority claim this
    display-tier retrieval read has no gauntlet for."""
    _catalog(tmp_path, [
        _note("a", "Tariff One", institution="Citi"),
        _note("b", "Tariff Two", institution="UBS"),
        _note("c", "Tariff Three", institution="ING"),
    ])
    cluster = _clusters(tmp_path)["clusters"][0]
    assert set(cluster) == {
        "theme", "n_reports", "n_institutions", "institutions", "window_days",
        "top_pick_count", "reports",
    }
    blob = json.dumps(_clusters(tmp_path)).lower()
    for banned in ("score", "confidence", "conviction", "probability", "validated"):
        assert banned not in blob


def test_search_mode_is_the_default_and_unchanged(tmp_path):
    """The P0 envelope is untouched — the gateway's existing call site passes no
    mode at all, and a typo must not cost the user his search."""
    _catalog(tmp_path, [_note("r", "Momentum Crowding Risk", points=["p1"])])
    baseline = _search(tmp_path, "momentum crowding")
    assert set(baseline) == {"query", "results", "count_scanned", "note"}
    for mode in (None, "search", "SEARCH", " search ", "clusterz", "", 7, ["clusters"]):
        result = bmi.search_research(tmp_path, "momentum crowding", now=NOW, mode=mode)
        assert result == baseline, f"mode={mode!r} did not fall back to search"


def test_clusters_mode_is_recognised_case_and_whitespace_insensitively(tmp_path):
    _catalog(tmp_path, [
        _note("a", "Tariff One", institution="Citi"),
        _note("b", "Tariff Two", institution="UBS"),
        _note("c", "Tariff Three", institution="ING"),
    ])
    for mode in ("clusters", "CLUSTERS", " Clusters "):
        assert bmi.search_research(tmp_path, "", now=NOW, mode=mode)["schema"] == \
            "brain.research_clusters.v1"


def test_clusters_mode_ignores_the_query_and_the_short_query_gate(tmp_path):
    """Convergence is a property of the whole window. Filtering it by search terms
    would answer "who agrees with my premise", and the 2-token gate must not fire
    on a mode that never reads the query."""
    _catalog(tmp_path, [
        _note("a", "Tariff One", institution="Citi"),
        _note("b", "Tariff Two", institution="UBS"),
        _note("c", "Tariff Three", institution="ING"),
    ])
    for query in ("", "x", None, "completely unrelated words"):
        result = bmi.search_research(tmp_path, query, now=NOW, mode="clusters")
        assert [c["theme"] for c in result["clusters"]] == ["tariff"], query
        assert result["note"] != "query too short"


@pytest.mark.skipif(
    not (ROOT / "data" / "research_vault" / "catalog.json").exists(),
    reason="data/research_vault/catalog.json not present in this checkout",
)
def test_real_catalog_clusters_are_coherent():
    """The committed vault at the WALL clock, like its search sibling: the one test
    that proves clusters work against real data as it ages.

    Every reported theme must be a real subject word carried by the TITLE of every
    member — that is the whole reason membership is title-anchored (a bag-of-words
    build over title+summary produced a 51-report 'hike fed rate' cluster whose
    members had nothing in common).
    """
    result = bmi.search_research(ROOT, "", mode="clusters")
    assert result["count_scanned"] > 100, "the real catalog was scanned"
    assert result["clusters"], "the real catalog converges on something"
    assert len(result["clusters"]) <= 5
    for cluster in result["clusters"]:
        assert cluster["n_reports"] >= 3
        assert cluster["n_institutions"] >= 2
        assert len(cluster["institutions"]) == cluster["n_institutions"]
        assert cluster["theme"] and cluster["theme"] == cluster["theme"].lower()
        assert 1 <= len(cluster["reports"]) <= 3
        first_term = cluster["theme"].split()[0]
        for report in cluster["reports"]:
            assert first_term in (report["title"] or "").lower(), (
                f"{first_term!r} is not in the title of {report['title']!r} — the "
                "theme is not the note's own declared subject"
            )
    # Themes are distinct: the doc-set merge folds one subject said two ways.
    themes = [c["theme"] for c in result["clusters"]]
    assert len(set(themes)) == len(themes)


# --------------------------------------------------------------------------- #
# 47-62  W4 — the full-report escalation (mode='report', PRO, metered)
# --------------------------------------------------------------------------- #
# The corpus is R2-only, so the body layer is reached through ONE seam
# (research_vault.corpus.get_document) and every test replaces it. Nothing here
# opens a socket; the quota ledger, where a test lets the real one run, is rooted
# at a tmp MACRO_API_STATE_DIR.

_PRO = {"user_id": "u-pro-1", "ip_hint": "203.0.113.9"}


def _excerpts(root: pathlib.Path, mapping: dict) -> None:
    """Write the committed public-excerpt snapshot (excerpt.write_repo_snapshot's
    shape: {"schema": 1, "excerpts": {doc_id: [paragraph, ...]}})."""
    directory = root / "data" / "research_vault"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "excerpts.json").write_text(
        json.dumps({"schema": 1, "excerpts": mapping}), encoding="utf-8")


def _stub_document(monkeypatch, body: str, *, calls: list | None = None, **over):
    """Replace the corpus seam with a canned document row (no R2, no sqlite)."""
    from engine.research_vault import corpus as corpus_mod

    def _get_document(doc_id, store_factory=None):
        if calls is not None:
            calls.append(doc_id)
        row = {"doc_id": doc_id, "title": "Corpus Title", "institution": "Corpus Co",
               "side": "sell", "published_at": "2026-01-01T00:00:00Z",
               "summary": "corpus summary", "body": body,
               # corpus.DOCUMENT_FIELDS carries the measured text-layer state; ''
               # is the unmeasured default a pre-probe row returns.
               "text_layer": ""}
        row.update(over)
        return row

    monkeypatch.setattr(corpus_mod, "get_document", _get_document)


def _stub_no_document(monkeypatch, calls: list | None = None):
    """The corpus is unreachable (no R2 creds, dead bucket, unknown row)."""
    from engine.research_vault import corpus as corpus_mod

    def _get_document(doc_id, store_factory=None):
        if calls is not None:
            calls.append(doc_id)
        return None

    monkeypatch.setattr(corpus_mod, "get_document", _get_document)


def _stub_quota(monkeypatch, allowed: bool = True, *, remaining: int = 59,
                limit: int = 60, calls: list | None = None):
    """Replace the hourly view ledger; `calls` records every debit attempt."""
    from engine.research_vault import view_ratelimit

    def _allow(user_id, ip, root=None, now=None):
        if calls is not None:
            calls.append((user_id, ip, now))
        return allowed, {"remaining": remaining if allowed else 0, "limit": limit}

    monkeypatch.setattr(view_ratelimit, "allow", _allow)


def _report(root, report_id, *, user_ctx=_PRO, **kw) -> dict:
    return bmi.search_research(root, "", now=NOW, mode="report",
                               report_id=report_id, user_ctx=user_ctx, **kw)


def _seed_one(root: pathlib.Path, *, points=("**Thesis**: the range holds.",),
              institution="Goldman Sachs", excerpt=("Opening paragraph of the note.",)):
    _catalog(root, [_note("gs-oil-1", "Oil Tracker", points=points,
                          institution=institution)])
    if excerpt is not None:
        _excerpts(root, {"gs-oil-1": list(excerpt)})


def test_report_assembles_metadata_excerpt_and_body(tmp_path, monkeypatch):
    """The happy path: the three layers arrive together and the envelope names
    itself, so the model knows it is holding one note, not a search."""
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "The curve is backwardated because inventories drew.")
    _stub_quota(monkeypatch)

    result = _report(tmp_path, "gs-oil-1")

    assert result["schema"] == "brain.research_report.v1"
    assert result["asof"] == "2026-07-29T15:00:00Z"
    report = result["report"]
    assert set(report) == set(bmi.REPORT_FIELDS)
    assert report["id"] == "gs-oil-1"
    assert report["title"] == "Oil Tracker"
    assert report["institution"] == "Goldman Sachs"
    assert report["side"] == "sell"
    assert report["summary_points"] == ["**Thesis**: the range holds."]
    assert report["excerpt_paragraphs"] == ["Opening paragraph of the note."]
    assert "inventories drew" in report["body_text"]
    assert report["body_truncated"] is False
    assert result["quota"] == {"remaining": 59, "limit": 60}


def test_the_note_carries_the_attribution_and_redistribution_terms(tmp_path, monkeypatch):
    """The chat equivalent of the PDF watermark: the rights line rides in the
    payload, names the actual publisher, and is addressed to the model."""
    _seed_one(tmp_path, institution="Morgan Stanley")
    _stub_document(monkeypatch, "body text")
    _stub_quota(monkeypatch)

    note = _report(tmp_path, "gs-oil-1")["note"]
    assert "Morgan Stanley" in note
    assert "attribute" in note.lower()
    assert "quote sparingly" in note.lower()
    assert "not for redistribution" in note.lower()
    assert "verbatim" in note.lower()


def test_the_body_is_capped_at_twelve_thousand_chars_with_a_marker(tmp_path, monkeypatch):
    """The exposure cap is the operator's dial (excerpt.py's rule), so it is
    pinned mechanically — and the marker is INSIDE the budget, so the documented
    number is the true ceiling."""
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "lorem ipsum dolor " * 4000)  # ~72k chars
    _stub_quota(monkeypatch)

    report = _report(tmp_path, "gs-oil-1")["report"]
    assert bmi.REPORT_BODY_MAX_CHARS == 12_000
    assert len(report["body_text"]) <= 12_000
    assert report["body_truncated"] is True
    assert report["body_text"].endswith(
        "…full report continues — available in the Research Vault")
    assert "Research Vault" in report["body_text"], "the fuller surface is named"


def test_a_body_inside_the_cap_is_served_whole_and_unmarked(tmp_path, monkeypatch):
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "short body")
    _stub_quota(monkeypatch)

    report = _report(tmp_path, "gs-oil-1")["report"]
    assert report["body_text"] == "short body"
    assert report["body_truncated"] is False
    assert "continues" not in report["body_text"]


def test_the_whole_payload_never_carries_more_than_the_cap(tmp_path, monkeypatch):
    """TI-R5-style whole-payload check: no key anywhere — not `body_text`, not a
    field added later — may exceed the exposure cap, and nothing may read as a
    desk score over somebody else's note."""
    _seed_one(tmp_path, points=tuple(f"point {i}" for i in range(20)))
    _stub_document(monkeypatch, "argument " * 9000)
    _stub_quota(monkeypatch)

    result = _report(tmp_path, "gs-oil-1")

    def _walk(node):
        if isinstance(node, str):
            assert len(node) <= bmi.REPORT_BODY_MAX_CHARS
        elif isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(result)
    blob = json.dumps(result).lower()
    for banned in ("confidence", "conviction", "probability", "validated"):
        assert banned not in blob
    # Summary points keep the catalog's own clamp (8 kept, 220 chars each).
    assert len(result["report"]["summary_points"]) == 8


def test_an_unreachable_corpus_falls_back_to_the_excerpt_and_charges_nothing(
        tmp_path, monkeypatch):
    """The excerpt is ALREADY public (it renders outside the paywall on the SEO
    pages), so serving it costs no exposure and must cost no quota either —
    metering a public read would deny a member what the website shows anyone."""
    _seed_one(tmp_path, excerpt=("Opening paragraph.", "Second paragraph."))
    _stub_no_document(monkeypatch)
    debits: list = []
    _stub_quota(monkeypatch, calls=debits)

    result = _report(tmp_path, "gs-oil-1")

    assert debits == [], "the excerpt-only fallback must not debit the hourly cap"
    assert result["quota"] is None
    report = result["report"]
    assert report["excerpt_paragraphs"] == ["Opening paragraph.", "Second paragraph."]
    assert report["body_text"] == ""
    assert report["body_truncated"] is False
    assert "opening pages" in result["note"].lower(), "the shortfall is disclosed"
    assert "not reachable" in result["note"].lower()


def test_an_empty_corpus_body_is_treated_as_unreachable(tmp_path, monkeypatch):
    """A scanned PDF with no text layer stores an empty body. That is the same
    situation as a dead corpus — excerpt only, disclosed, unmetered."""
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "   ")
    debits: list = []
    _stub_quota(monkeypatch, calls=debits)

    result = _report(tmp_path, "gs-oil-1")
    assert debits == []
    assert result["quota"] is None
    assert result["report"]["body_text"] == ""


def test_a_scanned_report_is_disclosed_as_scanned_not_as_a_temporary_failure(
        tmp_path, monkeypatch):
    """text_layer='none' means the extractor RAN and this PDF is image-only: the
    excerpt is all the text that will ever exist for it. Telling the user the full
    text 'is not reachable right now' promises a retry that can never deliver."""
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "", text_layer="none")
    debits: list = []
    _stub_quota(monkeypatch, calls=debits)

    result = _report(tmp_path, "gs-oil-1")

    note = result["note"]
    assert "scanned/image-only" in note
    assert "all the text there is" in note
    assert "not reachable" not in note.lower(), "a scan is not a temporary failure"
    # Everything else about the empty-body path is unchanged: public excerpt,
    # no body, no quota debit.
    assert debits == []
    assert result["quota"] is None
    assert result["report"]["body_text"] == ""
    assert result["report"]["excerpt_paragraphs"] == ["Opening paragraph of the note."]
    # The note is the whole mechanism — no new key reaches the model's context.
    assert set(result["report"]) == set(bmi.REPORT_FIELDS)


@pytest.mark.parametrize("layer", ["unavailable", "", "thin", "full"])
def test_every_other_empty_body_keeps_the_temporary_shortfall_note(
        tmp_path, monkeypatch, layer):
    """'unavailable' is a HOST fault (poppler missing on the runner, 2026-07-30)
    that ingest._reextract_bodies repairs, and '' is simply unmeasured — for both,
    'not reachable right now' is the true sentence."""
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "", text_layer=layer)
    _stub_quota(monkeypatch)

    note = _report(tmp_path, "gs-oil-1")["note"]
    assert "not reachable" in note.lower()
    assert "scanned" not in note.lower()


def test_an_absent_corpus_row_keeps_the_temporary_shortfall_note(tmp_path, monkeypatch):
    """No row at all says nothing about the DOCUMENT — the corpus is unreachable
    or the id was never indexed, both of which a later read may resolve."""
    _seed_one(tmp_path)
    _stub_no_document(monkeypatch)
    _stub_quota(monkeypatch)

    note = _report(tmp_path, "gs-oil-1")["note"]
    assert "not reachable" in note.lower()
    assert "scanned" not in note.lower()


def test_a_served_body_debits_exactly_one_view(tmp_path, monkeypatch):
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "the argument")
    debits: list = []
    _stub_quota(monkeypatch, calls=debits)

    _report(tmp_path, "gs-oil-1")
    assert len(debits) == 1
    user_id, ip, now = debits[0]
    assert user_id == "u-pro-1"
    assert ip == "brain:u-pro-1", "the ip ledger key is the per-user synthetic marker"
    assert now == NOW, "the ledger period is keyed on the caller's instant"


def test_the_ip_ledger_bucket_is_per_user_not_one_shared_noip_bucket(
        tmp_path, monkeypatch):
    """Proves the synthetic marker against the REAL limiter.

    view_ratelimit hashes the ip into a SECOND ledger and maps an empty/'unknown'
    address to the literal bucket 'noip'. Passing '' (or the gateway's shared NAT
    address) would put every chat user in one hourly counter, so one Pro member's
    reading would deny everyone else's. With the cap forced to 1: user A is
    allowed once then denied, and user B — who has read nothing — is still
    allowed. Under a shared bucket B's first call would already be denied.
    """
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("RESEARCH_VIEW_HOURLY", "1")
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "the argument")

    a = {"user_id": "u-alpha"}
    b = {"user_id": "u-beta"}

    assert _report(tmp_path, "gs-oil-1", user_ctx=a)["quota"] == {"remaining": 0, "limit": 1}
    assert _report(tmp_path, "gs-oil-1", user_ctx=a)["error"] == "view_limit_reached"
    second_user = _report(tmp_path, "gs-oil-1", user_ctx=b)
    assert "error" not in second_user, (
        "user B was denied on his first read — the two users shared an ip bucket")
    assert second_user["quota"] == {"remaining": 0, "limit": 1}


def test_a_broken_ledger_fails_OPEN_like_the_limiter_it_wraps(tmp_path, monkeypatch):
    """view_ratelimit's own rule: a broken state dir must not lock a paying
    subscriber out of what he bought. The debit is best-effort, so the report is
    still served — with the remaining/limit it could not read left honestly null,
    never invented."""
    from engine.research_vault import view_ratelimit

    _seed_one(tmp_path)
    _stub_document(monkeypatch, "the argument")

    def _boom(user_id, ip, root=None, now=None):
        raise OSError("state dir is read-only")

    monkeypatch.setattr(view_ratelimit, "allow", _boom)
    result = _report(tmp_path, "gs-oil-1")
    assert result["report"]["body_text"] == "the argument"
    assert result["quota"] == {"remaining": None, "limit": None}


def test_a_denied_view_is_honest_and_leaks_no_body(tmp_path, monkeypatch):
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "the paid argument")
    _stub_quota(monkeypatch, allowed=False, limit=60)

    result = _report(tmp_path, "gs-oil-1")
    assert result["error"] == "view_limit_reached"
    assert result["remaining"] == 0
    assert result["limit"] == 60
    assert "hourly" in result["note"].lower()
    assert "resets" in result["note"].lower()
    assert "report" not in result, "no content is served past the cap"
    assert "paid argument" not in json.dumps(result)


def test_an_unknown_report_id_tells_the_model_to_search_again(tmp_path, monkeypatch):
    _seed_one(tmp_path)
    reads: list = []
    _stub_document(monkeypatch, "body", calls=reads)
    debits: list = []
    _stub_quota(monkeypatch, calls=debits)

    result = _report(tmp_path, "hallucinated-id")
    assert result["error"] == "report_not_found"
    assert result["report_id"] == "hallucinated-id"
    assert "search_research" in result["note"], "the model is told how to recover"
    assert "never guess" in result["note"].lower()
    assert reads == [], "an id the catalog does not carry never reaches the corpus"
    assert debits == []


@pytest.mark.parametrize("report_id", ["", None, "  ", "../../etc/passwd", 17])
def test_a_missing_or_malformed_report_id_is_not_found_not_a_crash(
        tmp_path, monkeypatch, report_id):
    _seed_one(tmp_path)
    reads: list = []
    _stub_document(monkeypatch, "body", calls=reads)
    result = _report(tmp_path, report_id)
    assert result["error"] == "report_not_found"
    assert reads == []


def test_no_user_ctx_is_pro_required_and_fails_closed(tmp_path, monkeypatch):
    """The gateway owns the tier decision; this is the fail-safe under it. An
    unmeterable serve of third-party research is exactly what the cap prevents."""
    _seed_one(tmp_path)
    reads: list = []
    _stub_document(monkeypatch, "the paid argument", calls=reads)
    debits: list = []
    _stub_quota(monkeypatch, calls=debits)

    for ctx in (None, {}, {"user_id": ""}, {"user_id": "   "}, {"ip_hint": "1.2.3.4"}):
        result = _report(tmp_path, "gs-oil-1", user_ctx=ctx)
        assert result["error"] == "pro_required", ctx
        assert "Pro" in result["note"]
        assert "report" not in result
    assert reads == [], "no identity, no corpus read"
    assert debits == []


def test_a_missing_or_corrupt_catalog_reports_the_vault_unavailable(tmp_path, monkeypatch):
    _stub_document(monkeypatch, "body")
    missing = _report(tmp_path, "gs-oil-1")
    assert missing["error"] == "vault_unavailable"
    assert "could not be read" in missing["note"]

    directory = tmp_path / "data" / "research_vault"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "catalog.json").write_text("{not json", encoding="utf-8")
    assert _report(tmp_path, "gs-oil-1")["error"] == "vault_unavailable"


def test_a_corpus_that_raises_never_takes_the_turn_down(tmp_path, monkeypatch):
    """The retrieval-must-not-raise contract, extended to the new R2-backed leg."""
    from engine.research_vault import corpus as corpus_mod
    _seed_one(tmp_path)

    def _boom(doc_id, store_factory=None):
        raise RuntimeError("R2 is down")

    monkeypatch.setattr(corpus_mod, "get_document", _boom)
    result = _report(tmp_path, "gs-oil-1")
    assert result["report"]["body_text"] == "", "degrades to the public excerpt"
    assert result["quota"] is None


def test_a_missing_or_malformed_excerpts_snapshot_still_serves_the_report(
        tmp_path, monkeypatch):
    """Excerpt coverage is partial (384/502 on the committed snapshot), so an
    absent excerpt is normal — an empty list, never a failure."""
    _seed_one(tmp_path, excerpt=None)  # no excerpts.json at all
    _stub_document(monkeypatch, "the argument")
    _stub_quota(monkeypatch)
    assert _report(tmp_path, "gs-oil-1")["report"]["excerpt_paragraphs"] == []

    for payload in ("[]", '{"schema": 1}', '{"schema": 1, "excerpts": []}',
                    '{"schema": 1, "excerpts": {"gs-oil-1": "not a list"}}',
                    "{broken"):
        (tmp_path / "data" / "research_vault" / "excerpts.json").write_text(
            payload, encoding="utf-8")
        report = _report(tmp_path, "gs-oil-1")["report"]
        assert report["excerpt_paragraphs"] == [], payload
        assert report["body_text"] == "the argument", payload


def test_report_mode_is_recognised_case_and_whitespace_insensitively(tmp_path, monkeypatch):
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "body")
    _stub_quota(monkeypatch)
    for mode in ("report", "REPORT", " Report "):
        result = bmi.search_research(tmp_path, "", now=NOW, mode=mode,
                                     report_id="gs-oil-1", user_ctx=_PRO)
        assert result["schema"] == "brain.research_report.v1", mode


def test_report_mode_ignores_the_query_and_the_short_query_gate(tmp_path, monkeypatch):
    """A Pro member asking what ONE note argues is not searching — the 2-token
    gate must not fire on a mode that never reads the query."""
    _seed_one(tmp_path)
    _stub_document(monkeypatch, "the argument")
    _stub_quota(monkeypatch)
    for query in ("", "x", None, "completely unrelated words"):
        result = bmi.search_research(tmp_path, query, now=NOW, mode="report",
                                     report_id="gs-oil-1", user_ctx=_PRO)
        assert result["report"]["body_text"] == "the argument", query
        assert result["note"] != "query too short"


def test_search_and_clusters_never_reach_the_corpus_or_the_ledger(tmp_path, monkeypatch):
    """The escalation is opt-in: the P0/W2 modes stay pure catalog reads, so a
    plain search still costs no R2 fetch and no metered view."""
    _catalog(tmp_path, [
        _note("a", "Tariff One", institution="Citi"),
        _note("b", "Tariff Two", institution="UBS"),
        _note("c", "Tariff Three", institution="ING"),
    ])
    reads: list = []
    debits: list = []
    _stub_document(monkeypatch, "body", calls=reads)
    _stub_quota(monkeypatch, calls=debits)

    bmi.search_research(tmp_path, "tariff one", now=NOW)
    bmi.search_research(tmp_path, "", now=NOW, mode="clusters")
    assert reads == [] and debits == []


@pytest.mark.skipif(
    not (ROOT / "data" / "research_vault" / "catalog.json").exists(),
    reason="data/research_vault/catalog.json not present in this checkout",
)
def test_real_catalog_report_assembles_against_the_committed_vault(monkeypatch):
    """The committed catalog + the committed excerpt snapshot, with only the
    R2-backed body stubbed (there is no bucket in dev). Proves the assembled
    shape against real ids and real public excerpts, at the WALL clock like its
    search and clusters siblings."""
    excerpts = json.loads(
        (ROOT / "data" / "research_vault" / "excerpts.json").read_text(encoding="utf-8")
    )["excerpts"]
    real_id = sorted(excerpts)[0]
    _stub_document(monkeypatch, "REAL BODY " * 3000)
    _stub_quota(monkeypatch)

    result = bmi.search_research(ROOT, "", mode="report", report_id=real_id,
                                 user_ctx=_PRO)
    assert result["schema"] == "brain.research_report.v1"
    report = result["report"]
    assert set(report) == set(bmi.REPORT_FIELDS)
    assert report["id"] == real_id
    assert report["title"] and report["institution"]
    assert report["excerpt_paragraphs"] == excerpts[real_id]
    assert 0 < len(report["body_text"]) <= bmi.REPORT_BODY_MAX_CHARS
    assert report["body_truncated"] is True
    assert report["institution"] in result["note"]
