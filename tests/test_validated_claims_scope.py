"""tests/test_validated_claims_scope.py — BC-2 scan SCOPE (which surfaces the gate judges).

Companion to the gate's behaviour tests in tests/test_ladder_risk_calibration.py §4 (EN/zh
matching, negation, whole-tree clean). This file pins the OTHER half: what BC-2 is allowed
to adjudicate at all.

Regression it exists for — main red 2026-07-27. The nightly render (ff5d3b1c8) mirrored a
sell-side "US Daily" economics note into the research vault, and the economist's sentence
"…validated two likely sources of ongoing disinflation…" failed check_validated_claims,
red-lining main and the ci-pack-0 lane on every open PR. The first fix (#3767) added a
phrase-scoped allowlist entry. That clears exactly ONE document: the vault holds ~161
reports and ingests more every night, so the next drop carrying the word re-reds the build.

The structural fix: BC-2 judges claims the PLATFORM makes. Text ingested verbatim from a
third party is quoted speech with no artifact of ours to cite, so its rendered surfaces are
out of scope by construction (check_validated_claims._INGESTED_SURFACES).

Lives in its own module — importing only stdlib + the gate — so it can run in the PR lane
(engine-render-guards, inside ci-pack-0). tests/test_ladder_risk_calibration.py is wired
only to cycle-calibration.yml, which is a MONTHLY cron with no pull_request trigger; pins
placed there would sit dark for up to a month.
"""
from __future__ import annotations

from scripts import check_validated_claims as GATE

# Unearned by construction: affirmative, no artifact reference, no allowlist entry.
_CLAIM = "Our basket is validated as a live cross-sectional edge."


def _scope_tree(tmp_path):
    """A synthetic mini-repo carrying the SAME unearned claim on every relevant surface."""
    (tmp_path / "site" / "research").mkdir(parents=True)
    (tmp_path / "templates").mkdir()
    rels = {
        "site/research/some-ingested-note-abc123.html",   # a per-report landing page
        "site/research/a-different-note-def456.html",     # ANY future drop, not just one
        "site/research/index.html",                       # the /research/ crawl hub
        "site/research_vault.html",                       # SSR cards + rv-catalog island
        "site/research_vault_app.js",                     # hand-written house JS
        "site/index.html",                                # an ordinary rendered page
        "templates/research_report.html.j2",              # where OUR copy actually lives
        "templates/research_vault.html.j2",
    }
    for rel in rels:
        (tmp_path / rel).write_text(_CLAIM, encoding="utf-8")
    return rels


def test_ingested_vault_surfaces_are_out_of_scope(tmp_path, monkeypatch):
    """Vault render surfaces are skipped — and their TEMPLATES still fire.

    The second half is what makes this an exemption rather than a hole. No platform claim
    loses coverage, because everything on those pages is either house chrome from a
    still-scanned template or a catalog/excerpt field:
      • build_research_vault.render() passes exactly two variables, catalog_json and
        ssr_feed, both projected from the ingest catalog;
      • build_research_pages.build() passes normalized catalog fields plus excerpt_paras,
        the verbatim first pages of the PDF.
    """
    all_rels = _scope_tree(tmp_path)
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(GATE, "ALLOWLIST", tmp_path / "absent.json")   # hermetic

    assert {r["file"] for r in GATE.scan()} == {
        "site/research_vault_app.js",
        "site/index.html",
        "templates/research_report.html.j2",
        "templates/research_vault.html.j2",
    }

    # Anti-vacuity: lift ONLY the exemption and the same tree reports all eight. So the
    # four suppressed above are suppressed by the provenance rule — not by a glob that
    # never descended into site/research/ to begin with.
    monkeypatch.setattr(GATE, "_INGESTED_SURFACES", ())
    assert {r["file"] for r in GATE.scan()} == all_rels


def test_ingested_exemption_is_path_exact():
    """Directory entries match a tree; file entries match exactly. No neighbour drift."""
    for rel in ("site/research/x.html", "site/research/deep/y.html", "site/research_vault.html"):
        assert GATE._is_ingested_surface(rel), rel
    for rel in ("site/research_vault_app.js", "site/research_vault.html.bak",
                "site/researchers.html", "site/index.html",
                "templates/research_report.html.j2", "site/prophet/plans/p.json"):
        assert not GATE._is_ingested_surface(rel), rel


def test_allowlist_holds_no_ingested_document_entries():
    """The allowlist is a citation registry, not a mute button.

    Its own contract: "each entry justifies an affirmative use ... by naming the backing
    evidence artifact ... adding an entry is a claim of record". Quoted third-party text has
    no citation to give, so a provenance exemption belongs in the scanner. #3767's entry —
    whose `backing` read "NOT a platform claim" — was removed when the scanner learned the
    rule; this keeps the next one from being written.
    """
    for e in GATE._load_allowlist():
        backing = (e.get("backing") or "").strip()
        assert backing, f"allowlist entry cites nothing: {e.get('match')!r}"
        assert "not a platform claim" not in backing.lower(), (
            f"{e.get('match')!r} is a provenance exemption wearing a citation's clothes — "
            "add the surface to check_validated_claims._INGESTED_SURFACES instead")


def test_gate_selftest_covers_scope():
    """The CI selftest step (`--selftest`, run in the validated-claims job) must itself
    prove the scope decision — so the PR lane catches a scope regression even if this
    pytest module is ever dropped from a pack."""
    assert GATE.selftest() == 0
