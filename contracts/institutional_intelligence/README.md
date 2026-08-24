# K2-B Institutional Intelligence — Manager Research Intent

This is a pure, read-only contract for describing manager-complex observations. It is not an institutional data store, a 13F replacement, a trading signal, a ranker, an entry gate, or a product/runtime adapter.

The four separate planes are `manager_research_intent`, `fund_flow_pressure`, `theme_capital_rotation`, and `institutionalization_saturation`. They may be reported together but are never netted into a score. `form_13f` observations require report-period, filing, publication, and knowability clocks; before knowability they are `NOT_KNOWABLE`, and they can never be `live_flow`.

Manager complex and vehicle identities are epoch-bound. The independent count is a distinct `(manager_complex_id, manager_identity_epoch)` count, so vehicles at one complex cannot multiply consensus. Passive, systematic, overlay, leveraged, and synthetic vehicles cannot emit manager research intent. Mechanical flow stays in its own plane and compiles to `MECHANICAL_FLOW_RESIDUAL` or `MECHANICAL_FLOW_PROXY_OR_UNRESOLVED`, never intent.

Each observation now carries executable holdings normalization: 13F is only
`13f_unscaled_reported_shares` and has typed `shares_outstanding: unsupported`;
it cannot borrow the ETF normalization formula. ETF normalization requires its
own true-shares-outstanding basis. Mechanical residuals name their
`true_shares_outstanding`, `proxy`, or `unresolved` basis and compile to a
non-intent state. Observed shares outstanding is strictly positive; absent and
unsupported are strictly null.

The recipe also carries an actual K1 `EvidenceRef`, validated through
`lib.evidence_foundation.validate_reference`; it is the immutable K1 vocabulary
and all-false-authority anchor, not a copied owner payload or a second store. The
per-observation source pointer (`reference_id`, owner-native object id, accession,
source URL and clocks) remains pointer-only. Corrections append a new observation
that supersedes an earlier one. Reliability is a descriptive, shrunk posterior
keyed by manager complex × domain × horizon × action; it has no oracle semantics.
All five authority axes are false.

K1 vocabulary reuse is literal: coverage, rights, typed missingness, publication
and knowability clocks, and append/supersede corrections are represented on the
observation and preserved in the compilation receipt. Unknown, partial,
rights-unknown, and rights-blocked coverage remain typed receipt states, never
`OBSERVED` by omission. Event and pointer clocks must be identical.

Campaigns are append-only transition records, not a free list of state labels.
Each record binds campaign, subject, complex epoch, transition/knowability clocks,
one or more observations, and a pointer id; duplicate, skipped, reversed,
post-closed, or unproven transitions fail closed. A within-theme preference must
carry a point-in-time comparator and denominator observation set in the exact same
theme identity epoch.

The complex-count receipt reports raw vehicle/filer counts, same-complex vehicle
deductions, unresolved complexes, excluded passive/systematic vehicles, and
mechanical vehicles. Its `independent_research_complex_count` is only the count
of resolved active complexes with an eligible observed intent descriptor; it
retains `independence_state: declarative_unverified` and never calls distinct
complexes proven independent.

China actor classes are additive extensions of the B0 manager-complex model:
`cn_public_fund`, `cn_insurer`, `cn_securities_firm`, `cn_qfii`,
`cn_social_security`, `cn_southbound_holder`, `cn_lhb_seat`, and
`cn_institutional_visit_actor`. Each must name
`CHINA_ALPHA_INTELLIGENCE_ARCHITECTURE_FREEZE` as its adoption source; this does
not replace the China ontology.

Legacy `engine/manager_quality.py`, `engine/manager_trades.py`, and `engine/fund_followability.py` remain their existing retrospective, display-tier quality, trade-history, and `follow_score` surfaces. K2-B neither imports nor relabels them as this prospective reliability object, and they confer no K2-B authority. A future bridge needs a separate commission and point-in-time proof.
