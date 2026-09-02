"""TOP ANATOMY R0b — the engine band must restore massive_stock_day BEFORE it runs
build_top_maturation.

Proven defect (nightly run 33232322255 / engine job 99066153702, 2026-08-29): the
`regional + desk builders` band runs `scripts.build_top_maturation` (cl_stage) while
`data/massive_stock_day` — R2-canonical, gitignored, never present in a fresh engine
checkout — is still empty, because the engine job's only restore of that store sat in
the later price_pressure step. Winner Health then fail-opens to a null artifact with a
healthy vintage stamp (the manifest is committed while the shards are not), and the
board goes dark at rc=0: 21,452 tickers were restored 43 minutes AFTER the band needed
them, in the same job. Four consecutive null nights (08-23, 08-27, 08-28, 08-29).

These assertions pin the repair shape:
1. the extracted band body performs a guarded massive_stock_day restore at top level,
   textually above any cluster function definition (top-level code runs before any
   cluster launches, so this is an execution-order guarantee, not a style check);
2. the band still runs the consumer (scripts.build_top_maturation) — keeps (1) honest;
3. the workflow step that invokes the band body carries the four R2_* env keys the
   restore needs — without them fetch_r2 cannot authenticate and the ordering fix
   silently regresses to the pre-fix null behavior.
"""
from pathlib import Path
import re

import yaml

REPO = Path(__file__).resolve().parents[1]
BAND = REPO / "scripts" / "ci" / "daily_engine_regional_desk_builders.sh"
DAILY = REPO / ".github" / "workflows" / "daily.yml"


def test_band_restores_massive_stock_day_before_any_cluster():
    lines = BAND.read_text().splitlines()
    restore = next(
        (i for i, l in enumerate(lines) if "fetch_r2" in l and "massive_stock_day" in l),
        None,
    )
    assert restore is not None, (
        "band body has NO massive_stock_day restore — build_top_maturation (cl_stage) "
        "reads an empty store on a cold runner and Winner Health goes dark at rc=0"
    )
    first_cluster = next(
        (i for i, l in enumerate(lines) if re.match(r"^cl_[a-z_]+\(\)\s*\{", l)), None
    )
    assert first_cluster is not None, (
        "band body lost its cluster functions — update this test to wherever the "
        "builders moved"
    )
    assert restore < first_cluster, (
        f"massive_stock_day restore at line {restore + 1} must sit ABOVE the first "
        f"cluster definition (line {first_cluster + 1}) so it executes before any "
        "cluster launches"
    )
    guard_window = "\n".join(lines[max(0, restore - 3) : restore + 1])
    assert "find data/massive_stock_day" in guard_window, (
        "restore must keep the existing find(1) guard idiom — an unconditional fetch "
        "re-walks ~20k objects every warm night"
    )


def test_band_still_runs_top_maturation_consumer():
    assert "scripts.build_top_maturation" in BAND.read_text(), (
        "band no longer runs build_top_maturation — the ordering assertions above are "
        "vacuous; move them to wherever the consumer went"
    )


def test_band_step_env_carries_r2_credentials():
    daily = yaml.safe_load(DAILY.read_text())
    steps = [s for j in daily["jobs"].values() for s in (j.get("steps") or [])]
    band_steps = [
        s for s in steps if "daily_engine_regional_desk_builders.sh" in str(s.get("run", ""))
    ]
    assert band_steps, "no daily.yml step invokes daily_engine_regional_desk_builders.sh"
    for step in band_steps:
        env = step.get("env") or {}
        missing = [
            k
            for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
            if k not in env
        ]
        assert not missing, (
            f"band step is missing R2 env keys {missing} — the massive_stock_day "
            "restore inside the band body cannot authenticate"
        )
