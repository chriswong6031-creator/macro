"""Chat-facing plain-word projection for internal state enums.

WHY THIS EXISTS
---------------
Live guest probes (2026-07-30/31, EN and zh) showed raw internal enum tokens —
``RISK_OFF``, ``CAUTION`` — verbatim in Mastermind chat prose, copied out of
read_world_state / read_contradictions tool payloads.  The design law bans raw
slugs in glance-tier copy, and the W2.1 lesson (MASTERMIND masterplan) is that
INPUT-side substitution beats prompt directives: the model copies its input
tokens over instructions (a bare "Goldilocks" in the zh digest survived the
language directive until market_packet substituted 理想增长 at render).  So the
token has to be a plain word BEFORE the model reads it.

WHERE IT APPLIES — AND WHERE IT MUST NOT
----------------------------------------
Applied ONLY at the chat read-tool boundary (ask_brain._dispatch_read_tool,
which both /api/ask and /api/brain/* delegate to).  The stored artifacts
(world_state.json, confluence_graph.json, …), the cortex/metabolism internal
loop, and every admin surface keep the raw enums — they are contracts that
other consumers pin (e.g. contradictions._RISK_OFF_VERDICTS matches on the raw
token).  Only the chat projection translates.

SHAPE OF THE MAP
----------------
FINITE and CURATED — exact SCREAMING-form state tokens with a deliberate
plain-word target each.  Matching is whole-token and case-sensitive (the
market_packet _ZH_STATE_RE idiom), so tickers/ids that merely look shouty
(MAG7, AUDUSD, CPI-016) and lowercase plain words are untouched, and an
unmapped token degrades to the status quo, never to a mangled string.  Plain
ENGLISH targets only: once the slug is gone the language directive owns
translation, and the world_state verdict block already carries label_zh
alongside for zh answers.
"""
from __future__ import annotations

import re
from typing import Any

# Token → plain word.  Sources of the domains:
#   market_state verdicts   engine/market_state.py::_LABEL (RISK_ON/MIXED/RISK_OFF)
#   MTF confluence grades   engine/commodity_mtf.py, engine/btc_mtf.py,
#                           engine/theme_scoring.py (TREND-FOLLOW/BUY-THE-DIP/
#                           WAIT/CAUTION/AVOID)
#   confirmer verdicts      engine/gex_confirm.py, engine/options_ivspread.py
#                           (CONFIRM/NEUTRAL/CAUTION)
#   regime transition       engine/transition.py::_LEVELS + contradictions.py
#                           (STABLE/WEAKENING/TRANSITIONING/RATCHETED-TRANSITION)
#   demand bands            engine/foresight_health.py::_REAL_DEMAND
#   remaining entries       state tokens observed in the live world_state.json
#                           payload served to chat (2026-07-30): ladder_state,
#                           contagion_regime, china phase, thematic stages,
#                           macro_deltas transitions.
_PLAIN_TOKENS: tuple[tuple[str, str], ...] = (
    # market_state verdict (the verified RISK_OFF leak)
    ("RISK_OFF", "Risk-off"),
    ("RISK_ON", "Risk-on"),
    ("MIXED", "Mixed"),
    # MTF grades (the verified CAUTION leak) + confirmer verdicts
    ("TREND-FOLLOW", "Trend-follow"),
    ("BUY-THE-DIP", "Buy-the-dip"),
    ("CAUTION", "Caution"),
    ("AVOID", "Avoid"),
    ("WAIT", "Wait"),
    ("CONFIRM", "Confirm"),
    ("NEUTRAL", "Neutral"),
    # regime transition states
    ("RATCHETED-TRANSITION", "Ratcheted transition"),
    ("TRANSITIONING", "Transitioning"),
    ("WEAKENING", "Weakening"),
    ("STABLE", "Stable"),
    # demand bands / contagion / macro-delta states
    ("ACCELERATING", "Accelerating"),
    ("CONTRACTING", "Contracting"),
    ("COOLING", "Cooling"),
    ("ELEVATED", "Elevated"),
    ("STEADY", "Steady"),
    ("BROKEN", "Broken"),
    # commodity ladder / china phase / thematic stages (live payload 2026-07-30)
    ("COUNTERTREND BOUNCE", "Countertrend bounce"),
    ("POLICY_PUT", "Policy put"),
    ("RE-RATING", "Re-rating"),
    ("BROADENING", "Broadening"),
    ("PRECIPICE", "Precipice"),
)

_PLAIN_MAP: dict[str, str] = dict(_PLAIN_TOKENS)

# Longest-first so a longer form can never be shadowed by a shorter alternation
# branch (re alternation is leftmost-first, not longest-first).  Lookarounds
# treat letters, digits and '_' as word-glue: RISK_OFF matches inside
# "verdict=RISK_OFF" but RISK_OFF_2 / XCAUTION / CAUTIONARY never match.
_TOKEN_RE = re.compile(
    "(?<![A-Za-z0-9_])("
    + "|".join(re.escape(k) for k in sorted(_PLAIN_MAP, key=len, reverse=True))
    + ")(?![A-Za-z0-9_])"
)

# Values under these keys are identifiers, never display vocabulary — their
# whole subtree passes verbatim so a symbol/id that collides with a future map
# entry can never be rewritten.
_VERBATIM_KEYS: frozenset[str] = frozenset(
    {"symbol", "symbols", "ticker", "tickers", "asset", "assets",
     "pair", "pairs", "id", "ids"}
)


def _sub(text: str) -> str:
    return _TOKEN_RE.sub(lambda m: _PLAIN_MAP[m.group(1)], text)


def project_plain_words(obj: Any) -> Any:
    """Recursively map internal state enums to plain words in a tool payload.

    PURE — builds new containers, never mutates the input.  Dict KEYS are
    schema and pass through untouched; only string VALUES are rewritten, and
    subtrees under identifier keys (_VERBATIM_KEYS) pass verbatim.
    """
    if isinstance(obj, dict):
        return {
            k: (v if k in _VERBATIM_KEYS else project_plain_words(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [project_plain_words(v) for v in obj]
    if isinstance(obj, str):
        return _sub(obj)
    return obj
