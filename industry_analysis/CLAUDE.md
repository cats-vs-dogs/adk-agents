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
       |- section_researcher           -> section_research_findings
       |- iterative_refinement_loop (Loop, max 3)
       |    |- research_evaluator      -> research_evaluation (pass/fail)
       |    |- escalation_checker      breaks the loop on 'pass'
       |    \- enhanced_search_executor-> section_research_findings (merged)
       \- report_composer              -> final_cited_report
```

Data moves between agents through **session state**, injected into instructions
with `{key?}` placeholders (the `?` makes a missing key render empty instead of
raising). State keys: `research_plan`, `report_sections`,
`section_research_findings`, `research_evaluation`, `sources`,
`citation_sources`, `final_cited_report`.

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
- **Preview models are `global`-endpoint only on Cloud.** `gemini-3.1-pro-preview`
  404s on regional endpoints such as `us-central1`; `GOOGLE_CLOUD_LOCATION` must
  be `global`. This does not apply in API-key mode. If a region is required for
  data residency, `critic_model` has to move to a GA model.
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

## Verified so far

- Graph imports and assembles correctly on ADK 2.6.2 / Python 3.12.10.
- `adk web` discovers the agent (`/list-apps` returns `["industry_analysis"]`).
- Callbacks unit-tested with stubs: source dedup, id stability across refinement
  rounds, all three `<cite>` tag forms, hallucinated-id stripping, file save with
  no-clobber, sources appendix.

**Not yet verified end-to-end**: no live model run has happened, because
Application Default Credentials were not set up on this machine. The first real
run is still ahead — see README.
