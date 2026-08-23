from __future__ import annotations

import json
from unittest.mock import patch

from engine import quote_resolution
from engine.neuralweb import brain_gateway


class JsonResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_batch_hub_uses_one_request_and_preserves_existing_row_shape(tmp_path):
    seen = []
    payload = {
        "AAPL": {
            "last": 231.9,
            "ts": 1785593100,
            "prevClose": 229.0,
            "chg": 1.27,
            "market": "us",
            "regularSessionDate": "2026-07-31",
            "basis": "DELAYED_15M",
            "live": False,
        },
        "BTC-USD": {
            "last": 118250.0,
            "ts": 1785593100,
            "prevClose": 117000.0,
            "chg": 1.07,
            "market": "crypto",
            "live": True,
        },
    }

    def open_once(request, *_args, **_kwargs):
        seen.append(request.full_url)
        return JsonResponse(payload)

    with patch("urllib.request.urlopen", side_effect=open_once):
        result = quote_resolution.resolve_quotes(
            ["aapl", "BTC-USD"], tmp_path, "http://localhost:3100", tmp_path
        )

    assert len(seen) == 1
    assert "/quotes?syms=AAPL%2CBTC-USD" in seen[0]
    assert result["AAPL"] == {
        "symbol": "AAPL",
        "price": 231.9,
        "prev_close": 229.0,
        "change_pct": 1.27,
        "as_of": "2026-08-01T14:05:00+00:00",
        "live": False,
        "source": "terminal_hub",
        "delayed_min": 15,
    }
    assert result["BTC-USD"]["source"] == "terminal_hub"
    assert result["BTC-USD"]["live"] is True


def test_batch_fallback_loads_full_snapshot_once_and_rejects_cold_us_placeholder(
    tmp_path, monkeypatch
):
    full = tmp_path / "quotes_full.json"
    full.write_text(
        json.dumps(
            {
                "asof": "2026-08-01T13:44:30+00:00",
                "quotes": {
                    "AAPL": {"price": 231.5, "ts": 1785591900000},
                    "MSFT": {"price": 550.0, "ts": 1785591900000},
                },
                "meta": {"delayed_min": 15},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MACRO_QUOTES_FULL_PATH", str(full))
    payload = {
        "AAPL": {
            "last": 210.0,
            "ts": 1785593100,
            "market": "us",
            "basis": "EOD",
            "live": False,
        }
    }
    original_read = type(full).read_text
    reads = []

    def counted_read(path, *args, **kwargs):
        if path == full:
            reads.append(path)
        return original_read(path, *args, **kwargs)

    with (
        patch("urllib.request.urlopen", return_value=JsonResponse(payload)),
        patch.object(type(full), "read_text", counted_read),
    ):
        result = quote_resolution.resolve_quotes(
            ["AAPL", "MSFT"], tmp_path, "http://localhost:3100", tmp_path
        )

    assert reads == [full]
    assert result["AAPL"]["price"] == 231.5
    assert result["MSFT"]["price"] == 550.0
    assert all(row["source"] == "live_plane_full" for row in result.values())


def test_malformed_hub_row_falls_through_without_poisoning_later_valid_symbol(
    tmp_path, monkeypatch
):
    full = tmp_path / "quotes_full.json"
    full.write_text(
        json.dumps(
            {
                "asof": "2026-08-01T13:44:30+00:00",
                "quotes": {"AAPL": {"price": 231.5, "ts": 1785591900000}},
                "meta": {"delayed_min": 15},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MACRO_QUOTES_FULL_PATH", str(full))
    payload = {
        "AAPL": {
            "last": 1.0,
            "ts": 1e100,
            "market": "us",
            "regularSessionDate": "2026-08-22",
        },
        "MSFT": {
            "last": 550.0,
            "ts": 1785593100,
            "market": "us",
            "regularSessionDate": "2026-08-22",
        },
    }
    calls = []

    def one_hub_call(request, *_args, **_kwargs):
        calls.append(request.full_url)
        return JsonResponse(payload)

    with patch("urllib.request.urlopen", side_effect=one_hub_call):
        result = quote_resolution.resolve_quotes(
            ["AAPL", "MSFT"], tmp_path, "http://localhost:3100", tmp_path
        )

    assert len(calls) == 1
    assert result["AAPL"]["source"] == "live_plane_full"
    assert result["AAPL"]["price"] == 231.5
    assert result["MSFT"]["source"] == "terminal_hub"
    assert result["MSFT"]["price"] == 550.0


def test_malformed_full_snapshot_row_does_not_poison_later_valid_symbol(
    tmp_path, monkeypatch
):
    full = tmp_path / "quotes_full.json"
    full.write_text(
        json.dumps(
            {
                "asof": "2026-08-01T13:44:30+00:00",
                "quotes": {
                    "AAPL": {"price": 231.5, "ts": 1e100},
                    "MSFT": {"price": 550.0, "ts": 1785591900000},
                },
                "meta": {"delayed_min": 15},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MACRO_QUOTES_FULL_PATH", str(full))
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "as_of": "2026-07-31",
                "symbols": {"AAPL": {"price": 220.0, "verdict": "hold", "wr": 0.5}},
            }
        ),
        encoding="utf-8",
    )

    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        result = quote_resolution.resolve_quotes(
            ["AAPL", "MSFT"], tmp_path, "http://localhost:3100", tmp_path
        )

    assert result["AAPL"]["source"] == "manifest"
    assert result["AAPL"]["price"] == 220.0
    assert result["MSFT"]["source"] == "live_plane_full"
    assert result["MSFT"]["price"] == 550.0


def test_brain_tool_is_a_mechanical_single_symbol_delegate(tmp_path):
    expected = {
        "symbol": "AAPL",
        "price": 231.9,
        "as_of": "2026-08-01T14:05:00+00:00",
        "source": "terminal_hub",
    }
    with patch.object(quote_resolution, "resolve_quote", return_value=expected) as delegated:
        actual = brain_gateway._tool_get_quote(
            {"symbol": "aapl"}, tmp_path, "http://localhost:3100", tmp_path
        )
    assert actual is expected
    delegated.assert_called_once_with(
        "aapl", tmp_path, "http://localhost:3100", tmp_path
    )


def test_safe_symbol_parity_and_unavailable_shape(tmp_path):
    for raw in ["nvda", "../etc", "BRK.B", "600036.SH", "SSE:600036", "HKEX:700"]:
        assert quote_resolution.safe_symbol(raw) == brain_gateway._safe_symbol(raw)
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert quote_resolution.resolve_quote("???", tmp_path, "", tmp_path) == {
            "error": "symbol required"
        }
        assert quote_resolution.resolve_quote("AAPL", tmp_path, "", tmp_path) == {
            "symbol": "AAPL",
            "available": False,
            "note": "quote not available from any source",
        }
