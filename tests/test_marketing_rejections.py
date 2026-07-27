"""tests/test_marketing_rejections.py — the operator feedback loop.

Reject is the verdict Hold never was: terminal, and it records WHY. These pin
the properties that make the loop trustworthy — a rejection leaves the review
rail, the reason survives, exporting clears the BOX without destroying the
CORPUS, and a second export cannot re-serve work already reviewed.
"""
from __future__ import annotations

import json

import pytest


# Per-ticker DISTINCT copy: the enqueue-time near-dup guard (2026-07-27, token
# Jaccard ≥ 0.7 per account) would collapse two watchlist posts that share the
# same skeleton and only swap the cashtag — a real "deeply reworded" repeat. Real
# per-ticker posts differ in price/move/wording, so give each its own body.
_TICKER_COPY = {
    "TSLA": "$TSLA into the week\n\nClosed 313, down 18% — still bleeding below the 200-day.",
    "MSFT": "$MSFT heading into earnings\n\nHolding 420 after a shallow three percent dip.",
    "NVDA": "$NVDA momentum check\n\nRipped to 132 on a nine percent breakout, volume huge.",
    "AAPL": "$AAPL quietly basing\n\nCoiled near 195 for weeks; a breakout would need catalysts.",
}


def _item(root, ticker="TSLA", text=None, as_of="2026-07-26"):
    from engine.marketing.outbox import make_item, enqueue
    _default = _TICKER_COPY.get(ticker, f"${ticker} weekly note\n\nUnique read on {ticker} today.")
    it = make_item(
        account="flagship", kind="watchlist",
        text=text or _default,
        as_of=as_of, provenance="weekend_levels",
        source={"ticker": ticker, "state": "downtrend"},
        media=[{"kind": "chart_svg", "path": f"p/{ticker}.svg", "chart_id": ticker,
                "ticker": ticker, "media_url": f"https://pub-x.r2.dev/{ticker}.png"}],
    )
    enqueue(it, root=root)
    return it


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "data" / "marketing" / "outbox").mkdir(parents=True)
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Reject: terminal, and it keeps the reason
# ─────────────────────────────────────────────────────────────────────────────

def test_reject_is_terminal_and_leaves_the_review_rail(repo):
    from admin import marketing as M
    from engine.marketing.outbox import fold_state

    it = _item(repo)
    assert fold_state(repo)["status"][it["id"]] == "queued"

    res = M.reject_outbox(it["id"], reason="reads like a template", root=repo)
    assert res["ok"] and res["rejected"] and res["logged"]
    # quarantined is terminal — app.js treats it as history, not review rail.
    assert fold_state(repo)["status"][it["id"]] == "quarantined"


def test_rejecting_twice_is_refused(repo):
    """Hold is reversible; reject is not. A second reject must not re-log."""
    from admin import marketing as M
    it = _item(repo)
    assert M.reject_outbox(it["id"], root=repo)["ok"] is True
    again = M.reject_outbox(it["id"], root=repo)
    assert again["ok"] is False
    assert M.rejections_pending(root=repo)["count"] == 1


def test_reject_unknown_id_is_refused(repo):
    from admin import marketing as M
    r = M.reject_outbox("ob-nope", root=repo)
    assert r["ok"] is False and "unknown" in r["error"]


def test_reason_is_optional(repo):
    """Forcing a sentence out of an operator mid-triage yields 'bad' fifty times."""
    from admin import marketing as M
    it = _item(repo)
    assert M.reject_outbox(it["id"], root=repo)["ok"] is True
    row = M.rejections_pending(root=repo)["rejections"][0]
    assert row["reason"] is None


def test_rejection_snapshots_the_post_not_a_pointer(repo):
    """The corpus must outlive the queue: text and chart are copied in."""
    from admin import marketing as M
    it = _item(repo, ticker="MSFT")
    M.reject_outbox(it["id"], reason="stiff", root=repo)
    row = M.rejections_pending(root=repo)["rejections"][0]
    assert row["text"] == it["text"]
    assert row["ticker"] == "MSFT"
    assert row["provenance"] == "weekend_levels"
    assert row["media"][0]["media_url"].endswith("MSFT.png")
    assert row["reason"] == "stiff"


# ─────────────────────────────────────────────────────────────────────────────
# Export: clears the VIEW, keeps the CORPUS
# ─────────────────────────────────────────────────────────────────────────────

def test_export_clears_the_box_but_keeps_the_ledger(repo):
    from admin import marketing as M
    from engine.marketing import rejections as R

    for tk in ("TSLA", "MSFT"):
        M.reject_outbox(_item(repo, ticker=tk)["id"], reason=f"{tk} bad", root=repo)
    assert M.rejections_pending(root=repo)["count"] == 2

    ex = M.export_rejections(root=repo)
    assert ex["ok"] and ex["count"] == 2 and ex["cleared"] is True
    assert ex["filename"].startswith("rejected-posts-") and ex["filename"].endswith(".md")

    # The box is empty — no mixing reviewed work with new.
    assert M.rejections_pending(root=repo)["count"] == 0
    # ...but the rows are still on disk, which is the whole point of the loop.
    raw = R.ledger_path(repo).read_text().splitlines()
    kept = [json.loads(l) for l in raw if json.loads(l).get("row") == "rejection"]
    assert len(kept) == 2


def test_export_with_nothing_pending_is_refused(repo):
    from admin import marketing as M
    r = M.export_rejections(root=repo)
    assert r["ok"] is False and r["count"] == 0


def test_a_later_rejection_starts_a_fresh_batch(repo):
    """New rejections after an export must not re-serve the exported ones."""
    from admin import marketing as M
    M.reject_outbox(_item(repo, ticker="TSLA")["id"], root=repo)
    M.export_rejections(root=repo)

    M.reject_outbox(_item(repo, ticker="NVDA")["id"], reason="awkward", root=repo)
    pend = M.rejections_pending(root=repo)
    assert pend["count"] == 1
    assert pend["rejections"][0]["ticker"] == "NVDA"

    ex = M.export_rejections(root=repo)
    assert ex["count"] == 1 and "TSLA" not in ex["markdown"]


def test_markdown_is_annotatable(repo):
    from admin import marketing as M
    M.reject_outbox(_item(repo, ticker="TSLA")["id"], reason="template-y", root=repo)
    md = M.export_rejections(root=repo)["markdown"]

    assert md.startswith("# Rejected posts")
    assert "**What's wrong:**" in md          # the field the operator fills in
    assert "> $TSLA into the week" in md      # the post, quoted verbatim
    assert "https://pub-x.r2.dev/TSLA.png" in md
    assert "Rejected because: template-y" in md


def test_export_is_fail_soft_on_a_broken_ledger(repo):
    """A garbage line must not take the box down."""
    from admin import marketing as M
    from engine.marketing import rejections as R
    M.reject_outbox(_item(repo)["id"], root=repo)
    with R.ledger_path(repo).open("a") as f:
        f.write("{not json at all\n")
    assert M.rejections_pending(root=repo)["count"] == 1
