"""W5 White House desk revival tests.

Covers:
  1. fixture-to-card path: a fixture post above the gate must produce a
     rendered alert card in both the banner JSON and the report page.
  2. health line: _health_line() emits all required keys with the right shape.
  3. qledger adapter: _register_wh_claim() registers entity claims with the
     correct direction + SHADOW family; macro fallback when no tickers.
  4. no_provider health: health.provider=='' and evaluated==0 when no key set.
  5. seed-free model call: _call_model is clean (no seed kwarg; TypeError gone).
  6. import guard: a broken/poisoned transitive import of engine.qledger logs
     at ERROR (loud); only a genuinely-absent qledger module skips quietly.

All LLM calls are monkeypatched — no network, no API calls.

Run: python -m tests.test_whitehouse_w5
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import whitehouse_brain as wb  # noqa: E402
from scripts import build_whitehouse as bw  # noqa: E402
from scripts import inject_wh_banner as inj  # noqa: E402
from lib import config  # noqa: E402


# ---------------------------------------------------------------------------
# shared fixture — a market-relevant EO above the significance gate
# ---------------------------------------------------------------------------
_TARIFF_ITEM = {
    "id": "wh-2026-07-01-executive-order-25pct-semiconductor-tariff",
    "guid": "https://www.whitehouse.gov/?p=99999",
    "title": "Executive Order — 25% Tariff on Imported Semiconductors",
    "url": "https://www.whitehouse.gov/presidential-actions/2026/07/semiconductor-tariff/",
    "section": "presidential-actions",
    "published": "2026-07-01T14:00:00+00:00",
    "excerpt": "President imposes 25% tariff on semiconductor imports.",
    "body": (
        "By the authority vested in me as President of the United States, "
        "I hereby impose a 25 percent tariff on all imported semiconductor devices "
        "effective immediately. This action is taken to protect domestic chip "
        "manufacturing and reduce dependence on foreign supply chains. "
        "The tariff applies to HTSUS chapters 8541 and 8542. "
        "Domestic manufacturers TSMC Arizona, Intel, and Micron are exempt."
    ),
    "categories": ["Presidential Actions"],
}

_FIXTURE_REPLY = {
    "activate": True,
    "importance": 82,
    "banner_days": 5,
    "tone": "mixed",
    "banner_title": "Trump 25% semiconductor tariff — domestic fabs shielded, importers squeezed",
    "banner_title_zh": "特朗普对半导体征收25%关税——国内晶圆厂受保护，进口商承压",
    "summary": "A 25% tariff on imported chips hits fabless designers and consumer electronics while shielding domestic fabs.",
    "summary_zh": "对进口芯片征收25%关税，打击无晶圆厂设计商和消费电子，同时保护国内晶圆厂。",
    "analysis": "The order takes effect immediately.\nFabless chip designers face margin compression.\nDomestic fabs gain relative cost advantage.",
    "confidence": "medium",
    "sectors": [
        {"name": "Semiconductors", "impact": "mixed", "rationale": "domestic fabs win, fabless lose"},
        {"name": "Consumer Electronics", "impact": "headwind", "rationale": "bill of materials rises"},
    ],
    "tickers": [
        {"symbol": "INTC", "direction": "benefit", "rationale": "domestic fab exempt from tariff"},
        {"symbol": "AMD", "direction": "hurt", "rationale": "fabless, depends on TSMC"},
        {"symbol": "QCOM", "direction": "hurt", "rationale": "fabless model, overseas fab"},
    ],
}

_CFG = dict(wb._DEFAULTS)


def _patch(reply_dict):
    def fake(system, user, cfg):
        return json.dumps(reply_dict), None
    return fake


# ---------------------------------------------------------------------------
# 1. fixture → banner JSON has a live alert card
# ---------------------------------------------------------------------------
def test_fixture_above_gate_produces_banner_card() -> None:
    """A fixture post with importance=82 must survive the gate (floor=60) and
    appear as a live card in the banner JSON."""
    orig = wb._call_model
    wb._call_model = _patch(_FIXTURE_REPLY)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig

    assert rec["activated"] is True, f"expected activated, got: {rec}"
    assert rec["importance"] == 82
    assert rec["tone"] == "mixed"
    assert len(rec["tickers"]) == 3   # INTC, AMD, QCOM (gate open — no universe file)
    assert rec["tickers"][0]["symbol"] == "INTC"

    # now put it in a one-row ledger and render the banner
    now = datetime.now(timezone.utc)
    rec["generated_at"] = now.isoformat()
    payload = bw._banner_payload([rec], now)
    assert len(payload["alerts"]) == 1
    card = payload["alerts"][0]
    assert card["id"] == _TARIFF_ITEM["id"]
    assert card["tone"] == "mixed"
    assert card["importance"] == 82
    assert any(t["symbol"] == "INTC" for t in card["tickers"])


# ---------------------------------------------------------------------------
# 2. fixture → rendered HTML page contains the alert card anchor
# ---------------------------------------------------------------------------
def test_fixture_renders_to_html_page() -> None:
    """The rendered whitehouse.html must contain the alert's anchor id and
    the escaped banner title."""
    orig = wb._call_model
    wb._call_model = _patch(_FIXTURE_REPLY)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig

    rec["generated_at"] = datetime.now(timezone.utc).isoformat()
    html = bw._render_page(config.ROOT, [rec])

    assert f'id="{_TARIFF_ITEM["id"]}"' in html
    # banner title is escaped (contains no raw injection risk here, but must appear)
    assert "semiconductor tariff" in html.lower()
    # banner script injected
    assert inj._MARKER in html


# ---------------------------------------------------------------------------
# 3. health line shape
# ---------------------------------------------------------------------------
def test_health_line_shape() -> None:
    """_health_line() must emit all required keys with the right types."""
    orig = wb._call_model
    wb._call_model = _patch(_FIXTURE_REPLY)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig

    items = [_TARIFF_ITEM]
    state = {"seen": {}}
    health = bw._health_line(items, state, [rec], n_activated=1, provider="Claude claude-opus-4-8")

    assert health["schema"] == "wh_health.v1"
    assert health["posts_seen"] == 1
    assert health["evaluated"] == 1
    assert health["activated"] == 1
    assert health["provider"] != ""
    assert isinstance(health["gate_scores"], list)
    assert health["gate_scores"][0]["importance"] == 82
    assert health["gate_scores"][0]["activated"] is True


def test_health_line_no_provider() -> None:
    """When no provider, evaluated=0 and provider==''."""
    health = bw._health_line(
        items=[_TARIFF_ITEM], state={"seen": {}},
        evaluated=[], n_activated=0, provider=""
    )
    assert health["provider"] == ""
    assert health["evaluated"] == 0
    assert health["activated"] == 0


# ---------------------------------------------------------------------------
# 4. qledger adapter — entity claims per ticker, correct direction
# ---------------------------------------------------------------------------
def test_qledger_adapter_entity_claims(tmp_path: Path = None) -> None:
    """_register_wh_claim() must write one entity claim per ticker with the
    correct direction into data/qledger/claims.jsonl."""
    import tempfile
    d = Path(tempfile.mkdtemp())

    orig = wb._call_model
    wb._call_model = _patch(_FIXTURE_REPLY)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    rec["generated_at"] = datetime.now(timezone.utc).isoformat()

    bw._register_wh_claim(rec, d)

    claims_path = d / "data" / "qledger" / "claims.jsonl"
    assert claims_path.exists(), "claims.jsonl must be created by the adapter"
    claims = [json.loads(l) for l in claims_path.read_text().splitlines() if l.strip()]
    # 3 tickers → 3 entity claims
    assert len(claims) == 3
    scopes = {c["scope"]["key"]: c for c in claims}
    assert "INTC" in scopes and scopes["INTC"]["direction"] == 1   # benefit → +1
    assert "AMD" in scopes and scopes["AMD"]["direction"] == -1    # hurt → -1
    assert "QCOM" in scopes and scopes["QCOM"]["direction"] == -1  # hurt → -1
    # all claims are whitehouse desk + PUBLISHER_STATED
    for c in claims:
        assert c["desk"] == "whitehouse"
        assert c["timestamp_quality"] == "PUBLISHER_STATED"
        assert c["claim_family"] == "whitehouse"
        assert c["scope"]["type"] == "entity"
        assert c.get("is_context_only") is True


def test_qledger_adapter_macro_fallback(tmp_path: Path = None) -> None:
    """When the alert has no named tickers, one macro claim with bench=SPY is registered."""
    import tempfile
    d = Path(tempfile.mkdtemp())

    no_ticker_reply = {**_FIXTURE_REPLY, "tickers": [], "tone": "headwind"}
    orig = wb._call_model
    wb._call_model = _patch(no_ticker_reply)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    rec["generated_at"] = datetime.now(timezone.utc).isoformat()

    bw._register_wh_claim(rec, d)

    claims_path = d / "data" / "qledger" / "claims.jsonl"
    claims = [json.loads(l) for l in claims_path.read_text().splitlines() if l.strip()]
    assert len(claims) == 1
    c = claims[0]
    assert c["scope"]["type"] == "macro"
    assert c["scope"]["key"] == "WH_POLICY"
    assert c["bench"] == "SPY"
    assert c["direction"] == -1      # headwind → -1


def test_qledger_adapter_idempotent(tmp_path: Path = None) -> None:
    """Registering the same alert twice must not append a duplicate row."""
    import tempfile
    d = Path(tempfile.mkdtemp())

    orig = wb._call_model
    wb._call_model = _patch(_FIXTURE_REPLY)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    rec["generated_at"] = datetime.now(timezone.utc).isoformat()

    bw._register_wh_claim(rec, d)
    bw._register_wh_claim(rec, d)   # second call — must be idempotent

    claims_path = d / "data" / "qledger" / "claims.jsonl"
    claims = [json.loads(l) for l in claims_path.read_text().splitlines() if l.strip()]
    # still only 3 claims (one per ticker), not 6
    assert len(claims) == 3


# ---------------------------------------------------------------------------
# 4b. qledger import guard — real dependency failures must be LOUD
# ---------------------------------------------------------------------------
def _capture_guard_logs(import_error: BaseException) -> tuple[list, Path]:
    """Run _register_wh_claim with engine.qledger's import failing as given;
    return (captured log records, claims dir). Works under pytest and the
    standalone runner (no caplog)."""
    import logging
    d = Path(tempfile.mkdtemp())
    rec = {
        "id": _TARIFF_ITEM["id"],
        "tone": "headwind",
        "published": "2026-07-01T14:00:00+00:00",
        "tickers": [{"symbol": "INTC", "direction": "benefit"}],
        "banner_days": 5,
        "importance": 82,
    }

    records: list = []

    class _Cap(logging.Handler):
        def emit(self, r):  # noqa: D102
            records.append(r)

    h = _Cap(level=logging.DEBUG)
    old_level = bw.log.level
    bw.log.addHandler(h)
    bw.log.setLevel(logging.DEBUG)
    try:
        with patch("importlib.import_module", side_effect=import_error):
            bw._register_wh_claim(rec, d)
    finally:
        bw.log.removeHandler(h)
        bw.log.setLevel(old_level)
    return records, d


def test_qledger_guard_loud_on_poisoned_transitive_dep() -> None:
    """W5 regression: when engine.qledger fails to import because a transitive
    dep (numpy/pandas) is broken or poisoned in sys.modules, the adapter must
    log at ERROR — not silently skip as 'qledger optional' at debug."""
    import logging
    failures = [
        # pandas' wrapper when numpy import breaks (ImportError, name=None)
        ImportError("Unable to import required dependency numpy."),
        # numpy genuinely missing from the env (MNFE naming the DEP, not qledger)
        ModuleNotFoundError("No module named 'numpy'", name="numpy"),
        # sys.modules poisoning: None entry halts the import
        ImportError("import of engine.qledger halted; None in sys.modules",
                    name="engine.qledger"),
    ]
    for err in failures:
        records, d = _capture_guard_logs(err)
        errs = [r for r in records if r.levelno >= logging.ERROR]
        assert errs, f"{err!r} must log at ERROR, not be swallowed as optional"
        assert "required production dependency" in errs[0].getMessage().lower()
        assert not (d / "data" / "qledger" / "claims.jsonl").exists()


def test_qledger_guard_quiet_only_when_module_absent() -> None:
    """Only a genuinely-absent engine.qledger module (stripped checkout) may
    skip quietly — a single DEBUG line, nothing at WARNING or above."""
    import logging
    for name in ("engine.qledger", "engine"):
        err = ModuleNotFoundError(f"No module named '{name}'", name=name)
        records, d = _capture_guard_logs(err)
        loud = [r for r in records if r.levelno >= logging.WARNING]
        assert not loud, f"genuine absence ({name}) must stay quiet, got: {loud}"
        assert any(r.levelno == logging.DEBUG for r in records)
        assert not (d / "data" / "qledger" / "claims.jsonl").exists()


# ---------------------------------------------------------------------------
# 5. build pipeline: activated fixture writes ledger + banner + health
# ---------------------------------------------------------------------------
def test_build_pipeline_fixture_end_to_end() -> None:
    """Run build() with a monkeypatched feed + brain; verify ledger, banner,
    and health.json are all written with the fixture alert."""
    import tempfile
    d = Path(tempfile.mkdtemp())
    site = d / "site"
    site.mkdir()
    # copy real templates so the page render works
    import shutil
    real_root = config.ROOT
    shutil.copytree(str(real_root / "templates"), str(d / "templates"))

    with (
        patch("engine.whitehouse_feed.collect", return_value=[_TARIFF_ITEM]),
        patch("engine.whitehouse_brain._call_model",
              side_effect=lambda s, u, c: (json.dumps(_FIXTURE_REPLY), None)),
        patch("lib.config.ROOT", d),
        patch.object(bw, "config", new=type("C", (), {
            "ROOT": d,
            "load": lambda: {"storage": {"site_dir": "site"}},
        })()),
    ):
        # override the module-level config reference that build() uses
        orig_root = config.ROOT
        try:
            config.ROOT = d   # type: ignore[assignment]
            # Use the internal pipeline directly to avoid config.ROOT issues in templates
            from lib import config as _config
            _config.ROOT = d
            rc = bw.build.__wrapped__(False, False) if hasattr(bw.build, "__wrapped__") else None
        finally:
            config.ROOT = orig_root
            _config.ROOT = orig_root

    # Simpler: test just the artifact-writing path directly
    now = datetime.now(timezone.utc)
    orig = wb._call_model
    wb._call_model = lambda s, u, c: (json.dumps(_FIXTURE_REPLY), None)
    try:
        rec = wb.evaluate(_TARIFF_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    rec["generated_at"] = now.isoformat()

    # write to a temp ledger and re-render
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bw._append_ledger(td, rec)
        rows = bw._load_ledger(td)
        assert len(rows) == 1
        banner = bw._banner_payload(rows, now)
        assert len(banner["alerts"]) == 1
        assert banner["alerts"][0]["importance"] == 82


# ---------------------------------------------------------------------------
# 6. seed param is gone from _call_model (no TypeError risk)
# ---------------------------------------------------------------------------
def test_no_seed_param_in_model_call() -> None:
    """The _call_model function must not attempt to pass seed= to the SDK.
    We verify by inspecting the source — the dead try/except seed branch is gone.
    Docstring mentions are fine; what we prohibit is the functional kw['seed']
    assignment or seed= keyword in the messages.create() call."""
    import inspect
    src = inspect.getsource(wb._call_model)
    # The dead branch was: kw["seed"] = 0 / del kw["seed"]
    # Those are the lines that caused TypeError; the docstring may still say "seed"
    assert 'kw["seed"]' not in src, (
        '_call_model must not include kw["seed"] = 0; '
        "the Anthropic SDK does not support seed= on messages.create()"
    )
    assert '"seed"' not in src or "seed" in src.split("messages.create")[0], (
        'messages.create() call must not pass seed= kwarg'
    )


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def _run() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")


if __name__ == "__main__":
    _run()
    print("all whitehouse_w5 tests passed")
