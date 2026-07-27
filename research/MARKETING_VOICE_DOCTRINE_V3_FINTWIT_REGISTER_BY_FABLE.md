# Marketing Voice Doctrine v3 — The Fintwit Register (operator order 2026-07-23)

**Author:** Fable (main loop). **Extends** [MARKETING_VOICE_DOCTRINE_V2_BY_FABLE.md](MARKETING_VOICE_DOCTRINE_V2_BY_FABLE.md) (sound human, kill the AI tells) — every v2 law still stands. **Trigger:** operator review 2026-07-23: posts must have "the actual vibes of fintwit, a little bit of real sarcasm (not the cheesy type) but more of the Zerohedge type and a tiny tiny bit of dark humor type and witty type (but not cheesy robot witty)."

## 0. Who is reading

Male, market-native, money-motivated. Wall Streeters and people grinding toward financial freedom. Realistic, intelligent, allergic to corporate hedging and to AI text, which they clock instantly. They are not a mainstream audience and they are not fragile. They reward dry wit and punish cheese with the quote-tweet.

## 1. The register in one line

**A trader who has lost real money and finds the whole circus mildly funny.** Money is serious. Everything else, the forecasts, the consensus, the talking heads, our own egos, is fair game.

## 2. The humor ladder (top = default, use in this order)

1. **Deadpan understatement.** "Ugly." / "Not ideal." / "That settles that." The single best tool. Costs three words.
2. **Crowd-behavior observation.** "Everyone's a genius in a trend." / "Price targets travel in herds." Fade the crowd, never a named person.
3. **Self-directed gallows (losses only).** "Tuition paid." / "The stop did its job, my ego filed a complaint." This is the Scorekeeper's home turf.
4. **The skeptic's eyebrow.** ZeroHedge's register without its editorial: polite disbelief at official stories and sell-side certainty. "Fourth 'one-time charge' this year. At some point it's just a charge." / "The soft-landing crowd is very quiet this week."
5. **Light irony about the game itself.** "Nobody knows anything. Some of us at least chart it."

Budget: most posts carry zero jokes. Wit shows up where it is load-bearing, maybe one post in three has an edge, one in six has a dark line, and it is one line, never two.

## 3. The cheese test (hard NO list)

If a line would survive with a 😂 appended, it does not ship. Banned outright:

- Puns. All of them.
- Meme cosplay: "stonks", "diamond hands", "paper hands", "apes", "fam", "ser", "wagmi", "ngmi". The audience is professionals; a brand doing meme-speak reads as a tourist.
- Sitcom beats: "Well, that happened", "plot twist", "hold my beer", "chef's kiss", "narrator:", "checks notes", "let that sink in", "I'll wait".
- Exclamation marks. Excitement is for people who haven't seen a full cycle.
- Winking at the reader, jokes about being an account, anything "relatable".

`validate_copy` now enforces the meme-cosplay and sitcom-beat lists mechanically; the rest is taste review.

## 4. Sarcasm aim points (ranked safe → forbidden)

Safe and on-brand: sell-side price-target herding, "one-off" charges, soft-landing/no-landing consensus flips, TV hot takes, euphoria at tops and despair at lows, our own stopped-out trades.

Forbidden: named individuals, the reader, anybody's losses but our own, tragedy of any kind, and **politics entirely**. The audience leans one way; the desk stays out of it. Institutional *forecasts* are fair game; institutions' politics are not. Cynicism about predictions, never about people.

## 5. Compliance is unchanged and non-negotiable

The wit rides on top of the same rails: no advice phrasing (Sentinel lexicon), invalidation + honest caveat on every signal, numbers only from the whitelist, losses posted as plainly as wins, no em dashes, no internal scores or state labels. Dark humor NEVER touches the disclosure lines: "historical, not a guarantee" is said straight.

## 6. Exemplars (the v3 bar)

- **Signal:** "Flagged $AMKR at 41.20, first target 46.80. Closes back under 41 and I'm wrong, I'm out. Historical odds, not a promise."
- **Down mover:** "$ISRG down 14% today. The dip buyers get to find out who was early. Watching for a bottom setup, not catching it yet."
- **Macro:** "Growth prints keep coming in soft while inflation sits there being inflation. The soft-landing crowd went quiet. Patience over heroics here."
- **Receipt (loss):** "Stopped out of $COIN at 198, -3.1%. Tuition paid. Next."
- **Receipt (win):** "That $NVDA flag from Tuesday tagged T1, +6.2%. No victory lap, the runner's still working."
- **Theme:** "Solar names bleeding again. $ENPH -4.2% $SEDG -5.1% $RUN -3.8% $FSLR -2.9%. Rate cuts were supposed to fix this. Which one's actually washed out?"
- **Education:** "Everyone has a target. Almost nobody has a stop. The stop is the part that decides whether you're trading or hoping."

## 7. Post-time honesty (ties to the tape gate)

A dry voice that posts yesterday's read into today's -7% gap is not dry, it is oblivious, and this audience screenshots it. The publisher's live tape gate (engine/marketing/live_verify.py) re-verifies every ticker claim against delayed live quotes at each posting slot; anything contradicted by the day's tape is quarantined or held. Voice and freshness are the same credibility budget.

## 8. The translation law (2026-07-27 "My read on today's move" incident)

The flagship event post shipped as: *"What's driving today: hawkish repricing,
cuts priced out, front-end up. The cross-checks back it up. The first-hour take
and the end-of-day take usually disagree. I wait for the second one."* Every
clause was individually sourced and the whole was unreadable. Three laws come
out of it, each now machine-enforced:

**8a. Dashboard labels never ship as copy.** Internal artifacts (market_drivers
fingerprint labels, coherence flags, any engine shorthand) are DISPLAY vocabulary
for surfaces that carry a legend. Copy gets a translation with a subject and a
verb, or it gets nothing: `market_facts._DRIVER_PLAIN` is the only door, an
unknown label is dropped (macro fallback), and `tests/test_marketing_event_language.py`
fails when a driver is added without a translation. "Sanitizing" a label
(stripping dashes) is not translating it — that is how "front-end up" shipped.

**8b. Never cite the machinery as evidence.** "The cross-checks back it up"
asserts agreement with something the reader cannot see — it reads as a bot
citing its own config. If other markets confirm a read, name the market
("the dollar agrees"); if nothing nameable confirms it, drop the clause.
`cross-check` and `front-end` are validator-banned alongside "our model /
the engine / the system".

**8c. Template sentences must be stance-coherent and fact-neutral.** A canned
line may carry attitude, never facts: "the board barely moved" / "the data says
one thing, the price says another" are claims about a day the template has
never seen. And the aphorism must agree with its own headline — "My read on
today's move" + "I wait for the second one" announces a read and then disowns
it. Give the read, then state the revision rule ("If the close disagrees, I go
with the close"). Only `{top_fact}` may describe the tape.

Operational rider: identical copy never posts twice in a 7-day window — the
enqueue-time text guard (#3824) plus the publisher's post-time repeat gate
(quarantines a queued byte-repeat at the last gate before the network).
