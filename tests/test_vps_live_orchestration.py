from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import vps_live_orchestrator as vlo
from scripts import watch_release_publications as wrp
from scripts.check_vps_live_health import evaluate as evaluate_live_health

FOMC_STATEMENT = """
    <html><body>
    <p>July 29, 2026</p>
    <p>The Federal Open Market Committee approved the following statement
    for release by a 9 – 3 vote:</p>
    <p>The Committee decided to maintain the target range for the federal
    funds rate at 3-1/2 to 3-3/4 percent.</p>
    <p>Voting against the monetary policy action were Beth M. Hammack,
    Neel Kashkari, and Lorie K. Logan, who preferred to raise the target
    range for the federal funds rate by 1/4 percentage point at this
    meeting.</p>
    </body></html>
""".encode()


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


def test_fomc_watcher_publishes_verified_decision_facts():
    after = datetime(2026, 7, 29, 18, 0, 30, tzinfo=timezone.utc)  # 14:00:30 ET

    def fetcher(spec, prior, timeout):
        assert spec.source_id == "fed_fomc"
        assert spec.url.endswith("/monetary20260729a.htm")
        assert prior == {}
        return _http_result(
            FOMC_STATEMENT,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    assert payload["schema"] == "release_publications.v2"
    assert [row["type"] for row in payload["due"]] == ["FOMC"]
    publication = payload["publications"][0]
    assert publication["status"] == "published"
    assert publication["data_ready"] is True
    assert publication["scheduled_at"] == "2026-07-29T14:00:00-04:00"
    assert publication["source_released_at"] == "2026-07-29T18:00:15+00:00"
    assert publication["parser"] == {"name": "fomc", "version": 1}
    assert publication["source_url"].endswith("/monetary20260729a.htm")
    assert publication["actual"] == {
        "kind": "policy_rate",
        "action": "hold",
        "target_low": 3.5,
        "target_high": 3.75,
        "unit": "percent",
        "vote_for": 9,
        "vote_against": 3,
        "dissent_preference": "hike",
        "dissent_basis_points": 25,
        "headline_en": "Fed holds at 3.50%–3.75%",
        "headline_zh": "美联储维持利率在 3.50%–3.75%",
        "summary_en": (
            "Fed holds at 3.50%–3.75% on a 9–3 vote. "
            "Dissenters preferred a rate increase of 25 basis points."
        ),
        "summary_zh": (
            "美联储维持利率在 3.50%–3.75%，表决结果为 9–3。 "
            "反对者倾向于加息 25 个基点。"
        ),
        "source_url": (
            "https://www.federalreserve.gov/newsevents/pressreleases/"
            "monetary20260729a.htm"
        ),
    }
    event = next(row for row in payload["events"] if row["type"] == "FOMC")
    assert event["status"] == "published"
    assert event["actual"]["action"] == "hold"
    assert all(row["event_id"] != event["event_id"] for row in payload["upcoming"])
    assert payload["poll_window"]["per_type_after_min"]["FOMC"] == 1440


def test_fomc_lifecycle_stops_calling_past_event_upcoming_on_source_delay():
    after = datetime(2026, 7, 29, 18, 2, tzinfo=timezone.utc)  # 14:02 ET

    def unavailable(spec, prior, timeout):
        raise RuntimeError("official source unavailable")

    _, payload = wrp.detect(now=after, state={}, fetcher=unavailable)
    event = next(row for row in payload["events"] if row["type"] == "FOMC")
    assert event["status"] == "awaiting_publication"
    assert payload["publications"] == []
    assert payload["source_health"][0]["status"] == "error"
    assert payload["source_health"][0]["error"] == "RuntimeError"
    assert "official source unavailable" not in json.dumps(payload)


def test_fomc_parser_handles_page_visible_before_scheduled_time():
    before = datetime(2026, 7, 29, 17, 59, 30, tzinfo=timezone.utc)
    after = datetime(2026, 7, 29, 18, 0, 1, tzinfo=timezone.utc)
    statement = (
        b"July 29, 2026 Federal Open Market Committee decided to maintain the "
        b"target range for the federal funds rate at 3-1/2 to 3-3/4 percent."
    )

    calls: list[bool] = []

    def fetcher(spec, prior, timeout):
        calls.append(bool(prior))
        if prior:
            return {
                "status": 304,
                "body": b"",
                "fingerprint": prior["fingerprint"],
                "etag": prior["etag"],
                "last_modified": prior["last_modified"],
                "content_type": prior["content_type"],
            }
        return _http_result(
            statement,
            last_modified="Wed, 29 Jul 2026 17:59:00 GMT",
        )

    state, payload = wrp.detect(now=before, state={}, fetcher=fetcher)
    assert payload["publications"] == []
    _, payload = wrp.detect(now=after, state=state, fetcher=fetcher)
    # The post-time conditional request is realistically a 304. The watcher
    # retries once without validators so the deterministic parser gets bytes.
    assert calls == [False, True, False]
    assert payload["publications"][0]["actual"]["target_high"] == 3.75


def test_fomc_unparseable_official_statement_is_not_reported_as_healthy():
    after = datetime(2026, 7, 29, 18, 3, 30, tzinfo=timezone.utc)
    changed_format = (
        b"<html><body>July 29, 2026 Federal Open Market Committee "
        b"target range decision expressed in an unsupported format.</body></html>"
    )

    def fetcher(spec, prior, timeout):
        return _http_result(
            changed_format,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    publication = payload["publications"][0]
    assert publication["status"] == "published_unparsed"
    assert publication["data_ready"] is False
    event = next(row for row in payload["events"] if row["type"] == "FOMC")
    assert event["status"] == "published_unparsed"

    health = _healthy_vps_status()
    health["checks"]["release_publications"].update(
        {
            "event_status": {"published_unparsed": 1, "scheduled": 3},
            "max_publication_lag_min": 3.5,
        }
    )
    assert any(
        "official publication detected" in failure
        and "remain unparsed 3.5m after schedule" in failure
        for failure in evaluate_live_health(health, now=after)
    )


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc),  # Jul 29 21:00 ET
        datetime(2026, 7, 30, 5, 0, tzinfo=timezone.utc),  # Jul 30 01:00 ET
    ],
)
def test_fomc_cold_start_recovers_through_24_hour_watch_window(now):
    def fetcher(spec, prior, timeout):
        assert spec.source_id == "fed_fomc"
        return _http_result(
            FOMC_STATEMENT,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=now, state={}, fetcher=fetcher)
    publication = next(row for row in payload["publications"] if row["type"] == "FOMC")
    assert publication["data_ready"] is True
    assert publication["actual"]["action"] == "hold"


def test_fomc_missing_result_stays_delayed_after_24_hour_poll_window():
    after_window = datetime(2026, 7, 30, 18, 1, tzinfo=timezone.utc)

    def no_fomc_fetch(spec, prior, timeout):
        assert spec.source_id != "fed_fomc"
        return _http_result(b"unrelated same-day release page")

    _, payload = wrp.detect(now=after_window, state={}, fetcher=no_fomc_fetch)
    event = next(
        row for row in payload["events"] if row["event_id"] == "fomc:2026-07-29"
    )
    assert event["status"] == "verification_delayed"
    assert all(row["type"] != "FOMC" for row in payload["due"])


def test_fomc_unparsed_result_stays_unhealthy_after_24_hours():
    after_window = datetime(2026, 7, 30, 18, 1, tzinfo=timezone.utc)
    event = {
        "event_id": "fomc:2026-07-29",
        "type": "FOMC",
        "date": "2026-07-29",
        "time_et": "14:00",
        "label": "FOMC rate decision",
        "label_zh": "美联储议息会议",
        "status": "published_unparsed",
        "data_ready": False,
        "detected_at": "2026-07-29T18:00:30+00:00",
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"FOMC:2026-07-29": event},
    }

    def no_fomc_fetch(spec, prior, timeout):
        assert spec.source_id != "fed_fomc"
        return _http_result(b"unrelated same-day release page")

    _, payload = wrp.detect(now=after_window, state=state, fetcher=no_fomc_fetch)
    retained = next(
        row for row in payload["events"] if row["event_id"] == "fomc:2026-07-29"
    )
    assert retained["status"] == "published_unparsed"
    assert any(
        row["event_id"] == "fomc:2026-07-29"
        for row in payload["publications"]
    )

    health = _healthy_vps_status()
    health["checks"]["release_publications"].update(
        {
            "event_status": {"published_unparsed": 1},
            "unparsed_publications": 1,
            "max_publication_lag_min": 1441,
        }
    )
    assert any(
        "remain unparsed" in failure
        for failure in evaluate_live_health(health, now=after_window)
    )


def test_fomc_unparsed_result_retries_and_recovers_after_fast_window():
    retry_tick = datetime(2026, 7, 30, 18, 15, tzinfo=timezone.utc)
    event = {
        "event_id": "fomc:2026-07-29",
        "type": "FOMC",
        "date": "2026-07-29",
        "time_et": "14:00",
        "label": "FOMC rate decision",
        "label_zh": "美联储议息会议",
        "status": "published_unparsed",
        "data_ready": False,
        "detected_at": "2026-07-29T18:00:30+00:00",
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"FOMC:2026-07-29": event},
    }

    def fetcher(spec, prior, timeout):
        if spec.source_id == "fed_fomc":
            return _http_result(
                FOMC_STATEMENT,
                last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
            )
        return _http_result(b"unrelated same-day release page")

    _, payload = wrp.detect(now=retry_tick, state=state, fetcher=fetcher)
    recovered = next(
        row for row in payload["publications"]
        if row["event_id"] == "fomc:2026-07-29"
    )
    assert recovered["status"] == "published"
    assert recovered["data_ready"] is True
    assert recovered["actual"]["action"] == "hold"


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


def test_quote_snapshot_quality_rejects_empty_or_low_coverage(tmp_path: Path):
    path = tmp_path / "quotes.json"
    path.write_text('{"quotes":{},"meta":{"requested":25,"resolved":0}}')
    assert "quality too low" in (
        vlo.quote_snapshot_error(path, min_resolved=5, min_coverage=0.2) or ""
    )
    path.write_text(
        json.dumps(
            {
                "quotes": {f"S{i}": {"price": i + 1} for i in range(5)},
                "meta": {"requested": 25, "resolved": 5},
            }
        )
    )
    assert vlo.quote_snapshot_error(
        path, min_resolved=5, min_coverage=0.2
    ) is None


def test_command_can_publish_private_state_outside_public_root(tmp_path: Path):
    source = tmp_path / "stage" / "quotes_full.json"
    source.parent.mkdir()

    def runner(*args, **kwargs):
        source.write_text('{"quotes":{}}')
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


def test_command_does_not_publish_stale_required_output(tmp_path: Path):
    source = tmp_path / "stage" / "overlay.json"
    target = tmp_path / "public" / "overlay.json"
    source.parent.mkdir()
    source.write_text('{"stale":true}')
    target.parent.mkdir()
    target.write_text('{"last_good":true}')

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="silent no-op", stderr="")

    orch = vlo.Orchestrator(
        live_dir=tmp_path / "public",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        runner=runner,
    )
    result = orch.command(
        "silent_noop",
        ["fixture"],
        outputs=((source, target),),
        timeout=1,
    )
    assert result.status == "failed"
    assert result.published == ()
    assert json.loads(target.read_text()) == {"last_good": True}


def test_main_returns_nonzero_when_lane_has_failed_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class FakeOrchestrator:
        def __init__(self, **kwargs):
            self.results = [vlo.TaskResult("fixture", "failed", 0.01)]

        def fast(self):
            return None

        def write_status(self, lane, started_at):
            return None

    lock = (tmp_path / "fast.lock").open("a+")
    monkeypatch.setattr(vlo, "_lock_lane", lambda state_dir, lane: lock)
    monkeypatch.setattr(vlo, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vps_live_orchestrator",
            "--lane",
            "fast",
            "--live-dir",
            str(tmp_path / "live"),
            "--state-dir",
            str(tmp_path / "state"),
            "--data-dir",
            str(tmp_path / "data"),
        ],
    )
    assert vlo.main() == 1


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
    external = (root / ".github" / "workflows" / "vps-live-heartbeat.yml").read_text()
    assert "runs-on: ubuntu-latest" in external
    assert "vars.VPS_LIVE_PRIMARY == 'true'" in external
    self_heal = (root / ".github" / "workflows" / "regime-self-heal.yml").read_text()
    assert "vars.VPS_LIVE_PRIMARY == 'true'" in self_heal
    assert "scripts.refresh_regime_if_stale" in self_heal
    assert "data/regime/latest.json data/market_state/latest.json data/reflexes/" in self_heal
    legacy = (root / ".github" / "workflows" / "heartbeat.yml").read_text()
    assert 'VPS_LIVE_PRIMARY: ${{ vars.VPS_LIVE_PRIMARY }}' in legacy


def test_live_setup_retires_legacy_only_after_smoke_and_timer_enable():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "live-setup.sh").read_text()
    smoke = text.index("systemctl start macro-live-fast.service")
    enable = text.index("systemctl enable --now")
    retire = text.index('grep -v "macro-live')
    assert smoke < enable < retire
    assert "first install failed; restoring legacy-only ownership" in text
    assert 'systemd-analyze verify "${unit_sources[@]}"' in text


def test_live_rollback_is_non_destructive_and_restores_legacy_writer():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "live-rollback.sh").read_text()
    assert "systemctl disable --now" in text
    assert "systemctl stop" in text
    assert "/usr/local/bin/macro-live" in text
    assert 'mv "$PUBLIC_DIR" "$backup_dir"' in text
    assert "rm -rf" not in text


def _healthy_vps_status() -> dict:
    return {
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


def test_vps_health_contract_covers_us_live_lanes():
    now = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    assert evaluate_live_health(_healthy_vps_status(), now=now) == []


def test_vps_health_contract_reports_failed_or_stale_lane():
    payload = _healthy_vps_status()
    payload["checks"]["orchestrator"]["lanes"]["snapshot"] = {
        "ok": False,
        "age_min": 22,
    }
    failures = evaluate_live_health(
        payload,
        now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert "lane snapshot: last run was not healthy" in failures
    assert any("lane snapshot: stale" in failure for failure in failures)


def test_vps_health_contract_reports_semantically_late_release():
    payload = _healthy_vps_status()
    payload["checks"]["release_publications"].update(
        {
            "event_status": {"awaiting_publication": 1, "scheduled": 3},
            "max_publication_lag_min": 2.5,
        }
    )
    failures = evaluate_live_health(
        payload,
        now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert (
        "release_publications: official result still unavailable 2.5m after schedule"
        in failures
    )


def test_vps_health_contract_does_not_require_equity_lanes_on_weekend():
    payload = _healthy_vps_status()
    del payload["checks"]["orchestrator"]["lanes"]["snapshot"]
    del payload["checks"]["orchestrator"]["lanes"]["bars"]
    del payload["checks"]["basket_pulse"]
    del payload["checks"]["flow_pulse"]
    assert evaluate_live_health(
        payload,
        now=datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc),
    ) == []


def test_caddy_serves_live_store_without_cache():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "Caddyfile").read_text()
    assert "@vps_public_live" in text
    assert "@vps_external" in text
    assert "handle /live/quotes.json" in text
    assert "handle /live/release_publications.json" in text
    assert "root * /var/lib/macro-live/public" in text
    assert 'Cache-Control "no-store"' in text
    # Only explicitly reviewed market-display and official-event facts bypass
    # auth. All other external live artifacts stay inside the fail-closed route.
    assert "handle /live/*" not in text
    protected = text[text.index("handle @reg_asset {") : text.index("@gate_html {")]
    assert "rewrite /api/regwall/check" in protected
    assert "rewrite /api/paywall/check" in protected
    assert "handle @vps_external" in protected
