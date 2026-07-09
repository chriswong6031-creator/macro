"""Guard: a FRED series id registered in multiple config.yml groups MUST use one alias.

collectors/fred.py `_all_series()` dict-merges every `fred.series` group (last group
wins on a duplicate id). The store upsert's outlier guard then reads the EXISTING
parquet by the merged alias — so two groups registering the same series id under
different column aliases raise KeyError inside lib/store.upsert and kill the whole
fred adapter run (every FRED series goes stale, tripping the collect circuit breaker).

This happened 2026-07: the bottleneck block registered NEWORDER as `new_orders_capex`
(vs cycle_leading's `cap_goods_orders`) and ISRATIO as `inv_sales_total` (vs
cycle_lagging's `inventory_sales`) — the adapter failed for ~8 consecutive nightly
runs before the KeyError was traced. Duplicate ids are allowed (a series may serve
several engines); conflicting aliases are not.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_no_conflicting_fred_series_aliases():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text())
    series_groups = cfg["fred"]["series"]

    seen: dict[str, tuple[str, str]] = {}  # sid -> (group, alias)
    conflicts: list[str] = []
    for grp, mapping in series_groups.items():
        for sid, alias in (mapping or {}).items():
            if sid in seen and seen[sid][1] != alias:
                prev_grp, prev_alias = seen[sid]
                conflicts.append(
                    f"{sid}: {prev_alias!r} (group {prev_grp}) vs {alias!r} (group {grp})"
                )
            seen.setdefault(sid, (grp, alias))

    assert not conflicts, (
        "FRED series registered with conflicting column aliases — this KeyErrors the "
        "store upsert and kills the whole fred adapter (see module docstring). Align "
        "the alias with the first registration / on-disk parquet column:\n  "
        + "\n  ".join(conflicts)
    )
