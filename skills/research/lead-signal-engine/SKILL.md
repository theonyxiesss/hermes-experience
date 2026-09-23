---
name: lead-signal-engine
description: "Lead signal detection and qualification layer on GDIR."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Lead-Generation, Signal-Detection, Qualification, YouTube, Shorts]
    category: research
    related_skills: [goal-driven-research, youtube-public-lead-research, html_structured_extractor, verify_candidate]
    requires_toolsets: [terminal, web, file]
---

# Lead Signal Engine

Commercial reasoning layer that sits on top of the existing GDIR research pipeline. Transforms raw discovery into qualified leads by detecting commercial signals, qualifying them with evidence, and integrating with existing verification.

## When to Use

- Goal involves finding potential clients/leads for a service
- Need to distinguish between "interesting entity" and "qualified lead"
- Must avoid false positives and fabrication
- Need structured evidence trail for every qualification decision

## Architecture

```
GDIR (brain) → Discovery/Extraction (senses) → Lead Signal Engine (commercial reasoning) → Verification (evidence control)
```

Does NOT rewrite GDIR loop. Integrates as a strategy: `lead_signal_research`.

## Signal Taxonomy

### Intent Signals (strong evidence of immediate need)
- `hiring_editor`, `looking_for_editor`, `looking_for_shorts_editor`
- `looking_for_video_editor`, `looking_for_content_repurposing`
- `request_for_editor`, `request_for_clipping`

### Content Signals (medium evidence of content type)
- `frequent_long_form`, `podcast_content`, `interview_content`
- `educational_long_form`, `high_clip_potential`, `multiple_long_form_videos`

### Distribution Signals (requires explicit observation)
- `limited_shorts`, `inconsistent_shorts`, `no_observed_shorts`
- `active_long_form_weak_shorts` — only when explicitly observed

### Business Signals (requires pattern match in text)
- `active_business`, `creator_monetization`, `course_business`
- `agency_business`, `podcast_business`, `sponsorship_activity`
- `product_or_service`, `team_or_company`

### Contact Signals (strong when found)
- `public_email`, `contact_page`, `public_linkedin`, `public_x`, `public_website`

## Qualification Rules

### INTENT LEAD (QUALIFIED)
- ≥1 strong intent signal (hiring/editor/shorts)
- Confirmed identity/context

### OPPORTUNITY LEAD (QUALIFIED)
- ≥2 content signals AND ≥1 distribution signal (explicitly observed)
- AND ≥1 business signal OR contact signal

### POTENTIAL
- Some signals but insufficient for QUALIFIED
- Needs manual review or additional sources

### REJECTED / UNKNOWN
- Negative evidence (already has editor, signal expired, niche mismatch)
- No signals detected

## Anti-Confirmation-Bias Checks

For every potential lead, automatically check:
- Already has editing team?
- Already has Shorts operation?
- Signal may be expired (past tense)?
- Niche mismatch (gaming/beauty/fashion)?
- Signal belongs to different person?

## Evidence Requirements

Every signal must have:
```json
{
  "type": "signal_type",
  "strength": "strong|medium|weak",
  "source_url": "...",
  "evidence": "...",
  "method": "regex_match|observation|regex_extract",
  "verified": true
}
```

## Qualification States (separate from identity verification)

| Identity | Lead Status | Meaning |
|---|---|---|
| VERIFIED | QUALIFIED (INTENT) | Identity confirmed + strong intent signal |
| VERIFIED | QUALIFIED (OPPORTUNITY) | Identity confirmed + sufficient opportunity signals |
| VERIFIED | POTENTIAL | Identity confirmed, signals insufficient |
| PARTIAL | POTENTIAL | Identity unconfirmed, signals present |
| ANY | REJECTED | Negative evidence found |

## Integration

1. Discovery finds candidate
2. Enrichment searches public sources
3. SignalDetector extracts signals from text
4. LeadQualifier qualifies with strict rules
5. verify_candidate.py runs existing verification
6. GDIR evaluates → REPLAN or DONE

## Sources (priority order)
1. YouTube oEmbed / video pages
2. Personal/official website
2. Public X profile/posts
3. Public LinkedIn profile/posts
4. Reddit posts/comments
5. Patreon
6. Podbean
6. Public job/contact pages

## Files

- `scripts/lead_signal_engine.py` — main engine (SignalDetector, LeadQualifier, LeadSignalEngine)
- `scripts/html_structured_extractor.py` — updated 4-status extractor
- `scripts/verify_candidate.py` — existing verification pipeline
- `scripts/youtube_public_lead_research.py` — discovery strategy
- `references/end-to-end-test-2026-09-19.md` — session transcript

## Real Test Results (2026-09-19)

- Target: 10
- Found: 5 POTENTIAL (0 QUALIFIED)
- VERIFIED identity: 2, PARTIAL: 1
- Signals: 20 (all real regex/observation)
- Fabricated: 0
- Main bottleneck: Public YouTube/Google lack structured intent/business signals

## Anti-Fabrication Guarantees

- No invented names, metrics, contacts, URLs
- UNKNOWN used instead of invented identity
- FAILURE documented when source unavailable
- PARTIAL never promoted to VERIFIED without independent structured source
- All evidence tied to source URL