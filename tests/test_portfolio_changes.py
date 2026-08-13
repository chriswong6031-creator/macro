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
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.portfolio_changes import (  # noqa: E402
    SNAPSHOT_SCHEMA,
    compose_since_section,
    diff_snapshots,
    snapshot_state,
)
from engine.portfolio_digest import compose_digest, idem_key  # noqa: E402
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
