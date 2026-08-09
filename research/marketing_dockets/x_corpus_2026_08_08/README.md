# Fintwit style corpus — 2026-08-08 pull

One-time bounded pull (operator-authorized 2026-08-08) via twitterapi.io
`user/last_tweets`: 100 recent ORIGINAL posts × 5 accounts, 26 API calls total.
No polling was set up and none may be (DNR ruling 2026-08-03: hot-polling billed
X reads is dead; the XS push websocket is the only approved recurring shape).
Endpoint returns originals only — reply behavior is NOT observable here.

Purpose: style ground truth for the Codex copy engine (masterplan
`research/MARKETING_X_ENGINE_CODEX_QUALITY_AND_FASTLANES_MASTERPLAN_2026_08_08.md` §2 R7).
Complements `x_corpus_2026_07_29/` (286 posts, 17 accounts).

## Stats

| Account | Range | Med likes | Med views | % media | Med chars | Cashtags |
|---|---|---|---|---|---|---|
| TrendSpider | 08-05→08-08 (3d) | 230 | 71k | 89% | 120 | 81% |
| KobeissiLetter | 07-31→08-07 (8d) | 2,687 | 332k | 77% | 459 | 16% |
| charliebilello | 07-21→08-07 (17d) | 378 | 66k | 69% | 218 | 25% |
| unusual_whales | 08-05→08-08 (3d) | 1,059 | 211k | 9% | 103 | 13% |
| MacroCharts | 02-02→08-04 (6mo) | 137 | 27k | 68% | 169 | 0% |

## Binding format patterns (500/500 posts)

1. **Hashtags: 0% across every account.** Ban outright.
2. **"BREAKING:"** is the wire-desk opener (Kobeissi 60%, whales 25%); analytical
   accounts never use it. Openers are role-scoped, not universal.
3. **Econ prints**: headline number vs consensus, then 1–2 revision/context lines,
   zero adjectives. ("...loses -23,000 jobs in July, well below expectations of
   +85,000. The unemployment rate fell to 4.1%, below expectations of 4.2%.
   June's number was also revised down by -37,000.")
4. **Chart captions are minimal** (<10 words common); the image carries the analysis.
5. **Emoji sparse + functional only** (👀 setup, 🔥 momentum, 🚨 urgency); Kobeissi
   uses zero. Never decorative strings.
6. **No threads** (0–2%). Long content = ONE post with line breaks separating claim
   from supporting stats. (Kobeissi's 459-char median implies Premium long posts.)
7. **No hedging** ("I think"/"IMO": 4 of 500), **no exclamation marks** (496/500 zero),
   **no CTAs** ("follow for more" etc.: zero).
8. **Numbers exact and comparative** — always paired with a delta vs estimate /
   prior / all-time-high; never rounded for effect.
9. **Quotes ship flat**: `Name: statement` or `Name (affiliation): "quote"` — opinion
   is implied by selection, never appended.
10. Register splits by role: terse fragments for real-time desks (~103–120 chars),
    full declarative sentences with quantified support for research desks.
11. Stacked-list posts (bilello "% Below All-Time High..." format) are a
    high-engagement analytical shape our distance-from-high data can feed.

Files: `<handle>.jsonl` — one tweet/line: id, created_at, text, like/retweet/reply/
view counts, media flags. Fetched 2026-08-08; scripts stayed in session scratchpad.
