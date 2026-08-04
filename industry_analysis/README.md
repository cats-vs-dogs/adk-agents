# Industry Analysis and Economic Research Agent

A prototype research agent built on Google ADK. You ask for analysis of an
industry or economic sector, agree a research plan, and the agent then researches
it autonomously and writes a cited report.

Default market is **Bulgaria**, with EU and global context. Reports are written in
English.

## How it works

1. You ask for analysis of a sector — *"Prepare a market research brief for Tourism"*.
2. The agent drafts a tagged research plan and shows it to you.
3. You add, remove or change goals until you are happy.
4. **Nothing happens until you explicitly approve.**
5. Once approved, the pipeline outlines the report, gathers evidence, has a critic
   agent review it and send the researcher back for anything thin, and finally
   writes a report with inline citations.
6. The report appears in the chat and is saved to `output/`.

Plan tags: `[RESEARCH]` and `[DELIVERABLE]` mark what kind of goal it is;
`[NEW]`, `[MODIFIED]` and `[IMPLIED]` mark what changed when a plan is revised —
`[IMPLIED]` is how you see what the agent added that you did not ask for.

## Setup on a new machine

From the repo root (the folder **containing** `industry_analysis/`):

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r industry_analysis/requirements.txt
```

Create a `.env` in the repo root — one folder **above** `industry_analysis/`:

```
GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

Then authenticate. This opens a browser and is the one step that cannot be
scripted:

```bash
gcloud auth application-default login
```

If `gcloud` is not installed, get it from
https://cloud.google.com/sdk/docs/install — the agent cannot reach any model
without Application Default Credentials.

## Running

From the repo root, **not** from inside `industry_analysis/`:

```bash
adk web
```

Open the URL it prints and pick `industry_analysis` from the agent dropdown.

## Checking your model IDs

Model IDs are set in `config.py` and were correct as of 4 August 2026. Gemini
model names move quickly, so if a run fails with a model-not-found error, list
what your project can actually see:

```bash
.venv/Scripts/python -c "from google import genai; [print(m.name) for m in genai.Client().models.list() if 'gemini' in m.name]"
```

Then update `critic_model` / `worker_model` in `config.py`. Do not switch to a
Gemini 2.5 model — that generation shuts down in October 2026.

## Layout

| File | What it holds |
|---|---|
| `agent.py` | The agent graph and the two callbacks |
| `prompts.py` | Every agent instruction — most tuning happens here |
| `config.py` | Models, refinement-loop cap, default market, output folder |
| `output/` | Generated reports, one dated `.md` per run |
| `CLAUDE.md` | Working notes and ADK gotchas for future sessions |

## Known limits of v1

- Supplying a list of specific websites to research is not implemented.
- Reports are English-only.
- The critic loop is capped at 3 rounds to keep runs affordable; raise
  `max_search_iterations` in `config.py` for deeper work.
- No automated tests ship with the prototype; quality is judged by reading the
  output.
