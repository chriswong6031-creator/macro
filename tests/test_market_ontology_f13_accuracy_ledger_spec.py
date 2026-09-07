"""Frozen-spec tests for packet B-F13-4 (MO-DELTA-007 personal accuracy ledger spec)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "research" / "market_intelligence_productization" / \
    "MARKET_ONTOLOGY_F13_PERSONAL_ACCURACY_LEDGER_SPEC_2026-09-06.md"
TEXT = SPEC.read_text(encoding="utf-8")  # module-level; a missing file fails loudly


def test_spec_file_exists_and_is_utf8():
    assert SPEC.exists()
    assert len(TEXT) > 0
    # already decoded as utf-8 above; re-affirm round trip
    assert TEXT.encode("utf-8").decode("utf-8") == TEXT


def test_row_id_line_verbatim():
    assert (
        "Ledger row: MO-DELTA-007 (F13-OPS-LEARNING) — authority ceiling: learning_only."
        in TEXT
    )
    assert "MO-DELTA-007" in TEXT


def test_ceiling_line_verbatim():
    assert (
        "CEILING (learning_only): this score never feeds a signal, a rank, a size, or a gate."
        in TEXT
    )


def test_no_leaderboard_line_verbatim():
    assert (
        "NO LEADERBOARD: no cross-user ranking, no percentile against other users, "
        "no team or company scoreboard, ever."
        in TEXT
    )


def test_dnr_key_line_verbatim():
    assert (
        "DNR:KILL-LLM-CONFIDENCE — no LLM-originated number anywhere in this ledger: "
        "the model never states a probability, never grades an outcome, "
        "never adjusts a score."
        in TEXT
    )


def test_honest_n_line_verbatim():
    assert (
        "HONEST-N: episode-level count, printed on every surface, "
        "never hidden and never rounded away."
        in TEXT
    )


def test_data_null_line_verbatim():
    assert (
        "DATA NULL (2026-09-06): no user-claim store exists in this repository; "
        "nothing can be scored today and nothing may be fabricated."
        in TEXT
    )


def test_do_not_redo_clause_verbatim():
    assert (
        "do_not_redo (MO-DELTA-007): no universal analyst score conflating quality, "
        "retention, alpha, or P&L."
        in TEXT
    )


def test_forbidden_use_list_is_complete():
    stems = [
        "never an input to any signal",
        "never an ordering key",
        "never a position size",
        "never a promotion gate",
        "never an alert",
        "never visible to",
        "never a pricing",
    ]
    for stem in stems:
        assert stem in TEXT, f"missing forbidden-use stem: {stem!r}"


def _extract_block(marker: str) -> str:
    start = f"<!-- GLANCE-COPY-{marker}:START -->"
    end = f"<!-- GLANCE-COPY-{marker}:END -->"
    start_idx = TEXT.index(start)
    end_idx = TEXT.index(end)
    assert start_idx < end_idx
    return TEXT[start_idx + len(start):end_idx]


def test_glance_copy_blocks_are_paired():
    en = _extract_block("EN")
    zh = _extract_block("ZH")
    en_lines = [l for l in en.splitlines() if l.strip()]
    zh_lines = [l for l in zh.splitlines() if l.strip()]
    assert len(en_lines) > 0
    assert len(en_lines) == len(zh_lines)


def test_glance_copy_has_no_statistics_or_study_names():
    banned_re = re.compile(
        r"(?i)\bbrier\b|hit[- ]rate|%|p-value|sharpe|z-score|"
        r"explanation_memory|trial_ledger|Calibration Lab|"
        r"right-for-right-reason|\bvalidated\b"
    )
    for marker in ("EN", "ZH"):
        block = _extract_block(marker)
        assert banned_re.search(block) is None, f"banned term found in {marker} block"
        stripped = block.replace("{n}", "")
        assert re.search(r"\d", stripped) is None, (
            f"bare digit found in {marker} block outside the {{n}} placeholder"
        )


def test_cited_owner_files_exist():
    owners = [
        "engine/explanation_memory.py",
        "engine/validation.py",
        "engine/trial_ledger.py",
        "scripts/build_explanation_memory.py",
        "lib/evidence_foundation.py",
        "templates/measurement.html.j2",
        "research/DO_NOT_REBUILD.md",
    ]
    for rel in owners:
        assert (ROOT / rel).exists(), f"cited owner file missing: {rel}"


def test_spec_does_not_claim_a_live_user_claim_store():
    assert "no user-claim store exists" in TEXT
    assert "PROJECTION_ONLY" in TEXT
    for phrase in ("is live", "now shipping", "users can now"):
        assert phrase not in TEXT


def test_brier_is_scored_per_episode_not_per_claim():
    assert "Per-episode Brier contribution" in TEXT
    assert "one pair per **episode**" in TEXT
    assert "never per claim" in TEXT
    assert "outcome AND the episode's `stated_probability`" in TEXT
    assert "always come from the same member, never from different claims" in TEXT


def test_claim_id_digest_includes_resolves_at():
    assert (
        "`sha256` of `(user_id, subject, condition, stated_at, resolves_at)` "
        "first 16 hex" in TEXT
    )
    assert "millisecond precision" in TEXT


def test_claim_id_digest_does_not_misclaim_sameness_with_trial_ledger_hash():
    # Review finding: engine/trial_ledger.py:61 _hash is sha1, not sha256, so
    # the spec must not claim "same digest discipline" with a precedent whose
    # algorithm differs. It may claim the shared 16-hex-truncation discipline.
    assert "same digest discipline as `engine/trial_ledger.py:61 _hash`" not in TEXT
    assert (
        "distinct algorithm from, but the same 16-hex-truncation discipline as, "
        "`engine/trial_ledger.py:61 _hash` (which hashes with sha1, not sha256)"
        in TEXT
    )


def test_team_rollup_is_deferred_not_killed():
    assert "DEFERRED, NOT KILLED" in TEXT
    assert "team-accuracy rollup" in TEXT
    assert (
        "permanently forbids ranking/leaderboard use of *this ledger's data* "
        "within its own contract"
        in TEXT
    )
    assert (
        "not a codebase-wide `DNR:KILL-*` registry kill"
        in TEXT
    )
    assert (
        "non-ranking team-accuracy rollup capability is explicitly DEFERRED, "
        "not killed here"
        in TEXT
    )


def test_ranking_kill_is_scoped_to_this_spec_not_a_registry_row():
    assert "a prohibition scoped to this spec's own forbidden-uses list, not" in TEXT
    for phrase in ("kills the ranking/leaderboard half permanently",
                   "permanently kills the cross-user ranking/leaderboard"):
        assert phrase not in TEXT


def test_episode_key_includes_threshold():
    assert (
        "`condition.metric` + `condition.comparator` + `condition.threshold`"
        in TEXT
    )
    assert "SPX >= 6000" in TEXT and "SPX >= 7000" in TEXT


def test_episode_partition_is_transitive_closure():
    assert "**transitive closure**" in TEXT
    assert "pairwise-only clustering that would split such a chain" in TEXT


def test_still_live_is_defined():
    assert (
        "still-live means `status` in `{open, matured, resolved}`" in TEXT
    )
    assert (
        "if every member of an episode is `withdrawn` or `void_unscorable`, "
        "the episode carries no outcome or probability" in TEXT
    )


def test_null_ladder_has_a_band_for_high_resolved_low_probability_pairs():
    assert "independently-keyed" in TEXT
    assert "Hit-rate axis (keyed on resolved episodes):" in TEXT
    assert (
        "Calibration axis (keyed on probability-carrying episode pairs, "
        "independent of the resolved-episode count above"
        in TEXT
    )
    assert "0–29 probability pairs" in TEXT


def test_glance_copy_includes_the_two_null_disclosures_bilingually():
    en = _extract_block("EN")
    zh = _extract_block("ZH")
    assert (
        "Not enough settled calls yet to check how well your odds match "
        "reality."
        in en
    )
    assert "calls could not be checked" in en and "{n}" in en
    assert "还没有足够的已结算判断来核对你的把握是否准确。" in zh
    assert "有 {n} 条判断无法核对" in zh


def test_glance_copy_includes_the_early_days_line_bilingually():
    # Review finding: §5's 1-9-episode line ("Too early to say — checked {n}
    # of your calls so far.") must be in the verbatim glance-copy block too,
    # or the successor UI packet has to invent the combined sentence itself.
    en = _extract_block("EN")
    zh = _extract_block("ZH")
    assert "Too early to say — checked {n} of your calls so far." in en
    assert "还看不出来——目前核对了你的 {n} 条判断。" in zh


def test_dnr_key_cited_in_colon_form():
    dnr_mentions = re.findall(r"DNR[:\w-]*", TEXT)
    assert dnr_mentions, "expected at least one DNR: citation"
    for mention in re.findall(r"\bDNR\b[^\n]{0,40}", TEXT):
        assert "DNR:" in mention or mention.strip() == "DNR"
    assert "row 54" not in TEXT
    # House law: cite registry rows as DNR:<KEY>, never by row/line number —
    # numbers shift on every append. Catches any "DO_NOT_REBUILD.md:NN" citation,
    # not only the one literal "row 54" phrasing checked above.
    assert re.search(r"DO_NOT_REBUILD\.md:\d+", TEXT) is None


def test_dnr_llm_confidence_citation_does_not_overclaim_registry_scope():
    # Review finding: the registry row DNR:KILL-LLM-CONFIDENCE is scoped to CHF
    # surfaces (research/DO_NOT_REBUILD.md), not "anywhere in this ledger" as
    # the spec's citation implied. The spec may still apply the same house
    # principle independently; it must not attribute that scope to the row.
    assert (
        "That registry row's own scope is CHF surfaces, "
        "`research/DO_NOT_REBUILD.md`; this ledger applies the same A7 "
        "no-origination principle independently, not by extending that "
        "row's scope."
        in TEXT
    )


def test_f00c_dependency_claim_cites_row_key_and_quotes_it():
    # Review gap: the blocking-dependency line must name the CSV row by its key
    # (MO-DELTA-007), not merely a line number, and quote the row's own words
    # rather than paraphrasing them.
    assert "row key `MO-DELTA-007`" in TEXT
    quoted = (
        "DEFER — dependency the Thesis-object vertical "
        "(user claim authoring surface) before Eval OS can score it"
    )
    assert (
        "next_bounded_child` field, quoted verbatim: "
        f'"{quoted}"'
        in TEXT
    )
    csv_path = ROOT / "research" / "market_intelligence_productization" / \
        "MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv"
    assert csv_path.exists()
    import csv as csv_module
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv_module.DictReader(fh))
    matches = [r for r in rows if r.get("id") == "MO-DELTA-007"]
    assert len(matches) == 1, "expected exactly one MO-DELTA-007 row in the CSV"
    # MINOR-5 (review): the prior version of this test only checked that the
    # quote appeared somewhere in the CSV text — it must be bound to the
    # MO-DELTA-007 row's own next_bounded_child field, which is the claim
    # ruling item (4) actually locks.
    assert matches[0]["next_bounded_child"] == quoted, (
        "spec's quoted next_bounded_child text must equal the live "
        "MO-DELTA-007 row's own next_bounded_child field, verbatim"
    )
