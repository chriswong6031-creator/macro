from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import vps_live_orchestrator as vlo
from scripts import watch_release_publications as wrp


def _http_result(body: bytes, *, last_modified: str = "Tue, 14 Jul 2026 12:30:00 GMT"):
    return {
        "status": 200,
        "body": body,
        "fingerprint": __import__("hashlib").sha256(body).hexdigest(),
        "etag": '"fixture"',
        "last_modified": last_modified,
        "content_type": "text/html",
    }


def test_release_watcher_seeds_before_release_then_detects_change():
    before = datetime(2026, 7, 14, 12, 25, tzinfo=timezone.utc)  # 08:25 ET
    after = datetime(2026, 7, 14, 12, 31, tzinfo=timezone.utc)   # 08:31 ET

    def seed_fetcher(spec, prior, timeout):
        assert spec.source_id == "bls_cpi"
        return _http_result(b"prior CPI release")

    state, payload = wrp.detect(now=before, state={}, fetcher=seed_fetcher)
    assert [row["type"] for row in payload["due"]] == ["CPI"]
    assert payload["publications"] == []

    def changed_fetcher(spec, prior, timeout):
        assert prior["fingerprint"]
        return _http_result(
            b"Consumer Price Index Transmission July 14, 2026 official publication"
        )

    state, payload = wrp.detect(now=after, state=state, fetcher=changed_fetcher)
    assert len(payload["publications"]) == 1
    publication = payload["publications"][0]
    assert publication["type"] == "CPI"
    assert publication["status"] == "published"
    assert publication["data_ready"] is False
    assert publication["is_context_only"] is True


def test_release_watcher_cold_start_recovers_from_official_date():
    after = datetime(2026, 7, 14, 12, 35, tzinfo=timezone.utc)

    def fetcher(spec, prior, timeout):
        return _http_result(
            b"CONSUMER PRICE INDEX - JUNE 2026 Transmission July 14, 2026"
        )

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    assert [row["type"] for row in payload["publications"]] == ["CPI"]


def test_atomic_publish_rejects_invalid_json(tmp_path: Path):
    source = tmp_path / "bad.json"
    target = tmp_path / "public" / "bad.json"
    source.write_text("{bad")
    with pytest.raises(ValueError, match="invalid JSON"):
        vlo.atomic_publish(source, target)
    assert not target.exists()


def test_atomic_publish_makes_browser_artifact_readable(tmp_path: Path):
    source = tmp_path / "good.json"
    target = tmp_path / "public" / "good.json"
    source.write_text('{"ok":true}')
    vlo.atomic_publish(source, target)
    assert target.stat().st_mode & 0o777 == 0o644


def test_command_can_publish_private_state_outside_public_root(tmp_path: Path):
    source = tmp_path / "stage" / "quotes_full.json"
    source.parent.mkdir()
    source.write_text('{"quotes":{}}')

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    orch = vlo.Orchestrator(
        live_dir=tmp_path / "public",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        runner=runner,
    )
    target = orch.state_dir / "quotes_full.json"
    result = orch.command(
        "private_snapshot",
        ["fixture"],
        outputs=((source, target),),
        timeout=1,
    )
    assert result.status == "ok"
    assert result.published == ("quotes_full.json",)
    assert target.stat().st_mode & 0o777 == 0o600


def test_fast_lane_staggers_overlay_and_risk(tmp_path: Path):
    even = vlo.Orchestrator(
        live_dir=tmp_path / "live",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        now=datetime(2026, 7, 20, 14, 2, tzinfo=timezone.utc),
    )
    even_names: list[str] = []
    even.module = lambda name, *args, **kwargs: even_names.append(name) or vlo.TaskResult(  # type: ignore[method-assign]
        name, "ok", 0.0
    )
    even.fast()
    assert "live_overlay" in even_names
    assert "risk_state" not in even_names

    odd = vlo.Orchestrator(
        live_dir=tmp_path / "live2",
        state_dir=tmp_path / "state2",
        data_dir=tmp_path / "data2",
        now=datetime(2026, 7, 20, 14, 3, tzinfo=timezone.utc),
    )
    odd_names: list[str] = []
    odd.module = lambda name, *args, **kwargs: odd_names.append(name) or vlo.TaskResult(  # type: ignore[method-assign]
        name, "ok", 0.0
    )
    odd.fast()
    assert "risk_state" in odd_names
    assert "turn_notifications" in odd_names
    assert "live_overlay" not in odd_names


def test_status_is_external_and_lane_scoped(tmp_path: Path):
    orch = vlo.Orchestrator(
        live_dir=tmp_path / "live",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
    )
    orch.results.append(vlo.TaskResult("fixture", "ok", 0.01, returncode=0))
    orch.write_status("fast", datetime.now(timezone.utc))
    public = json.loads((tmp_path / "live" / "orchestrator_status.json").read_text())
    assert public["lanes"]["fast"]["ok"] is True
    assert public["lanes"]["fast"]["tasks"][0]["name"] == "fixture"


def test_cutover_guards_keep_manual_recovery():
    root = Path(__file__).resolve().parents[1]
    for name in ("intraday-fastpath.yml", "intraday.yml", "live-quotes.yml", "btc-live.yml"):
        text = (root / ".github" / "workflows" / name).read_text()
        assert "vars.VPS_LIVE_PRIMARY != 'true'" in text
        assert "github.event_name == 'workflow_dispatch'" in text


def test_caddy_serves_live_store_without_cache():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "Caddyfile").read_text()
    assert "@vps_live" in text
    assert "handle /live/*" in text
    assert "root * /var/lib/macro-live/public" in text
    assert 'Cache-Control "no-store"' in text
    assert "not path /live/* /marketdata/sp500_heatmap.json" in text
