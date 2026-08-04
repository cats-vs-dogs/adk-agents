# Industry Analysis Agent - working notes

An Industry Analysis and Economic Research agent built on Google ADK, driven
through `adk web`. The user asks for analysis of a sector, approves a research
plan, and the pipeline then researches and writes a cited report autonomously.

**Work only inside `industry_analysis/`.** The `.env`, `.venv` and `.gitignore`
live one folder up and are not part of this project's scope.

## Running it

```bash
adk web
```

Run from the **parent** directory (`adk-agents/`), not from `industry_analysis/`.
`adk web` treats each subdirectory as an agent, so from the parent it finds
`industry_analysis`; from inside it finds nothing. Verified working.

## Architecture

Four Python files. `agent.py` holds the graph, `prompts.py` holds every
instruction, `config.py` holds every tunable.

```
interactive_planner_agent          root; the only agent the user talks to
  |- plan_generator (as a tool)    drafts and revises the tagged plan
  \- research_pipeline (Sequential)  runs only after explicit approval
       |- section_planner              -> report_sections
       |- research_query_planner       -> search_queries (24+ explicit queries)
       |- section_researcher           -> section_research_findings
       |- iterative_refinement_loop (Loop, max config.max_search_iterations = 5)
       |    |- research_evaluator      -> research_evaluation (pass/fail)
       |    |                             + appends to disputed_figures
       |    |- escalation_checker      breaks the loop on 'pass'
       |    \- enhanced_search_executor-> new_findings, APPENDED to the base
       \- report_composer              -> final_cited_report
```

Data moves between agents through **session state**, injected into instructions
with `{key?}` placeholders (the `?` makes a missing key render empty instead of
raising). State keys: `research_plan`, `report_sections`,
`section_research_findings`, `research_evaluation`, `sources`,
`citation_sources`, `final_cited_report`, `token_usage`, `search_queries`.

## Why research is split into two agents

`research_query_planner` writes an explicit numbered list of 24+ targeted queries;
`section_researcher` then has to execute them and publish a search log accounting
for each one, which `research_evaluator` checks first and fails hardest on.

This exists because of a measured failure. On the first live run the researcher
made **one** model call on 5,420 input tokens - barely more than its own
instruction - emitted 18,900 tokens of "findings", and produced only 3 grounded
search events in the entire session. It wrote a large evidence base from almost no
retrieved material, and the critic then failed it three rounds running until the
loop hit `max_search_iterations`.

Pre-committing the queries in a separate, tool-free step is what stops the model
collapsing the whole job into a single grounded pass: it cannot quietly skip
searching when a numbered list of searches is sitting in its context and a log of
them is what it will be graded on. Keep that separation if you refactor.

**It worked**: on the next run `section_researcher` issued 33 queries instead of
12, and the run as a whole 72 instead of 48, retrieving 118 grounding chunks
against 63.

### Measuring search volume correctly

Count `grounding_metadata.web_search_queries`, **not** grounding events. Gemini's
built-in `google_search` issues many queries inside a single model call, so events
count model calls, not searches. Judging the pipeline by event count understates
it by roughly an order of magnitude — a mistake that once led to the wrong
diagnosis here.

## The evidence base is append-only - do not undo this

`enhanced_search_executor` writes **only new material** to `new_findings`;
`merge_new_findings_callback` appends it to `section_research_findings` under a
round heading. Earlier rounds are immutable.

Never point the executor's `output_key` back at `section_research_findings`. That
was the original design and it failed badly: told to "return the complete merged
evidence base", the model rewrote ~20k tokens every round, and measurement across
a live run showed it

- **dropped 42% of the researcher's findings on the first pass** (57,626 chars in,
  33,420 out), then
- regrew the base each round by inventing figures to fill what it had lost.

The critic's five verdicts each named a *different* set of fabrications, none
repeating, and the comments got longer rather than shorter. The refinement loop
was a fabrication generator: more rounds meant more invented numbers, so it could
never converge and always hit `max_search_iterations`.

Removing the rewrite removes the mechanism. A model cannot corrupt findings it is
never asked to reproduce.

## Fabrication control

The critic detects invented figures by cross-checking them against the search log.
That detection is worthless unless something acts on it, so:

- `research_evaluator` must **quote the offending figure verbatim**, because its
  comment is what the next agent uses to hunt the figure down.
- `record_disputed_findings_callback` appends every failing verdict to
  `state["disputed_figures"]`. Because the evidence base is append-only, a
  rejected figure cannot be edited out of it - so it is **quarantined** instead
  and enforced at the composer, the only place that decides what a reader sees.
- `research_evaluator` is told **not to re-flag** anything already quarantined,
  and to judge only material added since its last review. Without this the loop
  cannot converge, since the rejected figures are still sitting in the base.
- `report_composer` receives the quarantine list and must publish nothing on it
  unless a later round attached a source - hedged or otherwise.
- `finalize_report_callback` prepends a warning banner whenever the final grade is
  not `pass`, driven by `state["research_evaluation"]` rather than by asking the
  composer to admit it. An absent or missing grade is treated as *not* passed —
  fail closed, never silently clean.

This exists because a live run shipped three figures the critic had explicitly
named as fabricated, each wearing a citation that made it indistinguishable from a
sourced one.

## Cost tracking

`track_model_usage_callback` is an `after_model_callback` on all seven LlmAgents.
It accumulates `usage_metadata` per agent into `state["token_usage"]` and logs a
running line to the terminal after every model call. `format_cost_report` renders
the breakdown, which `finalize_report_callback` appends to both the chat reply and
the saved `.md`.

Notes for anyone changing it:
- **Thinking tokens are billed as output**, so `thoughts_token_count` is added to
  the output figure rather than reported separately.
- Token counts are exact (from the API); prices come from `MODEL_PRICING` in
  `config.py` and go stale — that is why the output says "estimate".
- Unknown or version-suffixed model ids degrade gracefully: `_price_for` falls
  back to prefix matching, then to zero, rather than raising mid-run.
- Grounded-search requests are counted and priced separately, because whether
  they cost anything depends on the month's total against the free allowance.
- **Add `after_model_callback=track_model_usage_callback` to any new LlmAgent**,
  or its cost silently vanishes from the total.

### Mining a past run

`adk web` persists sessions to `industry_analysis/.adk/session.db` (SQLite,
gitignored). The `events` table holds one JSON blob per event, each carrying
`author`, `usage_metadata` and `grounding_metadata` — so a finished run can be
analysed after the fact even without the cost callback:

```python
import sqlite3, json
for (data,) in sqlite3.connect(".adk/session.db").execute("SELECT event_data FROM events"):
    e = json.loads(data)
    print(e.get("author"), e.get("usage_metadata"))
```

Counting calls per agent is the quickest way to tell whether the refinement loop
exited on a `pass` or ran out of iterations: equal call counts for
`research_evaluator` and `enhanced_search_executor` mean the critic never passed.

The loop agents and the composer set `include_contents="none"` — they work purely
from injected state, not conversation history. If you add an agent that seems to
"not see" its input, this is why: give it a `{placeholder}`.

## Standing decisions

| Decision | Choice |
|---|---|
| Default market | Bulgaria, with EU and global context |
| Output | Chat **and** a dated `.md` in `output/` |
| Report language | English always (Bulgarian-language *sources* encouraged) |
| Report length | Inferred from the request, stated in the plan for approval |
| Models | Pro for judgment, Flash for search legwork |
| User-supplied website lists | Deliberately out of scope in v1 |

## ADK 2.x gotchas found the hard way

- **This is ADK 2.x** (built and verified on 2.6.2). 2.0 replaced the hierarchical
  executor with a graph-based workflow runtime. `LlmAgent`/`SequentialAgent`/
  `LoopAgent`/`BaseAgent` still work, but **1.x blog posts and tutorials are not
  reliable** — check against the installed package.
- **`GOOGLE_GENAI_USE_ENTERPRISE` is correct**, not a typo for
  `GOOGLE_GENAI_USE_VERTEXAI`. It is the current name after the Vertex AI ->
  Gemini Enterprise Agent Platform rebrand. Setting both to conflicting values
  raises a `ValueError`.
- **Two auth modes, one switch.** `GOOGLE_GENAI_USE_ENTERPRISE=0` uses an API key
  (`GOOGLE_API_KEY`); `=1` uses the Cloud project and **ignores the API key
  entirely**. A `DefaultCredentialsError` despite a valid key means the flag is
  still `1`. Both setups can live in `.env` at once. See README for the full
  comparison.
- **Gemini 3.x is `global`-endpoint only on Cloud.** Verified 4 Aug 2026 with live
  calls: both `gemini-3.1-pro-preview` and `gemini-3.6-flash` return 404 from
  `us-central1` and work from `global`, so `GOOGLE_CLOUD_LOCATION` must be
  `global`. Not a preview-only restriction. Does not apply in API-key mode.
- **ADC needs a quota project.** `gcloud` user credentials have none by default;
  fix with `gcloud auth application-default set-quota-project <PROJECT_ID>` to
  avoid misleading quota/API-not-enabled errors later.
- **Never move to a Gemini 2.5 model** — that generation shuts down October 2026.
- **An agent with `output_schema` cannot have tools or hand off.** This is why
  `research_evaluator` is tool-free and sets `disallow_transfer_to_*`.
- **An agent with a built-in tool (`google_search`) cannot also carry custom
  function tools.** This is why saving the report happens in a callback rather
  than a save tool — it keeps the graph free of that conflict.
- **`.env` discovery walks up to the filesystem root**, so the `.env` one folder
  up is found. Verified by reading `google.adk.cli.utils.envs`.
- `prompts.TODAY` is resolved at import time. Restart `adk web` if the server has
  been running across midnight and the report date matters.
- `section_researcher` uses `BuiltInPlanner` with thinking enabled. If a model
  ever rejects the thinking config, dropping the `planner=` line is the fix.

## Where to change things

- **Report quality, tone, rigor** -> `prompts.py`. This is where almost all tuning
  belongs. The `EVIDENCE_STANDARD` block is shared by the researcher, critic and
  composer, so editing it moves all three at once.
- **Which sources the agent reaches for** -> `MARKET_CONTEXT` in `prompts.py`.
- **Models, loop count, default market, output folder** -> `config.py`.
- **The graph itself** -> `agent.py`. Changing it should be rare.

## State of the prototype

Working end to end on ADK 2.6.2 / Python 3.12.10, verified across five live runs
on 4-5 Aug 2026 (Cloud auth, `global` endpoint).

| Run | Sector | Outcome | Rounds | Cost |
|---|---|---|---|---|
| 1 | Tourism | failed review 3/3 | hit cap | $1.16 |
| 2 | Transport | failed review 3/3 | hit cap | $1.42 |
| 3 | Construction | failed review 5/5 | hit cap | $1.97 |
| 4 | Construction | **passed** | 4 | $1.01 |
| 5 | Oil and gas | **passed** | 3 | $0.78 |

Runs 1-3 predate the append-only redesign; 4-5 follow it. Passing runs are both
cheaper and better, because the expense was the loop failing to converge.

**[RUN_HISTORY.md](RUN_HISTORY.md) holds the full measurements** — per-agent
tokens, query counts, verdict-length progressions, and the evidence-base size
traces that diagnosed the rewrite problem. The session database those came from
stays on the original machine, so that file is the record.

Also verified: `adk web` discovers the agent (`/list-apps` returns
`["industry_analysis"]`), and the callbacks are unit-tested with stubs — source
dedup, id stability across rounds, all three `<cite>` tag forms, hallucinated-id
stripping, no-clobber save, sources appendix, cost arithmetic, review banner,
append-only merge and quarantine.

## The open question for the next session

**Passing reports are getting shorter**: 2,987 words (run 4), 2,258 (run 5),
against 4,000-5,000 for the failing runs. The evidence rules are working — the
long reports were substantially padded with unsourced material — but there is a
real risk the pipeline now optimises for *passing review* rather than *being
useful*, since the cheapest way to satisfy the critic is to claim less.

If a report reads thin, the fix is more research depth — raise the query floor
above 24 in `QUERY_PLANNER`, or add queries per section — **not** relaxing the
evidence standard. That standard is the reason the reports can be trusted at all.
