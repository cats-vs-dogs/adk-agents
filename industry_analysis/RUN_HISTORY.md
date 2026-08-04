# Run history and measurements

Raw measurements from the five live runs on 4–5 August 2026, extracted from
`.adk/session.db` before it was left behind on the original machine. Kept because
the conclusions in `CLAUDE.md` are only trustworthy if the numbers behind them
survive.

All runs: Cloud auth, `global` endpoint, `gemini-3.1-pro-preview` (critic) and
`gemini-3.6-flash` (worker). Costs use the rates in `config.py`; token counts are
exact, from the API.

## Summary

| # | Sector | Pipeline | Outcome | Rounds | Queries | In | Out | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | Tourism | original | failed 3/3 | hit cap | 48 | 161,867 | 99,096 | $1.16 |
| 2 | Transport | + query planner | failed 3/3 | hit cap | 72 | 198,429 | 124,055 | $1.42 |
| 3 | Construction | + purge prompts, cap 5 | failed 5/5 | hit cap | 75 | 283,853 | 172,256 | $1.97 |
| 4 | Construction | **append-only** | **passed** | 4 | 53 | 180,820 | 76,588 | $1.01 |
| 5 | Oil and gas | append-only | **passed** | 3 | 56 | 120,238 | 57,357 | $0.78 |

Report lengths: 3,770 / 4,048 / 5,070 / 2,987 / 2,258 words.

## Finding 1 — search volume must be measured as queries, not events

Run 1 showed only 3 events carrying `grounding_metadata`, which was initially read
as "the researcher barely searched". Wrong. Gemini's built-in `google_search`
issues **many queries inside a single model call**, so grounding events count model
calls, not searches. Run 1 had actually issued 48 queries.

Count `grounding_metadata.web_search_queries`. Counting events understates search
volume by roughly an order of magnitude and produced a wrong diagnosis.

## Finding 2 — pre-committing queries genuinely increases search depth

Adding `research_query_planner` (run 2) raised `section_researcher` from 12 to 33
queries, and the run total from 48 to 72, with grounding chunks 63 → 118. Cost rose
22%. The planner itself costs ~$0.03.

## Finding 3 — the refinement loop was generating fabrications, not removing them

The decisive measurement. In run 3 the executor was instructed to "return the
complete merged evidence base". Sizes of the evidence base it emitted, in
characters:

```
section_researcher        57,626
enhanced_search_executor  33,420   <- lost 42% of the researcher's work
enhanced_search_executor  35,891
enhanced_search_executor  40,630
enhanced_search_executor  45,948
enhanced_search_executor  48,710
```

It discarded 24,206 characters of real findings on its first pass, then regrew the
base each round by inventing figures to fill what it had lost.

The critic's five verdicts each named a **different** set of fabrications, none
repeating, comment lengths 807 → 965 → 876 → 1,033 → 905. Objections were not
converging; they were tracking freshly invented material. Raising
`max_search_iterations` 3 → 5 made this worse, because every extra round was
another rewrite.

No instruction fixes this: rewriting 20k tokens of findings *is* an act of
generation. Hence the append-only redesign.

## Finding 4 — append-only converges

| | Run 3 (rewrite) | Run 4 (append) | Run 5 (append) |
|---|---|---|---|
| Verdict lengths | 807, 965, 876, 1033, 905 | 881, 842, 665, **287** | 1082, 638, **321** |
| Result | failed at cap | **passed round 4** | **passed round 3** |
| Executor output tokens | 111,357 | 20,847 | 16,418 |
| Emitted per round (chars) | 33k–49k rewrites | 9,500 / 8,069 / 3,479 | 12,872 / 6,238 |
| Cost | $1.97 | $1.01 | $0.78 |

Objections now shrink monotonically. Run 4's passing verdict: *"previously
quarantined figures have either been successfully sourced or explicitly declared as
unavailable."* Executor output fell 81%.

**Quality and cost were not in tension.** The expensive runs were the ones failing
to converge.

## Finding 5 — fabrications reached delivered reports before the fix

In runs 1 and 2, figures the critic had explicitly named as unsupported appeared in
the final report carrying citation tags, indistinguishable from sourced numbers.
Run 2 shipped `€6.39bn`, `825,533 sq.m` and `€50.8m` after all three were flagged.

Detection without enforcement is not a control. Enforcement now lives in three
places, only the first of which is deterministic:

1. `finalize_report_callback` — banner whenever the final grade is not `pass`;
   fails closed on a missing grade.
2. `record_disputed_findings_callback` — every objection quarantined in state.
3. Prompt instructions telling the composer not to publish quarantined figures.

Run 5 verified the quarantine held: `132,000 tonnes` and the `240,000` figure,
flagged in round 2 and never sourced, are absent from the report. Figures that
*were* subsequently sourced (run 4's `€116,018m`, `42.3%`, `73.0%`) correctly
appear with NSI citations — quarantine bans an unsourced figure, sourcing lifts it.

## Finding 6 — the context-cache warning is immaterial

The `adk web` UI warns that system instructions changed between consecutive turns.
In a multi-agent pipeline consecutive calls come from *different agents*, so this
is unavoidable and expected. Measured in run 3: **5,984 cached tokens out of
283,853 input**, about 2%, all in `section_researcher`. Input is roughly $0.39 of a
$1.97 run, so perfect cache alignment would save single-digit cents. Ignore it.

## Open question

Passing reports are getting shorter — 2,987 then 2,258 words, against 4,000–5,000
for the failing runs. The evidence rules are working, and the long reports were
substantially padded with unsourced material. But the pipeline may now be
optimising for *passing review* rather than *being useful*, since the cheapest way
to satisfy the critic is to claim less.

This needs a human reading a report and judging whether it is substantive enough to
decide on. If it reads thin, raise research depth — the query floor above 24 in
`QUERY_PLANNER`, or more queries per section — rather than relaxing the evidence
standard, which is the only reason the figures can be trusted.

## Reproducing this analysis

`adk web` writes sessions to `industry_analysis/.adk/session.db` (SQLite,
gitignored). One JSON blob per event in the `events` table:

```python
import sqlite3, json
db = sqlite3.connect(".adk/session.db")
sid = list(db.execute("SELECT id FROM sessions ORDER BY update_time DESC"))[0][0]
for (data,) in db.execute("SELECT event_data FROM events WHERE session_id=?", (sid,)):
    e = json.loads(data)
    print(e.get("author"), e.get("usage_metadata"), len(
        (e.get("grounding_metadata") or {}).get("web_search_queries") or []))
```

Equal call counts for `research_evaluator` and `enhanced_search_executor` mean the
critic never passed and the loop exhausted `max_search_iterations`. A run that
converged shows one more evaluator call than executor calls.

Set `PYTHONIOENCODING=utf-8` before printing — search queries contain Cyrillic and
will crash a default Windows console codec.
