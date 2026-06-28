"""engine/whitehouse_brain.py tests — the significance gate, JSON normalisation,
ticker/sector sanitisation, and degrade paths. No network/LLM (the model call is
monkeypatched).

Run: python -m tests.test_whitehouse_brain
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import whitehouse_brain as wb  # noqa: E402

_ITEM = {
    "id": "wh-2026-06-22-auto-tariffs", "title": "Auto tariff order",
    "url": "https://www.whitehouse.gov/x/", "section": "presidential-actions",
    "published": "2026-06-22T20:00:00+00:00", "body": "A 25% tariff on imported autos.",
    "excerpt": "",
}

_CFG = dict(wb._DEFAULTS)


def _patch_reply(monkeyish: dict | None, reason=None):
    """Return a _call_model stand-in yielding the given JSON object."""
    def fake(system, user, cfg):
        if monkeyish is None:
            return None, reason or "no_provider"
        return json.dumps(monkeyish), reason
    return fake


def test_activated_alert_normalised(tmp=None) -> None:
    payload = {
        "activate": True, "importance": 88, "banner_days": 12,  # >7 → clamped
        "tone": "mixed", "banner_title": "x" * 200,             # >140 → truncated
        "banner_title_zh": "汽车关税", "summary": "25% auto tariff.", "summary_zh": "汽车关税25%。",
        "analysis": "Para one.\nPara two.", "confidence": "HIGH",
        "sectors": [
            {"name": "Autos", "impact": "headwind", "rationale": "import cost up"},
            {"name": "Domestic OEM", "impact": "tailwind", "rationale": "shielded"},
            {"name": "", "impact": "tailwind", "rationale": "dropped (no name)"},
        ],
        "tickers": [
            {"symbol": "gm", "direction": "benefit", "rationale": "domestic"},
            {"symbol": "TM", "direction": "hurt", "rationale": "importer"},
            {"symbol": "this is not a ticker", "direction": "benefit", "rationale": "junk"},
            {"symbol": "GM", "direction": "benefit", "rationale": "dup dropped"},
        ],
    }
    orig = wb._call_model
    wb._call_model = _patch_reply(payload)
    try:
        rec = wb.evaluate(_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    assert rec["activated"] is True
    assert rec["importance"] == 88
    assert rec["banner_days"] == 7                # clamped to max
    assert rec["tone"] == "mixed"
    assert len(rec["banner_title"]) <= 140
    assert rec["banner_title_zh"] == "汽车关税"
    assert rec["confidence"] == "high"            # lowercased + validated
    # sector with empty name dropped
    assert [s["name"] for s in rec["sectors"]] == ["Autos", "Domestic OEM"]
    # tickers: uppercased, junk + dup dropped, direction kept
    syms = [t["symbol"] for t in rec["tickers"]]
    assert syms == ["GM", "TM"]
    assert rec["tickers"][0]["direction"] == "benefit"
    assert rec["tickers"][1]["direction"] == "hurt"
    assert rec["tickers"][0]["chg_pct"] is None   # no price file under fake root


def test_importance_floor_suppresses_low_value(tmp=None) -> None:
    payload = {"activate": True, "importance": 40, "banner_title": "meh",
               "tone": "neutral", "summary": "low", "analysis": "x", "sectors": [], "tickers": []}
    orig = wb._call_model
    wb._call_model = _patch_reply(payload)
    try:
        rec = wb.evaluate(_ITEM, {**_CFG, "min_importance": 60}, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    assert rec["activated"] is False              # below the floor → no banner
    assert rec["importance"] == 40


def test_inactive_when_model_declines(tmp=None) -> None:
    orig = wb._call_model
    wb._call_model = _patch_reply({"activate": False, "importance": 12})
    try:
        rec = wb.evaluate(_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    assert rec["activated"] is False
    assert rec["importance"] == 12
    assert rec["banner_title"] is None


def test_no_provider_degrades_cleanly(tmp=None) -> None:
    orig = wb._call_model
    wb._call_model = _patch_reply(None, reason="no_provider")
    try:
        rec = wb.evaluate(_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    assert rec["activated"] is False
    assert rec["degraded_reason"] == "no_provider"


def test_unparseable_reply_degrades(tmp=None) -> None:
    orig = wb._call_model
    wb._call_model = lambda s, u, c: ("not json at all", None)
    try:
        rec = wb.evaluate(_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    assert rec["activated"] is False
    assert rec["degraded_reason"] == "unparseable_reply"


def test_recent_change_missing_symbol_returns_none() -> None:
    assert wb._recent_change("ZZZZZZ", Path("/nonexistent")) is None
    assert wb._recent_change("bad sym!", Path("/nonexistent")) is None


def test_coerce_int_bounds() -> None:
    assert wb._coerce_int("99", 0, 7, 3) == 7
    assert wb._coerce_int(-5, 0, 100, 0) == 0
    assert wb._coerce_int("nope", 1, 7, 3) == 3


def test_truthy_handles_stringy_booleans() -> None:
    assert wb._truthy(True) is True
    assert wb._truthy(False) is False
    assert wb._truthy("true") is True and wb._truthy("YES") is True
    # the bug this guards: bool("false") is True in Python
    assert wb._truthy("false") is False
    assert wb._truthy("no") is False and wb._truthy("") is False


def test_stringy_false_does_not_activate(tmp=None) -> None:
    # model emits activate as the STRING "false" with high importance — must NOT activate
    payload = {"activate": "false", "importance": 95, "banner_title": "x",
               "tone": "headwind", "summary": "s", "analysis": "a", "sectors": [], "tickers": []}
    orig = wb._call_model
    wb._call_model = _patch_reply(payload)
    try:
        rec = wb.evaluate(_ITEM, _CFG, root=Path("/nonexistent"))
    finally:
        wb._call_model = orig
    assert rec["activated"] is False
    assert rec["importance"] == 95


def _run() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")


if __name__ == "__main__":
    _run()
    print("all whitehouse_brain tests passed")
