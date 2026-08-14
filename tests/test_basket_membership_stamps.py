"""Point-in-time honesty of `data/baskets/membership.json` member stamps (W1-C).

WHAT WENT WRONG (measured 2026-08-07). `gold_miners` was created 2026-07-30 and
`silver_miners` 2026-08-05, yet every member of both claimed ``added: 2023-05-09``
— the file's `seed_date`. Read literally that says the desk had been watching the
whole precious-metals complex for three years. It had not: the rosters are days
old. The consequence was not cosmetic. ``data/basket_turn/ledger.jsonl`` stamps
``silver_miners IGNITION k=4`` on 2026-08-05, the same day the sleeve was curated,
and with back-dated membership there was nothing in the file to say that row is a
first observation rather than a detection.

WHY `added` IS NOT THE FIELD TO FIX. `added` is the equal-weight index-inclusion
mask, not a provenance stamp: ``engine/baskets.py:89-91`` builds the live mask as
``idx >= added`` and roughly twenty sibling engines repeat that shape
(``engine/basket_index.py:277``, ``engine/theme_scoring.py:960``,
``engine/group_flow.py:509``, ``engine/oracle/panel.py:976``, …). Rewriting `added`
to the true curation date truncates the price mask for **768 of 1,034 members
across 34 baskets** — including all eleven ``us_sector_*`` sleeves, 503 members
between them — collapsing their charts to days of history and dropping them under
``engine/narrative_rotation.py``'s ``MIN_HISTORY_D = 160`` floor. The back-projection
is a legitimate charting convention; what was missing was the disclosure and a
separate honest date.

WHAT THIS PINS. Every member carries `curated_added` — the date a curator actually
put that name in that basket — alongside the unchanged `added` mask, the file
explains the difference in `added_semantics`, and `history_note` (already surfaced
to readers via ``engine/baskets.py:291``) says the levels are back-projected. The
checks below run against the REAL committed file and against deliberately broken
synthetic documents, so the guard is proven able to see the failure rather than
merely agreeing with today's data.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MEMBERSHIP = ROOT / "data" / "baskets" / "membership.json"
LEDGER = ROOT / "data" / "basket_turn" / "ledger.jsonl"
LEDGER_META = ROOT / "data" / "basket_turn" / "ledger_meta.json"

#: The three precious-metals sleeves this program is accountable for. A live member
#: of any of them must be reachable by the graded universe — that is G0.5.
PRECIOUS_SLEEVES = ("gold_miners", "silver_miners", "pgm_miners")


@pytest.fixture(scope="module")
def membership() -> dict:
    return json.loads(MEMBERSHIP.read_text(encoding="utf-8"))


# ── the contract, as one function used against real AND broken documents ──────

def _changelog_names(basket: dict, ticker: str) -> bool:
    """True when the basket's changelog records a removal that names this ticker."""
    pat = re.compile(rf"\b{re.escape(ticker)}\b")
    return any(
        "remove" in str(c.get("action", "")).lower() and pat.search(str(c.get("note", "")))
        for c in basket.get("changelog") or []
    )


def pit_violations(doc: dict) -> list[str]:
    """Every way a membership document lies about when a name was curated.

    Deliberately returns a list rather than raising, so the same function can be
    pointed at the real file (expect empty) and at broken fixtures (expect a
    specific complaint). A guard that only ever sees passing input is not a guard.
    """
    out: list[str] = []
    seed = doc.get("seed_date") or ""
    baskets = doc.get("baskets") or {}

    any_backdated = False
    for bid, b in baskets.items():
        created = b.get("created") or seed
        for m in b.get("members") or []:
            t = m.get("ticker", "?")
            where = f"{bid}/{t}"
            added = m.get("added") or seed
            curated_added = m.get("curated_added")
            if not curated_added:
                out.append(f"{where}: no curated_added — the true curation date is unrecorded")
                continue
            try:
                date.fromisoformat(curated_added)
            except (TypeError, ValueError):
                out.append(f"{where}: curated_added {curated_added!r} is not an ISO date")
                continue
            if curated_added < created:
                out.append(
                    f"{where}: curated_added {curated_added} predates the basket's own "
                    f"created {created} — a name cannot be curated into a basket that "
                    f"did not exist yet")
            if curated_added < added:
                out.append(
                    f"{where}: curated_added {curated_added} is earlier than added "
                    f"{added} — back-projection only ever runs backwards")
            if added < created:
                any_backdated = True
                if curated_added == seed:
                    out.append(
                        f"{where}: curated_added is the seed_date {seed} on a basket "
                        f"created {created} — that is the back-dated stamp this guard exists "
                        f"to refuse, not a curation date")
            # A removal stamped BEFORE the basket's own record has two legitimate
            # readings and one bad one. Legitimate: `removed`, like `added`, is a
            # mask date, so a same-sweep exit closes the mask at the prior session
            # (non_ai_tech/IBM removed 2026-06-18 on a basket created 2026-06-19 —
            # the changelog dates the actual decision 2026-06-21); or the security
            # stopped existing before anyone curated it (silver_miners/MAG, GATO).
            # Bad: a removal nobody wrote down. Require ONE of the two explanations.
            removed = m.get("removed")
            if removed and removed < curated_added:
                explained = m.get("delisted_before_curation") or _changelog_names(b, t)
                if not explained:
                    out.append(
                        f"{where}: removed {removed} predates curated_added "
                        f"{curated_added} and nothing explains it — no changelog "
                        f"`remove` entry names {t} and no delisted_before_curation flag")

    if any_backdated:
        if not (doc.get("added_semantics") or "").strip():
            out.append(
                "members are back-dated ahead of their basket's created date but the file "
                "carries no added_semantics — the two dates' meanings are undocumented")
        note = (doc.get("history_note") or "").lower()
        if "back-projected" not in note:
            out.append(
                "members are back-dated but history_note does not disclose back-projection "
                "— readers are shown a chart nobody could have held")
    return out


# ── the real committed file ──────────────────────────────────────────────────

def test_live_membership_carries_honest_curation_stamps(membership) -> None:
    assert pit_violations(membership) == []


def test_every_member_has_a_curated_added_stamp(membership) -> None:
    missing = [
        f"{bid}/{m.get('ticker')}"
        for bid, b in membership["baskets"].items()
        for m in b["members"]
        if not m.get("curated_added")
    ]
    assert not missing, f"members with no curated_added: {missing[:20]}"


def test_the_2026_sleeves_no_longer_claim_a_2023_curation(membership) -> None:
    """The exact defect: gold_miners (created 2026-07-30) and silver_miners
    (2026-08-05) claiming their members were added on 2023-05-09. A curation
    LATER than the basket's creation is legitimate (gold_miners/B, the 2026-08-14
    wrong-issuer repair, is the first) — what this refuses is any stamp EARLIER
    than the basket existed, and the seed_date stamp in particular."""
    for bid in ("gold_miners", "silver_miners"):
        b = membership["baskets"][bid]
        created = b["created"]
        assert created.startswith("2026-"), f"{bid} created moved unexpectedly: {created}"
        for m in b["members"]:
            assert m["curated_added"] >= created, (
                f"{bid}/{m['ticker']} curated_added {m['curated_added']} predates the "
                f"basket's own creation date {created}")
            assert m["curated_added"] != membership["seed_date"]


def test_history_note_and_added_semantics_are_reader_facing(membership) -> None:
    """`history_note` reaches the basket page through engine/baskets.py:291, so the
    back-projection disclosure has a real consumer rather than sitting write-only."""
    note = membership["history_note"]
    assert "back-projected" in note.lower()
    assert "curated_added" in note
    semantics = membership["added_semantics"]
    assert "curated_added" in semantics and "`added`" in semantics


# ── the two securities that had already stopped existing ─────────────────────

@pytest.mark.parametrize(
    "ticker,removed,receipt",
    [("MAG", "2025-09-04", "25-NSE"), ("GATO", "2025-01-16", "25-NSE")],
)
def test_delisted_silver_members_are_stamped_not_silently_carried(
    membership, ticker: str, removed: str, receipt: str
) -> None:
    """MAG and GATO were the ONLY two members of any basket in this file with no
    price series in data/stocks, data/yahoo or data/baskets/ohlcv (census
    2026-08-07). The hole was a delisting, not a fetch gap: both were acquired
    before silver_miners was curated, and by companies already in the sleeve
    (PAAS and AG). Same shape as BLD in `housing`, pinned by
    tests/test_basket_ohlcv_freshness.py::test_bld_is_stamped_removed_in_live_membership.
    """
    rows = [m for m in membership["baskets"]["silver_miners"]["members"]
            if m["ticker"] == ticker]
    assert len(rows) == 1, f"{ticker} missing from silver_miners"
    m = rows[0]
    assert m["removed"] == removed
    assert m.get("delisted_before_curation") is True
    assert "DELISTED BEFORE CURATION" in m["rationale"]
    assert receipt in m["rationale"], "no SEC exchange-delisting receipt in the rationale"
    assert m["removed"] < m["curated_added"], (
        "the whole point of this row is that the delisting predates the curation")


def test_gold_miners_wrong_issuer_row_is_stamped_not_silently_carried(membership) -> None:
    """The 2026-08-14 identity repair. NYSE 'GOLD' stopped being Barrick on
    2025-05-08 (Barrick Mining trades as 'B' since 2025-05-09) and has been
    Gold.com, Inc. — fka A-Mark Precious Metals, a bullion dealer — since
    2025-12-02, yet the 2026-07-30 curation keyed the Barrick slot to 'GOLD':
    a live listing, absent from the dead registry, invisible to every store
    audit class, reading a DEALER's tape in a producers sleeve. Unlike
    MAG/GATO the security never stopped existing — the flag for that shape
    (`delisted_before_curation`) would be false here AND would wrongly drop
    GOLD from the fetch universe (Gold.com's file is correct as Gold.com).
    The repair instead stamps `removed` at the store tape's own FIRST bar so
    the inclusion interval is empty in BOTH read modes: the strict
    [added, removed) mask and the deep pit=False read that ignores `added`
    and gates on the tape's first bar (engine/basket_index._live_mask). B
    inherits the row's exact back-projected `added`, so the slot transfers
    wholesale — no gap, no double-count, no silent Gold.com 'Barrick era'."""
    b = membership["baskets"]["gold_miners"]
    rows = {m["ticker"]: m for m in b["members"]}
    g = rows["GOLD"]
    assert g["removed"] == "2014-03-17", "must equal data/baskets/ohlcv/GOLD.parquet's first bar"
    assert g["removed"] < g["added"], "the interval must be EMPTY, not merely short"
    assert not g.get("delisted_before_curation"), (
        "GOLD is a live listing (Gold.com) — the delisting flag is the wrong shape and "
        "would drop the correctly-maintained Gold.com file from the fetch universe")
    for needle in ("NEVER", "Gold.com", "1591588", "756894", "2025-12-02", "2025-05-09"):
        assert needle in g["rationale"], f"identity receipt {needle!r} missing from the rationale"
    assert _changelog_names(b, "GOLD"), "the removal must be written down in the changelog"

    bar = rows["B"]
    assert bar["removed"] is None
    assert bar["added"] == g["added"] == "2023-05-09", (
        "the slot transfers wholesale: B must carry the exact back-projected mask GOLD had")
    assert bar["curated_added"] == "2026-08-14"
    live = [m["ticker"] for m in b["members"] if not m.get("removed")]
    assert "GOLD" not in live and "B" in live and len(live) == 12, live


def test_b_curated_tape_is_barrick_and_not_the_goldcom_dealer_tape() -> None:
    """The replacement slot must be backed by the intended issuer's OHLCV tape.

    Shape checks keep a close-only fallback from masquerading as the curated plane;
    return correlations prove B agrees with Barrick's long Yahoo store and disagrees
    with the dealer tape under GOLD.
    """
    import pandas as pd

    curated = pd.read_parquet(ROOT / "data" / "baskets" / "ohlcv" / "B.parquet")
    barrick = pd.read_parquet(ROOT / "data" / "yahoo" / "B.parquet")
    dealer = pd.read_parquet(ROOT / "data" / "baskets" / "ohlcv" / "GOLD.parquet")

    assert isinstance(curated.index, pd.DatetimeIndex)
    assert curated.index.name == "Date"
    assert curated.index.is_monotonic_increasing and curated.index.is_unique
    assert list(curated.columns) == ["open", "high", "low", "close", "volume"]
    # Immutable seed receipt, not a ceiling: the membership collector advances this
    # curated tape nightly after the PR lands.
    assert len(curated) >= 3_172
    assert curated.index.min() == pd.Timestamp("2014-01-02")
    assert curated.index.max() >= pd.Timestamp("2026-08-13")

    b_pair = pd.concat(
        [curated["close"].pct_change(), barrick["close"].pct_change()], axis=1, join="inner"
    ).dropna()
    dealer_pair = pd.concat(
        [curated["close"].pct_change(), dealer["close"].pct_change()], axis=1, join="inner"
    ).dropna()
    assert b_pair.corr().iloc[0, 1] > 0.999
    assert dealer_pair.corr().iloc[0, 1] < 0.35


def test_gold_masks_to_zero_and_b_owns_the_slot_in_both_read_modes(membership) -> None:
    """Exercise the actual basket mask, not only the membership prose."""
    import pandas as pd

    from engine.basket_index import _live_mask

    rows = {
        row["ticker"]: row for row in membership["baskets"]["gold_miners"]["members"]
        if row["ticker"] in {"GOLD", "B"}
    }
    b = pd.read_parquet(ROOT / "data" / "baskets" / "ohlcv" / "B.parquet")["close"]
    gold = pd.read_parquet(ROOT / "data" / "baskets" / "ohlcv" / "GOLD.parquet")["close"]
    idx = b.index
    close = pd.concat({"GOLD": gold, "B": b}, axis=1, sort=False).reindex(idx)
    members = [rows["GOLD"], rows["B"]]

    strict = _live_mask(members, idx, ["GOLD", "B"], pit=True, close=close)
    deep = _live_mask(members, idx, ["GOLD", "B"], pit=False, close=close)
    assert int(strict["GOLD"].sum()) == 0
    assert int(deep["GOLD"].sum()) == 0
    b_row = rows["B"]
    strict_expected = idx >= pd.Timestamp(b_row["added"])
    if b_row.get("removed"):
        strict_expected &= idx < pd.Timestamp(b_row["removed"])
    assert int(strict["B"].sum()) == int(strict_expected.sum())
    assert int(deep["B"].sum()) == len(b)


def test_a_delisted_symbol_is_never_requested_nightly() -> None:
    """collectors/yahoo.py:93 turns stock_search.extra_tickers into the nightly fetch
    list. Listing a security that stopped existing parks a permanent entry in the
    missing-symbol warning, which is what config/delisted_symbols.yml exists to
    prevent — so a dead symbol must not be added there in the first place."""
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    extras = set(cfg.get("stock_search", {}).get("extra_tickers", []) or [])
    assert not ({"MAG", "GATO"} & extras), (
        "a delisted symbol was added to the nightly fetch list")


# ── G0.5: the complexes are actually reachable by the graded universe ────────

def test_precious_metals_members_are_all_reachable_by_the_graded_universe(membership) -> None:
    """The measured 2026-08-07 gap: the silver complex was absent from the graded US
    population entirely, so it was invisible through a 10-19% rally. A live member of
    any precious-metals sleeve must resolve either through the S&P Composite 1500
    pipeline or through stock_search.extra_tickers (collectors/yahoo.py:90-93 ->
    data/yahoo/<T>.parquet -> scripts/build_stock_library.py:801)."""
    import pandas as pd

    universe_p = ROOT / "data" / "universe" / "membership.parquet"
    if not universe_p.exists():                                  # pragma: no cover
        pytest.skip("S&P-1500 universe table not present in this checkout")
    indexed = set(pd.read_parquet(universe_p, columns=["ticker"])["ticker"].astype(str))

    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    scfg = cfg.get("stock_search", {}) or {}
    extras = set(scfg.get("extra_tickers", []) or [])
    names = scfg.get("extra_names", {}) or {}

    unreachable, unlabelled = [], []
    for bid in PRECIOUS_SLEEVES:
        for m in membership["baskets"][bid]["members"]:
            if m.get("removed"):
                continue
            t = m["ticker"]
            if t not in indexed and t not in extras:
                unreachable.append(f"{bid}/{t}")
            elif t in extras and t not in indexed and t not in names:
                unlabelled.append(f"{bid}/{t}")
    assert not unreachable, f"precious-metals members outside the graded universe: {unreachable}"
    assert not unlabelled, (
        f"extras with no extra_names entry — these render as bare 'ETF / macro': {unlabelled}")


def test_the_silver_sleeve_clears_the_render_floor(membership) -> None:
    """engine/baskets.py:205 skips a basket resolving fewer than 3 members. Stamping
    MAG and GATO removed takes silver_miners from 10 to 8."""
    live = [m["ticker"] for m in membership["baskets"]["silver_miners"]["members"]
            if not m.get("removed")]
    assert len(live) == 8, live
    assert {"MAG", "GATO"}.isdisjoint(live)


def test_the_pgm_sleeve_exists_and_discloses_its_thin_members(membership) -> None:
    b = membership["baskets"]["pgm_miners"]
    live = [m["ticker"] for m in b["members"] if not m.get("removed")]
    assert live == ["SBSW", "IMPUY", "ANGPY", "PLG"]
    assert len(live) > 3, "a basket sitting exactly on the 3-member floor dies on one bad pull"
    assert "CHARTER DEVIATION" in dict((m["ticker"], m["rationale"]) for m in b["members"])["PLG"]
    assert "OTC ADR" in b["thesis"] or "OTC ADRs" in b["thesis"]
    assert "physical platinum trust" in b["etf_proxy_note"]


# ── the fired ledger row is disclosed, never rewritten ───────────────────────

def test_the_silver_ignition_row_is_annotated_and_untouched() -> None:
    """Forward ledgers advance nightly only (per-file commit law), so the 2026-08-05
    curation-day IGNITION keeps its exact fired shape; the context lives in the meta
    sidecar instead. scripts/heal_basket_turn_ledger.py:239-265 only ever rewrites
    `quarantine` and `known_gaps`, so `curation_notes` survives a heal."""
    rows = [json.loads(ln) for ln in LEDGER.read_text(encoding="utf-8").splitlines() if ln.strip()]
    fired = [r for r in rows
             if r.get("basket_id") == "silver_miners" and r.get("date") == "2026-08-05"]
    assert len(fired) == 1
    assert fired[0]["state"] == "IGNITION" and fired[0]["k"] == 4, (
        "the fired row was mutated — a forward ledger's history is not editable")

    meta = json.loads(LEDGER_META.read_text(encoding="utf-8"))
    notes = [n for n in meta.get("curation_notes") or []
             if n.get("basket_id") == "silver_miners" and n.get("session") == "2026-08-05"]
    assert notes, "the curation-day IGNITION carries no disclosure in the meta sidecar"
    assert all(n.get("row_mutated") is False for n in notes)
    joined = " ".join(n["note"] for n in notes)
    assert "curated" in joined and "first-observation" in joined.lower()
    assert "MAG" in joined and "GATO" in joined


# ── proof the guard can see each failure ─────────────────────────────────────

def _doc() -> dict:
    return {
        "seed_date": "2023-05-09",
        "added_semantics": "`added` is the index-inclusion mask; `curated_added` is provenance.",
        "history_note": "Basket levels are back-projected; see curated_added.",
        "baskets": {
            "silver_miners": {
                "created": "2026-08-05",
                "members": [
                    {"ticker": "PAAS", "added": "2023-05-09",
                     "curated_added": "2026-08-05", "removed": None},
                ],
            },
        },
    }


def test_a_clean_synthetic_document_passes() -> None:
    assert pit_violations(_doc()) == []


def test_a_2026_basket_claiming_a_2023_curation_fails() -> None:
    """The acceptance gate, stated as a refutation: back-date the honest stamp and
    the guard must complain."""
    doc = _doc()
    doc["baskets"]["silver_miners"]["members"][0]["curated_added"] = "2023-05-09"
    bad = pit_violations(doc)
    assert any("back-dated stamp this guard exists to refuse" in v for v in bad), bad


def test_dropping_the_honest_stamp_entirely_fails() -> None:
    doc = _doc()
    del doc["baskets"]["silver_miners"]["members"][0]["curated_added"]
    assert any("no curated_added" in v for v in pit_violations(doc))


def test_a_curation_predating_its_own_basket_fails() -> None:
    doc = _doc()
    doc["baskets"]["silver_miners"]["members"][0]["curated_added"] = "2026-07-01"
    assert any("predates the basket's own created" in v for v in pit_violations(doc))


def test_a_stamp_running_forward_of_the_mask_is_allowed_but_never_backward() -> None:
    doc = _doc()
    doc["baskets"]["silver_miners"]["members"][0]["added"] = "2026-08-06"
    doc["baskets"]["silver_miners"]["members"][0]["curated_added"] = "2026-08-05"
    assert any("back-projection only ever runs backwards" in v for v in pit_violations(doc))


def test_stripping_the_disclosure_fails_even_with_honest_stamps() -> None:
    for key in ("added_semantics", "history_note"):
        doc = _doc()
        doc[key] = ""
        assert pit_violations(doc), f"removing {key} left the guard silent"


def test_a_member_delisted_before_it_was_curated_must_say_so() -> None:
    doc = _doc()
    doc["baskets"]["silver_miners"]["members"].append(
        {"ticker": "GATO", "added": "2023-05-09", "curated_added": "2026-08-05",
         "removed": "2025-01-16"})
    assert any("nothing explains it" in v for v in pit_violations(doc))
    doc["baskets"]["silver_miners"]["members"][-1]["delisted_before_curation"] = True
    assert pit_violations(doc) == []


def test_a_same_sweep_exit_is_explained_by_the_changelog_instead() -> None:
    """The legitimate sibling shape: `removed` is a mask date closed at the prior
    session, so it can sit a day before the basket's own record. non_ai_tech/IBM,
    memory_storage/NTAP, cybersecurity/NSSC+YOU and big_pharma/ZTS are all this —
    removed 2026-06-18 on baskets created 2026-06-19/06-21, with the decision dated
    2026-06-21 in the changelog. A changelog entry naming the ticker is the receipt."""
    doc = _doc()
    b = doc["baskets"]["silver_miners"]
    b["members"].append(
        {"ticker": "EXK", "added": "2023-05-09", "curated_added": "2026-08-05",
         "removed": "2026-08-04"})
    assert any("nothing explains it" in v for v in pit_violations(doc))
    b["changelog"] = [{"date": "2026-08-06", "action": "remove",
                       "note": "EXK: removed after coherence audit."}]
    assert pit_violations(doc) == []
    # ...and a changelog that names some OTHER ticker must not launder this one.
    b["changelog"] = [{"date": "2026-08-06", "action": "remove",
                       "note": "SVM: removed after coherence audit."}]
    assert any("nothing explains it" in v for v in pit_violations(doc))
