# GDIR Citation Formats Reference

This reference documents how GDIR integrates with the `grounded-citations` skill for citation management.

## Citation Ledger Location

The GDIR citation ledger is stored at:
```
$HERMES_HOME/cache/research/<session-id>/citations/ledger.json
```

## Integration Points

### 1. Source Registration (ACT Phase)

After each search/extract operation, register sources:

```bash
# From ACT phase results
python3 $HERMES_HOME/skills/research/grounded-citations/scripts/sources.py add \
  https://example.com/paper1 \
  https://example.com/paper2 \
  --title "Paper 1 Title" --title "Paper 2 Title"
```

### 2. Evidence Attachment (LEARN Phase)

Attach verbatim quotes for fact-checking:

```bash
python3 $HERMES_HOME/skills/research/grounded-citations/scripts/sources.py quote 1 \
  --text "Exact quote from the paper" \
  --from extracted_page.txt
```

### 3. Verification (VERIFY Phase)

Verify the deliverable before delivery:

```bash
python3 $HERMES_HOME/skills/research/grounded-citations/scripts/sources.py verify deliverable.md \
  --evidence --min-coverage 0.5
```

### 4. Sources Block Rendering (DONE Phase)

Render the final sources block:

```bash
python3 $HERMES_HOME/skills/research/grounded-citations/scripts/sources.py render \
  --style markdown --cited-in deliverable.md
```

## Workflow Integration

The GDIR loop with citations:

```
GOAL
→ PLAN: Determine strategies
→ ACT: Execute searches
  → Register sources with sources.py add
  → Extract content
  → Attach evidence with sources.py quote
→ EVALUATE: Assess results
→ LEARN: Diagnose failures
  → Note citation gaps
→ REPLAN: Choose new strategies
→ ... (repeat)
→ VERIFY: sources.py verify --evidence
→ DONE: sources.py render --cited-in deliverable.md
```

## Citation Style for GDIR Deliverables

Use the evidence render style for maximum verifiability:

```bash
sources.py render --style evidence --cited-in deliverable.md
```

This produces a Sources section with each source's URL and attached verbatim quotes.

## Automatic Citation ID Assignment

The `sources.py add` command assigns stable IDs:
- Same URL always gets same ID within a ledger
- IDs are reused across iterations for the same source
- This ensures consistent citation numbers in the deliverable

## Multi-Session Citation Sharing

To share citations across GDIR sessions or with subagents:

```bash
# Set shared ledger location
export HERMES_CITATION_LEDGER=/shared/path/ledger.json

# Or pass explicitly
sources.py --ledger /shared/path/ledger.json add <url>
```