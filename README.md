# adk-agents

A collection of agents built with the **Google Agent Development Kit (ADK)**, run
locally through `adk web`.

Each agent is a self-contained sub-project in its own folder. They share one
virtual environment, one credentials file and one repo-root `.gitignore`, so
adding a new agent needs no infrastructure setup.

## Agents in this repo

| Folder | What it does | Status |
|---|---|---|
| [`industry_analysis/`](industry_analysis/README.md) | Industry and economic research. Takes a sector, agrees a research plan with the user, then researches it and writes a cited report. Bulgaria-focused, EU and global context. | v1 prototype |

*Update this table whenever a new agent folder is added.*

## Layout

```
adk-agents/
├── .env                  shared credentials - NOT in git
├── .venv/                shared virtual environment - NOT in git
├── .gitignore            repo-wide ignores
├── README.md             this file
│
├── industry_analysis/    one agent
│   ├── __init__.py       must contain: from . import agent
│   ├── agent.py          must expose: root_agent
│   ├── requirements.txt  what THIS agent needs
│   ├── .gitignore        ignores specific to THIS agent
│   ├── CLAUDE.md         working notes
│   └── README.md         setup and usage
│
└── <next_agent>/         same shape
```

`adk web` treats every subdirectory containing `__init__.py` and `agent.py` as one
agent, and lists them in a dropdown.

## Shared infrastructure

### `.venv` — one environment for everything

All agents run from the single `.venv` at the repo root. This is deliberate: the
agents share most of their dependencies (`google-adk` alone pulls in ~127
packages), so one environment means installing that once rather than per project.

The trade-off is **no isolation between agents** — see the warning below.

### `requirements.txt` — one per agent, but they all install into that one `.venv`

This is the part that surprises people. `requirements.txt` is inert
documentation: it has no power to direct packages anywhere. What decides the
install target is *which pip you invoke*:

```bash
.venv/Scripts/python -m pip install -r industry_analysis/requirements.txt
```

That is `.venv`'s pip, so the packages land in `.venv` — and they would land there
identically if the file lived anywhere else. Every agent's dependencies therefore
pool into a single shared environment.

Three consequences worth knowing:

1. **No isolation.** Once one agent installs a library, every other agent can
   import it — even one that never declared it. That works on this machine and
   fails on a fresh clone: the classic "works on my machine" trap.
2. **Version conflicts have no resolution.** If agent A needs `pydantic>=2` and
   agent B needs `pydantic<2`, one environment cannot satisfy both. pip installs
   whichever was requested last, and the other agent breaks at *runtime* rather
   than at install time, which makes it awkward to diagnose.
3. **Each `requirements.txt` is still the source of truth** for what its agent
   genuinely needs. It is the only record that survives to another machine, which
   is exactly why they stay per-agent.

**Never run `pip freeze > some_agent/requirements.txt`.** In a shared environment
that captures *every* agent's libraries plus all transitive dependencies, writing
hundreds of lines into one agent's manifest. Declare direct dependencies by hand —
`industry_analysis/requirements.txt` is a single line, and that is correct.

**When to split into per-agent virtual environments:** the first time you hit a
real version conflict, or when an agent needs something heavy and unrelated to the
others. Not before — splitting pre-emptively costs disk and setup time for a
problem you may never have. If you do split, no config change is needed: the root
`.gitignore` pattern `.venv/` has no leading slash, so it already matches a
`.venv` at any depth.

### `.env` — one credentials file for all agents

Lives at the repo root and is shared. ADK searches for `.env` by walking **up**
from the agent's folder to the filesystem root, so every agent finds it without
any per-agent copy.

Two authentication modes, selected by a single flag:

```
# Option A - API key, no SDK needed
GOOGLE_GENAI_USE_ENTERPRISE=0
GOOGLE_API_KEY=your-key-here

# Option B - Google Cloud project, needs gcloud
GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
```

Set to `1`, the client uses the Cloud path and **ignores `GOOGLE_API_KEY`
entirely**; set to `0`, it uses the key and ignores the project settings. All four
lines can coexist — flip the one character to switch. For Option B, also run
`gcloud auth application-default login` and
`gcloud auth application-default set-quota-project YOUR_PROJECT_ID`.

**Location matters:** Gemini 3.x models are served from the `global` endpoint on
Cloud. Verified 4 Aug 2026 — both `gemini-3.1-pro-preview` and the stable
`gemini-3.6-flash` return **404 NOT_FOUND** from `us-central1` and work from
`global`. This is not a preview-only restriction.

`.env` is gitignored and must never be committed. The root `.gitignore` pattern
has no leading slash, so it also protects a stray `some_agent/.env`.

### `.gitignore` — two levels, by scope

| File | Holds | Rule of thumb |
|---|---|---|
| `adk-agents/.gitignore` | `.env`, `.venv/`, `__pycache__/`, `*.pyc` | Would a brand-new, unrelated agent also need this line? |
| `<agent>/.gitignore` | That agent's own artefacts, e.g. `misc/`, `output/*.md` | Only meaningful for this agent |

Nested `.gitignore` files **combine** rather than override, so there is no
precedence puzzle — each rule applies to its own subtree. Note also that a
`.gitignore` can only ignore things *inside* its own folder: patterns never reach
upward, which is why `.env` and `.venv/` must be covered at the root.

To check whether a rule is actually firing:

```bash
git check-ignore -v path/to/file
```

It prints the file and line number that did the ignoring. Never use `git add -f`
on anything near a `.env`.

## Running an agent

From the repo root — **not** from inside an agent folder:

```bash
adk web
```

`adk web` needs the *parent* of the agent folders, so from here it finds them all;
from inside one it finds nothing. Pick the agent from the dropdown in the browser.

If `adk` is not on your PATH, either activate the environment first
(`.venv\Scripts\Activate.ps1`) or call it directly at
`.venv\Scripts\adk.exe web`.

## Adding a new agent

1. Create the folder, e.g. `energy_market/`.
2. Add `__init__.py` containing `from . import agent`.
3. Add `agent.py` exposing a `root_agent` variable.
4. Add `requirements.txt` listing only that agent's **direct** dependencies.
5. Install them into the shared environment:
   `.venv/Scripts/python -m pip install -r energy_market/requirements.txt`
6. Add a `<agent>/.gitignore` only if it has artefacts worth ignoring. Do not
   repeat `__pycache__/` — the root file already covers it.
7. Add a `README.md`, and a `CLAUDE.md` if the agent has non-obvious conventions.
8. **Add a row to the agents table at the top of this file.**
9. If the agent adapts an existing sample or project, credit it in that agent's
   own `README.md` — see the convention below.
10. Confirm discovery: run `adk web` and check the agent appears, or
    `curl -s http://127.0.0.1:8000/list-apps`.

## Credits

Some agents here are written from scratch; others start from a published sample.
Where one does, it credits its sources in its own `README.md`, so the attribution
stays next to the code it describes.

- **`industry_analysis/`** adapts Google's **Deep Search** sample (formerly
  *gemini-fullstack*) from
  [google/adk-samples](https://github.com/google/adk-samples/tree/main/python/agents/deep-search),
  Apache 2.0 — specifically its research-plan tag vocabulary and its
  outline → search → critique → refine → compose pipeline. See
  [that agent's README](industry_analysis/README.md#credit) for what was taken and
  what diverges.
