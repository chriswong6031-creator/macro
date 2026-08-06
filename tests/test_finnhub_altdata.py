"""Pure fixture-based tests for collectors/finnhub_altdata.py.

No network — `_get` is monkeypatched. The defect these pin (2026-08-05): the collector
reported every auth/plan rejection as `no rows from 120 tickers (errors=120)`, which is
indistinguishable from a transient outage and from a rotated key, so nobody could act on
it and `data/finnhub/recommendation.parquet` was never produced. Seven consumers fail
open to null on that missing store.

Two behaviours are pinned here:
  1. an auth/plan gate is NAMED (expected_failure -> status 'blocked') and stops the
     sweep on the first one, instead of proving the same wall 120 times;
  2. the three endpoints are INDEPENDENT — a gate on one must not cost the others.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
import requests

from collectors import finnhub_altdata as FA


def _resp_exc(code: int) -> requests.HTTPError:
    """An HTTPError shaped like the one base.http_get re-raises from raise_for_status."""
    class _R:
        status_code = code
    e = requests.HTTPError(f"{code} Client Error")
    e.response = _R()
    return e


def _adapter(tmp_path, watch=("AAPL", "MSFT", "NVDA")):
    a = FA.FinnhubAltdataAdapter()
    a.api_key = "test-key-not-a-real-secret"
    a.expected_failure = None
    a._gate = None
    return a


# ------------------------------------------------------------------ classification

class TestGateClassification:
    def test_401_is_a_key_problem(self):
        r = FA.gate_reason_from_exc(_resp_exc(401))
        assert r and "401" in r and "rotate" in r.lower()

    def test_403_is_a_tier_problem(self):
        r = FA.gate_reason_from_exc(_resp_exc(403))
        assert r and "403" in r and "tier" in r.lower()

    def test_5xx_and_429_are_not_gates(self):
        """A real outage must stay a real failure — never laundered into 'blocked'."""
        assert FA.gate_reason_from_exc(_resp_exc(500)) is None
        assert FA.gate_reason_from_exc(_resp_exc(429)) is None
        assert FA.gate_reason_from_exc(Exception("connection reset")) is None

    def test_digits_inside_a_token_do_not_match(self):
        """The message fallback is anchored: a ticker/id containing 403 is not a gate."""
        assert FA.gate_reason_from_exc(Exception("symbol X4031 unknown")) is None
        assert FA.gate_reason_from_exc(Exception("id 14030 missing")) is None

    def test_message_fallback_still_catches_a_bare_code(self):
        assert FA.gate_reason_from_exc(Exception("HTTP 403")) is not None

    def test_http200_error_payload_is_a_gate(self):
        assert FA.gate_reason_from_payload(
            {"error": "You don't have access to this resource."}) is not None
        assert FA.gate_reason_from_payload({"error": "Premium plan required"}) is not None

    def test_ordinary_error_payload_is_not_a_gate(self):
        assert FA.gate_reason_from_payload({"error": "Symbol not supported"}) is None
        assert FA.gate_reason_from_payload({"data": []}) is None
        assert FA.gate_reason_from_payload([1, 2, 3]) is None


# ------------------------------------------------------------------ sweep behaviour

class TestSweepStopsOnGate:
    def test_total_gate_is_blocked_not_an_opaque_error(self, tmp_path, capsys):
        """Every endpoint 403 -> expected_failure set (status 'blocked') + a named reason."""
        a = _adapter(tmp_path)
        with patch.object(FA, "basket_members", return_value=["AAPL", "MSFT", "NVDA"]), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(a, "_get", side_effect=_resp_exc(403)):
            with pytest.raises(RuntimeError) as ei:
                a.fetch()
        assert a.expected_failure, "a plan gate must set expected_failure -> 'blocked'"
        assert "403" in a.expected_failure
        msg = str(ei.value)
        assert "403" in msg and "errors=" not in msg, (
            f"the error must NAME the gate, not just count failures; got {msg!r}")

    def test_gate_stops_the_sweep_instead_of_hammering(self, tmp_path):
        """The old code spent 120 tickers x 3 endpoints proving the same wall."""
        calls: list[str] = []

        def boom(path, params):
            calls.append(path)
            raise _resp_exc(403)

        a = _adapter(tmp_path)
        watch = [f"T{i}" for i in range(120)]
        with patch.object(FA, "basket_members", return_value=watch), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(a, "_get", side_effect=boom):
            with pytest.raises(RuntimeError):
                a.fetch()
        assert len(calls) <= 3, (
            f"a whole-key gate must stop after the first pass over the 3 endpoints; "
            f"made {len(calls)} calls across a {len(watch)}-ticker watchlist")

    def test_annotation_starts_the_line(self, tmp_path, capsys):
        """GitHub only parses ::warning at line start — a logger prefix would kill it."""
        a = _adapter(tmp_path)
        with patch.object(FA, "basket_members", return_value=["AAPL"]), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(a, "_get", side_effect=_resp_exc(401)):
            with pytest.raises(RuntimeError):
                a.fetch()
        out = capsys.readouterr().out
        ann = [ln for ln in out.splitlines() if "::warning" in ln]
        assert ann, "a gate must emit a ::warning annotation"
        for ln in ann:
            assert ln.startswith("::"), f"annotation must start the line, got {ln!r}"

    def test_real_failure_is_not_laundered_into_blocked(self, tmp_path):
        """A 500 storm must stay 'failed' — expected_failure must NOT be set."""
        a = _adapter(tmp_path)
        with patch.object(FA, "basket_members", return_value=["AAPL", "MSFT"]), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(a, "_get", side_effect=_resp_exc(500)):
            with pytest.raises(RuntimeError) as ei:
                a.fetch()
        assert not a.expected_failure, (
            "a 5xx outage must not be reported as a known limitation")
        assert "real failure" in str(ei.value)


class TestEndpointIsolation:
    def test_one_gated_endpoint_does_not_cost_the_others(self, tmp_path):
        """THE SECOND DEFECT: the three calls shared a try-block, so a gate on
        insider-sentiment silently dropped the earnings call for every ticker."""
        def routed(path, params):
            if "insider-sentiment" in path:
                raise _resp_exc(403)
            if "recommendation-trends" in path:
                return [{"period": "2026-08-01", "strongBuy": 5, "buy": 3,
                         "hold": 1, "sell": 0, "strongSell": 0},
                        {"strongBuy": 4, "buy": 3}]
            return [{"period": "2026-06-30", "actual": 1.2,
                     "estimate": 1.0, "surprisePercent": 20.0}]

        a = _adapter(tmp_path)
        with patch.object(FA, "basket_members", return_value=["AAPL", "MSFT"]), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(FA, "PACE_S", 0), \
             patch.object(a, "_get", side_effect=routed):
            out = a.fetch()

        rec = pd.read_parquet(tmp_path / "finnhub" / "recommendation.parquet")
        earn = pd.read_parquet(tmp_path / "finnhub" / "earnings.parquet")
        assert len(rec) == 2, "recommendation must survive an insider-sentiment gate"
        assert len(earn) == 2, (
            "earnings is called AFTER insider-sentiment — it must still run when "
            "insider-sentiment is gated (this is the bug)")
        assert not (tmp_path / "finnhub" / "insider_sentiment.parquet").exists()
        assert not a.expected_failure, "a partial gate is not a whole-source block"
        ing = out["finnhub_altdata__ingest"]
        assert ing["gated_endpoints"].iloc[0] == "insider-sentiment"

    def test_gated_endpoint_is_only_probed_once(self, tmp_path):
        seen: list[str] = []

        def routed(path, params):
            seen.append(path)
            if "insider-sentiment" in path:
                raise _resp_exc(403)
            return [{"period": "p", "strongBuy": 1, "buy": 1, "hold": 0,
                     "sell": 0, "strongSell": 0}]

        a = _adapter(tmp_path)
        watch = [f"T{i}" for i in range(10)]
        with patch.object(FA, "basket_members", return_value=watch), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(FA, "PACE_S", 0), \
             patch.object(a, "_get", side_effect=routed):
            a.fetch()
        n_insider = sum(1 for p in seen if "insider-sentiment" in p)
        assert n_insider == 1, (
            f"a gated endpoint must be probed once, not once per ticker; got {n_insider}")

    def test_happy_path_writes_all_three_stores(self, tmp_path):
        def routed(path, params):
            if "recommendation-trends" in path:
                return [{"period": "2026-08-01", "strongBuy": 5, "buy": 3, "hold": 1,
                         "sell": 0, "strongSell": 0}, {"strongBuy": 4, "buy": 3}]
            if "insider-sentiment" in path:
                return {"data": [{"year": 2026, "month": 7, "mspr": 12.5, "change": 100}]}
            return [{"period": "2026-06-30", "actual": 1.2, "estimate": 1.0,
                     "surprisePercent": 20.0}]

        a = _adapter(tmp_path)
        with patch.object(FA, "basket_members", return_value=["AAPL"]), \
             patch.object(FA.config, "data_dir", return_value=tmp_path), \
             patch.object(FA, "PACE_S", 0), \
             patch.object(a, "_get", side_effect=routed):
            out = a.fetch()
        d = tmp_path / "finnhub"
        rec = pd.read_parquet(d / "recommendation.parquet")
        assert {"ticker", "period", "strongBuy", "prev_buy"} <= set(rec.columns)
        assert rec["prev_buy"].iloc[0] == 7          # 4 + 3 from the prior period
        assert len(pd.read_parquet(d / "insider_sentiment.parquet")) == 1
        assert len(pd.read_parquet(d / "earnings.parquet")) == 1
        assert out["finnhub_altdata__ingest"]["gated_endpoints"].iloc[0] == ""
        assert not a.expected_failure
