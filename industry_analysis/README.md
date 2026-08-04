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

## More

- **[SETUP.md](SETUP.md)** — installation, authentication, models, troubleshooting
- **[CLAUDE.md](CLAUDE.md)** — architecture and working notes
