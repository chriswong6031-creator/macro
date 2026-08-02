"""tests/test_sector_pulse_wiring.py — regression guard for the sector_pulse injection wiring.

History (the exact failure mode this file pins):
  PR #1170 (ca936d37cc) wired engine.sector_pulse per-ticker output into
  scripts/build_stock_library.py — a precompute map + injection into each
  stockdata/<SYM>.json rec AND into the wide-board rows consumed by the
  dashboard .nb-pulse-heat chip and the Terminal SectorPulseChip.
  PR #1193 (f6de54afb1, an unrelated qledger/near-miss change ~90 min later)
  silently deleted all three blocks, starving both consumers for a day.

  2026-07-22 (fe7a7426c49, prophet card v1 — operator-ratified 2026-07-21):
  the multi-chip standout card was retired wholesale, and the per-card
  .nb-pulse-heat chip (the n.get('sector_pulse') reader) went with it — an
  INTENTIONAL design removal, not the #1193 silent-starvation mode. The
  surviving dashboard consumer of engine.sector_pulse is the SECTOR HEAT
  STRIP (#sector-heat, stocks mode), fed by build_site._sector_heat_view();
  the stockdata rec injection still feeds the Terminal SectorPulseChip.
  (The wide-board row injection now has no template consumer — retained as
  harmless row data; drop it producer-side only with a matching update here.)

These tests pin the producer wiring at the source (AST) level and the
template-consumer contract, so a future refactor of build_stock_library.py
or build_site.py cannot drop the wiring without a test naming exactly what
went missing. All tests are hermetic — no build run, no network, no site/
output needed.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BUILDER = _REPO / "scripts" / "build_stock_library.py"
_TEMPLATE = _REPO / "templates" / "dashboard.html.j2"

# The compact-block contract: keys the dashboard chip + Terminal SectorPulseChip read.
_REQUIRED_BLOCK_KEYS = {
    "as_of", "theme_id", "theme_name", "theme_name_zh", "heat", "label",
    "reco", "rank", "n_themes", "rank_delta_5d", "theme_ids",
}


def _builder_tree() -> ast.Module:
    return ast.parse(_BUILDER.read_text(encoding="utf-8"))


def _subscript_key(node: ast.expr) -> str | None:
    """Constant string key of a Subscript target like rec["sector_pulse"], else None."""
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        if isinstance(node.slice.value, str):
            return node.slice.value
    return None


class TestBuilderProducerWiring:
    """scripts/build_stock_library.py must compute AND inject sector_pulse."""

    def test_imports_pulse_functions(self):
        """The precompute block imports build_pulse + ticker_themes from engine.sector_pulse."""
        imported: set[str] = set()
        for node in ast.walk(_builder_tree()):
            if isinstance(node, ast.ImportFrom) and node.module == "engine.sector_pulse":
                imported |= {a.name for a in node.names}
        assert "build_pulse" in imported and "ticker_themes" in imported, (
            "build_stock_library.py no longer imports build_pulse/ticker_themes from "
            "engine.sector_pulse — the sector_pulse precompute block was dropped "
            "(this exact regression shipped once in PR #1193; restore per PR #1170)"
        )

    def test_sector_pulse_injected_in_two_places(self):
        """Both injection sites survive: the stockdata JSON rec AND the wide-board row.

        Variable names may drift (rec/r are free to be renamed); what is pinned is
        that at least TWO distinct subscript assignments write a "sector_pulse" key.
        """
        sites = [
            node.lineno
            for node in ast.walk(_builder_tree())
            if isinstance(node, ast.Assign)
            and any(_subscript_key(t) == "sector_pulse" for t in node.targets)
        ]
        assert len(sites) >= 2, (
            f"Expected >=2 sector_pulse injection sites in build_stock_library.py "
            f"(stockdata rec + wide-board row), found {len(sites)} at lines {sites}. "
            "A refactor dropped the injection — this starves the dashboard "
            ".nb-pulse-heat chip and the Terminal SectorPulseChip (see PR #1170/#1193)."
        )

    def test_compact_block_carries_consumer_keys(self):
        """The dict literal stored in the pulse map keeps every key consumers read."""
        for node in ast.walk(_builder_tree()):
            if not isinstance(node, ast.Assign):
                continue
            if not any(_subscript_key(t) is None and isinstance(t, ast.Subscript)
                       for t in node.targets):
                continue  # map writes use a variable key: _sector_pulse_map[_sp_tick]
            if not isinstance(node.value, ast.Dict):
                continue
            keys = {k.value for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "theme_id" in keys:  # this is the compact pulse block
                missing = _REQUIRED_BLOCK_KEYS - keys
                assert not missing, (
                    f"sector_pulse compact block lost consumer-contract keys: {missing}"
                )
                return
        pytest.fail(
            "Could not find the sector_pulse compact-block dict literal in "
            "build_stock_library.py — the precompute mapping block was dropped"
        )


_BUILD_SITE = _REPO / "scripts" / "build_site.py"

# The sector-heat strip's unique extraction landmark (guard line of the panel).
_STRIP_LANDMARK = "{% if mode == 'stocks' and sector_heat %}"


class TestDashboardConsumerContract:
    """templates/dashboard.html.j2 must still surface engine.sector_pulse output.

    The per-card .nb-pulse-heat chip (n.get('sector_pulse')) was retired
    INTENTIONALLY by prophet card v1 (fe7a7426c49, operator-ratified
    2026-07-21) along with the whole multi-chip standout card. The surviving
    dashboard consumer is the SECTOR HEAT STRIP (#sector-heat, stocks mode):
    build_site._sector_heat_view() → engine.sector_pulse.build_pulse('us')
    → the sector_heat template var. These tests pin that strip so IT cannot
    starve silently the way the chip's predecessor did in #1193.
    """

    def test_template_reads_sector_heat(self):
        src = _TEMPLATE.read_text(encoding="utf-8")
        assert 'id="sector-heat"' in src and "sh-chip" in src, (
            "dashboard.html.j2 lost the sector-heat strip (#sector-heat / .sh-chip) — "
            "the last dashboard consumer of engine.sector_pulse (producer/consumer "
            "contract broken; see module docstring for the chip-retirement history)"
        )
        assert src.count(_STRIP_LANDMARK) == 1, (
            f"sector-heat strip guard line {_STRIP_LANDMARK!r} is no longer unique/present "
            "in dashboard.html.j2 — update _STRIP_LANDMARK if the guard was rephrased"
        )

    def test_build_site_wires_sector_heat_view(self):
        """build_site.py keeps _sector_heat_view() AND binds it into the template ctx.

        The view returns None-never-raises, so dropping either the engine import
        or the ctx binding hides the strip forever with zero errors — exactly
        the starvation mode this file exists to catch.
        """
        tree = ast.parse(_BUILD_SITE.read_text(encoding="utf-8"))
        view = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_sector_heat_view"),
            None,
        )
        assert view is not None, (
            "build_site.py lost _sector_heat_view() — the sector-heat strip producer"
        )
        imports = {
            a.name
            for n in ast.walk(view)
            if isinstance(n, ast.ImportFrom) and n.module == "engine.sector_pulse"
            for a in n.names
        }
        assert "build_pulse" in imports, (
            "_sector_heat_view() no longer imports build_pulse from engine.sector_pulse"
        )
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_sector_heat_view"
        ]
        assert calls, (
            "build_site.py never calls _sector_heat_view() — the sector_heat ctx "
            "binding was dropped; the strip renders hidden with zero errors"
        )

    def _strip_block(self) -> str:
        """Extract the REAL strip block from the template (guard {% if %} … matching endif).

        Balances if/endif depth per line — chip rows carry INLINE
        {% if %}…{% endif %} pairs (rank badge, as_of stamp), so "first endif" is wrong.
        """
        lines = _TEMPLATE.read_text(encoding="utf-8").splitlines()
        start = next(i for i, ln in enumerate(lines) if _STRIP_LANDMARK in ln)
        depth = 0
        for i in range(start, len(lines)):
            depth += lines[i].count("{% if ") - lines[i].count("{% endif %}")
            if depth == 0 and i > start:
                return "\n".join(lines[start:i + 1])
        pytest.fail("Unbalanced sector-heat strip block in dashboard.html.j2")

    def _render(self, heat: dict | None, mode: str = "stocks") -> str:
        import jinja2
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        tpl = env.from_string(self._strip_block())
        return tpl.render(mode=mode, sector_heat=heat, help=lambda *a, **k: "")

    # A payload shaped EXACTLY like _sector_heat_view()'s output.
    _HEAT = {
        "as_of": "2026-07-02",
        "heating": [
            {"id": "us_sector_tech", "name": "Technology", "name_zh": "科技",
             "heat": "heating", "rank": 3, "rank_delta_5d": 2,
             "label": "dominant", "reco": "accumulate"},
        ],
        "cooling": [
            {"id": "us_sector_energy", "name": "Energy", "name_zh": "能源",
             "heat": "cooling", "rank": 41, "rank_delta_5d": -6,
             "label": "fading", "reco": "reduce"},
        ],
    }

    def test_strip_renders_heating_and_cooling(self):
        out = self._render(self._HEAT)
        assert "sh-heat" in out and "▲" in out
        assert "sh-cool" in out and "▽" in out
        assert "Technology" in out and "科技" in out
        assert "basket/us_sector_tech.html" in out
        assert "#3" in out and "#41" in out

    def test_strip_suppressed_when_pulse_unavailable(self):
        out = self._render(None)
        assert "sh-chip" not in out and "sector-heat" not in out

    def test_strip_suppressed_in_macro_mode(self):
        # Macro mode surfaces sector heat inside the MARKETS tray instead;
        # the standalone strip is stocks-mode only.
        out = self._render(self._HEAT, mode="macro")
        assert "sh-chip" not in out
