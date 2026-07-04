"""tests/test_sector_pulse_wiring.py — regression guard for the sector_pulse injection wiring.

History (the exact failure mode this file pins):
  PR #1170 (ca936d37cc) wired engine.sector_pulse per-ticker output into
  scripts/build_stock_library.py — a precompute map + injection into each
  stockdata/<SYM>.json rec AND into the wide-board rows consumed by the
  dashboard .nb-pulse-heat chip and the Terminal SectorPulseChip.
  PR #1193 (f6de54afb1, an unrelated qledger/near-miss change ~90 min later)
  silently deleted all three blocks, starving both consumers for a day.

These tests pin the producer wiring at the source (AST) level and the
template-consumer contract, so a future refactor of build_stock_library.py
cannot drop the injection without a test naming exactly what went missing.
All tests are hermetic — no build run, no network, no site/ output needed.
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


class TestDashboardConsumerContract:
    """templates/dashboard.html.j2 must still read the key the builder writes."""

    def test_template_reads_sector_pulse(self):
        src = _TEMPLATE.read_text(encoding="utf-8")
        assert "n.get('sector_pulse')" in src, (
            "dashboard.html.j2 no longer reads n.get('sector_pulse') — the heat-chip "
            "consumer was dropped (producer/consumer contract broken)"
        )
        assert "nb-pulse-heat" in src, "dashboard.html.j2 lost the .nb-pulse-heat chip markup"

    def _chip_block(self) -> str:
        """Extract the REAL chip block from the template (set _sph … matching endif).

        Balances if/endif depth per line — the chip <span> carries an INLINE
        {% if %}…{% endif %} inside its tooltip attribute, so "first endif" is wrong.
        """
        lines = _TEMPLATE.read_text(encoding="utf-8").splitlines()
        start = next(i for i, ln in enumerate(lines) if "n.get('sector_pulse')" in ln)
        depth = 0
        for i in range(start, len(lines)):
            depth += lines[i].count("{% if ") - lines[i].count("{% endif %}")
            if depth == 0 and i > start:
                return "\n".join(lines[start:i + 1])
        pytest.fail("Unbalanced chip block in dashboard.html.j2")

    def _render(self, pulse: dict | None) -> str:
        import jinja2
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        tpl = env.from_string(self._chip_block())
        n = {"sector_pulse": pulse} if pulse is not None else {}
        return tpl.render(n=n)

    # A block shaped EXACTLY like the builder's injection output.
    _BLOCK = {
        "as_of": "2026-07-02", "theme_id": "us_sector_tech",
        "theme_name": "Technology", "theme_name_zh": "科技",
        "heat": "heating", "label": "dominant", "reco": "accumulate",
        "rank": 3, "n_themes": 46, "rank_delta_5d": 2,
        "theme_ids": ["us_sector_tech"],
    }

    def test_chip_renders_for_heating_theme(self):
        out = self._render(self._BLOCK)
        assert "nb-pulse-heat" in out and "ph-heating" in out
        assert "Technology" in out and "科技" in out
        assert "▲" in out

    def test_chip_renders_cooling_arrow(self):
        out = self._render({**self._BLOCK, "heat": "cooling"})
        assert "ph-cooling" in out and "▽" in out

    def test_chip_suppressed_when_idle(self):
        out = self._render({**self._BLOCK, "heat": "idle"})
        assert "nb-pulse-heat" not in out

    def test_chip_suppressed_when_absent(self):
        out = self._render(None)
        assert "nb-pulse-heat" not in out
