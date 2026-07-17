"""tests/test_levels_publish.py — WP-A2.5 levels publisher (helpers + standalone lane).

Hermetic: no network, no options store, no clock. Exercises the pure publish seam
(engine/levels_publish.py) and the standalone lane (scripts/build_levels.py) against
a crafted options_hub.gex/v1 payload with known structure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.levels_publish import (  # noqa: E402
    has_strikes,
    levels_payload_from_gex,
    levels_relpath,
    LEVELS_PREFIX,
)
import scripts.build_levels as bl  # noqa: E402


def _gex_payload(root: str = "SPY", asof: str = "2026-07-16") -> dict:
    """A minimal, realistic options_hub.gex/v1 payload (signed gamma_net, $mn)."""
    def row(k, g):
        return {"strike": float(k), "gamma_net": float(g), "gamma_call": max(g, 0.0),
                "gamma_put": min(g, 0.0), "delta_net": 0.0, "vanna_net": 0.0,
                "charm_net": 0.0}
    by_strike = [
        row(740, -8.0), row(745, -3.0), row(748, 1.0), row(750, 22.0),  # 750 = Anchor
        row(752, 2.0), row(755, 12.0), row(760, 5.0),
    ]
    return {
        "schema": "options_hub.gex/v1",
        "root": root,
        "asof": asof,
        "spot_ref": 750.0,
        "net_gex_bn": 0.031,
        "gamma_flip": 749.0,
        "call_wall": 755.0,
        "put_wall": 745.0,
        "by_strike": by_strike,
    }


class TestHelpers:
    def test_has_strikes(self):
        assert has_strikes(_gex_payload()) is True
        assert has_strikes({"by_strike": []}) is False
        assert has_strikes({}) is False
        assert has_strikes(None) is False

    def test_levels_relpath(self):
        assert levels_relpath("SPY") == "levels/SPY.json"
        assert LEVELS_PREFIX == "levels/"

    def test_payload_from_gex_real(self):
        lv = levels_payload_from_gex(_gex_payload())
        assert lv is not None
        assert lv["schema"] == "levels.v1"
        assert lv["root"] == "SPY"
        # spot flows from the gex spot_ref (board + exposure share one price)
        assert lv["spot"] == 750.0
        roles = {n["role"] for n in lv["nodes"]}
        assert "anchor" in roles
        anchor = next(n for n in lv["nodes"] if n["role"] == "anchor")
        # 750 carries the largest |gamma_net| in the fixture
        assert anchor["strike"] == 750.0
        assert "source" in lv and "regime" in lv and "palette_hint" in lv

    def test_payload_from_gex_empty_is_none(self):
        assert levels_payload_from_gex({"by_strike": []}) is None
        assert levels_payload_from_gex(None) is None

    def test_colorblind_passthrough(self):
        std = levels_payload_from_gex(_gex_payload(), colorblind=False)
        cb = levels_payload_from_gex(_gex_payload(), colorblind=True)
        # the palette hint differs; the node structure does not
        assert std["palette_hint"] != cb["palette_hint"]
        assert [n["role"] for n in std["nodes"]] == [n["role"] for n in cb["nodes"]]


class TestStandaloneLane:
    def test_resolve_roots_explicit(self, tmp_path):
        class A:
            roots = "spy, qqq"
            all = False
        assert bl._resolve_roots(A(), tmp_path) == ["SPY", "QQQ"]

    def test_resolve_roots_all_globs_gex_dir(self, tmp_path):
        (tmp_path / "SPY.json").write_text("{}")
        (tmp_path / "NVDA.json").write_text("{}")

        class A:
            roots = ""
            all = True
        assert bl._resolve_roots(A(), tmp_path) == ["NVDA", "SPY"]

    def test_load_gex_local_first(self, tmp_path):
        (tmp_path / "SPY.json").write_text(json.dumps(_gex_payload()))
        got = bl._load_gex("SPY", tmp_path, None, None, from_r2=False)
        assert got is not None and got["root"] == "SPY"
        # missing + no R2 -> None (no crash)
        assert bl._load_gex("MISSING", tmp_path, None, None, from_r2=False) is None

    def test_main_end_to_end_local(self, tmp_path):
        gex_dir = tmp_path / "gex"
        out_dir = tmp_path / "levels"
        gex_dir.mkdir()
        (gex_dir / "SPY.json").write_text(json.dumps(_gex_payload("SPY")))
        (gex_dir / "EMPTY.json").write_text(json.dumps({"schema": "options_hub.gex/v1",
                                                        "root": "EMPTY", "by_strike": []}))
        rc = bl.main([
            "--roots", "SPY,EMPTY,GONE",
            "--gex-dir", str(gex_dir),
            "--out-dir", str(out_dir),
            "--asof", "2026-07-16",
        ])
        assert rc == 0
        # SPY published, EMPTY skipped (no strikes), GONE missing
        spy = json.loads((out_dir / "SPY.json").read_text())
        assert spy["schema"] == "levels.v1"
        assert not (out_dir / "EMPTY.json").exists()
        assert not (out_dir / "GONE.json").exists()
        idx = json.loads((out_dir / "index.json").read_text())
        assert idx["roots"] == ["SPY"]
        assert idx["empty"] == ["EMPTY"]
        assert idx["missing"] == ["GONE"]
        assert idx["asof"] == "2026-07-16"

    def test_main_no_roots_returns_2(self, tmp_path):
        assert bl.main(["--gex-dir", str(tmp_path), "--out-dir", str(tmp_path)]) == 2
