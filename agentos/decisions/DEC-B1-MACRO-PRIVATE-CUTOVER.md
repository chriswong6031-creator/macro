---
key: B1-MACRO-PRIVATE-CUTOVER
question: >
  How does mastermindx-market-intelligence/macro become PRIVATE without freezing
  the primary site or staling Mastermind's trading inputs, and what proves every
  load-bearing anonymous dependency has an authenticated replacement before the
  Chairman flips visibility?
answer: >
  Sol Day-6 ruling: the canonical macro repo goes PRIVATE (supersedes the
  2026-07-30 "keep it public" operational recommendation; the underlying product
  law — public mirror/quote needs do NOT authorize anonymous exposure of paid
  product bytes — is unchanged). The repo stops being BOTH the internal
  source/provenance plane AND the anonymous distribution plane. Public delivery
  becomes an explicit allowlist of PUBLIC_FACT/ANONYMOUS projections only
  (approved facts, showcase/delayed data, public quote products,
  prophet/health.json) — never "secretless-API-because-a-file-exists-in-git".
  The Chairman performs the visibility flip ONLY after this session returns
  MACRO-PRIVATE-CUTOVER READY, proving every anonymous dependency has an
  authenticated replacement. NO git-history rewrite in B1 (thousands of receipts,
  Agent OS records and cross-repo citations depend on existing SHAs; a rewrite
  destroys provenance and cannot revoke already-downloaded copies — historical
  exposure is recorded as a disclosure fact, remediation is a separate
  Chairman-authorized program).
rationale: >
  The §8b boundary certification cannot issue BOUNDARY PASS while the repo is
  public: raw.githubusercontent, the GitHub Pages mirror, jsDelivr, and anonymous
  clone all serve the full Prophet plan book + premiumdata byte-identically
  (DSC:PROPHET-BOOK-PUBLIC-GIT-TWIN; verified 2026-08-21 all three = 200 /
  2,242,608B). Closing R2 alone (DEC:B1-PROPHET-PUBLIC-SPLIT) shut only one of
  the anonymous planes.
alternatives:
  - option: Keep the repo public, redact premium bytes out of the tracked tree
    why_not: >
      The premium artifacts (site/prophet/*, site/premiumdata/*) are legitimately
      Git-retained internal state; stripping them from the public branch breaks
      provenance and the internal consumers. Private canonical + explicit public
      projections is the clean split.
  - option: Rewrite history (filter-repo) to purge the premium bytes from all commits
    why_not: >
      Explicitly forbidden in B1 by Sol: destroys provenance across thousands of
      SHAs/receipts/records, and cannot retract copies third parties already
      downloaded. A future history-remediation is its own Chairman-authorized
      archaeology.
  - option: Create a second public Git mirror repo for the DR/Pages need
    why_not: >
      Sol: retirement preferred over a new public repo during B1. A sanitized
      public-export DR mirror, if ever wanted, is a separately commissioned
      allowlisted projection that no production system reads back as canonical.
  - option: Flip visibility first, then fix consumers
    why_not: >
      A premature flip freezes the primary site (the VPS /opt/macro pulled macro
      anonymously) and stales Mastermind's trading inputs — the exact failure in
      DSC:PROPHET-BOOK-PUBLIC-GIT-TWIN. Every dependency is migrated + proven
      BEFORE the flip; the flip is the Chairman's isolated final act.
evidence:
  - "Anonymous 200/2,242,608B on all three planes 2026-08-21: cdn.jsdelivr.net/gh/…/site/prophet/index.json, mastermindx-market-intelligence.github.io/macro/prophet/index.json, raw.githubusercontent.com/…/main/site/prophet/index.json"
  - "Wave A: /opt/macro pulled via anonymous HTTPS (macro-update:263 `git fetch --depth 1 origin main`); now switched to a read-only SSH deploy key (id 160889926) — authenticated fetch proven, read-only proven (push denied)"
  - "Wave B: /opt/mastermind/vendor/macro -> /opt/macro symlink (vendor/macro_src never materialized), so the VPS bot reads macro through Wave A's authenticated pull, not a GitHub clone; the macro_refresh.py clone path is a DR-only seam that needs env-configurable authenticated remote"
  - "Wave C: production LIVE_SNAPSHOT_URL='live/quotes.json' (same-origin; config.yml:671 + live), not raw-git — a code guard rejects re-pointing it at a GitHub distribution host"
  - "Wave D: Pages producers at daily.yml, weekly.yml, closing-bell.yml, pages.yml deploy the premium mirror; retired in code + Pages site disabled at cutover"
affects:
  - "app/deploy/update.sh"
  - "scripts/build_live_overlay.py"
  - ".github/workflows/daily.yml"
  - ".github/workflows/pages.yml"
  - "data_layer/macro_refresh.py (mastermind)"
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-21
related:
  - "DEC:B1-PROPHET-PUBLIC-SPLIT"
  - "DSC:PROPHET-BOOK-PUBLIC-GIT-TWIN"
  - "WS:PROPHET-US-V4-RECOVERY"
---

Recorded by the Day-6 session preparing the private-repo cutover. The ordered
migration (Waves A–F) and the readiness matrix live in the day-6 handoff under
agentos/handoffs/. The visibility flip itself is the Chairman's act, gated on the
MACRO-PRIVATE-CUTOVER READY receipt; the post-flip production proof + §8b
re-review follow it.
