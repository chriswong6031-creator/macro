"""Every kind the nightly emits must have an owner that can DECIDE it.

THE DEFECT (operator, 2026-08-05 queue screenshot: "these ones are one day
stale. like who tf wants to know yesterday's data").

A nightly `theme_list` sat in the approval queue 35 hours past its 12:00Z slot
still offering an Approve button, and two of its siblings sat SIXTY hours. They
were not slow - they were unowned. Three mechanisms each skipped them, each
assuming another had it:

  _auto_approve_pass       requires kind in publish.auto_approve_kinds AND
                           provenance == "publisher_live_movers". A nightly item
                           carries provenance "content_studio", so it never
                           matched - although `theme_list` and `mover` ARE in
                           auto_approve_kinds, which is what made the exclusion
                           below look safe.
  approval_desk.kinds      omitted both, on the written grounds that
                           "kind-scoped auto-approve already clears them seconds
                           after generation" - true of the publish-time lane,
                           assumed of the nightly one.
  expire_stale_planned     filtered on planned_kinds(), which contains neither,
                           so not even the reaper could retire them.

MEASURED over the whole shipped ledger before the fix: theme_list 0 of 5 posted,
mover 0 of 4 posted. 0%, against 19-26% for every desked kind. These are exactly
the "what is moving today / which sectors" posts the operator had asked for and
correctly reported never appeared.

The lesson these tests pin is not "add two strings to a list". It is that an
emitted item with no decider is INVISIBLE: it produces no ledger row, no
annotation and no alarm, so the failure looks like an empty queue rather than a
broken one.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())


def _nightly_emitted_kinds(cfg: dict) -> set[str]:
    """The kinds content_studio can put in the outbox.

    Read from the committed plan artifact when it is present (the ground truth
    for what the lane actually emits) and unioned with the planned kinds, so a
    kind that stops appearing in one night's plan cannot quietly narrow this.
    """
    from engine.marketing.outbox import planned_kinds

    kinds = set(planned_kinds())
    plan = ROOT / "data" / "marketing" / "content_plan.json"
    if plan.exists():
        import json
        try:
            doc = json.loads(plan.read_text())
        except ValueError:
            return kinds
        for acct in (doc.get("accounts") or []):
            for item in (acct.get("queue") or []):
                k = str(item.get("type") or item.get("kind") or "").strip()
                if k:
                    kinds.add(k)
    return kinds


def test_every_nightly_emitted_kind_has_a_decider():
    """No kind may be emitted by the nightly with nobody able to rule on it.

    The desk is the nightly's decider. `_auto_approve_pass` is NOT an owner for
    these items - it is provenance-scoped to the publish-time lane - so it
    cannot be counted as coverage here, and counting it is precisely the mistake
    that produced the defect.
    """
    cfg = _cfg()
    desk = cfg.get("approval_desk") or {}
    assert desk.get("enabled") is True, "the desk is the nightly's only decider"
    desked = {str(k) for k in (desk.get("kinds") or [])}

    emitted = _nightly_emitted_kinds(cfg)
    orphans = sorted(emitted - desked)
    assert not orphans, (
        f"kinds the nightly emits that no decider covers: {orphans}. An item "
        "with no decider never gets a ledger row, so it does not fail - it "
        "disappears. Add it to approval_desk.kinds, or stop emitting it."
    )


def test_the_two_kinds_that_were_orphaned_are_named():
    """A regression pin on the exact pair, so a config tidy cannot drop them.

    The generic closure test above would also catch this, but only while the
    plan artifact happens to contain them. This one does not depend on that.
    """
    desked = {str(k) for k in ((_cfg().get("approval_desk") or {}).get("kinds") or [])}
    for kind in ("mover", "theme_list"):
        assert kind in desked, (
            f"{kind} is emitted by content_studio and was unowned for its whole "
            "history (0 posted). It must stay desked."
        )


def test_the_reaper_retires_a_non_planned_nightly_kind(tmp_path, monkeypatch):
    """End to end: a stale content_studio theme_list is quarantined.

    Only meaningful while theme_list is NOT a planned kind - if that changes,
    the reaper's old kind filter would have covered it and this pins nothing.
    """
    from datetime import datetime, timedelta, timezone

    from engine.marketing import outbox
    from engine.marketing.outbox import planned_kinds

    assert "theme_list" not in set(planned_kinds())

    now = datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc)
    stale = (now - timedelta(hours=60)).isoformat().replace("+00:00", "Z")

    d = tmp_path / "data" / "marketing" / "outbox"
    d.mkdir(parents=True)
    item = {"schema": "marketing.outbox/v1", "id": "ob-x-1", "kind": "theme_list",
            "account": "flagship", "provenance": "content_studio",
            "as_of": "2026-08-04", "scheduled_at": stale, "text": "t"}
    (d / "items.jsonl").write_text(json.dumps(item) + "\n")
    (d / "status_ledger.jsonl").write_text("")

    out = outbox.expire_stale_planned(tmp_path, now=now)
    assert out["expired"] == 1, (
        f"a 60h-stale content_studio theme_list must be retired, got {out}")
    assert outbox.fold_state(tmp_path)["status"]["ob-x-1"] == "quarantined"

