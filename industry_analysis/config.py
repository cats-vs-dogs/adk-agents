"""Configuration for the industry analysis agent.

Everything tunable lives here: model choice, how hard the research loop tries,
and the default market. Nothing else in the project hardcodes these.
"""

import dataclasses
import pathlib


@dataclasses.dataclass
class ResearchConfiguration:
    """Tunable settings for the research pipeline.

    Attributes:
        critic_model: Model for judgment work - planning, critique, composition.
        worker_model: Model for high-volume search legwork.
        max_search_iterations: Hard cap on refinement rounds. The loop normally
            exits earlier, as soon as the critic grades the evidence 'pass'.
        default_market: Market analysed when the user does not name one.
        output_dir: Where finished reports are written.
    """

    # Verified against the Gemini API changelog on 4 Aug 2026:
    #   gemini-3.1-pro-preview  - latest Pro (preview since Feb 2026); this is
    #                             also what Google's own deep-search ADK sample
    #                             currently uses.
    #   gemini-3.6-flash        - latest stable Flash (released 21 Jul 2026).
    # Do not move to a Gemini 2.5 model: that generation shuts down Oct 2026.
    critic_model: str = "gemini-3.1-pro-preview"
    worker_model: str = "gemini-3.6-flash"

    # 3 rather than the sample's 5, to keep prototype runs affordable.
    max_search_iterations: int = 3

    default_market: str = "Bulgaria"

    output_dir: pathlib.Path = pathlib.Path(__file__).parent / "output"


config = ResearchConfiguration()


# USD per 1M tokens, used for the run-cost estimate shown after each report.
# Checked against the Gemini pricing page on 4 Aug 2026 - update when it moves.
# Caveat: the Pro tier charges more for prompts over 200k tokens ($4/$18) than
# the rates below, so a very large run is under-estimated rather than over.
MODEL_PRICING = {
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50},
}

# Grounded search is billed per request beyond a monthly allowance shared across
# all Gemini 3.x models. Reported separately from token cost, because whether it
# actually costs anything depends on the whole month's usage, not this one run.
SEARCH_FREE_REQUESTS_PER_MONTH = 5_000
SEARCH_COST_PER_1K_REQUESTS = 14.00
