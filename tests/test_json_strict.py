"""Truth tests for engine.json_strict — the strict-JSON write contract.

The defect being pinned: `json.dumps(summary, indent=2, default=str)` reads as if
it sanitizes and does not. `default=` is consulted ONLY for objects the encoder
cannot serialize; a float NaN serializes fine, as the bare token `NaN`, which is
not JSON — so three shipped `data/research/top_anatomy_*_summary.json` artifacts
carried six `NaN` tokens each under `ruler.*` and no strict parser would read them.

So the assertions here are deliberately about the OUTPUT TEXT and its strict
parseability, not just about the walker's return value: a test that only checked
`sanitize_non_finite(x) == y` would have passed against the broken emitter too.
`test_original_input_is_not_mutated` pins the other half of the contract — the
sanitizer runs at write time over engine return values that other code paths still
read, so it must copy rather than walk in place.

Deterministic, no network, no `data/` dependency (agent worktrees are sparse).
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pytest

from engine.json_strict import sanitize_non_finite
from scripts import research_top_anatomy_phase0 as rh


def _no_constants(const: str) -> Any:
    """`parse_constant` hook: strict JSON has no NaN/Infinity/-Infinity literals.

    `json.loads` accepts them by default, so a round-trip alone proves nothing —
    this turns any such token in the text into a hard failure.
    """
    raise AssertionError(f"non-JSON constant token in output: {const}")


def _strict_loads(text: str) -> Any:
    return json.loads(text, parse_constant=_no_constants)


# ══════════════════════════════════════════════════════════════════════════════
# walker unit
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_every_non_finite_float_becomes_none(bad):
    """NaN, +Inf and -Inf all map to None — Inf is as un-JSON as NaN."""
    assert sanitize_non_finite(bad) is None


def test_non_finite_is_reached_at_every_nesting_depth():
    """dicts, lists and tuples are all walked, including nested inside each other."""
    payload = {
        "ruler": {"fwd_63_excess": float("nan"), "legs": [1.0, float("inf")]},
        "rows": [{"t": float("-inf")}, {"t": 2.5}],
        "pair": (float("nan"), 3.0),
        "deep": [[{"x": [float("nan")]}]],
    }
    out = sanitize_non_finite(payload)
    assert out["ruler"]["fwd_63_excess"] is None
    assert out["ruler"]["legs"] == [1.0, None]
    assert out["rows"] == [{"t": None}, {"t": 2.5}]
    assert out["pair"] == [None, 3.0]          # tuple -> list, as json encodes it
    assert out["deep"] == [[{"x": [None]}]]


def test_numpy_float64_nan_becomes_none():
    """np.float64 subclasses float, so the `isinstance(obj, float)` branch catches it.

    This is the actual production source of the bad tokens — a pandas/numpy
    reduction over an empty group, not a hand-written `float("nan")`.
    """
    assert isinstance(np.float64("nan"), float)          # the property relied on
    out = sanitize_non_finite({"m": np.float64("nan"), "s": np.float64(1.25)})
    assert out["m"] is None
    assert out["s"] == pytest.approx(1.25)


def test_everything_finite_passes_through_unchanged():
    """Encoding-only: no rounding, no coercion, no dropped or renamed keys."""
    payload = {
        "f": 1.5, "neg": -0.0, "zero": 0.0, "big": 1e308,
        "i": 7, "s": "text", "none": None, "empty_d": {}, "empty_l": [],
        "nested": {"a": [1, 2, {"b": "c"}]},
    }
    out = sanitize_non_finite(payload)
    assert out == payload
    assert list(out) == list(payload)                    # key order preserved
    assert out["i"] == 7 and isinstance(out["i"], int)


def test_dict_keys_are_preserved_exactly():
    payload = {"n_fires": 0, "0": "str-zero", "": "empty", "ruler.fwd": float("nan")}
    out = sanitize_non_finite(payload)
    assert list(out.keys()) == ["n_fires", "0", "", "ruler.fwd"]
    assert out["ruler.fwd"] is None


def test_bools_are_not_coerced():
    """bool is not a float subclass, so True/False must survive as bools, not 1/0."""
    out = sanitize_non_finite({"ok": True, "bad": False, "xs": [True, False]})
    assert out["ok"] is True
    assert out["bad"] is False
    assert out["xs"] == [True, False]
    assert all(isinstance(v, bool) for v in out["xs"])


# ══════════════════════════════════════════════════════════════════════════════
# the do-not-mutate-engine-returns contract
# ══════════════════════════════════════════════════════════════════════════════
def test_original_input_is_not_mutated():
    """The sanitizer runs at write time over live engine return values.

    In the phase-0 harness the very same `summary` dict is handed to `write_report`
    AFTER the JSON write, so an in-place walk would silently change the report's
    inputs. Pinned with `math.isnan` on the original, not `==` (NaN != NaN).
    """
    inner = {"fwd_63_excess": float("nan"), "n_fires": 0}
    payload = {"ruler": inner, "legs": [float("inf"), 1.0]}
    out = sanitize_non_finite(payload)

    assert math.isnan(payload["ruler"]["fwd_63_excess"])
    assert math.isnan(inner["fwd_63_excess"])            # same object, still NaN
    assert payload["legs"][0] == float("inf")
    assert out is not payload
    assert out["ruler"] is not payload["ruler"]
    assert out["ruler"]["fwd_63_excess"] is None         # ... and the copy is clean


# ══════════════════════════════════════════════════════════════════════════════
# strict enforcement: sanitize is the fix, allow_nan=False is the enforcement
# ══════════════════════════════════════════════════════════════════════════════
def test_unsanitized_nan_raises_under_allow_nan_false():
    """The enforcement half: without the sanitizer the strict dump must fail loud."""
    with pytest.raises(ValueError):
        json.dumps({"ruler": {"fwd_63_excess": float("nan")}}, allow_nan=False)


def test_default_str_does_not_catch_nan():
    """Pins the root cause of the shipped defect, so nobody 'fixes' it with default=."""
    text = json.dumps({"x": float("nan")}, indent=2, default=str)
    assert "NaN" in text                                 # the bare, invalid token
    with pytest.raises(AssertionError):
        _strict_loads(text)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_sanitized_payload_survives_the_strict_dump(bad):
    payload = {"ruler": {"v": bad}, "xs": [bad, 1.0], "t": (bad,)}
    text = json.dumps(sanitize_non_finite(payload), indent=2, default=str,
                      allow_nan=False)
    assert _strict_loads(text) == {"ruler": {"v": None}, "xs": [None, 1.0],
                                  "t": [None]}


def test_no_non_json_constant_token_in_output():
    """Round-trip proof that none of the three literals reach the text."""
    payload = {"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": 1.0}
    text = json.dumps(sanitize_non_finite(payload), allow_nan=False)
    for token in ("NaN", "Infinity", "-Infinity"):
        assert token not in text
    assert _strict_loads(text) == {"a": None, "b": None, "c": None, "d": 1.0}


# ══════════════════════════════════════════════════════════════════════════════
# the emitter's single write path
# ══════════════════════════════════════════════════════════════════════════════
def test_write_summary_json_emits_strict_json(tmp_path):
    """The factored emitter, shaped like the artifact that shipped broken.

    `ruler.fwd_63_excess` is NaN exactly when a leg has no fires — the real case
    behind the six bad tokens in each of the three shipped W2/p0 summaries.
    """
    out = tmp_path / "top_anatomy_p0_summary.json"
    summary = {
        "ruler": {"fwd_63_excess": float("nan"), "n_fires": 0},
        "note": "x",
    }
    rh._write_summary_json(out, summary)

    text = out.read_text()
    assert "NaN" not in text
    decoded = _strict_loads(text)
    assert decoded == {"ruler": {"fwd_63_excess": None, "n_fires": 0}, "note": "x"}
    # and the caller's dict is untouched — write_report still reads it downstream
    assert math.isnan(summary["ruler"]["fwd_63_excess"])


def test_write_summary_json_keeps_default_str_for_unserializable_values(tmp_path):
    """`allow_nan=False` must not cost the `default=str` fallback the emitter had.

    Real summaries carry pandas Timestamps (`computed_at_utc`) and Paths; those are
    non-serializable, so `default=str` is load-bearing and must still fire.
    """
    import pandas as pd

    out = tmp_path / "s.json"
    ts = pd.Timestamp("2026-08-11T17:00:00Z")
    rh._write_summary_json(out, {"computed_at_utc": ts, "v": float("nan")})

    decoded = _strict_loads(out.read_text())
    assert decoded["computed_at_utc"] == str(ts)
    assert decoded["v"] is None


def test_write_summary_json_is_the_only_summary_write_path():
    """All three emitters route through the helper — no second `json.dumps(summary)`.

    A partial factoring is the failure mode here: one un-routed emitter keeps
    shipping bare `NaN` while the tests above stay green.
    """
    import inspect
    src = inspect.getsource(rh)

    # No emitter may dump `summary` without the sanitizer in front of it. The three
    # cache `meta.json` writes are deliberately NOT converted (their metadata is
    # equality-reconsumed by the cache loader), so this pins on `summary` only.
    raw = [ln.strip() for ln in src.splitlines()
           if ("json.dumps(summary" in ln or "json.dump(summary" in ln)]
    assert raw == [], raw

    # ... and the one sanctioned write path carries BOTH halves of the contract:
    # the sanitizer (the fix) and allow_nan=False (the enforcement).
    helper = inspect.getsource(rh._write_summary_json)
    assert "sanitize_non_finite(summary)" in helper
    assert "allow_nan=False" in helper

    # all three emitters go through it: roster-read, --w2-arm, phase-0 main
    assert len([ln for ln in src.splitlines() if "_write_summary_json(" in ln]) == 4
