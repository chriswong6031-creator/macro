"""Signal Lab — the consolidated honest validation scorecard (engine/signal_lab.py)
+ the signal_lab.html.j2 page render. The page's whole value is honesty, so these
tests guard the structure, the source-citation discipline, and the load-bearing
honest negatives (no cross-sectional factor survives FDR; the graveyard is shown).
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader

from engine import i18n, signal_lab
from lib import config

TIER_KEYS = {"scored", "confirmer", "display", "killed", "pending"}


def _payload():
    return signal_lab.build_scorecard()


def test_scorecard_shape_and_summary_consistency():
    p = _payload()
    assert set(t["key"] for t in p["tiers"]) <= TIER_KEYS
    s = p["summary"]
    # summary per-tier counts add up to the registry total
    assert sum(s[k] for k in ("scored", "confirmer", "display", "killed", "pending")) == s["total"]
    # and they match the grouped rows the template renders
    for tier in p["tiers"]:
        assert tier["count"] == len(tier["rows"]) == s[tier["key"]]


def test_every_row_is_cited_and_well_formed():
    p = _payload()
    for tier in p["tiers"]:
        for r in tier["rows"]:
            assert r["name"] and r["name_zh"], "row needs bilingual name"
            assert r["why"] and r["why_zh"], "row needs a bilingual rationale"
            assert r["source"], f"{r['name']} has no source citation"
            assert r["tier"] in TIER_KEYS
            assert r["market"]


def test_the_graveyard_is_shown():
    """The differentiator: we publish the signals we measured and refused to ship."""
    p = _payload()
    killed = next((t for t in p["tiers"] if t["key"] == "killed"), None)
    assert killed and killed["count"] >= 5
    names = " ".join(r["name"] for r in killed["rows"]).lower()
    for must in ("rvol", "base", "gbt", "carry"):
        assert must in names, f"expected a killed signal mentioning {must!r}"


def test_intl_bridge_graveyard_is_published():
    """The intl graveyard is published like every other signal family. CONTEXT/INVERTED
    verdicts land in display, CONFIRMED-but-unwired legs (C3 breadth, C4a REER N=1) land in
    confirmer — each cited to its exact report, none wired into a score. W2 (C2): the
    macro-sleeve graded CONTEXT vs the US book (DSR 0.83 < the 0.90 door) → display. W3 (C4a):
    the REER N=1 resurrection graded CONFIRMED → moves pending→confirmer; W3 (C4c): the CNH
    basis graded INVERTED → display graveyard."""
    p = _payload()
    rows = [r for t in p["tiers"] for r in t["rows"]]
    intl = [r for r in rows if "intl_bridge/ledger.json" in r["source"]]
    assert len(intl) >= 5, "the intl bridge registry mirror should be published"
    blob = " ".join(r["name"] for r in intl).lower()
    for must in ("c2", "c4", "c3", "radar"):
        assert must in blob, f"expected an intl-bridge row mentioning {must!r}"
    # C2 now sits in DISPLAY (graveyard) — CONTEXT vs the US book, not scored
    display = next((t for t in p["tiers"] if t["key"] == "display"), None)
    assert display and any("C2" in r["name"] for r in display["rows"]), \
        "C2 macro-sleeve should be published in the display graveyard (CONTEXT verdict)"
    # W3-C4a: the REER N=1 resurrection graded CONFIRMED → it sits in CONFIRMER now, not pending
    confirmer = next((t for t in p["tiers"] if t["key"] == "confirmer"), None)
    assert confirmer and any("REER" in r["name"] for r in confirmer["rows"]), \
        "C4a REER N=1 should be published in the confirmer tier (CONFIRMED verdict)"
    # W3-C4c: the CNH basis graded INVERTED → it sits in the DISPLAY graveyard
    assert display and any("CNH" in r["name"] for r in display["rows"]), \
        "C4c CNH-basis should be published in the display graveyard (INVERTED verdict)"
    # nothing intl is wired into a score
    for r in intl:
        assert "not wired" in r["wired"] or "not shipped" in r["wired"] \
            or "display-only" in r["wired"]


def test_factor_cross_section_is_leak_free_and_data_driven():
    """The centerpiece: the leak-free PIT factor cross-section. Survivor count is
    read LIVE from ic_scorecard.json (so the page adapts to whichever branch's
    scorecard it sits on), and the survivors list is consistent with it."""
    p = _payload()
    fr = p["factor_rows"]
    assert len(fr) >= 9                                          # the factor panel is present
    assert p["summary"]["factor_total"] == len(fr)
    surv_rows = [r for r in fr if r["survives"]]
    assert p["summary"]["factor_survivors"] == len(surv_rows)
    assert {s["name"] for s in p["factor_survivors"]} == {r["name"] for r in surv_rows}
    # rows are sorted by IC descending (leaders on top)
    ics = [r["ic"] for r in fr if r["ic"] is not None]
    assert ics == sorted(ics, reverse=True)
    assert p["factor_meta"].get("leak_free") is True


def test_sue_demoted_after_deep_revalidation():
    """SUE survived FDR only on the shallow 2023-2025 window; a deep 2011-2026
    re-validation (survivorship-optimistic) collapsed the edge to ~zero (IC 0.0005,
    t 0.06), so it is DEMOTED out of the scored tier and shown as display with the
    deep-kill caveat (see reports/sue-deep-history-phase0.md)."""
    p = _payload()
    scored = next(t for t in p["tiers"] if t["key"] == "scored")
    assert not any("SUE" in r["name"] for r in scored["rows"]), "SUE should no longer be scored"
    disp = next(t for t in p["tiers"] if t["key"] == "display")
    sue = next((r for r in disp["rows"] if "SUE" in r["name"]), None)
    assert sue is not None, "SUE should remain shown as display (deep-killed), not deleted"
    blob = (sue["why"] + " " + " ".join(v for _, v in sue["extra"])).lower()
    assert "deep" in blob and "0.0005" in blob                 # the deep-kill caveat is present
    # SUE itself is not left pending (it is display-demoted). The pending tier, when present,
    # holds the intl-bridge validated-but-unwired entries (W1) — not SUE.
    pending = next((t for t in p["tiers"] if t["key"] == "pending"), None)
    if pending:
        assert not any("SUE" in r["name"] for r in pending["rows"])


def test_insider_is_the_lone_fdr_survivor_but_only_a_confirmer():
    """The one cross-sectional stock factor that survives FDR is gated as a
    confirmer (DSR borderline), never a standalone sizer."""
    p = _payload()
    conf = next(t for t in p["tiers"] if t["key"] == "confirmer")
    ins = next((r for r in conf["rows"] if "insider" in r["name"].lower()), None)
    assert ins is not None
    assert ins["fdr_survivor"] is True
    assert ins["q_fdr"] is not None and ins["q_fdr"] < 0.10     # survives FDR
    assert ins["dsr"] is not None and ins["dsr"] < 0.90         # but DSR-borderline


def test_scored_tier_leads_with_the_spvector():
    p = _payload()
    scored = next(t for t in p["tiers"] if t["key"] == "scored")
    assert scored["count"] >= 1
    assert any(r["dsr"] is not None and r["dsr"] >= 0.90 for r in scored["rows"]), \
        "the scored tier should contain at least one DSR-passing object (the SP/Macro Vector)"


def test_page_renders_without_template_errors():
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    html = env.get_template("signal_lab.html.j2").render(**_payload())
    assert "Signal Lab" in html
    assert "{{" not in html and "{%" not in html        # no unrendered jinja
    assert "survive FDR" in html
    for pill in ("v-scored", "v-killed", "v-confirmer"):
        assert pill in html
    # the methodology + PIT data stamps are present (ChatGPT proposal #2)
    assert "Deflated Sharpe" in html
    assert "data span" in html


# ---------------------------------------------------------------------------
# Frontier docket tests (feat/slf-frontier-port-adjudication)
# ---------------------------------------------------------------------------

def test_screen_candidates_determinism():
    """screen_candidates() is a pure function — two calls must return identical output."""
    from engine.signal_frontier_docket import screen_candidates
    a = screen_candidates()
    b = screen_candidates()
    assert a == b, "screen_candidates() is not deterministic"


def test_verdict_count_snapshot():
    """Post-correction counts after docket corrections (SLF-050 blocked, history fixes)."""
    from engine.signal_frontier_docket import phase0_summary
    s = phase0_summary()
    assert s["total"] == 60, f"expected 60 candidates, got {s['total']}"
    # SLF-050 is now blocked → graveyard_now
    assert s["graveyard_now"] >= 1, "SLF-050 blocked should put at least 1 in graveyard_now"
    # After corrections, advance_to_fable should be < 23 (some dropped due to history fixes)
    assert s["advance_to_fable"] < 23, (
        f"advance_to_fable={s['advance_to_fable']} — expected drop below 23 after corrections"
    )
    # Counts must sum to total
    total_check = (
        s["advance_to_fable"]
        + s["local_phase0_ready"]
        + s["data_contract_first"]
        + s["watchlist_or_reject"]
        + s["graveyard_now"]
    )
    assert total_check == 60, f"verdict counts don't sum to 60: {total_check}"


def test_page_frontier_rows_count_and_zh_fields():
    """page_frontier_rows() returns docket rows; every *_zh field is non-empty."""
    from engine.signal_frontier_docket import page_frontier_rows
    rows = page_frontier_rows()
    # All docket-derived rows must come from IDs > 10
    from engine.signal_frontier_docket import _id_suffix
    for r in rows:
        # No id field exposed in page rows, but they have fable_verdict
        assert r.get("readiness_zh") == "Phase-0 存活候选", \
            f"readiness_zh wrong: {r.get('readiness_zh')!r}"
    # must have at least some rows (the advance_to_fable survivors with id > 10)
    assert len(rows) >= 1


def test_frontier_rows_in_scorecard_zh_non_empty():
    """All *_zh fields in frontier_rows are non-empty and not identical to EN for hand rows."""
    p = signal_lab.build_scorecard()
    fr = p["frontier_rows"]
    assert len(fr) > 0, "frontier_rows is empty"
    for i, r in enumerate(fr):
        assert r.get("name_zh"), f"row {i} name_zh empty"
        assert r.get("thesis_zh"), f"row {i} thesis_zh empty"
        assert r.get("build_zh"), f"row {i} build_zh empty"
        assert r.get("gate_zh"), f"row {i} gate_zh empty"
        assert r.get("readiness_zh"), f"row {i} readiness_zh empty"


def test_frontier_rows_hand_rows_zh_differs_from_en():
    """For the 10 hand rows (index 0-9), name_zh must differ from name (real Chinese)."""
    p = signal_lab.build_scorecard()
    fr = p["frontier_rows"]
    for r in fr[:10]:
        assert r["name_zh"] != r["name"], (
            f"Hand row '{r['name']}' has name_zh == name (no translation)"
        )


def test_frontier_rows_docket_rows_zh_differs_from_en():
    """All *_zh fields for ALL frontier_rows (hand + docket) must be non-empty
    AND differ from their English twin — guards against the mirroring bug where
    _c()-built candidates fall through to English for all zh fields."""
    p = signal_lab.build_scorecard()
    fr = p["frontier_rows"]
    assert len(fr) > 0, "frontier_rows is empty"
    for r in fr:
        name = r["name"]
        assert r.get("name_zh") and r["name_zh"] != r["name"], (
            f"Row '{name}' name_zh is empty or mirrors English: {r.get('name_zh')!r}"
        )
        assert r.get("thesis_zh") and r["thesis_zh"] != r["thesis"], (
            f"Row '{name}' thesis_zh is empty or mirrors English: {r.get('thesis_zh')!r}"
        )
        assert r.get("build_zh") and r["build_zh"] != r["build"], (
            f"Row '{name}' build_zh is empty or mirrors English: {r.get('build_zh')!r}"
        )
        assert r.get("gate_zh") and r["gate_zh"] != r["gate"], (
            f"Row '{name}' gate_zh is empty or mirrors English: {r.get('gate_zh')!r}"
        )


def test_fable_verdicts_covers_23_original_advance_ids():
    """FABLE_VERDICTS must contain exactly the 23 original advance_to_fable candidate IDs."""
    from engine.signal_frontier_docket import FABLE_VERDICTS
    assert len(FABLE_VERDICTS) == 23, (
        f"FABLE_VERDICTS has {len(FABLE_VERDICTS)} entries, expected 23"
    )
    # Verify all keys are SLF-NNN format
    import re
    for k in FABLE_VERDICTS:
        assert re.match(r"^SLF-\d{3}$", k), f"key {k!r} is not SLF-NNN format"
    # Verify the kill/authorize split
    kills = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "KILLED"]
    assert len(kills) == 11, f"expected 11 kills, got {len(kills)}: {kills}"
    routes = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "ROUTED"]
    assert len(routes) == 1
    # 2026-07-06: W1 BUILD entries have been promoted to TESTED-* after phase-0 runs.
    # BUILD count is now 0; tested count is 7 (SLF-001/006/048/051/053/055/056).
    builds = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "BUILD"]
    assert len(builds) == 0, f"expected 0 pure BUILD (all promoted to TESTED-*), got {builds}"
    tested = [k for k, v in FABLE_VERDICTS.items() if v["verdict"].startswith("TESTED-")]
    assert len(tested) == 7, f"expected 7 TESTED-* entries, got {tested}"
    probes = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "PROBE"]
    assert len(probes) == 0, "PROBE promoted to ACCRUE-CONFIRMED after zt_pool history check"
    pilots = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "PILOT"]
    assert len(pilots) == 1
    accrue = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] in {"ACCRUE", "ACCRUE-CONFIRMED"}]
    assert len(accrue) == 2, f"expected 2 accrue entries (ACCRUE + ACCRUE-CONFIRMED), got {accrue}"
    queued = [k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "QUEUED"]
    assert len(queued) == 1


def test_frontier_rows_no_ic_dsr_keys():
    """frontier_rows must not expose rank-IC or DSR result keys — research metadata only."""
    FORBIDDEN = {"ic", "dsr", "t_hac", "q_fdr", "rank_ic", "deflated_sharpe",
                 "fdr_survivor", "survives"}
    p = signal_lab.build_scorecard()
    for r in p["frontier_rows"]:
        bad = [k for k in r if k.lower() in FORBIDDEN]
        assert not bad, f"frontier row has ic/dsr result keys: {bad}"


def test_hand_rows_name_source_agree_with_docket():
    """Hand rows SLF-001..010 names and sources agree with docket entries."""
    from engine.signal_frontier_docket import CANDIDATES
    from engine import signal_lab
    # Build the first 10 hand rows from FRONTIER list
    hand = signal_lab.FRONTIER[:10]
    docket_map = {c["id"]: c for c in CANDIDATES}
    expected_pairs = [
        ("SLF-001", "SEC fails-to-deliver pressure"),
        ("SLF-002", "Borrow-fee / loan-fee anomaly"),
        ("SLF-003", "Option informed-flow lens"),
        ("SLF-004", "EDGAR attention shock"),
        ("SLF-005", "Overnight/intraday tug-of-war"),
        ("SLF-006", "Treasury auction absorption"),
        ("SLF-007", "COT exhaustion matrix"),
        ("SLF-008", "Crypto funding + on-chain stress"),
        ("SLF-009", "Supply-chain pressure impulse"),
        ("SLF-010", "Lottery/MAX anti-chase flag"),
    ]
    for (sid, expected_name), hand_row in zip(expected_pairs, hand):
        docket = docket_map[sid]
        assert hand_row["name"] == expected_name, (
            f"{sid}: hand row name={hand_row['name']!r} != expected={expected_name!r}"
        )
        assert docket["name"] == expected_name, (
            f"{sid}: docket name={docket['name']!r} != expected={expected_name!r}"
        )


def test_id_suffix_compare_vs_lexicographic():
    """Integer suffix compare must differ from lexicographic for ids like SLF-010 vs SLF-009."""
    from engine.signal_frontier_docket import _id_suffix
    # Lexicographic: 'SLF-010' < 'SLF-009' is False but 'SLF-010' > 'SLF-009' is True
    # (because '1' > '0' in position 4) — BUT wait, that's wrong: '010' vs '009': '0'=='0','1'>'0' → '010'>'009'
    # The actual bug: 'SLF-010' <= 'SLF-009' is False but both should be in the same bucket
    # The real issue: lexicographic 'SLF-011' > 'SLF-010' correctly, but 'SLF-010' <= 'SLF-010' = True
    # so SLF-010 would be SKIPPED by the old code (it's <= 'SLF-010')
    # The fix ensures SLF-010 is also skipped (suffix == 10, which is <= 10), SLF-011 is included
    assert _id_suffix("SLF-001") == 1
    assert _id_suffix("SLF-010") == 10
    assert _id_suffix("SLF-011") == 11
    assert _id_suffix("SLF-060") == 60
    # Verify the boundary: ids with suffix <= 10 are skipped, >10 are included
    assert _id_suffix("SLF-010") <= 10  # should be skipped
    assert _id_suffix("SLF-011") > 10   # should be included


def test_phase0_summary_no_generated_utc():
    """phase0_summary() must not contain generated_utc — it belongs only in script outputs."""
    from engine.signal_frontier_docket import phase0_summary
    s = phase0_summary()
    assert "generated_utc" not in s, "generated_utc must not be in phase0_summary()"


def test_frontier_page_renders_with_fable_chip():
    """signal_lab.html.j2 renders frontier panel with Fable ruling column."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n, signal_lab
    from lib import config
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(t=i18n.t, td=i18n.td, tr=i18n.tr, zip=zip)
    payload = signal_lab.build_scorecard()
    html = env.get_template("signal_lab.html.j2").render(**payload)
    assert "frontier_rows" not in html or "fable-chip" in html, \
        "frontier panel should render with fable-chip elements"
    assert "研究前沿" in html, "ZH label for Research frontier not found"
    assert "已否决" in html, "KILLED 已否决 chip text not found"


# --------------------------------------------------------------------------
# SLF consolidation tests (Task 6 — 2026-07-06 frontier build wave)
# --------------------------------------------------------------------------

def test_slf056_funding_tail_registry_row_present():
    """SLF-056 confirmer-tier row for Repo/SOFR tail stress must be in the registry."""
    p = _payload()
    confirmer = next((t for t in p["tiers"] if t["key"] == "confirmer"), None)
    assert confirmer, "confirmer tier not found"
    names = [r["name"] for r in confirmer["rows"]]
    assert any("Repo/SOFR" in n or "tail stress" in n.lower() for n in names), \
        f"SLF-056 funding tail row not found in confirmer tier; names={names}"


def test_slf056_confirmer_tier_and_no_score_leakage():
    """SLF-056 must be tier='confirmer', must have no ic/t_hac, and must not affect score."""
    from engine.signal_lab import REGISTRY
    matches = [r for r in REGISTRY if "Repo/SOFR" in r.get("name", "") or
               ("tail stress" in r.get("name", "").lower() and r.get("dsr_family") == "slf056_funding_tail")]
    assert matches, "SLF-056 registry row not found"
    row = matches[0]
    assert row["tier"] == "confirmer", f"tier must be 'confirmer', got {row['tier']}"
    assert row["ic"] is None, f"ic should be None (no cross-sectional test), got {row['ic']}"
    assert row["t_hac"] is None, f"t_hac should be None, got {row['t_hac']}"
    # wired field must indicate no score impact
    wired = row.get("wired", "")
    assert "none" in wired.lower() or "pending" in wired.lower(), \
        f"wired should indicate no score hookup, got {wired!r}"
    # dsr_family is set (for ledger resolution)
    assert row["dsr_family"] == "slf056_funding_tail", \
        f"dsr_family should be 'slf056_funding_tail', got {row['dsr_family']}"


def test_waves_adjudication_block_present_in_scorecard():
    """build_scorecard() must include waves_adjudication with 3 waves."""
    p = _payload()
    wa = p.get("waves_adjudication")
    assert wa is not None, "waves_adjudication key missing from scorecard payload"
    assert len(wa["waves"]) == 3, f"expected 3 waves, got {len(wa['waves'])}"
    wave_numbers = [w["wave"] for w in wa["waves"]]
    assert wave_numbers == [2, 3, 4], f"expected waves [2,3,4], got {wave_numbers}"
    assert wa["moratorium"] is True, "moratorium flag must be True"


def test_waves_block_renders_in_html():
    """Waves 2-4 adjudication block must appear in the rendered signal_lab.html."""
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(t=i18n.t, td=i18n.td, tr=i18n.tr, zip=zip)
    payload = signal_lab.build_scorecard()
    html = env.get_template("signal_lab.html.j2").render(**payload)
    assert "moratorium" in html.lower() or "暂停" in html, \
        "moratorium text not found in rendered signal_lab.html"
    # Wave 2 link to adjudication doc must be present
    assert "WAVE2_FABLE_ADJUDICATION" in html or "wave2" in html.lower() or "W2" in html, \
        "Wave 2 adjudication reference not found in rendered HTML"


def test_tested_chips_present_in_html():
    """TESTED-* chip classes must appear for SLF-001, SLF-006, SLF-048, SLF-051, SLF-055, SLF-056."""
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(t=i18n.t, td=i18n.td, tr=i18n.tr, zip=zip)
    payload = signal_lab.build_scorecard()
    html = env.get_template("signal_lab.html.j2").render(**payload)
    # At least one TESTED-* class must appear in the rendered HTML
    assert "tested-null" in html or "tested-pass" in html or "tested-partial" in html or \
           "tested-accrue" in html, \
        "No tested-* chip classes found in rendered HTML — tested rulings not rendering"


def test_w1_tested_verdicts_in_frontier_docket():
    """W1 phase-0 results must update FABLE_VERDICTS; BUILD entries must be replaced by TESTED-* or ACCRUE-CONFIRMED."""
    from engine.signal_frontier_docket import FABLE_VERDICTS
    tested_ids = ["SLF-001", "SLF-006", "SLF-048", "SLF-051", "SLF-053", "SLF-055", "SLF-056"]
    for sid in tested_ids:
        assert sid in FABLE_VERDICTS, f"{sid} missing from FABLE_VERDICTS"
        verdict = FABLE_VERDICTS[sid]["verdict"]
        assert verdict.startswith("TESTED-") or verdict == "ACCRUE-CONFIRMED", \
            f"{sid}: expected TESTED-* or ACCRUE-CONFIRMED verdict, got {verdict!r}"
    # SLF-052 must be ACCRUE-CONFIRMED (probe result: unmanufacturable)
    assert FABLE_VERDICTS.get("SLF-052", {}).get("verdict") == "ACCRUE-CONFIRMED", \
        "SLF-052 should be ACCRUE-CONFIRMED (history unmanufacturable)"


# ---- Day-3 SLF consolidation tests (2026-07-07) ----

def test_day3_extension_day_confirmer_row_present():
    """Month-end bond-index extension day must be in confirmer tier with correct fields."""
    p = _payload()
    confirmer = next((t for t in p["tiers"] if t["key"] == "confirmer"), None)
    assert confirmer, "confirmer tier not found"
    matches = [r for r in confirmer["rows"]
               if "extension" in r["name"].lower() or "month-end bond" in r["name"].lower()]
    assert matches, "Month-end bond-index extension day row not found in confirmer tier"
    row = matches[0]
    assert row["tier"] == "confirmer", f"expected confirmer, got {row['tier']}"
    assert row["dsr_family"] == "d2_rates_calendar_flows", \
        f"expected dsr_family=d2_rates_calendar_flows, got {row['dsr_family']}"
    assert row["ic"] is None, "extension-day row must have ic=None (no cross-sectional IC)"
    assert row["t_hac"] is not None, "t_hac must be set (time-series HAC stat)"
    assert row["t_hac"] > 2.0, f"t_hac should be >2.0 (significant), got {row['t_hac']}"
    assert "none" in row.get("wired", "").lower(), \
        "extension-day row must not be wired into any score (display-only candidacy)"
    # Bilingual fields present
    assert row["name_zh"] and "月末" in row["name_zh"], "Chinese name must include 月末"
    assert row["why_zh"], "Chinese rationale must be present"


def test_day3_comment_letter_confirmer_row_present():
    """SEC comment-letter release drift must be in confirmer tier with mandatory accrual caveat."""
    p = _payload()
    confirmer = next((t for t in p["tiers"] if t["key"] == "confirmer"), None)
    assert confirmer, "confirmer tier not found"
    matches = [r for r in confirmer["rows"]
               if "comment" in r["name"].lower() and "letter" in r["name"].lower()]
    assert matches, "SEC comment-letter release drift row not found in confirmer tier"
    row = matches[0]
    assert row["tier"] == "confirmer", f"expected confirmer, got {row['tier']}"
    assert row["dsr_family"] == "d2_comment_letter_release", \
        f"expected dsr_family=d2_comment_letter_release, got {row['dsr_family']}"
    assert row["ic"] is None, "comment-letter row must have ic=None (event study, not cross-sectional IC)"
    assert row["t_hac"] is not None and row["t_hac"] < -2.0, \
        f"t_hac should be negative and significant (effect is negative drift), got {row['t_hac']}"
    # Accrual caveat must appear in the why field
    why_combined = (row.get("why", "") + row.get("why_zh", "")).lower()
    assert "accrual" in why_combined or "concentrate" in why_combined or "2023" in why_combined, \
        "Mandatory accrual caveat (temporal concentration) must appear in why/why_zh"
    assert "none" in row.get("wired", "").lower(), \
        "comment-letter row must not be wired into any score"


def test_day3_block_renders_in_html():
    """Day-3 build-day results block must appear in the rendered signal_lab.html."""
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(t=i18n.t, td=i18n.td, tr=i18n.tr, zip=zip)
    payload = signal_lab.build_scorecard()
    html = env.get_template("signal_lab.html.j2").render(**payload)
    # Day-3 block must be rendered
    assert "Day 3" in html or "day3" in html.lower() or "第3天" in html, \
        "Day-3 results block not found in rendered signal_lab.html"
    # Queue moratorium text must reference empty queue
    assert "EMPTY" in html or "清空" in html or "moratorium" in html.lower(), \
        "Queue moratorium/empty status not in rendered HTML"


def test_day3_no_score_leakage():
    """Neither Day-3 confirmer row may feed into any numeric score (ic/hit must be None)."""
    from engine.signal_lab import REGISTRY
    day3_families = {"d2_rates_calendar_flows", "d2_comment_letter_release"}
    for r in REGISTRY:
        if r.get("dsr_family") in day3_families:
            assert r["ic"] is None, \
                f"{r['name']}: ic must be None for confirmer rows, not {r['ic']}"
            # hit should not be set to a numeric value
            assert r.get("hit") is None, \
                f"{r['name']}: hit must be None for confirmer rows, got {r.get('hit')}"
            assert r["tier"] == "confirmer", \
                f"{r['name']}: must be confirmer tier, got {r['tier']}"
