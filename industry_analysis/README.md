# Industry Analysis and Economic Research Agent

Produces a cited economic and market analysis of an industry or sector. Default
market is **Bulgaria**, with EU and global context. Reports are written in English.

## Starting a research run

Name the sector you want analysed:

> Prepare a market research brief for Tourism

The agent replies with a **research plan** — a short list of tagged goals, stating
the market, the target length and what it intends to cover. Nothing is researched
yet.

Change it however you like:

> add regulatory risk, drop the SWOT, and include named companies

**Research only begins once you explicitly approve:**

> approved, go ahead

The pipeline then works autonomously — outline, search, critique, re-search,
compose — and returns a cited report, also saved to `output/` with a cost
breakdown for the run.

## Reading the plan

| Tag | Meaning |
|---|---|
| `[RESEARCH]` | A goal met by gathering information |
| `[DELIVERABLE]` | A goal met by producing a table, matrix or ranked list |
| `[NEW]` / `[MODIFIED]` | Added or changed at your request |
| `[IMPLIED]` | Added by the agent on its own initiative — so you can see what it decided for you |

## Worth knowing

- **Company-level analysis is opt-in.** By default the agent analyses market
  structure and concentration without profiling named firms. Ask for it in the
  plan if you want it.
- **Length follows your wording.** "Brief" gets ~1,500–2,500 words; "full" or
  "detailed" gets ~4,000–6,000. The plan states the target so you can change it.
- **Gaps are declared, not filled.** Where a figure cannot be found the report
  says so rather than inventing one.

## Credit

The overall shape of this agent is adapted from Google's **Deep Search** sample
(formerly *gemini-fullstack*) in
[google/adk-samples](https://github.com/google/adk-samples/tree/main/python/agents/deep-search),
Apache 2.0. Taken from it:

- The **plan tag vocabulary** — `[RESEARCH]`, `[DELIVERABLE]`, `[MODIFIED]`,
  `[NEW]`, `[IMPLIED]` — and the human-approval gate before research starts
- The **pipeline shape**: outline → search → critique → refine → compose, with a
  loop that exits when a critic agent accepts the evidence
- The **citation mechanism**: inline tags rewritten into markdown links from
  collected search-grounding metadata

Built on top of that for this project: the Bulgaria/EU/global market framing and
its named primary sources, the evidence standard the researcher and critic are
held to, a query-planning step that pre-commits searches, an append-only evidence
base with quarantine for challenged figures, and per-run cost reporting.

## More

- **[SETUP.md](SETUP.md)** — installation, authentication, models, troubleshooting
- **[CLAUDE.md](CLAUDE.md)** — architecture and working notes
- **[RUN_HISTORY.md](RUN_HISTORY.md)** — measurements behind the design decisions
