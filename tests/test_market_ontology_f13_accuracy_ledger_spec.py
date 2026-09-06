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


def test_team_rollup_is_deferred_not_killed():
    assert "DEFERRED, NOT KILLED" in TEXT
    assert "team-accuracy rollup" in TEXT
    assert (
        "permanently kills the cross-user ranking/leaderboard capability"
        in TEXT
    )
    assert (
        "non-ranking team-accuracy rollup capability is explicitly DEFERRED, "
        "not killed here"
        in TEXT
    )


def test_dnr_key_cited_in_colon_form():
    dnr_mentions = re.findall(r"DNR[:\w-]*", TEXT)
    assert dnr_mentions, "expected at least one DNR: citation"
    for mention in re.findall(r"\bDNR\b[^\n]{0,40}", TEXT):
        assert "DNR:" in mention or mention.strip() == "DNR"
    assert "row 54" not in TEXT
