---
key: WATCHLIST-PORTFOLIO-CEO
title: Watchlist + Portfolio CEO revamp
objective: >
  Bring the Watchlist and Portfolio surfaces to the launch bar — coherent persistence,
  no husk pages, no dead surfaces. Done = both surfaces pass the launch bar with a single
  agreed persistence model.
status: active
program: terminal-user-services
p0: PRODUCT_TRUST_COHERENCE
repos: [macro, terminal]
owner: coo-fable
class: design
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: W0
    title: Initial revamp shipped
    status: done
    pr: 5457
  - id: P0-HUSK
    title: "P0 husk cured — 6-file shell, graded plane walled, shim trap closed"
    status: done
    pr: 5463
  - id: W1
    title: Persistence model implementation
    status: todo
    depends_on: [P0-HUSK]
    next_action: Blocked on the persistence-model decision below.
needs_ceo:
  question: "Portfolio and Watchlist persistence: one table or two?"
  options:
    - "Single positions table with a kind discriminator"
    - "Separate tables, joined at read time"
  recommendation: >
    Single positions table with a kind discriminator. Terminal /portfolio currently has zero
    portfolio_positions references, so the migration cost is near zero today and rises once
    W1 ships against either shape.
  by_when: 2026-08-14
next_action: Obtain the persistence-model ruling, then start W1.
---

## Context

Serves P0 `PRODUCT_TRUST_COHERENCE`. W0 and the P0 husk cure are merged; W1 cannot start
until the persistence model is settled, because both candidate shapes imply different
migrations.
