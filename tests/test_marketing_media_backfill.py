"""tests/test_marketing_media_backfill.py — the chart-recovery lane actually runs.

A marketing post attaches a chart only when its outbox item carries a PUBLIC
https media_url. That stamp happens once, inside the nightly's content_studio
build, and only if R2 creds were live in that process. Miss the window and the
day's posts are permanently text-only — against a standing operator law that a
ticker post ships with a picture or does not ship.

This lane is the way back. It was `workflow_dispatch` ONLY, which made it a
recovery path that ran only when somebody already knew the day was broken. The
symptom is silent: text-only posts look like a quiet day, not a fault. Production
lost a day exactly this way — 2026-07-28 left 53 outbox media entries with no
public URL, and the 37 sidecar rows for that date are the manual rescue somebody
had to notice and launch.

Pinned here: the schedule exists, it stays OFF the render pool, the unattended
sweep is bounded, and an explicit --as-of still overrides that bound.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "marketing-media-backfill.yml"


def _workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _triggers(doc: dict) -> dict:
    # PyYAML parses the bare key `on:` as the boolean True.
    return doc.get(True) or doc.get("on") or {}


class TestTheRecoveryLaneRuns:
    def test_it_is_scheduled_and_not_dispatch_only(self):
        on = _triggers(_workflow())
        assert "schedule" in on, (
            "the chart-recovery lane is dispatch-only again — it will run only "
            "when someone already knows the day shipped text-only, which is the "
            "one thing nobody can see from the outside"
        )
        crons = [str(e.get("cron")) for e in on["schedule"]]
        assert crons, "an empty schedule block never fires"

    def test_it_runs_more_than_once_a_day(self):
        """A single daily pass cannot rescue an intraday failure.

        Hot-tape cards are built through the session; a card whose upload fails
        at 15:00 must still be recoverable while slots remain to post it into.
        """
        on = _triggers(_workflow())
        hours = set()
        for entry in on["schedule"]:
            fields = str(entry.get("cron")).split()
            assert len(fields) == 5, f"malformed cron: {entry}"
            for part in fields[1].split(","):
                hours.add(part)
        assert len(hours) >= 2, f"only fires at hour(s) {hours}"

    def test_it_stays_off_the_render_pool(self):
        """The macstudio pool carries a ~67-minute nightly budget that is law.

        This lane rasterizes charts, so putting it on a self-hosted runner would
        spend that budget three times a day on recovery work.
        """
        job = _workflow()["jobs"]["backfill"]
        assert job["runs-on"] == "ubuntu-latest", job["runs-on"]

    def test_an_unattended_sweep_is_age_bounded(self):
        """The sidecar records SUCCESSES only.

        So a hole that cannot be filled — missing SVG, unrasterizable card —
        stays in the missing set forever and would be re-attempted on every run.
        Harmless once; unbounded growth on a cron.
        """
        body = WORKFLOW.read_text(encoding="utf-8")
        assert "--max-age-days" in body
        assert "schedule" in body.split("--max-age-days")[0][-400:], (
            "the age bound must be applied to the SCHEDULED run specifically — "
            "applying it unconditionally would silently cripple a manual rescue"
        )


class TestTheAgeBoundCannotSilenceARescue:
    """`--as-of` is an operator naming a date. It must win over a default bound.

    Otherwise rescuing a week-old day reports "0 to publish" and the operator
    reasonably concludes the outbox is already clean.
    """

    ITEMS = [
        {"as_of": "2026-07-30", "media": [{"chart_id": "today"}]},
        {"as_of": "2026-07-24", "media": [{"chart_id": "old"}]},
        {"as_of": "not-a-date", "media": [{"chart_id": "unparseable"}]},
        {"as_of": "2026-07-30",
         "media": [{"chart_id": "hosted", "media_url": "https://x/y.png"}]},
    ]
    TODAY = date(2026, 7, 30)

    def _ids(self, as_of, bound):
        from scripts.marketing_media_backfill import _iter_missing

        return [m["chart_id"]
                for _, m in _iter_missing(self.ITEMS, as_of, bound, self.TODAY)]

    def test_the_bound_drops_stale_items_on_an_unattended_sweep(self):
        assert self._ids(None, 3) == ["today", "unparseable"]

    def test_an_explicit_as_of_overrides_the_bound(self):
        assert self._ids("2026-07-24", 3) == ["old"]

    def test_no_bound_is_still_no_bound(self):
        assert self._ids(None, None) == ["today", "old", "unparseable"]

    def test_an_already_hosted_entry_is_never_touched(self):
        """This script fills holes; it must never re-upload a working image."""
        assert "hosted" not in self._ids(None, None)

    def test_an_unparseable_date_is_kept_not_dropped(self):
        """Fail OPEN on a bad date.

        Dropping an item because its date did not parse would silently shrink
        the recovery set, which is the one thing this script exists not to do.
        """
        from scripts.marketing_media_backfill import _older_than

        assert _older_than("garbage", 3, self.TODAY) is False
        assert _older_than("", 3, self.TODAY) is False
        assert _older_than(None, 3, self.TODAY) is False
        assert _older_than("2026-07-24", 3, self.TODAY) is True
        assert _older_than("2026-07-29", 3, self.TODAY) is False


class TestAnR2CredentialWithoutBoto3IsADeadLane:
    """A lane that is handed R2 secrets and cannot spend them.

    THE 2026-07-30 OUTAGE, in one missing package. `marketing-hot-tape.yml`
    passed R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET to
    the radar step and installed `pyyaml requests pyarrow anthropic`. No boto3.

    Nothing failed. `media_publish._client` takes the branch that only logs —
    "boto3 not installed — cannot upload chart PNG" — `publish_chart_png`
    returns None, `publish_card` returns media_url=None, and
    `hot_tape_radar._card` reads that as `no-media-url` and attaches NO media
    entry. The lane ran all day at full green: 8,081 SVG cards rendered and
    committed (392 MB into git), ZERO rows in media_urls.jsonl, and all 19
    hot-tape posts chartless. One reached the live flagship naming $COHR $GLW
    $JBL with no picture.

    Two properties make it invisible without this test. The upload is fail-soft
    by design (a dead R2 must degrade an image, never drop a post), and the
    media backfill — the lane built to heal exactly this — attaches URLs to
    EXISTING media[] entries, so an item that never got one is unreachable by
    the recovery path too.

    The invariant is narrow and mechanical: handing a job R2 credentials is a
    statement that it uploads something. If it cannot import the client, the
    credentials are decoration.
    """

    WORKFLOW_DIR = ROOT / ".github" / "workflows"

    def _jobs_with_r2(self):
        """[(workflow, job, install_run_text)] for every job given R2 creds."""
        yaml = pytest.importorskip("yaml")
        out = []
        for path in sorted(self.WORKFLOW_DIR.glob("*.yml")):
            raw = path.read_text(encoding="utf-8")
            if "R2_ACCESS_KEY_ID" not in raw:
                continue
            try:
                doc = yaml.safe_load(raw)
            except Exception:  # noqa: BLE001 — a malformed file is another test's job
                continue
            if not isinstance(doc, dict):
                continue
            for job_name, job in (doc.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
                env_blobs = [str(job.get("env") or "")] + [
                    str(s.get("env") or "") for s in steps
                ]
                if not any("R2_ACCESS_KEY_ID" in b for b in env_blobs):
                    continue
                runs = " ".join(str(s.get("run") or "") for s in steps)
                out.append((path.name, str(job_name), runs))
        return out

    def test_the_sweep_finds_the_lanes_it_is_meant_to_cover(self):
        """A census that matches nothing passes vacuously."""
        found = {w for w, _, _ in self._jobs_with_r2()}
        assert "marketing-hot-tape.yml" in found, (
            "the hot-tape radar is the lane this guard was written for; if it "
            "no longer reads as R2-credentialed, the sweep below proves nothing"
        )
        assert len(found) >= 2

    def test_requirements_still_carries_the_client(self):
        """The nightly lanes satisfy this through `pip install -r`, so that file
        is load-bearing for them and the sweep below trusts it."""
        req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert any(line.strip().startswith("boto3") for line in req.splitlines()), (
            "requirements.txt no longer pins boto3; every lane that installs "
            "via -r just lost its R2 client"
        )

    def test_every_r2_credentialed_job_installs_the_client(self):
        # Two ways to have boto3: name it, or pull it in with the requirements
        # file (verified above to still list it). Anything else means the job
        # holds credentials it cannot use.
        offenders = [
            f"{wf}:{job}"
            for wf, job, runs in self._jobs_with_r2()
            if "boto3" not in runs and "-r requirements.txt" not in runs
        ]
        assert not offenders, (
            "these jobs are handed R2 credentials but never install boto3, so "
            "media_publish.publish_chart_png returns None on every card and the "
            "posts ship with no picture — silently, at full green: "
            + ", ".join(offenders)
        )
