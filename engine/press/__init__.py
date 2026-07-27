"""engine.press — Media Network W1 (docket D14): the automated press engine.

Pipeline shape, in dependency order:

    desk_planner.plan()   deterministic  — picks stories/reports + gathers the
                                            SOURCE FACTS every later stage
                                            checks the draft against.
    writer.write()        the ONE stage that touches a network — an LLM writes
                                            prose from the planner's facts.
    validators.validate() deterministic  — zero LLM, zero network.  Every check
                                            is its own function and every
                                            result lands in validator_report.

The split is the point: nothing an LLM produces is trusted, and nothing that
verifies an LLM is written by one.  A draft that fails validation is
regenerated at most `quarantine.max_regenerations` times and then DROPPED with
a logged reason — a thin day beats a padded one.

Configuration: config/press.yml (thresholds, desks, publication registry) and
config.yml `llm_models` (press_brief / press_research model ids).

Nothing here publishes.  scripts/run_press.py defaults to --staging, which
writes only under data/press/staging/; --emit is the only path that touches
content/seo/blog/ and site/blog/, and the workflow that runs it is gated on the
PRESS_PUBLISH_ENABLED repo variable.
"""
from __future__ import annotations

__all__ = ["desk_planner", "writer", "validators"]
