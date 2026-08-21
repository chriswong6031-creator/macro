"""Canonical Agent OS compile tests plus Linear portfolio-plan P0 coverage.

The legacy compile-context suite is preserved byte-for-byte in the non-collectable
``tests.agentos_compile_legacy_cases`` module. The projector fixture cases and the
real-checkout receipt case live in non-collectable modules. This explicit aggregator
keeps one CI-owned pytest suite at the path already named by the always-on
``self-mod-fence`` job; it does not hide or waive any test family.
"""

from tests.agentos_compile_legacy_cases import *  # noqa: F401,F403
from tests.linear_portfolio_plan_cases import *  # noqa: F401,F403
from tests.linear_portfolio_plan_live_cases import *  # noqa: F401,F403
