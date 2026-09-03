"""Agent OS compile-context suite plus current Linear Initiative contract.

The original suite is retained byte-for-byte in ``tests.agentos_compile_legacy``.
The current-epoch Initiative tests are imported into this canonical, already-wired
pytest module so no duplicate CI job or workflow is created.
"""
from tests.agentos_compile_legacy import *  # noqa: F401,F403
from tests.linear_initiative_plan_current_epoch_cases import *  # noqa: F401,F403
