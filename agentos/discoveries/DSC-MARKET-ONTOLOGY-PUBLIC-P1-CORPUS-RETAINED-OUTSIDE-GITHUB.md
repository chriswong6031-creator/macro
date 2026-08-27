---
key: MARKET-ONTOLOGY-PUBLIC-P1-CORPUS-RETAINED-OUTSIDE-GITHUB
summary: >
  The original Market Ontology public P1 research corpus is materially richer than
  the 88-row authenticated paid census and remains retrievable from Chairman/Sol file
  retention, but its core 1,556-row capability ledger and Turn-1..Turn-6 public-phase
  artifacts are not currently discoverable in the MastermindX GitHub organization.
  F00 must reuse/import that retained corpus rather than re-research it or pretend the
  current 88-row + delta ledgers exhaust the historical public research.
impact: >
  Complete-parity accounting is not repository-self-contained yet. The current
  complete-parity carrier has the 88 authenticated baseline and a live public delta
  ledger, but the detailed historical inventory of user jobs, interactions, methods,
  object contracts, source/data requirements, authority boundaries, failure states,
  security/commercial controls and prior Mastermind owner/action mappings remains
  outside GitHub. A fresh F00 that sees only current repo state could therefore redo
  work, omit low-level capability states, or lose prior no-rebuild/adoption findings.
evidence:
  - >
    Retained file `MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5.csv` has header
    `index,id,domain,capability,mo_state,evidence_basis,method_status,mastermind_owner_or_analogue,mastermind_state,comparison,p1_action,priority,notes`
    and contains the historical public capability inventory through MO-1556.
  - >
    Retained Turn-6 artifact manifest records `MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5.csv`
    as 495184 bytes with SHA-256
    `1b5d1137710d6bae504e94bbcf4155a3bd5491863e0d8e84078b0d009564a827`;
    the JSON twin is 957866 bytes with SHA-256
    `785f83ca2e92e070d41174b2a6e28834019517d6c845351771eb261fde766d59`.
  - >
    Retained `MARKET_ONTOLOGY_P1_MASTER_ARTIFACT_INDEX_V0.md` states cumulative public
    P1 facts: 1,556 capabilities, 460 structured quality findings, public phase complete.
  - >
    Retained authenticated research handoff explicitly says not to read the 1,556-row
    ledger linearly; use it as a lookup table alongside detailed domain protocols.
  - >
    Retained public P1 adoption/no-rebuild map already maps many Market Ontology jobs
    to canonical Mastermind owner/action decisions and should be reused before minting
    any new architecture.
  - >
    Fresh GitHub organization searches on 2026-08-26/27 found no repository file named
    `MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5` and no current copy of
    `MARKET_ONTOLOGY_P1_TURN6_PLATFORM_DATA_API_SECURITY_COMMERCIAL_FINAL_2026-08-22`.
next_action: >
  F00 must treat exact-byte import/reconciliation of the retained public P1 research
  corpus as an early control-plane-free research task. Prefer copying the original
  Mastermind-created public black-box research artifacts into a bounded repository
  archive under `research/market_intelligence_productization/public_p1_archive/` with
  original bytes and an import manifest that verifies the recorded SHA-256 values.
  At minimum import the master artifact index, 1,556-row ledger (CSV/JSON/summary),
  Turn-1..Turn-6 final reports, adoption/no-rebuild map, public architecture freeze,
  implementation plan, quality-audit summaries and artifact manifests. Do not
  reconstruct the 1,556 rows from memory/snippets when exact retained bytes exist.
  After import, F00 crosswalks each historical row to the new F01-F13 lanes and marks
  alias/covered/gap/rejected status without treating every row as a separate engine.
status: OPEN_IMPORT_GATE
owner: "F00 Market Ontology parity control"
confidence: high
---

# What this discovery does and does not mean

The retained corpus is **Mastermind's own lawful public black-box research**, not a
competitor source-code/data dump. Importing those research artifacts does not authorize
copying Market Ontology proprietary implementation, private corpora, assets, branding,
credentials, hidden APIs or vendor-only datasets.

The existing 88-row authenticated ledger remains the immutable paid-surface baseline.
The 1,556-row public ledger is a deeper capability/method/contract/failure inventory.
The current-public delta ledger captures product evolution after that baseline. All
three are complementary inputs to F00 closure accounting:

```text
historical public P1: 1,556 detailed capability/method rows
        +
authenticated paid baseline: 88 advertised paid capabilities
        +
current-public delta: post-baseline names and newly explicit depth
        ↓
F00 canonical capability-family crosswalk
        ↓
F01-F13 bounded implementation / projection / context / rejection lanes
```

## Import acceptance

The public P1 import is accepted only when:

1. exact source bytes are used rather than model-reconstructed content;
2. manifest-recorded file size and SHA-256 match for the 1,556-row ledger and other
   imported artifacts where historical hashes exist;
3. imported files are clearly marked as historical research evidence, not current
   implementation authority;
4. the new complete-parity DEC/addendum remains higher authority for scope and
   operating model;
5. current repo/source-owner truth wins where the historical `mastermind_state` or
   owner mapping has become stale;
6. no duplicate workstream, truth store, graph, identity or control plane is created.

Until this import is complete, do not claim that the full 1,556-row public inventory is
GitHub-canonical or fully reconciled, even though its existence and hashes are known.