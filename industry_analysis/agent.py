"""Industry Analysis and Economic Research agent.

Flow:

    user request
      -> interactive_planner_agent   drafts a tagged plan, waits for approval
      -> research_pipeline           autonomous, only after explicit approval
           section_planner               -> report outline
           section_researcher            -> evidence base
           iterative_refinement_loop
               research_evaluator        -> pass / fail + follow-up queries
               EscalationChecker         -> breaks the loop on 'pass'
               enhanced_search_executor  -> closes the gaps
           report_composer               -> cited report, also saved to output/

Session state keys used across the pipeline:
    research_plan             the approved, tagged plan
    report_sections           the report outline
    section_research_findings the evidence base (rewritten each refinement round)
    research_evaluation       the critic's structured verdict
    sources                   {src-N: {url, title, domain}} harvested from search
    citation_sources          the same, rendered for the composer to cite from
    final_cited_report        the finished report

All instructions live in prompts.py; all tunables live in config.py.
"""

import datetime
import logging
import pathlib
import re
from collections.abc import AsyncGenerator
from typing import Literal, Optional

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.llm_response import LlmResponse
from google.adk.planners import BuiltInPlanner
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from . import prompts
from .config import (
    MODEL_PRICING,
    SEARCH_COST_PER_1K_REQUESTS,
    SEARCH_FREE_REQUESTS_PER_MONTH,
    config,
)

logger = logging.getLogger(__name__)

# Matches <cite source="src-1"/> and the variants models actually emit: single or
# double quotes, with or without the self-closing slash, and the paired
# <cite ...></cite> form. Leading whitespace is consumed so the replacement can
# supply exactly one space instead of doubling it.
_CITE_PATTERN = re.compile(
    r"""[ \t]*<cite\s+source\s*=\s*["'](src-\d+)["']\s*/?>(?:\s*</cite>)?"""
)


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


class SearchQuery(BaseModel):
    """A follow-up web search query aimed at a specific evidence gap."""

    search_query: str = Field(
        description="A targeted query naming the metric, institution and period."
    )


class Feedback(BaseModel):
    """The critic's verdict on the evidence base."""

    grade: Literal["pass", "fail"] = Field(
        description="'pass' if the evidence meets the standard, else 'fail'."
    )
    comment: str = Field(
        description="Specific critique naming the section and the missing quantity."
    )
    follow_up_queries: Optional[list[SearchQuery]] = Field(
        default=None, description="Queries that would close the gaps. Omit on pass."
    )


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


def track_model_usage_callback(
    callback_context: Context, llm_response: LlmResponse
) -> None:
    """Accumulate token usage per agent after every model call.

    Attached to all LlmAgents. Returning None leaves the response untouched -
    this callback only observes.

    Thinking tokens are billed as output, so they are counted there rather than
    reported separately.
    """
    usage = getattr(llm_response, "usage_metadata", None)
    if not usage:
        return None

    agent = callback_context.agent_name
    totals: dict = callback_context.state.get("token_usage", {})
    entry = totals.setdefault(
        agent, {"model": "", "input": 0, "output": 0, "calls": 0}
    )

    entry["model"] = llm_response.model_version or entry["model"]
    entry["input"] += usage.prompt_token_count or 0
    entry["output"] += (usage.candidates_token_count or 0) + (
        usage.thoughts_token_count or 0
    )
    entry["calls"] += 1

    callback_context.state["token_usage"] = totals

    cost = _agent_cost(entry)
    logger.info(
        "[cost] %-26s call %-2d | in %7d | out %6d | running $%.4f",
        agent,
        entry["calls"],
        entry["input"],
        entry["output"],
        cost,
    )
    return None


def _price_for(model: str) -> dict:
    """Pricing for a model id, tolerating version suffixes and unknown models."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    for known, prices in MODEL_PRICING.items():
        if model.startswith(known) or known.startswith(model):
            return prices
    return {"input": 0.0, "output": 0.0}


def _agent_cost(entry: dict) -> float:
    prices = _price_for(entry.get("model", ""))
    return (
        entry["input"] * prices["input"] + entry["output"] * prices["output"]
    ) / 1_000_000


def _count_search_requests(callback_context: CallbackContext) -> int:
    """Grounded search calls in this session, for the separate search charge."""
    return sum(
        1
        for event in callback_context.session.events
        if event.grounding_metadata and event.grounding_metadata.grounding_chunks
    )


def format_cost_report(callback_context: CallbackContext) -> str:
    """Markdown cost breakdown with a bar chart, ordered most expensive first."""
    totals: dict = callback_context.state.get("token_usage", {})
    if not totals:
        return ""

    rows = sorted(
        ((name, e, _agent_cost(e)) for name, e in totals.items()),
        key=lambda r: r[2],
        reverse=True,
    )
    grand_total = sum(cost for _, _, cost in rows)
    peak = max((cost for _, _, cost in rows), default=0.0)

    lines = [
        "## Run cost estimate",
        "",
        "| Agent | Model | Calls | Input | Output | Cost | Share |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for name, entry, cost in rows:
        bar = "#" * max(1, round((cost / peak) * 18)) if peak else ""
        share = (cost / grand_total * 100) if grand_total else 0
        model = entry.get("model") or "?"
        lines.append(
            f"| {name} | `{model}` | {entry['calls']} | "
            f"{entry['input']:,} | {entry['output']:,} | "
            f"${cost:.4f} | `{bar}` {share:.0f}% |"
        )

    total_in = sum(e["input"] for _, e, _ in rows)
    total_out = sum(e["output"] for _, e, _ in rows)
    lines.append(
        f"| **Total** | | | **{total_in:,}** | **{total_out:,}** | "
        f"**${grand_total:.4f}** | |"
    )

    searches = _count_search_requests(callback_context)
    search_cost = searches / 1000 * SEARCH_COST_PER_1K_REQUESTS
    lines += [
        "",
        f"Grounded search: **{searches} requests**. The first "
        f"{SEARCH_FREE_REQUESTS_PER_MONTH:,}/month are free across all Gemini 3.x "
        f"models, so these cost **$0** unless that allowance is already spent - "
        f"beyond it they would add ${search_cost:.2f} "
        f"(${SEARCH_COST_PER_1K_REQUESTS:.0f} per 1,000).",
        "",
        "*Token counts are exact, reported by the API. Prices are from "
        "`config.py` and may drift - treat the dollar figures as an estimate.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


def collect_research_sources_callback(callback_context: CallbackContext) -> None:
    """Harvest grounded search results into state as stable src-N ids.

    Runs after each searching agent. Sources accumulate across refinement rounds,
    deduplicated by URL, so ids stay stable once assigned and the composer can
    cite anything found at any point in the run.
    """
    sources: dict = callback_context.state.get("sources", {})
    seen_urls = {entry["url"] for entry in sources.values()}
    next_id = len(sources) + 1

    for event in callback_context.session.events:
        metadata = event.grounding_metadata
        if not metadata or not metadata.grounding_chunks:
            continue

        for chunk in metadata.grounding_chunks:
            web = getattr(chunk, "web", None)
            url = getattr(web, "uri", None)
            if not url or url in seen_urls:
                continue

            domain = getattr(web, "domain", "") or ""
            sources[f"src-{next_id}"] = {
                "url": url,
                "title": getattr(web, "title", None) or domain or url,
                "domain": domain,
            }
            seen_urls.add(url)
            next_id += 1

    callback_context.state["sources"] = sources
    # Rendered form, injected into the composer's instruction so it only ever
    # cites ids that actually exist.
    callback_context.state["citation_sources"] = "\n".join(
        f"- {sid}: {entry['title']} ({entry['domain'] or entry['url']})"
        for sid, entry in _sorted_sources(sources)
    )
    logger.info("Collected %d unique sources so far.", len(sources))


def finalize_report_callback(
    callback_context: CallbackContext,
) -> Optional[genai_types.Content]:
    """Turn citation tags into links, save the report, and return the final text.

    Doing the save here rather than in a tool keeps the agent graph unchanged and
    sidesteps ADK's rule that an agent using a built-in tool cannot also carry
    custom function tools.
    """
    report: str = callback_context.state.get("final_cited_report", "")
    if not report:
        logger.warning("No report found in state; nothing to finalize.")
        return None

    sources: dict = callback_context.state.get("sources", {})
    used: dict = {}

    def _link(match: re.Match) -> str:
        source_id = match.group(1)
        entry = sources.get(source_id)
        if not entry:
            # Hallucinated id - drop the tag rather than emit a broken link.
            logger.warning("Report cited unknown source %s; dropping.", source_id)
            return ""
        used[source_id] = entry
        return f" ([{entry['title']}]({entry['url']}))"

    report = _CITE_PATTERN.sub(_link, report)
    report = re.sub(r"[ \t]+([.,;:])", r"\1", report)  # tidy space before punctuation
    report = re.sub(r"</?cite[^>]*>", "", report)  # sweep up any malformed leftovers

    cost_report = format_cost_report(callback_context)

    # The saved file gets the report plus sources; the cost block goes in too,
    # so a report on disk always carries what it cost to produce.
    saved_path = _save_report(report, used, cost_report)

    if cost_report:
        report += "\n\n---\n\n" + cost_report
    if saved_path:
        report += f"\n\n*Saved to `{saved_path.name}`*"

    callback_context.state["final_cited_report"] = report
    return genai_types.Content(parts=[genai_types.Part(text=report)])


# ---------------------------------------------------------------------------
# Report saving
# ---------------------------------------------------------------------------


def _sorted_sources(sources: dict) -> list:
    """Sources ordered by their numeric id rather than lexically."""
    return sorted(sources.items(), key=lambda kv: int(kv[0].split("-")[1]))


def _slug_from_report(report: str) -> str:
    """Filename slug taken from the report's H1, falling back to a generic name."""
    match = re.search(r"^#\s+(.+)$", report, re.MULTILINE)
    title = match.group(1) if match else "industry-analysis"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "industry-analysis"


def _save_report(
    report: str, used_sources: dict, cost_report: str = ""
) -> Optional[pathlib.Path]:
    """Write the report plus a sources appendix to output/, never overwriting."""
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)

        stem = f"{datetime.date.today():%Y-%m-%d}_{_slug_from_report(report)}"
        path = config.output_dir / f"{stem}.md"
        suffix = 2
        while path.exists():  # keep earlier runs of the same sector on the same day
            path = config.output_dir / f"{stem}_{suffix}.md"
            suffix += 1

        body = [report]
        if used_sources:
            body += ["", "---", "", "## Sources", ""]
            body += [
                f"- {sid}: [{entry['title']}]({entry['url']})"
                for sid, entry in _sorted_sources(used_sources)
            ]
        if cost_report:
            body += ["", "---", "", cost_report]

        path.write_text("\n".join(body), encoding="utf-8")
        logger.info("Report saved to %s", path)
        return path
    except OSError:
        # A failed save must not lose the report - it is still returned to chat.
        logger.exception("Could not save report to %s", config.output_dir)
        return None


# ---------------------------------------------------------------------------
# Custom agent
# ---------------------------------------------------------------------------


class EscalationChecker(BaseAgent):
    """Stops the refinement loop as soon as the critic grades the evidence 'pass'."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        evaluation = ctx.session.state.get("research_evaluation") or {}
        grade = evaluation.get("grade")

        if grade == "pass":
            logger.info("Evidence graded 'pass' - ending refinement loop.")
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            logger.info("Evidence graded '%s' - refining further.", grade)
            yield Event(author=self.name)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

plan_generator = LlmAgent(
    name="plan_generator",
    model=config.worker_model,
    description="Drafts and revises the tagged research plan the user approves.",
    instruction=prompts.PLAN_GENERATOR,
    tools=[google_search],
    after_model_callback=track_model_usage_callback,
)

section_planner = LlmAgent(
    name="section_planner",
    model=config.worker_model,
    description="Turns the approved plan into a report outline.",
    instruction=prompts.SECTION_PLANNER,
    output_key="report_sections",
    after_model_callback=track_model_usage_callback,
)

section_researcher = LlmAgent(
    name="section_researcher",
    model=config.worker_model,
    description="Gathers the sourced evidence the report will be written from.",
    instruction=prompts.SECTION_RESEARCHER,
    planner=BuiltInPlanner(
        thinking_config=genai_types.ThinkingConfig(include_thoughts=True)
    ),
    tools=[google_search],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
    after_model_callback=track_model_usage_callback,
)

research_evaluator = LlmAgent(
    name="research_evaluator",
    model=config.critic_model,
    description="Peer-reviews the evidence base and grades it pass or fail.",
    instruction=prompts.RESEARCH_EVALUATOR,
    # An agent with output_schema cannot carry tools or hand off - keep it that way.
    output_schema=Feedback,
    output_key="research_evaluation",
    include_contents="none",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    after_model_callback=track_model_usage_callback,
)

enhanced_search_executor = LlmAgent(
    name="enhanced_search_executor",
    model=config.worker_model,
    description="Closes the gaps the reviewer identified and re-emits the evidence base.",
    instruction=prompts.ENHANCED_SEARCH_EXECUTOR,
    tools=[google_search],
    output_key="section_research_findings",
    include_contents="none",
    after_agent_callback=collect_research_sources_callback,
    after_model_callback=track_model_usage_callback,
)

report_composer = LlmAgent(
    name="report_composer",
    model=config.critic_model,
    description="Writes the final cited report from the verified evidence base.",
    instruction=prompts.REPORT_COMPOSER,
    output_key="final_cited_report",
    include_contents="none",
    after_agent_callback=finalize_report_callback,
    after_model_callback=track_model_usage_callback,
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    description=(
        "Executes an approved research plan: outlines the report, gathers and "
        "refines evidence under review, then composes the final cited report."
    ),
    sub_agents=[
        section_planner,
        section_researcher,
        LoopAgent(
            name="iterative_refinement_loop",
            max_iterations=config.max_search_iterations,
            sub_agents=[
                research_evaluator,
                EscalationChecker(name="escalation_checker"),
                enhanced_search_executor,
            ],
        ),
        report_composer,
    ],
)

interactive_planner_agent = LlmAgent(
    name="interactive_planner_agent",
    model=config.critic_model,
    description=(
        "Industry analysis assistant. Agrees a research plan with the user, then "
        "hands it to the research pipeline once they approve it."
    ),
    instruction=prompts.INTERACTIVE_PLANNER,
    tools=[AgentTool(plan_generator)],
    sub_agents=[research_pipeline],
    output_key="research_plan",
    after_model_callback=track_model_usage_callback,
)

root_agent = interactive_planner_agent
