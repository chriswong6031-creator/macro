"""tests/test_marketing_metrics_poll_quota.py — telemetry may not outbid posting.

THE INCIDENT (2026-08-03). `marketing-publish` ran the metrics poller on every
one of its ~30 daily sweeps, against ~54 targets, on the SAME Buffer token and
the SAME 24h quota the publisher posts with. The loop had no rate-limit
awareness: it took a 429 on the second call and then made 52 more doomed ones,
each still counted. Buffer answered `Retry-After: 20696` (5.7 hours) and the
next sweep's approved, due, human-audited post was refused with
`rate_limited=1`. Five consecutive days had ended with the desk network posting
nothing.

The ruling these tests pin: metrics are diagnostics, posting is the product, and
when they compete for one allowance the product wins.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.marketing_metrics_poll as MP


NOW = datetime(2026, 8, 3, 14, 31, tzinfo=timezone.utc)


class _Res:
    def __init__(self, ok, error=None):
        self.ok = ok
        self.error = error
        self.metrics = {"impressions": 10} if ok else {}
        self.raw = None
        self.metrics_updated_at = None
        self.external_url = None


class _Pub:
    """Counts calls so a test can prove what was NOT spent."""

    def __init__(self, fail_from: int | None = None, error: str = "Buffer returned 429"):
        self.calls = 0
        self._fail_from = fail_from
        self._error = error

    def fetch_post_metrics(self, remote_id, *, now=None):
        self.calls += 1
        if self._fail_from is not None and self.calls >= self._fail_from:
            return _Res(False, self._error)
        return _Res(True)


def _targets(monkeypatch, n: int) -> None:
    monkeypatch.setattr(MP, "gather_targets", lambda *a, **k: [
        {"remote_id": f"r{i}", "account": "flagship", "external_url": None}
        for i in range(n)
    ])


class TestARateLimitStopsTheRun:
    @pytest.mark.parametrize("error", [
        "Buffer returned 429 (Retry-After: 20696)",
        "graphql_error: rate limit exceeded",
        "HTTP 429 Too Many Requests",
        "quota exhausted for this token",
    ])
    def test_every_shape_of_throttle_is_recognised(self, error):
        assert MP._is_rate_limited(error), error

    def test_an_ordinary_failure_is_not_a_throttle(self):
        assert not MP._is_rate_limited("graphql_error: Post not found")
        assert not MP._is_rate_limited(None)

    def test_the_run_stops_on_the_first_429_instead_of_burning_the_rest(
        self, tmp_path, monkeypatch, capsys
    ):
        """THE PIN. Pre-fix this made 54 calls for 1 usable answer; the other 52
        spent the posting allowance to learn nothing."""
        _targets(monkeypatch, 54)
        pub = _Pub(fail_from=2)
        out = MP.poll(Path(tmp_path), now=NOW, publisher=pub)

        assert pub.calls == 2, f"kept calling past the 429: {pub.calls} calls"
        assert out["stopped"] == "rate_limited"
        assert out["polled"] == 2
        line = [l for l in capsys.readouterr().out.splitlines()
                if l.startswith("::warning title=marketing-metrics-poll-rate-limited")]
        assert line, "a run that abandons 52 targets must say so at line start"
        assert "52" in line[0], "the warning must name what it left un-polled"

    def test_a_healthy_run_is_still_capped(self, tmp_path, monkeypatch):
        """Even with no 429, one lane may not ask for the whole allowance."""
        _targets(monkeypatch, 200)
        pub = _Pub()
        out = MP.poll(Path(tmp_path), now=NOW, publisher=pub)
        assert pub.calls == MP._MAX_CALLS_PER_RUN
        assert out["stopped"] == "max_calls"

    def test_a_short_target_list_runs_clean_and_reports_no_stop(self, tmp_path, monkeypatch):
        """`stopped` must stay None when nothing was abandoned — otherwise a
        healthy run reads like a throttled one."""
        _targets(monkeypatch, 3)
        pub = _Pub()
        out = MP.poll(Path(tmp_path), now=NOW, publisher=pub)
        assert pub.calls == 3
        assert out["stopped"] is None
        assert out["polled"] == 3


class TestTheWorkflowPollsOnceADayNotOncePerSweep:
    WF = Path(__file__).resolve().parents[1] / ".github/workflows/marketing-publish.yml"

    def test_the_poll_step_is_clock_gated(self):
        import yaml
        steps = yaml.safe_load(self.WF.read_text())["jobs"]["publish"]["steps"]
        step = [s for s in steps if "poll post metrics" in str(s.get("name", ""))][0]
        run = step["run"]
        assert 'date -u +%H' in run and '"13"' in run, (
            "the poller must be gated to one hour a day")
        assert 'github.event_name' in run and 'schedule' in run, (
            "a manual dispatch must still poll")

    def test_the_gate_is_not_keyed_on_event_schedule(self):
        """The first version of this gate compared `github.event.schedule` to a
        single cron string. This workflow declares ONE cron for all 30 slots, so
        that value is identical on every sweep and the gate would have silenced
        the poller entirely rather than throttling it."""
        # COMMENTS EXCLUDED ON PURPOSE: the fix's own comment explains why
        # `github.event.schedule` is the wrong lever, and a guard that trips on
        # its own rationale teaches the next reader to delete the rationale.
        live = "\n".join(
            ln for ln in self.WF.read_text().splitlines()
            if not ln.lstrip().startswith("#")
        )
        assert "github.event.schedule" not in live, (
            "one cron covers every slot — event.schedule cannot single out an hour")
