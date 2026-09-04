"""Macro & Monetary workspace projection package (F01 / R1A).

The first vertical of the twelve-workspace Macro & Monetary suite. This package
is a small, pure PROJECTION layer over canonical macro owners:

    domain composer  reads owner-native artifacts (data/regime/latest.json ...)
    contract         validates + canonicalizes + digests the shared snapshot
    registry         the closed workspace-id registry
    build            atomically publishes latest.json + a per-workspace manifest
    consumer         a bounded, read-only machine consumer (inert on bad input)

Boundary (frozen by the F01 architecture, section 11.1):
    * domain modules READ owner-native artifacts; they never mutate an owner path;
    * the shared contract validates and canonicalizes;
    * the builder publishes atomically;
    * no mutable service state, no user data, no rank/gate/size/trade authority,
      no LLM-originated facts.

Everything here depends only on the standard library plus ``jsonschema`` — never
on pandas, the feature frame, or any owner engine module — so the projection can
run anywhere the published owner artifact can be read.
"""

from engine.market_os.macro_workspaces import contract, registry  # noqa: F401

__all__ = ["contract", "registry"]
