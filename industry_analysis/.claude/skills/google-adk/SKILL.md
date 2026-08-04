---
name: google-adk
description: Working reference for building agents with Google ADK 2.x in Python - verified import paths, agent types, session state and instruction templating, loop escalation, callbacks, and the constraints that cause most runtime errors. Use when writing, debugging or extending any ADK agent in this repo.
---

# Google ADK 2.x

Everything here was verified against **google-adk 2.6.2 / Python 3.12** by
introspecting the installed package, not copied from tutorials.

## First rule: ADK 2.x is not 1.x

ADK 2.0 replaced the hierarchical agent executor with a **graph-based workflow
runtime**. `LlmAgent`, `SequentialAgent`, `LoopAgent` and `BaseAgent` all still
work, but agents, tools and functions are now evaluated as nodes in a workflow
graph, and the event and session schemas changed.

Most ADK material online is 1.x. **Do not trust a blog post over the installed
package.** When unsure, introspect:

```bash
.venv/Scripts/python -c "from google.adk.agents import LlmAgent; print(sorted(LlmAgent.model_fields))"
```

Agents are Pydantic models, so `model_fields` is the authoritative list of what
you can pass. Same trick works for `Event`, `EventActions` and `Session`.

## Verified imports

```python
from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.planners import BuiltInPlanner
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types
```

## Choosing an agent type

| Need | Use |
|---|---|
| Model reasoning, tool calls, talking to the user | `LlmAgent` |
| Fixed A -> B -> C order | `SequentialAgent` |
| Repeat until good enough | `LoopAgent` |
| Plain Python control flow, no model call | `BaseAgent` subclass |
| Run one agent as a callable tool of another | `AgentTool(agent)` |

`sub_agents` on an `LlmAgent` means *the model may hand off to them*. `sub_agents`
on a `SequentialAgent`/`LoopAgent` means *they run in this order*. Mixing these
mental models is the most common design error.

## Session state is how agents talk

`output_key="foo"` writes an agent's final output to `state["foo"]`. Downstream
agents read it through **instruction templating**:

```python
instruction = "Review this evidence:\n{section_research_findings?}"
```

- `{key}` — raises `KeyError` if missing.
- `{key?}` — renders empty string if missing. **Prefer this**; it makes an agent
  survive being run before its input exists.
- `{artifact.name}` — loads an artifact instead of state.
- Anything that is not a valid state name is left untouched, so ordinary prose
  braces are safe.

Set `include_contents="none"` on an agent that should work purely from injected
state rather than conversation history. If you do, **every input it needs must be
a placeholder** — otherwise it sees nothing. This is the usual cause of an agent
that inexplicably ignores its input.

Because instructions are f-strings in this repo, write placeholder blocks as a
concatenated plain string so the braces survive:

```python
PROMPT = f"""...{SHARED_BLOCK}...""" + """
## Input
{some_state_key?}
"""
```

## Breaking a LoopAgent

A `LoopAgent` stops at `max_iterations`, or when a sub-agent escalates. Escalation
is a plain `BaseAgent` that inspects state and emits an event:

```python
class EscalationChecker(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        if (ctx.session.state.get("evaluation") or {}).get("grade") == "pass":
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            yield Event(author=self.name)
```

Note it is a generator that must yield an event on **both** paths — yielding
nothing stalls the loop. `_run_async_impl(self, ctx: InvocationContext)` is the
correct signature; access state via `ctx.session.state`.

Place the checker **between** the evaluator and the fixer, so a passing grade
skips the fixer entirely.

## Callbacks

```python
Callable[[CallbackContext], Optional[types.Content]]
```

Sync or async both work. Returning `Content` **replaces** the agent's output —
that is how you post-process a report. Returning `None` leaves it alone.

Useful `CallbackContext` members (all public in 2.x — do not reach for private
attributes as older samples do):

- `.state` — read and write session state
- `.session.events` — the full event list; `event.grounding_metadata` carries
  search results as `.grounding_chunks[i].web.uri / .title / .domain`
- `.agent_name`, `.invocation_id`, `.save_artifact()`, `.load_artifact()`

Callbacks are the right place for deterministic post-processing (rewriting
citations, saving files). They avoid the built-in-tool constraint below.

## Constraints that cause runtime errors

1. **`output_schema` excludes tools and handoff.** An agent with a Pydantic
   `output_schema` cannot have `tools`, and should set
   `disallow_transfer_to_parent=True` / `disallow_transfer_to_peers=True`.
   Instruct it to emit raw JSON with no markdown fence.
2. **A built-in tool cannot be combined with custom function tools** on the same
   agent. `google_search` is built-in. Need both? Split into two agents, or move
   the deterministic part into a callback.
3. **Grounding metadata only exists on events from agents that actually
   searched.** Harvest it in that agent's `after_agent_callback`, not later.
4. **Structured output arrives as a dict**, not the Pydantic object, when read
   back from state.

## Environment

```
GOOGLE_GENAI_USE_ENTERPRISE=1        # current name; was GOOGLE_GENAI_USE_VERTEXAI
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=us-central1
```

Setting both the old and new flag to conflicting values raises `ValueError`.
Enterprise mode needs Application Default Credentials —
`gcloud auth application-default login`. Without it you get
`DefaultCredentialsError` at the first model call, not at import.

ADK searches for `.env` by walking **up to the filesystem root** from the agent
folder, so a `.env` in a parent directory is found.

## Running

```bash
adk web
```

Run from the **parent** of the agent folder. Each subdirectory containing
`__init__.py` and `agent.py` is one agent; `agent.py` must expose `root_agent`,
and `__init__.py` must do `from . import agent`.

Check discovery without opening a browser:

```bash
curl -s http://127.0.0.1:8000/list-apps
```

## Models

Model IDs move fast. Check what a project can actually see rather than trusting a
constant:

```bash
.venv/Scripts/python -c "from google import genai; [print(m.name) for m in genai.Client().models.list() if 'gemini' in m.name]"
```

As of August 2026: `gemini-3.1-pro-preview` for reasoning, `gemini-3.6-flash` for
volume work. **Gemini 2.5 shuts down October 2026** — do not adopt it.

Keep model IDs in one config module so a rename is a one-line change.
