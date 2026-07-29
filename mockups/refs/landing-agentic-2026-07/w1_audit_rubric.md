# W1 audit rubric (Fable grades shots against this; each item PASS/FLAG with note)

## Hero copy block (vs attio-00 + DIRECTION §6.1)
1. Pill: white, hair border, sh-1, mono kicker type, green ping dot alive in live shot; not the old heavy black pill.
2. H1: exactly two rendered lines at 1440; line 1 "Your personal" muted #8b95a6-ish; line 2 ink; NO gradient anywhere; tracking tight (-.022em); wraps sane at 390 (2-3 lines max, no orphan word).
3. Sub: bold ink "Institutional-grade." lead + trimmed continuation; ≤2 lines at 1440; muted color; 56ch cap respected.
4. CTAs: primary blue w/ sh-2; secondary white w/ hair-2 border + sh-1; equal heights; hover states defined in CSS.
5. data-adtest-slot attrs still on h1 + p.sub (grep).
6. ZH hero: same two-tone split 「你的个人」/「市场情报台。」; sub lead 「机构级。」; no EN fragments; line breaks acceptable.

## Collage (vs §6.1 choreography)
7. pp3 center: visibly larger (scale 1.0), r-xl, stage shadow — reads as THE object; gauge/needle intact; "demo" kicker present.
8. pp2/pp4 float tier (.93), pp1/pp5 lift tier (.87, opacity .94); wings tuck UNDER neighbors (~48px overlap); z-order correct (no wing overlapping center's shadow weirdly).
9. No blur on wings; text in wings still legible.
10. Curtain field: hairline verticals visible-but-quiet under collage; radial wash bottom-anchored; edge mask fades curtain before section edge; NOT visible above the fold copy zone.
11. Card internals: .mk kickers, hair-weak inner dividers, tnum digits; heatmap tiles have subtle inner borders; no cramped padding.
12. Entrance (live shot): collage settled correctly (no half-transformed cards frozen by ?still logic leaking into live).

## Foundation sweep (full-page shot)
13. Downstream sections did NOT visually break from the token migration (old --sh-deep/--sh-card consumers still look intentional at their new tiers) — terminal frame, belt cards, feature cards, tier cards, matrix, cband all sane.
14. Nav: spacing/hover polish present; DOM untouched (tests green is the proof).
15. Regime tint: body[data-regime] rules exist; @property registered; live shot after 4s shows tint ≠ default OR default (cycle timing-dependent — either fine); ?still shows static default.
16. Reduced-motion + still blocks cover every new transition/animation (grep the new CSS for transition/animation names and cross-check the kill blocks).

## Mechanical gates
17. Tests: the 8-file set green.
18. Pairs byte-identical after sync.
19. Console: CLEAN in capture.
20. landing.css < 100KB; no new external requests (grep https:// diff).
21. Commit message per spec; no push.

Verdict: APPROVE (minor notes to fold into W2) / FIX-ROUND (specific defects, re-shoot) / REJECT (contract broken).
