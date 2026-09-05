"""CN-PR-1 host wiring: systemd units, update.sh, backstop workflow, serving gate."""
from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

import scripts.cn_live_evaluator as E
from engine.prophet_live import r2io
from scripts.check_vps_live_health import evaluate as evaluate_live_health

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-live-cnprophet.service"
TIMER = DEPLOY / "macro-live-cnprophet.timer"
UPDATE_SH = (DEPLOY / "update.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "cn-prophet-live.yml").read_text(
    encoding="utf-8")
POLICY = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
SERVED_URL_PATH = "/live/cn_prophet_live.json"


def _unit(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(path.read_text(encoding="utf-8"))
    return cp


def test_service_is_a_capped_oneshot() -> None:
    svc = _unit(SERVICE)["Service"]
    assert svc["Type"] == "oneshot"
    assert svc["ExecStart"].endswith("-m scripts.cn_live_evaluator")
    assert svc["WorkingDirectory"] == "/opt/macro"
    assert svc["EnvironmentFile"] == "-/etc/macro-live.env"
    assert int(svc["CPUQuota"].rstrip("%")) <= 60
    assert svc["MemoryMax"] == "512M"
    assert int(svc["TimeoutStartSec"]) <= 120
    assert svc["NoNewPrivileges"] == "true"


def test_timer_covers_the_mainland_session_without_a_second_clock() -> None:
    cal = _unit(TIMER)["Timer"]["OnCalendar"]
    m = re.fullmatch(r"Mon\.\.Fri \*-\*-\* (\d+)\.\.(\d+):(\d+)/(\d+):00 UTC", cal)
    assert m, cal
    lo, hi, offset, step = (int(g) for g in m.groups())
    assert lo == 1 and hi == 7 and step == 5
    assert 0 <= offset < 5


def test_update_sh_self_arms_only_the_cn_units() -> None:
    assert "macro-live-cnprophet.service" in UPDATE_SH
    assert "macro-live-cnprophet.timer" in UPDATE_SH
    assert re.search(r"enable --now macro-live-cnprophet\.timer", UPDATE_SH)
    # Must not restart the oneshot.
    cn_block = UPDATE_SH.split("CN PROPHET LIVE")[1].split("CLOSE-PASS")[0]
    assert "restart macro-live-cnprophet.service" not in cn_block
    assert "restart macro-live-cnprophet.timer" in cn_block


def test_backstop_workflow_self_disables_when_vps_is_primary() -> None:
    assert "VPS_LIVE_PRIMARY" in WORKFLOW
    assert "CN_PROPHET_LIVE_DISABLED" in WORKFLOW
    assert "ubuntu-latest" in WORKFLOW
    assert "macstudio" not in WORKFLOW
    assert "contents: read" in WORKFLOW
    assert "python -m scripts.cn_live_evaluator" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW


def test_served_artifact_is_not_a_public_live_exception() -> None:
    public = POLICY["public"]
    assert SERVED_URL_PATH not in set(public["exact"])
    assert not any(SERVED_URL_PATH.startswith(p) for p in public["prefixes"])
    free = POLICY["free_registered"]
    assert SERVED_URL_PATH not in set(free.get("exact") or [])
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    assert "cn_prophet_live.json" not in caddy.split("@vps_public_live")[1][:800]


def test_r2_and_served_paths_bridge_the_prefix() -> None:
    assert r2io.CN_LIVE_KEY == "live_flow/cn_prophet_live.json"
    assert E.SERVED_PATH.endswith("/live/cn_prophet_live.json")
    assert Path(E.SERVED_PATH).name == Path(r2io.CN_LIVE_KEY).name


def test_cn_kill_switch_is_independent_of_the_us_one(tmp_path, monkeypatch) -> None:
    dest = tmp_path / "cn_prophet_live.json"
    dest.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CN_PROPHET_LIVE_NO_PUBLISH", "1")
    monkeypatch.delenv("PROPHET_LIVE_NO_PUBLISH", raising=False)
    assert E.publish_served(dest, {"schema": "x"}) is False
    assert dest.read_text(encoding="utf-8") == "{}"
    monkeypatch.delenv("CN_PROPHET_LIVE_NO_PUBLISH")
    assert E.publish_served(dest, {"schema": "x"}) is True
    assert json.loads(dest.read_text(encoding="utf-8"))["schema"] == "x"


def test_health_clause_is_absent_ok_and_phase_aware() -> None:
    now = datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc)  # morning
    base = {
        "status": "ok",
        "checks": {
            "quotes": {"age_min": 1, "requested": 25, "resolved": 20},
            "release_publications": {
                "schema": "release_publications.v2",
                "age_min": 1,
                "event_status": {"published": 1, "scheduled": 3},
                "max_publication_lag_min": 0,
            },
            "orchestrator": {
                "age_min": 1,
                "lanes": {
                    "fast": {"ok": True, "age_min": 1},
                    "snapshot": {"ok": True, "age_min": 4},
                    "bars": {"ok": True, "age_min": 30},
                },
            },
            "basket_pulse": {"age_min": 4},
            "overlay": {"age_min": 2},
            "risk_state": {"age_min": 2},
            "china_risk_state": {"age_min": 2},
            "flow_pulse": {"age_min": 30},
        },
    }
    assert evaluate_live_health(base, now=now) == []
    base["checks"]["cn_prophet_live"] = {"age_min": 2}
    assert evaluate_live_health(base, now=now) == []
    base["checks"]["cn_prophet_live"] = {"age_min": 12}
    fails = evaluate_live_health(base, now=now)
    assert any("cn_prophet_live: stale" in f for f in fails)
    lunch = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)
    base["checks"]["cn_prophet_live"] = {"age_min": 12}
    assert evaluate_live_health(base, now=lunch) == []
    after = datetime(2026, 8, 18, 7, 25, tzinfo=timezone.utc)
    base["checks"]["cn_prophet_live"] = {"age_min": 2}
    fails = evaluate_live_health(base, now=after)
    assert any("close_board missing" in f for f in fails)


def test_evaluator_stands_down_outside_the_session() -> None:
    from datetime import datetime as dt
    weekend = dt(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
    rc = E.run(ROOT, now=weekend, dry_run=True, cfg={"live": {"delayed_min": 15}})
    assert rc == 0


# Research Vault source-content liveness.  This deliberately lives in an already
# wired VPS-health suite: adding a new collecting tests/test_*.py file trips the
# repository's unrun-suite guard and would widen this incident into CI authority.
def _research_catalog(*, generated_at: str, published_at: str | None) -> dict:
    items = []
    if published_at is not None:
        items.append(
            {
                "id": "marketdesk-fixture-000001",
                "title": "Fixture institutional report",
                "institution": "Fixture Bank",
                "side": "sell",
                "published_at": published_at,
                "summary_points": ["Fixture point"],
            }
        )
    return {
        "schema": "research_vault.catalog.v1",
        "generated_at": generated_at,
        "count": len(items),
        "institutions": ["Fixture Bank"] if items else [],
        "items": items,
    }


def _run_research_source_guard(tmp_path: Path, catalog: dict, *, now: str):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.check_research_vault_source_freshness",
            "--catalog",
            str(catalog_path),
            "--now",
            now,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_research_source_guard_rejects_timestamp_only_false_green(tmp_path: Path) -> None:
    result = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-05T03:53:00Z",
            published_at="2026-08-25T16:47:24Z",
        ),
        now="2026-09-05T04:00:00Z",
    )
    assert result.returncode == 1
    assert "PRODUCER_STALE" in result.stdout
    assert "2026-08-25T16:47:24+00:00" in result.stdout


def test_research_source_guard_accepts_recent_report(tmp_path: Path) -> None:
    result = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-05T03:53:00Z",
            published_at="2026-09-04T18:00:00Z",
        ),
        now="2026-09-05T04:00:00Z",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SOURCE_FRESH" in result.stdout


def test_research_source_guard_allows_normal_friday_to_monday_gap(tmp_path: Path) -> None:
    result = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-07T11:53:00Z",
            published_at="2026-09-04T17:00:00Z",
        ),
        now="2026-09-07T12:00:00Z",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SOURCE_FRESH" in result.stdout
    assert '"limit_hours": 96.0' in result.stdout


def test_research_source_guard_fails_after_weekend_grace_expires(tmp_path: Path) -> None:
    result = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-09T11:53:00Z",
            published_at="2026-09-04T17:00:00Z",
        ),
        now="2026-09-09T12:00:00Z",
    )
    assert result.returncode == 1
    assert "PRODUCER_STALE" in result.stdout
    assert '"limit_hours": 48.0' in result.stdout


def test_research_source_guard_fails_typed_on_empty_invalid_and_future_rows(
    tmp_path: Path,
) -> None:
    empty = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-05T03:53:00Z",
            published_at=None,
        ),
        now="2026-09-05T04:00:00Z",
    )
    assert empty.returncode == 1
    assert "NO_REPORTS" in empty.stdout

    invalid = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-05T03:53:00Z",
            published_at="not-a-time",
        ),
        now="2026-09-05T04:00:00Z",
    )
    assert invalid.returncode == 1
    assert "LATEST_REPORT_INVALID" in invalid.stdout

    future = _run_research_source_guard(
        tmp_path,
        _research_catalog(
            generated_at="2026-09-05T03:53:00Z",
            published_at="2026-09-05T04:10:01Z",
        ),
        now="2026-09-05T04:00:00Z",
    )
    assert future.returncode == 1
    assert "FUTURE_REPORT_CLOCK" in future.stdout


def test_research_source_guard_is_wired_to_both_existing_health_owners() -> None:
    ingest = (ROOT / ".github" / "workflows" / "research-ingest.yml").read_text(
        encoding="utf-8"
    )
    heartbeat = (ROOT / ".github" / "workflows" / "vps-live-heartbeat.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts.check_research_vault_source_freshness" in ingest
    assert "steps.source_freshness.outputs.rc" in ingest
    assert "scripts.check_research_vault_source_freshness" in heartbeat
    assert "https://www.mastermind-x.com/api/research/catalog?limit=3&offset=0" in heartbeat
    assert "if: always()" in heartbeat
