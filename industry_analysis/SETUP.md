# Setup and troubleshooting

Installation, authentication and model configuration for the industry analysis
agent. For what the agent does and how to run a research request, see
[README.md](README.md).

## Setup on a new machine

From the repo root (the folder **containing** `industry_analysis/`):

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r industry_analysis/requirements.txt
```

Then create a `.env` in the repo root — one folder **above**
`industry_analysis/`. There are two ways to authenticate; pick either.

### Option A — AI Studio API key (simplest)

No SDK to install. Get a key at https://aistudio.google.com/apikey, then:

```
GOOGLE_GENAI_USE_ENTERPRISE=0
GOOGLE_API_KEY=your-key-here
```

### Option B — Gemini Enterprise Agent Platform, formerly Vertex AI

Bills against a Google Cloud project and gives you its quotas, data residency
and audit controls. Requires the gcloud SDK.

```
GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
```

Then authenticate. This opens a browser and is the one step that cannot be
scripted:

```bash
gcloud auth application-default login
```

If `gcloud` is missing, install it from https://cloud.google.com/sdk/docs/install
(or `winget install Google.CloudSDK`) and **open a new terminal** afterwards —
the installer edits PATH and your current shell will not see it.

### Which flag does what

`GOOGLE_GENAI_USE_ENTERPRISE` decides everything. Set to `1`, the client takes
the Cloud path and **ignores `GOOGLE_API_KEY` entirely**; set to `0`, it uses the
API key and ignores the project and location settings. Getting a
`DefaultCredentialsError` while holding a perfectly good API key almost always
means this flag is still `1`.

You can safely keep all four lines in `.env` and switch between the two setups by
flipping that single character.

The variable used to be called `GOOGLE_GENAI_USE_VERTEXAI`. Both names work, but
setting them to conflicting values raises a `ValueError` — use one.

## Model availability differs between the two

Worth knowing before you pick, because it bites in confusing ways:

- **Gemini 3.x models are global-endpoint only on Cloud.** Verified on 4 Aug 2026:
  *both* models this project ships with — `gemini-3.1-pro-preview` and the stable
  `gemini-3.6-flash` — return **404 NOT_FOUND** from `us-central1`, and both
  respond normally from `global`. This is not a preview-only restriction, and it is
  why Option B above sets `GOOGLE_CLOUD_LOCATION=global`. If you need a specific
  region for data residency, both models in `config.py` must change to older ones
  your region actually serves.
- **AI Studio has no such restriction** — an API key reaches these models
  directly, which is part of why it is the easier starting point.
- **Set a quota project for ADC.** User credentials from `gcloud` carry no quota
  project by default, which surfaces later as spurious "quota exceeded" or "API not
  enabled" errors. Pre-empt it with
  `gcloud auth application-default set-quota-project YOUR_PROJECT_ID`.
- **New models usually appear on AI Studio first**, then on Cloud.
- **Quotas and billing are separate.** AI Studio has a free tier with low rate
  limits; Cloud has no free tier but far higher throughput. The research pipeline
  makes many search-grounded calls per run, so a free-tier key can hit rate limits
  on a long report.

Whichever you choose, confirm your two configured models are actually reachable
before a full run — see below.

## Running

From the repo root, **not** from inside `industry_analysis/`:

```bash
adk web
```

Open the URL it prints and pick `industry_analysis` from the agent dropdown.

## Checking your model IDs

Model IDs are set in `config.py` and were correct as of 4 August 2026. Gemini
names move quickly, so run this once after setting up `.env` — it lists what your
credentials can actually reach, and takes seconds compared to discovering a bad
model ID part-way through a research run:

```bash
.venv/Scripts/python -c "from dotenv import load_dotenv; load_dotenv('.env'); from google import genai; [print(m.name) for m in genai.Client().models.list() if 'gemini' in m.name]"
```

The explicit `load_dotenv` matters — `adk web` reads `.env` for you, but a bare
`python -c` does not, so without it you will get a credentials error that has
nothing to do with your actual setup.

Then update `critic_model` / `worker_model` in `config.py` to match. Do not switch
to a Gemini 2.5 model — that generation shuts down in October 2026.

How the failures read, so you can tell them apart:

| Symptom | Cause |
|---|---|
| `DefaultCredentialsError` | Option B selected but `gcloud auth application-default login` not run — or `GOOGLE_GENAI_USE_ENTERPRISE=1` while you meant to use an API key |
| `404 model not found` | Model ID wrong, or a preview model requested from a regional endpoint instead of `global` |
| `429` / quota errors mid-run | AI Studio free-tier rate limits; lower `max_search_iterations` in `config.py` or move to Option B |

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
