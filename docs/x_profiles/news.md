# X profile kit — Mastermind News (@mastermindnews1)

> **OPERATOR APPLICATION DRAFT.** Not published by any engine. See `README.md` in
> this directory for the two standing rules (no invented numbers, no house-banned claim token).

**Editorial identity:** the wire and Brief property voice; pairs with
mastermindx.ai. (`config/personas/mastermind_news.yml`.)

> **POSTING IS DARK.** The Buffer channel is bound and the desk_network entry
> exists, but `enabled: false` — this property's whole job is the wire/news
> cadence and that is blocked on the XG-W2 cadence resolver. Apply the profile
> now if you like; do not start posting from it before the resolver lands.

---

## Bio draft

> Market wire from MastermindX. What crossed, when it crossed, and the one line
> of context that makes it matter. Timestamps on everything.

*136 characters.* "Timestamps on everything" is the differentiator against every
other relay account and is checkable on the first post.

**Alternative, shorter:**

> The MastermindX wire. What crossed, when, and why it matters. Every item
> timestamped and sourced.

*97 characters.*

---

## Pinned post draft

> A wire account is only worth following if it is faster than your feed and more
> honest than your feed. Both are testable, so here is the standard we hold
> ourselves to.
>
> Every item carries the time it crossed and where it came from. Nothing runs on
> a single unconfirmed source. When a story turns out to be wrong we post the
> correction with the same prominence as the original, which is the part most
> wires quietly skip.
>
> What arrives: flashes as they cross, a two-paragraph explainer when a story
> deserves one, and an overnight roundup of what mattered while you were asleep.
>
> Follow if you want the tape without the adjectives.

**Answers the §8.6 five:** who (the wire property) / edge (speed plus timestamped
provenance) / formats (flash, explainer, overnight roundup) / proof (the
correction standard, visible from the first mistake) / why now (the standard is
the offer).

---

## Franchise slots

1. **On the tape** — the flash wire.
2. **The two-paragraph version** — an explainer when the flash is not enough.
3. **What mattered overnight** — the morning roundup.

---

## Notes for the operator

- This account's register is the **house wire voice**
  (`engine/marketing/wire_voice.py`), not a desk persona — which is why it has no
  `copywriter.personas` block. Its expression dial is 0 by construction: zero
  personality on wire and news kinds.
- The correction promise in the pinned post is a real operational commitment. Do
  not apply this pinned post until there is a corrections practice behind it; a
  wire that promises corrections and never posts one reads worse than a wire that
  promised nothing.
