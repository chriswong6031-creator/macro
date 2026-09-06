---
key: MCP-RESEARCH-JSON-BYTE-AND-ERROR-BOUNDARY
claim: >
  The research MCP JSON helper at the cited source counts characters and has
  an unchecked final fallback. A bounded diagnostic reproduced oversized and
  non-strict JSON outputs. Claude SDK 0.2.152 reads handler is_error and converts
  it to wire isError; a camelCase-only handler error flag is not preserved.
falsifier: >
  In a disposable Mastermind checkout at 0d9cf2f58f9a6a1fe895d5d199abc18735201e24
  with its permitted SDK dependencies, read
  `git show 0d9cf2f58f9a6a1fe895d5d199abc18735201e24:brain/bot_mcp.py` and run
  `python -c "from brain.bot_mcp import _json; r=_json({f'k{i}':'x'*200 for i in range(150)}); print(len(r['content'][0]['text'].encode('utf-8'))); print(_json({'v':float('nan')})['content'][0]['text'])"`.
  The output must reproduce 31,782 bytes and a non-strict NaN literal; a bounded
  strict-JSON result at those original bytes disproves the respective claim.
  Read the separate SDK converter with
  `gh api 'repos/anthropics/claude-agent-sdk-python/contents/src/claude_agent_sdk/__init__.py?ref=v0.2.152' -H 'Accept: application/vnd.github.raw+json'`.
  A converter that preserves a camelCase-only handler isError flag disproves
  the SDK claim. These read/probe commands are falsifiers, not executed wire proof.
so_what: >
  Continue only Mastermind issue487 and its exact carrier. Require real-source
  RED, final strict UTF-8 payload measurement, explicit bounded transport errors,
  and an actual decorated-handler-to-wire error-bit test. Do not change SDK
  versions, duplicate the SDK converter, or report excerpt diagnostics as wire proof.
kind: landmine
verified_at: 2026-09-05
verified_by: >
  GitHub.fetch_file Mastermind@0d9cf2f58f9a6a1fe895d5d199abc18735201e24
  brain/bot_mcp.py lines37-115, reported full blob
  b6d62f398166cc7986212d1fbf2d4a1e9953c38e; stdlib diagnostic of unchanged
  excerpt SHA256 8cddeb2e25bd200c9e47e9dbd9ac88fda9b434281f64ef81dafcd6017af5e953;
  anthropics/claude-agent-sdk-python@v0.2.152 src/claude_agent_sdk/__init__.py,
  blob d8c83bcac0d5be4ab6facf44f1b405f574a88ce4; issue487 correction5550336685.
scope:
  - WS:SOL-CAPABILITY-FABRIC
  - mastermind:brain/bot_mcp.py
  - mastermind:tests/test_bot_mcp.py
confidence: verified
---
# Evidence and limits

The excerpt diagnostic had twelve cases: four controls and eight counterexamples.
Unicode inputs returned 8,109 and 16,009 UTF-8 bytes; a wide scalar fallback
returned 31,782 bytes. NaN and Infinity were emitted as non-JSON literals, and
one lone-surrogate result could not be strictly UTF-8 encoded. The original
helper's budget unit was ambiguous; issue487 deliberately freezes 8,000 bytes
of TextContent.text, not a universal MCP or whole-JSON-RPC limit. The ASCII
wide-fallback defect also violates a character-count ceiling.

The diagnostic did not import the full module, run a real handler, install an
SDK, or call a provider. Its excerpt hash is not a full-file Git blob proof.
The assigned worker must reproduce against actual source before editing.

The cited SDK reads result.get('is_error', False) and constructs wire isError.
Use handler is_error=True, then prove wire isError=true. Do not add two flags
or infer wire behavior from a helper dictionary assertion.

Sole repair: mcp-research-json-response-boundary-20260905-sol-001,
Mastermind issue487, Slack C0BSBM78V1N/1788593637.332099. No source acceptance,
START, installed fix, production failure, or trade authority is asserted here.
