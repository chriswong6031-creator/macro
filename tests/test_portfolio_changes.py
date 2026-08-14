"""tests/test_portfolio_changes.py — the W6 retention spine.

Covers engine/portfolio_changes.py (state digest + diff + "since your last visit"),
engine/portfolio_digest.py (the change-triggered email COMPOSER), and the
POST /api/portfolio/changes endpoint.

The load-bearing assertions here are the BOUNDARY ones, not the formatting ones:

  * TWO-ORGANISMS LAW — a state digest carries tickers and desk state and nothing else.
    No shares, no cost basis, no entry price, no weights, no user id. Asserted against a
    book whose rows carry all of those, so the test fails if any leaks through.
  * NO MAIL FROM A TEST OR A BUILD — engine/portfolio_digest.py imports no mailer and
    contains no send call, so importing it (here or in a build) cannot deliver anything.
    Asserted from the module's AST, not from a comment promising it.
  * FIRST VISIT IS NOT "EVERYTHING CHANGED" — an absent prior snapshot yields no changes
    and no email.
  * Advice-filter clean + "validated" absent, same bar as the brief composer.
"""
from __future__ import annotations

import ast
import builtins
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.portfolio_changes import (  # noqa: E402
    CURSOR_DISCLOSURE,
    _safe_text,
    MAX_CHANGES,
    MAX_PREVIOUS_NAMES,
    SNAPSHOT_SCHEMA,
    compose_since_section,
    diff_snapshots,
    is_snapshot,
    snapshot_state,
)
from engine.portfolio_digest import compose_digest, idem_key  # noqa: E402
from engine.portfolio_vocab import CLASS_WORD  # noqa: E402
from tests.test_portfolio_brief import BOOKS, TODAY, _ctx  # noqa: E402

# The install set of the CI job that runs this file (portfolio-ctx). An import outside
# this set passes locally and ERRORs on CI; pinned below against the workflow itself.
PACK_DEPS = {"pytest", "pandas", "pyarrow", "jinja2", "fastapi", "httpx", "pydantic",
             "yaml", "requests"}

TICKERS = ["NVDA", "AVGO", "SMCI", "XOM"]


def _snap(ctx=None, tickers=None) -> dict:
    return snapshot_state(ctx if ctx is not None else _ctx(), tickers or TICKERS)


def _moved_ctx() -> dict:
    """The fixture ctx with five independent desk moves applied."""
    c = copy.deepcopy(_ctx())
    c["tickers"]["NVDA"]["stage"]["n"] = 3                      # stage move
    c["tickers"]["AVGO"]["entry"]["state"] = "EXTENDED"          # entry read move
    c["sectors"]["Technology"]["class"] = "headwind"             # board move
    c["regime"]["us"]["label_en"] = "Neutral"                    # regime move
    c["regime"]["us"]["label_zh"] = "中性"
    c["tickers"]["XOM"]["earnings"] = {"next": "2026-07-28", "days_to": 5}  # into window
    return c


# ── the boundary: what a snapshot may carry ──────────────────────────────────

def test_snapshot_carries_no_money_fields():
    """THE law this module exists to keep. The book below carries shares and entry
    prices on every row; none of it may appear in the digest, at any depth."""
    ctx = _ctx()
    holdings = BOOKS["concentrated-semis"]
    assert all(h["shares"] and h["entry_price"] for h in holdings), "fixture must carry money"
    snap = snapshot_state(ctx, [h["ticker"] for h in holdings])

    blob = json.dumps(snap, ensure_ascii=False)
    for money in ("shares", "entry_price", "cost", "weight", "qty", "quantity",
                  "market_value", "pnl", "user_id"):
        assert money not in blob, f"{money} leaked into the state digest"
    # And the actual values, not just the key names.
    for h in holdings:
        assert str(h["entry_price"]) not in blob
        assert f'"{h["shares"]}"' not in blob

    # What it MAY carry: tickers + desk state.
    assert set(snap["names"]) == {h["ticker"] for h in holdings}
    assert snap["names"]["NVDA"]["stage"] == 2


def test_snapshot_shape_and_determinism():
    a, b = _snap(), _snap()
    assert a["schema"] == SNAPSHOT_SCHEMA == "portfolio_state_digest.v1"
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # Ticker order in the input must not change the output.
    assert (json.dumps(_snap(tickers=list(reversed(TICKERS))), sort_keys=True)
            == json.dumps(a, sort_keys=True))


def test_uncovered_names_are_omitted_not_recorded_empty():
    """An uncovered name has no desk state; recording it as {} would diff as a spurious
    change the night coverage arrived."""
    snap = _snap(tickers=["NVDA", "NOTACOVEREDNAME"])
    assert "NOTACOVEREDNAME" not in snap["names"]
    assert "NVDA" in snap["names"]


# ── the diff ─────────────────────────────────────────────────────────────────

def test_first_visit_reports_nothing():
    """No prior snapshot = a first visit. Reporting "everything is new" would spam the
    panel on day one and mail a wall of text on the first digest."""
    cur = _snap()
    assert diff_snapshots({}, cur) == []
    assert diff_snapshots(None, cur) == []
    assert compose_since_section({}, cur) is None


def test_quiet_day_reports_nothing():
    assert diff_snapshots(_snap(), _snap()) == []
    assert compose_since_section(_snap(), _snap()) is None


def test_detects_each_kind_of_desk_move():
    changes = diff_snapshots(_snap(), _snap(_moved_ctx()))
    kinds = {c["kind"] for c in changes}
    assert {"regime", "stage", "entry", "sector_class", "earnings"} <= kinds
    by_kind = {c["kind"]: c for c in changes}
    assert "Stage 2 uptrend" in by_kind["stage"]["en"]
    assert "Stage 3 topping" in by_kind["stage"]["en"]
    assert by_kind["stage"]["ticker"] == "NVDA"
    assert by_kind["earnings"]["ticker"] == "XOM"


def test_membership_changes_are_reported():
    prev = _snap(tickers=["NVDA", "AVGO"])
    cur = _snap(tickers=["NVDA", "XOM"])
    by_kind = {c["kind"]: c for c in diff_snapshots(prev, cur)}
    assert "XOM" in by_kind["added"]["en"]
    assert "AVGO" in by_kind["removed"]["en"]


def test_diff_is_deterministic_and_sorted():
    prev, cur = _snap(), _snap(_moved_ctx())
    a = json.dumps(diff_snapshots(prev, cur), sort_keys=True, ensure_ascii=False)
    b = json.dumps(diff_snapshots(prev, cur), sort_keys=True, ensure_ascii=False)
    assert a == b
    tickers = [c["ticker"] for c in diff_snapshots(prev, cur) if c.get("ticker")]
    assert tickers == sorted(tickers)


def test_since_section_caps_lines_and_names_the_overflow():
    prev, cur = _snap(), _snap(_moved_ctx())
    sec = compose_since_section(prev, cur, cap=2)
    assert sec["key"] == "since"
    assert sec["title_en"] == "Since your last visit"
    assert len(sec["lines"]) == 3          # 2 capped + 1 overflow line
    assert "not shown here" in sec["lines"][-1]["en"]


def test_every_change_line_is_bilingual_and_nonempty():
    for c in diff_snapshots(_snap(), _snap(_moved_ctx())):
        assert c["en"].strip() and c["zh"].strip()
        assert c["en"] != c["zh"]


# ── round-2 review fixes ─────────────────────────────────────────────────────

def test_empty_names_snapshot_is_a_real_visit_not_a_first_visit():
    """Reviewer C3/B2. `snapshot_state` returns `names: {}` for a user whose holdings are
    ALL desk-uncovered (uncovered names are omitted). That is a genuine prior visit, and
    the day one of those names gains coverage the membership change is real. The old
    guard treated it as a first visit and returned changes ALONGSIDE first_visit=true —
    the response contradicting itself. `is_snapshot` is now the single definition both
    sides read. No attacker needed to reach this."""
    previous = {"schema": SNAPSHOT_SCHEMA, "asof": "2026-07-22", "names": {},
                "sectors": {}, "regime_en": "Risk-on"}
    assert is_snapshot(previous) is True
    changes = diff_snapshots(previous, _snap())
    assert changes, "a covered name appearing is a real change"
    assert any(c["kind"] == "added" for c in changes)


def test_is_snapshot_is_the_single_first_visit_definition():
    assert is_snapshot({}) is False           # no prior digest at all
    assert is_snapshot(None) is False
    assert is_snapshot({"names": {}}) is True  # a real visit with nothing covered
    assert is_snapshot(_snap()) is True
    # …and the thing it gates agrees with it.
    assert diff_snapshots({}, _snap()) == []


def test_sector_class_never_ships_a_raw_slug_in_either_language():
    """A4. `class` values are internal slugs; `late` is in the LIVE artifact today. They
    must never reach a sentence — least of all an English token inside Chinese prose."""
    prev = _snap()
    moved = copy.deepcopy(_ctx())
    moved["sectors"]["Technology"]["class"] = "late"
    cur = _snap(moved)
    line = next(c for c in diff_snapshots(prev, cur) if c["kind"] == "sector_class")
    for slug in ("neutral", "late", "entry_now", "headwind", "tailwind", "forming",
                 "buyable"):
        assert slug not in line["zh"], f"raw slug {slug!r} in Chinese prose"
    assert "偏后段" in line["zh"] and "中性" in line["zh"]
    assert "late" in line["en"]


def test_unmapped_class_omits_the_clause_rather_than_printing_the_slug():
    """The fallback that would reintroduce the defect is explicitly absent."""
    prev_ctx = copy.deepcopy(_ctx())
    prev_ctx["sectors"]["Technology"]["class"] = "zzz_new_slug"
    cur_ctx = copy.deepcopy(_ctx())
    cur_ctx["sectors"]["Technology"]["class"] = "headwind"
    changes = diff_snapshots(_snap(prev_ctx), _snap(cur_ctx))
    assert not any(c["kind"] == "sector_class" for c in changes)
    assert "zzz_new_slug" not in json.dumps(changes, ensure_ascii=False)


def test_unmapped_class_still_lets_the_conviction_change_through():
    """Omitting the class clause must not swallow a sibling change that IS renderable."""
    prev_ctx = copy.deepcopy(_ctx())
    prev_ctx["sectors"]["Technology"]["class"] = "zzz_new_slug"
    cur_ctx = copy.deepcopy(_ctx())
    cur_ctx["sectors"]["Technology"]["class"] = "headwind"
    cur_ctx["sectors"]["Technology"]["conviction_en"] = "Reduce"
    cur_ctx["sectors"]["Technology"]["conviction_zh"] = "减配"
    changes = diff_snapshots(_snap(prev_ctx), _snap(cur_ctx))
    assert any(c["kind"] == "sector_conviction" for c in changes)


@pytest.mark.parametrize("hostile", [
    "<img src=x onerror=alert(1)>",
    "Risk-on\nThe desk's daily read moved from A to B",
    "{{constructor.constructor('alert(1)')()}}",
    "x" * 500,
    "ctrl\x07char",
])
def test_client_supplied_text_is_never_echoed_into_desk_prose(hostile):
    """B1. `previous` is client-supplied and its values land inside sentences the SERVER
    composes, shape-identical to desk-authored `headline.en`. A value that fails the
    allowlist is dropped along with its clause — never echoed, never half-cleaned."""
    previous = _snap()
    previous["regime_en"] = hostile
    previous["names"]["NVDA"]["entry"] = hostile
    previous["sectors"]["Technology"]["conviction_en"] = hostile
    blob = json.dumps(diff_snapshots(previous, _snap(_moved_ctx())), ensure_ascii=False)
    assert hostile not in blob
    for frag in ("<img", "onerror", "constructor", "\x07"):
        assert frag not in blob


@pytest.mark.parametrize("invisible", [
    "‮",              # RTL OVERRIDE — reverses rendered order; sentence spoofing
    "⁦", "⁩",    # directional isolates
    "​",              # zero-width space — hides inside a word
    "‎", "‏",    # LTR/RTL marks
    " ", " ",    # line/paragraph separators; JS line terminators
])
def test_invisible_format_characters_cannot_reach_desk_prose(invisible):
    """The character blacklist rejects markup and control codes, but Unicode FORMAT
    characters are invisible and slipped through. U+202E is the classic spoofing
    primitive: it can make a composed desk sentence DISPLAY as something the desk never
    said, and no reviewer eyeballing the payload would see it."""
    previous = _snap()
    previous["regime_en"] = f"Risk{invisible}-on"
    previous["names"]["NVDA"]["entry"] = f"BUY{invisible} ZONE"
    previous["sectors"]["Technology"]["conviction_en"] = f"Cau{invisible}tious"
    blob = json.dumps(diff_snapshots(previous, _snap(_moved_ctx())), ensure_ascii=False)
    assert invisible not in blob
    assert invisible not in json.dumps(
        compose_since_section(previous, _snap(_moved_ctx())), ensure_ascii=False)


def test_the_allowlist_still_passes_every_shape_of_real_copy():
    """The other half of the tightening: a filter that rejects legitimate desk copy would
    silently drop real changes. These are the shapes this estate actually produces —
    CJK, em-dashes, ampersands, dotted and hyphenated tickers, parentheses, slashes."""
    legitimate = [
        "Risk-on", "Risk-off", "Neutral", "Cautious", "Accumulate", "Reduce",
        "BUY ZONE", "FRESH BREAKOUT", "UNCONFIRMED TURN", "COUNTERTREND BOUNCE",
        "bounce, not a turn", "extended — watch", "watching for entry",
        "trend running", "S&P 500", "BRK.B", "BF-B", "Consumer Defensive",
        "Communication Services", "Basic Materials", "Information Technology",
        "谨慎", "积极配置", "减配", "风险偏好", "中性", "顺风", "逆风", "偏后段",
    ]
    rejected = [s for s in legitimate if _safe_text(s) is None]
    assert not rejected, f"the allowlist rejects real desk copy: {rejected}"
    # And the whole set survives a round trip through a rendered change line.
    for word in legitimate[:8]:
        previous = _snap()
        previous["names"]["NVDA"]["entry"] = word
        changes = diff_snapshots(previous, _snap(_moved_ctx()))
        assert any(word in c["en"] for c in changes if c.get("ticker") == "NVDA"), word


def test_class_word_covers_the_producer_vocabulary():
    """The omit-path is deliberate (an unmapped class drops its clause rather than
    printing a slug), but nothing reds when the PRODUCER's vocabulary GROWS. Without this
    a new subsector_confluence class would silently drop a real desk move in production
    instead of failing CI here, where it is one line to fix.

    Read from the producer's own table rather than a copied list, so the check cannot be
    satisfied by a stale duplicate."""
    from engine.subsector_confluence import _CLASS_ORDER  # noqa: PLC0415

    missing = sorted(set(_CLASS_ORDER) - set(CLASS_WORD))
    assert not missing, (
        "engine/subsector_confluence.py publishes these rotation-board classes and "
        "engine/portfolio_vocab.CLASS_WORD has no display word for them, so a change "
        "into or out of them would be silently dropped: %s" % missing)
    # Every mapped word is bilingual and carries no raw slug.
    for slug, (en, zh) in CLASS_WORD.items():
        assert en.strip() and zh.strip()
        assert "_" not in en, f"{slug}: en display word still looks like a slug"


def test_out_of_range_stage_is_dropped_not_rendered_generically():
    """A client-supplied `stage: 999` must not render "moved from Stage 999 stage" —
    that is client text wearing the desk's voice."""
    previous = _snap()
    previous["names"]["NVDA"]["stage"] = 999
    changes = diff_snapshots(previous, _snap(_moved_ctx()))
    assert not any(c["kind"] == "stage" and c["ticker"] == "NVDA" for c in changes)
    assert "999" not in json.dumps(changes, ensure_ascii=False)


def test_output_cardinality_is_bounded():
    """B3, output half. Every name changing stage must not become one sentence per name.

    Built from hand-made snapshots rather than the ctx fixture on purpose: the fixture
    covers 7 tickers, so a diff over it can never approach the cap and a test written
    against it would pass whether or not the cap existed (the first version of this test
    did exactly that — it asserted `<= MAX_CHANGES` on a 2-change diff)."""
    previous = {"names": {f"T{i:04d}": {"stage": 2} for i in range(400)}}
    current = {"names": {f"T{i:04d}": {"stage": 3} for i in range(400)}}
    assert len(diff_snapshots(previous, current)) == MAX_CHANGES


def test_input_cardinality_is_bounded():
    """B3, input half. A 5000-name client snapshot is read only up to the cap."""
    previous = {"names": {f"T{i:04d}": {"stage": 2} for i in range(5000)}}
    removed = next(c for c in diff_snapshots(previous, {"names": {}})
                   if c["kind"] == "removed")
    assert removed["en"].startswith(f"{MAX_PREVIOUS_NAMES} names left")


def test_membership_sentence_does_not_paste_hundreds_of_tickers():
    """A true count is not a readable sentence. The list is capped independently of the
    count, and the remainder is named rather than silently dropped."""
    previous = {"names": {}}
    current = {"names": {f"T{i:04d}": {"stage": 2} for i in range(100)}}
    added = next(c for c in diff_snapshots(previous, current) if c["kind"] == "added")
    assert added["en"].startswith("100 names joined")
    assert "and 80 more" in added["en"]
    assert added["en"].count(",") <= 21     # 20 listed names + the "and N more" comma
    assert "等 80 只" in added["zh"]


def test_cursor_scope_is_disclosed_in_the_payload():
    """B4. The per-device limitation is disclosed where users are, not only in a PR
    body — the same mechanism `population.disclosure_*` uses to make silence visible."""
    assert CURSOR_DISCLOSURE["scope"] == "device"
    assert CURSOR_DISCLOSURE["note_en"].strip() and CURSOR_DISCLOSURE["note_zh"].strip()
    assert CURSOR_DISCLOSURE["note_en"] != CURSOR_DISCLOSURE["note_zh"]


# ── the digest composer ──────────────────────────────────────────────────────

def test_digest_module_cannot_send_mail():
    """Enforced structurally, not by discipline: engine/portfolio_digest.py imports no
    mailer and makes no send call, so no test and no build step that imports it can
    deliver anything to a human."""
    src = (ROOT / "engine" / "portfolio_digest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert "mailer" not in name and not name.startswith("app."), \
                f"the digest composer must not import a send path: {name}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("send", "sendmail", "send_message"), \
                "the digest composer must not call a send path"


def test_digest_is_none_on_a_quiet_day():
    """PSI §19.5: a quiet day sends NOTHING."""
    assert compose_digest(_snap(), _snap(), user_id="u1", asof="2026-07-23") is None
    assert compose_digest({}, _snap(), user_id="u1", asof="2026-07-23") is None


def test_digest_composes_on_change_with_the_send_arguments():
    d = compose_digest(_snap(), _snap(_moved_ctx()), user_id="u1", asof="2026-07-23",
                       population="positions")
    assert d is not None
    assert d["cls"] == "marketing"          # recurring bulk, never transactional
    assert d["idem_key"] == "psi_digest:u1:2026-07-23"
    assert d["change_count"] >= 5
    assert d["subject"] and d["title_zh"]
    assert d["blocks"]


def test_digest_idem_key_is_one_per_user_day():
    assert idem_key("u1", "2026-07-23") != idem_key("u1", "2026-07-24")
    assert idem_key("u1", "2026-07-23") != idem_key("u2", "2026-07-23")


def test_digest_names_the_population_it_describes():
    """A8 reaches the inbox too: an email about a watchlist must not say "your book"."""
    prev, cur = _snap(), _snap(_moved_ctx())
    wl = compose_digest(prev, cur, user_id="u1", asof="2026-07-23",
                        population="watchlist_union")
    blob = json.dumps(wl, ensure_ascii=False).lower()
    assert "your watchlist" in blob
    assert "your book" not in blob
    pos = compose_digest(prev, cur, user_id="u1", asof="2026-07-23",
                         population="positions")
    assert "your book" in json.dumps(pos, ensure_ascii=False).lower()


def test_digest_carries_no_money_fields():
    d = compose_digest(_snap(), _snap(_moved_ctx()), user_id="u1", asof="2026-07-23",
                       population="positions")
    blob = json.dumps(d, ensure_ascii=False)
    for money in ("shares", "entry_price", "cost_basis", "market_value", "pnl"):
        assert money not in blob


# ── ADVERSARIAL: the same copy bar as the brief ──────────────────────────────

def _all_strings(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _all_strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _all_strings(v)]
    return []


def test_no_change_or_digest_line_matches_the_advice_filter():
    from engine.neuralweb.ask_brain import _ADVICE_PATTERNS  # noqa: PLC0415
    payloads = [
        diff_snapshots(_snap(), _snap(_moved_ctx())),
        compose_since_section(_snap(), _snap(_moved_ctx())),
        compose_digest(_snap(), _snap(_moved_ctx()), user_id="u1", asof="2026-07-23",
                       population="positions"),
    ]
    offenders = []
    for payload in payloads:
        for s in _all_strings(payload):
            for p in _ADVICE_PATTERNS:
                if p.search(s):
                    offenders.append((p.pattern, s))
    assert not offenders, f"advice-filter matches: {offenders}"


def test_no_validated_and_no_refutation_language():
    """"validated" is CI-enforced; falsifier/refutation vocabulary is never front-facing
    (operator 2026-07-27) — these are "what changed" lines, not verdicts on a thesis."""
    payloads = [
        diff_snapshots(_snap(), _snap(_moved_ctx())),
        compose_digest(_snap(), _snap(_moved_ctx()), user_id="u1", asof="2026-07-23"),
    ]
    for payload in payloads:
        blob = json.dumps(payload, ensure_ascii=False)
        low = blob.lower()
        assert "validated" not in low
        for banned in ("falsifi", "refut", "invalidated", "thesis failed"):
            assert banned not in low, f"{banned} is not front-facing language"
        for banned_zh in ("证伪", "已验证"):
            assert banned_zh not in blob


# ── endpoint smoke (guarded: skips when fastapi/httpx unavailable) ───────────

def _client(monkeypatch, tmp_path, *, tier="pro", ctx=None, holdings=None,
            population="positions"):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient  # noqa: PLC0415

    repo = tmp_path
    (repo / "site" / "data").mkdir(parents=True, exist_ok=True)
    if ctx is not None:
        (repo / "site" / "data" / "portfolio_ctx.json").write_text(
            json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("MACRO_REPO", str(repo))
    for mod in list(sys.modules):
        if mod == "app.main" or mod.startswith("app.main."):
            del sys.modules[mod]
    import app.main as m  # noqa: PLC0415

    m.app.dependency_overrides[m.require_user] = lambda: {"id": "u-test", "email": "t@x.co"}
    monkeypatch.setattr(m, "_portfolio_resolve_tier",
                        lambda uid: {"tier": tier, "status": "active"})
    monkeypatch.setattr(m, "_portfolio_load_holdings",
                        lambda uid: ((holdings if holdings is not None
                                      else [{"ticker": t} for t in TICKERS]), population))
    return m, TestClient(m.app)


def test_changes_endpoint_first_visit(monkeypatch, tmp_path):
    m, client = _client(monkeypatch, tmp_path, ctx=_ctx())
    r = client.post("/api/portfolio/changes", json={},
                    headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["first_visit"] is True
    assert body["changes"] == []
    assert body["state_digest"]["schema"] == SNAPSHOT_SCHEMA
    assert r.headers.get("Cache-Control") == "private, no-store"
    m.app.dependency_overrides.clear()


def test_changes_endpoint_returns_the_diff(monkeypatch, tmp_path):
    """Round trip: the digest the client stored last visit goes back up, and the desk's
    moves since come back down."""
    previous = _snap()
    m, client = _client(monkeypatch, tmp_path, ctx=_moved_ctx())
    r = client.post("/api/portfolio/changes", json={"previous": previous},
                    headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["first_visit"] is False
    assert {c["kind"] for c in body["changes"]} >= {"stage", "regime"}
    assert body["population"] == "positions"
    m.app.dependency_overrides.clear()


def test_changes_endpoint_is_pro_gated(monkeypatch, tmp_path):
    m, client = _client(monkeypatch, tmp_path, tier="free", ctx=_ctx())
    r = client.post("/api/portfolio/changes", json={},
                    headers={"Authorization": "Bearer x"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["error"] == "pro_required"
    m.app.dependency_overrides.clear()


def test_changes_endpoint_503_without_ctx(monkeypatch, tmp_path):
    m, client = _client(monkeypatch, tmp_path, ctx=None)
    r = client.post("/api/portfolio/changes", json={},
                    headers={"Authorization": "Bearer x"})
    assert r.status_code == 503, r.text
    m.app.dependency_overrides.clear()


def test_changes_endpoint_first_visit_flag_agrees_with_its_changes(monkeypatch, tmp_path):
    """B2 at the API tier: the empty-names snapshot must not come back as
    first_visit=true alongside a non-empty changes list."""
    previous = {"schema": SNAPSHOT_SCHEMA, "asof": "2026-07-22", "names": {},
                "sectors": {}, "regime_en": "Risk-on"}
    m, client = _client(monkeypatch, tmp_path, ctx=_ctx())
    r = client.post("/api/portfolio/changes", json={"previous": previous},
                    headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["first_visit"] is False
    assert body["changes"]
    # The invariant, stated once: the two fields can never disagree.
    assert body["first_visit"] == (not body["changes"] and body["first_visit"])
    m.app.dependency_overrides.clear()


def test_changes_endpoint_discloses_the_cursor_scope(monkeypatch, tmp_path):
    m, client = _client(monkeypatch, tmp_path, ctx=_ctx())
    r = client.post("/api/portfolio/changes", json={},
                    headers={"Authorization": "Bearer x"})
    assert r.json()["cursor"]["scope"] == "device"
    m.app.dependency_overrides.clear()


# ── A1/A2/A3: the population is never a guess, including on error paths ──────

def _loader_with(monkeypatch, tmp_path, sb_get):
    """Load app.main with brain_gateway._sb_get stubbed, exercising the REAL loader."""
    pytest.importorskip("fastapi")
    repo = tmp_path
    (repo / "site" / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MACRO_REPO", str(repo))
    for mod in list(sys.modules):
        if mod == "app.main" or mod.startswith("app.main."):
            del sys.modules[mod]
    import app.main as m  # noqa: PLC0415
    import engine.neuralweb.brain_gateway as gw  # noqa: PLC0415
    monkeypatch.setattr(gw, "_sb_get", sb_get)
    return m


def test_failed_positions_query_is_unspecified_not_watchlist_union(monkeypatch, tmp_path):
    """A2 — the blocker. `_sb_get` returns None for a missing env var, a 5s timeout, a
    PostgREST 5xx and bad JSON alike; [] means genuinely no rows. Collapsing them told a
    Pro user with ten open positions "Watchlist structure — equal weighted" whenever
    Supabase blinked."""
    def sb_get(path):
        if "portfolio_positions" in path:
            return None                      # the query FAILED
        if "watchlists?" in path:
            return [{"id": "L1"}]
        return [{"symbol": "NVDA"}]
    m = _loader_with(monkeypatch, tmp_path, sb_get)
    rows, population = m._portfolio_load_holdings("u1")
    assert population == "unspecified"
    assert rows == []


def test_genuinely_empty_positions_still_falls_through_to_watchlist(monkeypatch, tmp_path):
    """The other half of A2: [] is a real answer and must NOT be treated as a failure,
    or the watchlist path would become unreachable."""
    def sb_get(path):
        if "portfolio_positions" in path:
            return []                        # genuinely no open positions
        if "watchlists?" in path:
            return [{"id": "L1"}]
        return [{"symbol": "NVDA"}]
    m = _loader_with(monkeypatch, tmp_path, sb_get)
    rows, population = m._portfolio_load_holdings("u1")
    assert population == "watchlist_union"
    assert [r["ticker"] for r in rows] == ["NVDA"]


@pytest.mark.parametrize("failing", ["watchlists?", "watchlist_symbols"])
def test_failed_watchlist_queries_are_also_unspecified(monkeypatch, tmp_path, failing):
    def sb_get(path):
        if "portfolio_positions" in path:
            return []
        if failing in path:
            return None
        if "watchlists?" in path:
            return [{"id": "L1"}]
        return [{"symbol": "NVDA"}]
    m = _loader_with(monkeypatch, tmp_path, sb_get)
    _rows, population = m._portfolio_load_holdings("u1")
    assert population == "unspecified"


def test_positions_query_success_reports_positions(monkeypatch, tmp_path):
    def sb_get(path):
        if "portfolio_positions" in path:
            return [{"ticker": "NVDA", "shares": 10, "entry_price": 100.0}]
        return None
    m = _loader_with(monkeypatch, tmp_path, sb_get)
    rows, population = m._portfolio_load_holdings("u1")
    assert population == "positions"
    assert len(rows) == 1


def test_import_failure_reports_unspecified_not_positions(monkeypatch, tmp_path):
    """A1 — when the gateway import fails, NO query ran, so nothing about the population
    is known. Hard-coding "positions" told a Pro user with ten real positions "This read
    describes the 0 names you hold."."""
    pytest.importorskip("fastapi")
    repo = tmp_path
    (repo / "site" / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MACRO_REPO", str(repo))
    for mod in list(sys.modules):
        if mod == "app.main" or mod.startswith("app.main."):
            del sys.modules[mod]
    import app.main as m  # noqa: PLC0415

    real_import = builtins.__import__

    def boom(name, *a, **kw):
        if name == "engine.neuralweb.brain_gateway":
            raise ImportError("simulated gateway import failure")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", boom)
    rows, population = m._portfolio_load_holdings("u1")
    assert (rows, population) == ([], "unspecified")


def test_two_error_paths_no_longer_claim_opposite_populations(monkeypatch, tmp_path):
    """The tell that neither old answer was evidence-based: the import-failure path
    claimed `positions` while the query-failure path claimed `watchlist_union` — for the
    same state of knowledge, which is none."""
    def sb_get(path):
        return None
    m = _loader_with(monkeypatch, tmp_path, sb_get)
    _rows, query_fail = m._portfolio_load_holdings("u1")
    assert query_fail == "unspecified"


def test_brain_gateway_loader_also_refuses_to_guess(monkeypatch, tmp_path):
    """A2 applies to BOTH loaders. The gateway has its own inline copy of the
    positions→watchlist fallback, so fixing only app.main would leave the Brain tool
    telling a user "your watchlist" about a position book — the silent sibling."""
    import engine.neuralweb.brain_gateway as gw  # noqa: PLC0415

    repo = tmp_path
    (repo / "site" / "data").mkdir(parents=True, exist_ok=True)
    (repo / "site" / "data" / "portfolio_ctx.json").write_text(
        json.dumps(_ctx(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "pro", "status": "active"})

    # positions query FAILS, watchlist would answer → must NOT claim watchlist_union.
    monkeypatch.setattr(gw, "_sb_get",
                        lambda path: None if "portfolio_positions" in path
                        else ([{"id": "L1"}] if "watchlists?" in path
                              else [{"symbol": "NVDA"}]))
    out = gw._tool_get_portfolio_brief({}, repo, user_id="u1")
    assert out["population"]["mode"] == "unspecified", out["population"]

    # genuinely empty positions → watchlist_union is correct and still reachable.
    monkeypatch.setattr(gw, "_sb_get",
                        lambda path: [] if "portfolio_positions" in path
                        else ([{"id": "L1"}] if "watchlists?" in path
                              else [{"symbol": "NVDA"}]))
    out = gw._tool_get_portfolio_brief({}, repo, user_id="u1")
    assert out["population"]["mode"] == "watchlist_union"

    # real positions → positions.
    monkeypatch.setattr(gw, "_sb_get",
                        lambda path: [{"ticker": "NVDA", "shares": 10,
                                       "entry_price": 100.0}]
                        if "portfolio_positions" in path else None)
    out = gw._tool_get_portfolio_brief({}, repo, user_id="u1")
    assert out["population"]["mode"] == "positions"


def test_cache_key_covers_population_change(monkeypatch, tmp_path):
    """A3 — the cached brief embeds the population, which is Supabase-derived and
    invisible to (uid, ctx-mtime). A user adding their first position kept a cached
    `watchlist_union` brief for 5 minutes while /api/portfolio/changes reported
    `positions` — two live endpoints disagreeing about the same book."""
    pytest.importorskip("fastapi")
    repo = tmp_path
    (repo / "site" / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MACRO_REPO", str(repo))
    for mod in list(sys.modules):
        if mod == "app.main" or mod.startswith("app.main."):
            del sys.modules[mod]
    import app.main as m  # noqa: PLC0415

    watchlist = ([{"ticker": "NVDA", "shares": None, "entry_price": None}],
                 "watchlist_union")
    positions = ([{"ticker": "NVDA", "shares": 10, "entry_price": 100.0}], "positions")
    assert m._holdings_fingerprint(*watchlist) != m._holdings_fingerprint(*positions)
    # Same rows, different population → still a different key.
    assert (m._holdings_fingerprint(watchlist[0], "watchlist_union")
            != m._holdings_fingerprint(watchlist[0], "unspecified"))
    # Same everything → stable key (the cache must still work).
    assert m._holdings_fingerprint(*positions) == m._holdings_fingerprint(*positions)
    # And it holds no user data in the clear.
    assert "NVDA" not in m._holdings_fingerprint(*positions)


def test_brief_endpoint_reflects_a_population_change_immediately(monkeypatch, tmp_path):
    """The A3 defect end-to-end: two calls inside the TTL, holdings changed between."""
    state = {"holdings": ([{"ticker": "NVDA", "shares": None, "entry_price": None}],
                          "watchlist_union")}
    m, client = _client(monkeypatch, tmp_path, ctx=_ctx())
    monkeypatch.setattr(m, "_portfolio_load_holdings", lambda uid: state["holdings"])
    r1 = client.get("/api/portfolio/brief", headers={"Authorization": "Bearer x"})
    assert r1.json()["population"]["mode"] == "watchlist_union"
    state["holdings"] = ([{"ticker": "NVDA", "shares": 10, "entry_price": 100.0}],
                         "positions")
    r2 = client.get("/api/portfolio/brief", headers={"Authorization": "Bearer x"})
    assert r2.json()["population"]["mode"] == "positions", \
        "the cache served a stale population"
    m.app.dependency_overrides.clear()


# ── the runner contract: this file's imports must match its CI job ───────────

def test_imports_stay_inside_the_pack_install_set():
    """This file's import surface is part of its contract with the runner. An import
    outside the job's install set passes locally and ERRORs on CI."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    stdlib = getattr(sys, "stdlib_module_names", set())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if (not top or top in stdlib or top in PACK_DEPS or top == "__future__"
                    or top in ("engine", "tests", "app", "scripts")):
                continue
            offenders.append(name)
    assert not offenders, (
        "these imports are not in the pack's install set %s — they pass locally and "
        "ERROR on CI: %s" % (sorted(PACK_DEPS), sorted(set(offenders))))


def test_the_pack_dep_list_matches_the_job_that_runs_this_file():
    """PACK_DEPS above is a copy of a list that lives in the workflow. A copy that can
    drift is worse than no copy, so it is checked against the source of truth."""
    import re  # noqa: PLC0415

    wf = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text(encoding="utf-8")
    job = wf[wf.index("  portfolio-ctx:"):]
    marker = "\n  options-estate-guards:"
    job = job[:job.index(marker)] if marker in job else job
    assert "tests/test_portfolio_changes.py" in job, \
        "this suite is no longer run by portfolio-ctx — PACK_DEPS is pinned to the wrong job"
    m = re.search(r"run: pip install ([^\n]+)", job)
    assert m, "the install line moved"
    installed = {d.strip() for d in m.group(1).split()}
    installed = {"yaml" if d == "pyyaml" else d for d in installed}
    assert installed == PACK_DEPS, (
        "the job's install set moved; update PACK_DEPS deliberately. "
        "job=%s PACK_DEPS=%s" % (sorted(installed), sorted(PACK_DEPS)))
