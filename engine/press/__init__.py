"""engine.press — Media Network W1 (docket D14): the automated press engine.

Pipeline shape, in dependency order:

    research_triage.rank()
                          deterministic — W2R (XG-W8).  Scores EVERY vault
                                            report in the window on six
                                            components and prints all of them
                                            to data/press/research_triage.jsonl,
                                            skipped and dropped included.  One
                                            scoring brain: it CALLS the XG-W5
                                            garbage gate, story spine and L1
                                            features rather than growing a
                                            second scorer.
    research_veto.run()   the veto pass — the cheapest model in the waterfall
                                            reads the ranked head and may only
                                            DEMOTE.  It returns reasons, never
                                            numbers; research_triage.apply_vetoes
                                            is the sole place a verdict touches
                                            a score, and it is clamped.
    desk_planner.plan()   deterministic  — picks stories/reports + gathers the
                                            SOURCE FACTS every later stage
                                            checks the draft against.  The
                                            research desks consume the triage
                                            ranking; the tier sets only the cap.
    writer.write()        the ONE stage that touches a network — an LLM writes
                                            prose from the planner's facts.
    validators.validate() deterministic  — zero LLM, zero network.  Every check
                                            is its own function and every
                                            result lands in validator_report.

    properties.render_property()
                          deterministic — W1.5.  Builds one publication's
                                            static property tree (front page,
                                            article pages, RSS, sitemap,
                                            robots, JSON-LD) from the
                                            append-only ledger + the .md
                                            archive.  No LLM, no network, and
                                            no wall-clock read, so two runs
                                            over one ledger are byte-identical.

The split is the point: nothing an LLM produces is trusted, and nothing that
verifies an LLM is written by one.  A draft that fails validation is
regenerated at most `quarantine.max_regenerations` times and then DROPPED with
a logged reason — a thin day beats a padded one.

Configuration: config/press.yml (thresholds, desks, publication registry) and
config.yml `llm_models` (press_brief / press_research model ids).

Nothing here publishes.  scripts/run_press.py defaults to --staging, which
writes only under data/press/staging/; --emit is the only path that touches
content/seo/blog/ and site/blog/, and the workflow that runs it is gated on the
PRESS_PUBLISH_ENABLED repo variable.  scripts/run_research_triage.py defaults to
--dry-run and appends only data/press/research_triage.jsonl under --write, gated
on RESEARCH_TRIAGE_ENABLED.  research_lane.py builds X shapes for an account that
does not exist yet and refuses to build anything while it stays dark.
"""
from __future__ import annotations

__all__ = [
    "desk_planner", "properties", "writer", "validators",
    "research_triage", "research_veto", "research_lane",
]
