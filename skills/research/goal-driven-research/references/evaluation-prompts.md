# Evaluation Prompts Reference

This reference documents the prompts used in the EVALUATE phase of the GDIR loop.

## Default Evaluation Prompt

Used when assessing if success criteria are met:

```
EVALUATION TASK:
Assess whether the collected research results satisfy the success criteria for the given goal.

GOAL: {goal}

SUCCESS CRITERIA:
{criteria_list}

COLLECTED RESULTS ({count} sources):
{results_summary}

INSTRUCTIONS:
For each success criterion, determine if it is:
- SATISFIED: Strong evidence from multiple sources
- PARTIALLY_SATISFIED: Some evidence but gaps remain
- NOT_SATISFIED: No or insufficient evidence

Also assess overall:
- COVERAGE: How comprehensively does the research address the goal?
- QUALITY: Are sources authoritative and recent?
- GAPS: What important aspects remain unaddressed?

OUTPUT FORMAT (JSON):
{
  "criteria_assessment": [
    {"criterion": "...", "status": "SATISFIED|PARTIALLY_SATISFIED|NOT_SATISFIED", "evidence": "...", "gaps": "..."}
  ],
  "overall": {
    "coverage_score": 0.0-1.0,
    "quality_score": 0.0-1.0,
    "gaps": ["...", "..."],
    "recommendation": "CONTINUE|COMPLETE"
  }
}
```

## Failure Diagnosis Prompt

Used in the LEARN phase to diagnose why a strategy failed:

```
FAILURE DIAGNOSIS TASK:
Analyze why the research strategy failed and extract actionable lessons.

FAILED STRATEGY: {strategy_name}
QUERIES TRIED: {queries}
RESULTS COUNT: {count}
ERROR/REASON: {failure_reason}

PREVIOUS LESSONS:
{previous_lessons}

INSTRUCTIONS:
1. Classify the failure type:
   - NO_RESULTS: Query returned nothing
   - IRRELEVANT_RESULTS: Results don't match goal
   - API_ERROR: Technical failure
   - PARSE_ERROR: Format/processing issue
   - CONFLICTING_INFO: Sources disagree
   - TIMEOUT: Too slow

2. Diagnose root cause:
   - Query formulation issue?
   - Strategy mismatch for goal?
   - Source limitations?
   - Technical issue?

3. Extract 1-3 actionable lessons for next iteration.

OUTPUT FORMAT (JSON):
{
  "failure_type": "...",
  "root_cause": "...",
  "lessons": ["...", "..."],
  "suggested_next_strategy": "...",
  "suggested_queries": ["...", "..."]
}
```

## Replanning Prompt

Used in the REPLAN phase to choose the next strategy:

```
REPLANNING TASK:
Choose the next research strategy based on all previous attempts.

GOAL: {goal}
SUCCESS_CRITERIA: {criteria}

STRATEGIES TRIED:
{strategies_summary}

LESSONS LEARNED:
{lessons}

AVAILABLE STRATEGIES:
- web_search: General web search
- arxiv_search: Academic papers (arXiv)
- web_extract: Deep content extraction
- semantic_scholar: Citation graphs, related papers
- blog_search: Industry blogs, tutorials

INSTRUCTIONS:
1. Identify which strategies haven't been tried yet
2. Based on lessons, which strategy is most promising?
3. Generate 1-3 specific queries for that strategy
4. Explain rationale

OUTPUT FORMAT (JSON):
{
  "next_strategy": "strategy_name",
  "queries": ["query1", "query2"],
  "rationale": "Why this strategy and these queries"
}
```

## Query Generation Prompt

Used to generate new queries based on lessons:

```
QUERY GENERATION TASK:
Generate improved search queries based on what we've learned.

GOAL: {goal}
LESSONS: {lessons}
PREVIOUS_QUERIES: {previous_queries}
STRATEGY: {strategy_name}

INSTRUCTIONS:
Generate 1-3 new queries that:
1. Address gaps identified in lessons
2. Use terminology discovered in previous results
3. Are appropriate for the target strategy
4. Avoid repeating failed queries

For web_search: Use natural language, include key terms
For arxiv_search: Use field prefixes (ti:, au:, abs:, cat:)
For semantic_scholar: Use keyword combinations

OUTPUT FORMAT (JSON):
{
  "queries": ["query1", "query2", "query3"]
}
```

## Configuration

Add to config.yaml to customize evaluation:

```yaml
gdir:
  evaluation_prompt: "path/to/custom_prompt.txt"
  failure_diagnosis_prompt: "path/to/custom_prompt.txt"
  replanning_prompt: "path/to/custom_prompt.txt"
  query_generation_prompt: "path/to/custom_prompt.txt"
```