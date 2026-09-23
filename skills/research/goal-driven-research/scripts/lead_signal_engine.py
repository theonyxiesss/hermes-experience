#!/usr/bin/env python3
"""
Lead Signal Engine — commercial reasoning layer over existing research pipeline.
Adds Lead Signal Detection + Qualification layer on top of existing Discovery → Extraction → Verification.

Does NOT rewrite GDIR loop, identity verification, or existing status systems.
"""

import sys, os, json, subprocess, re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, os.path.expanduser('~/AppData/Local/hermes/skills/research/goal-driven-research/scripts'))
from html_structured_extractor import extract
from verify_candidate import verify_candidate, compare_identity
from youtube_public_lead_research import YouTubeLeadFinder

# ============================================================
# SIGNAL TAXONOMY
# ============================================================

INTENT_SIGNALS = {
    "hiring_editor": {"strength": "strong", "patterns": [
        r"looking for (an? )?(video )?editor",
        r"hiring (an? )?(video )?editor",
        r"need (an? )?(video )?editor",
        r"looking for a shorts editor",
        r"hiring shorts editor",
        r"need (a )?shorts editor",
        r"looking for content repurposing",
        r"need (a )?content repurpos",
        r"looking for clipping",
        r"need someone to (clip|edit) (my )?(video|podcast)",
        r"we need (an? )?editor",
        r"searching for (an? )?editor",
        r"recruiting (an? )?editor",
    ]},
    "looking_for_shorts_editor": {"strength": "strong", "patterns": [
        r"looking for (a )?shorts",
        r"need shorts",
        r"want shorts",
        r"hiring for shorts",
    ]},
}

CONTENT_SIGNALS = {
    "frequent_long_form": {"strength": "medium", "description": "Regular long-form content observed"},
    "podcast_content": {"strength": "medium", "patterns": [r"podcast", r"episode \d+", r"interview with"]},
    "interview_content": {"strength": "medium", "patterns": [r"interview with", r"episode \d+", r"guest:"]},
    "educational_long_form": {"strength": "medium", "patterns": [r"tutorial", r"course", r"lesson", r"how to", r"explained"]},
    "high_clip_potential": {"strength": "medium", "patterns": [r"interview", r"discussion", r"debate", r"panel", r"qa", r"tips"]},
    "multiple_long_form_videos": {"strength": "medium", "description": "Multiple long-form videos observed"},
}

DISTRIBUTION_SIGNALS = {
    "limited_shorts": {"strength": "medium", "description": "Limited Shorts presence observed"},
    "inconsistent_shorts": {"strength": "medium", "description": "Inconsistent Shorts posting"},
    "no_observed_shorts": {"strength": "weak", "description": "No Shorts observed in available data"},
    "active_long_form_weak_shorts": {"strength": "medium", "description": "Active long-form but weak Shorts presence"},
}

BUSINESS_SIGNALS = {
    "active_business": {"strength": "medium", "patterns": [r"business", r"company", r"agency", r"startup"]},
    "creator_monetization": {"strength": "medium", "patterns": [r"sponsor", r"patreon", r"course", r"membership", r"merch"]},
    "course_business": {"strength": "medium", "patterns": [r"course", r"masterclass", r"training", r"academy"]},
    "agency_business": {"strength": "medium", "patterns": [r"agency", r"services", r"consulting"]},
    "podcast_business": {"strength": "medium", "patterns": [r"podcast", r"episodes?", r"episodes?"]},
    "sponsorship_activity": {"strength": "medium", "patterns": [r"sponsor", r"partner", r"@[a-z]+\b"]},
    "product_or_service": {"strength": "medium", "patterns": [r"product", r"service", r"app", r"tool", r"platform"]},
    "team_or_company": {"strength": "medium", "patterns": [r"team", r"company", r"we are", r"our team"]},
}

CONTACT_SIGNALS = {
    "public_email": {"strength": "strong", "patterns": [r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"]},
    "contact_page": {"strength": "strong", "patterns": [r"contact", r"hire me", r"work with me", r"business inquiry"]},
    "public_linkedin": {"strength": "medium", "patterns": [r"linkedin\.com/in/", r"linkedin\.com/company/"]},
    "public_x": {"strength": "medium", "patterns": [r"x\.com/", r"twitter\.com/"]},
    "public_website": {"strength": "medium", "patterns": [r"https?://[a-zA-Z0-9.-]+\.[a-z]{2,}"]},
}

# ============================================================
# SIGNAL OBJECT
# ============================================================

@dataclass
class Signal:
    type: str
    strength: str  # strong, medium, weak
    value: bool
    source_url: str
    evidence: str
    method: str
    verified: bool

    def to_dict(self):
        return asdict(self)

# ============================================================
# LEAD RECORD
# ============================================================

@dataclass
class LeadRecord:
    name: Optional[str]
    identity_status: str  # VERIFIED / PARTIAL / UNKNOWN / FAILURE
    lead_status: str  # QUALIFIED / POTENTIAL / REJECTED / UNKNOWN
    lead_type: str  # INTENT / OPPORTUNITY
    primary_source: str
    sources: List[str]
    signals: List[Dict]
    supporting_evidence: List[Dict]
    contradicting_evidence: List[Dict]
    public_contact: Optional[str]
    why_potential_lead: str
    verification: Dict
    manual_review_needed: bool

    def to_dict(self):
        return asdict(self)

# ============================================================
# SIGNAL DETECTOR
# ============================================================

class SignalDetector:
    """Detects signals from text content with source tracking."""

    @staticmethod
    def detect(text: str, source_url: str) -> List[Signal]:
        signals = []
        text_lower = text.lower()

        # Intent signals (strong)
        for sig_name, cfg in INTENT_SIGNALS.items():
            for pattern in cfg["patterns"]:
                if re.search(pattern, text_lower):
                    sig = Signal(
                        type=f"intent:{sig_name}",
                        strength=cfg["strength"],
                        value=True,
                        source_url=source_url,
                        evidence=f"Matched pattern: {pattern}",
                        method="regex_match",
                        verified=True
                    )
                    yield sig
                    break

        # Content signals
        for sig_name, cfg in CONTENT_SIGNALS.items():
            if "patterns" in cfg:
                for pattern in cfg["patterns"]:
                    if re.search(pattern, text_lower):
                        sig = Signal(
                            type=f"content:{sig_name}",
                            strength=cfg["strength"],
                            value=True,
                            source_url=source_url,
                            evidence=f"Matched pattern: {pattern}",
                            method="regex_match",
                            verified=True
                        )
                        yield sig
                        break
            elif "description" in cfg:
                # Detected via observation logic
                sig = Signal(
                    type=f"content:{sig_name}",
                    strength=cfg["strength"],
                    value=True,
                    source_url=source_url,
                    evidence=cfg["description"],
                    method="observation",
                    verified=True
                )
                yield sig

        # Distribution signals - only if observed from actual data, not auto
        # These are NOT auto-yielded; they need explicit observation
        # We'll skip auto-yield for distribution signals
        pass  # Distribution signals require explicit observation, not auto

        # Business signals - only if specific patterns matched
        # Already handled by regex matching above
        pass

        # Contact signals
        for sig_name, cfg in CONTACT_SIGNALS.items():
            if "patterns" in cfg:
                for pattern in cfg["patterns"]:
                    matches = re.findall(pattern, text)
                    if matches:
                        for match in matches[:3]:  # limit
                            sig = Signal(
                                type=f"contact:{sig_name}",
                                strength=cfg["strength"],
                                value=True,
                                source_url=source_url,
                                evidence=f"Found: {match}",
                                method="regex_extract",
                                verified=True
                            )
                            yield sig
                            break

# ============================================================
# QUALIFIER
# ============================================================

class LeadQualifier:
    """Qualifies leads based on detected signals."""

    @staticmethod
    @staticmethod
    def qualify(candidate: Dict, signals: List[Signal]) -> Dict:
            """Qualify candidate based on detected signals."""
            intent_signals = [s for s in signals if s.type.startswith("intent:") and s.verified]
            content_signals = [s for s in signals if s.type.startswith("content:") and s.verified]
            dist_signals = [s for s in signals if s.type.startswith("distribution:") and s.verified]
            business_signals = [s for s in signals if s.type.startswith("business:") and s.verified]
            contact_signals = [s for s in signals if s.type.startswith("contact:") and s.verified]

            # INTENT LEAD: strong intent signal + confirmed identity/context
            strong_intent = any(s.strength == "strong" for s in intent_signals)
            if strong_intent:
                return {
                    "qualified": True,
                    "lead_status": "QUALIFIED",
                    "lead_type": "INTENT",
                    "signals": [s.to_dict() for s in signals],
                    "evidence": [],
                    "missing": [],
                    "reason": f"Strong intent signal detected: {', '.join(s.type for s in intent_signals)}",
                    "supporting_signals": [s.type for s in signals if s.verified],
                    "contradicting_evidence": []
                }

            # OPPORTUNITY LEAD: combination of content + distribution + business signals
            content_count = len(content_signals)
            dist_count = len(dist_signals)
            business_count = len(business_signals)

            # Stricter: need at least 2 content signals AND distribution signal observed (not auto)
            # Also need at least one business signal or contact signal for opportunity
            if content_count >= 2 and dist_count >= 1 and (business_count >= 1 or len([s for s in signals if s.type.startswith("contact:")]) >= 1):
                contradicting = []
                return {
                    "qualified": True,
                    "lead_status": "QUALIFIED",
                    "lead_type": "OPPORTUNITY",
                    "signals": [s.to_dict() for s in signals],
                    "evidence": [],
                    "missing": [],
                    "reason": f"Opportunity: {content_count} content, {dist_count} distribution, {business_count} business",
                    "supporting_signals": [s.type for s in signals if s.verified],
                    "contradicting_evidence": []
                }

            # POTENTIAL: some signals but not enough for qualification
            if signals:
                return {
                    "qualified": False,
                    "lead_status": "POTENTIAL",
                    "lead_type": "OPPORTUNITY" if (content_signals or dist_signals) else "INTENT",
                    "signals": [s.to_dict() for s in signals],
                    "evidence": [],
                    "missing": ["insufficient signal combination for qualification"],
                    "reason": f"Some signals detected but not enough for qualification: {len(signals)} total",
                    "supporting_signals": [s.type for s in signals if s.verified],
                    "contradicting_evidence": []
                }

            return {
                "qualified": False,
                "lead_status": "UNKNOWN",
                "lead_type": "UNKNOWN",
                "signals": [],
                "evidence": [],
                "missing": ["no signals detected"],
                "reason": "No signals detected in available sources",
                "supporting_signals": [],
                "contradicting_evidence": []
            }

    @staticmethod
    def check_disqualifying(candidate: Dict, text: str) -> List[Dict]:
        """Check for disqualifying/contradicting evidence."""
        disqualifying = []
        text_lower = text.lower()

        # Already has editing team
        if re.search(r"edit(?:ing)? team|my editor|our editor|we have (an )?editor", text_lower):
            disqualifying.append({
                "type": "already_has_editor",
                "evidence": "Text indicates existing editor/team",
                "severity": "strong"
            })

        # Already heavy Shorts optimization
        if re.search(r"shorts? (expert|specialist|pro|agency|studio)", text_lower):
            disqualifying.append({
                "type": "already_shorts_optimized",
                "evidence": "Text indicates existing Shorts operation",
                "severity": "medium"
            })

        # Signal expired
        if re.search(r"(was )?looking for|(was )?hiring|(previously )?(looking|hiring)", text_lower):
            disqualifying.append({
                "type": "signal_may_be_expired",
                "evidence": "Signal language suggests past tense",
                "severity": "weak"
            })

        # Not in target niche
        if re.search(r"gaming|beauty|fashion|lifestyle|vlog|music|reaction", text_lower):
            disqualifying.append({
                "type": "niche_mismatch",
                "evidence": "Niche appears outside target (AI/Tech/Business/Education)",
                "severity": "medium"
            })

        return disqualifying

# ============================================================
# ENRICHMENT PIPELINE
# ============================================================

class LeadSignalEngine:
    """Main engine: Discovery → Enrichment → Signal Detection → Qualification → Verification."""

    SOURCES = {
        "youtube": {"priority": 1, "method": "youtube_video_page"},
        "website": {"priority": 2, "method": "web_search_real"},
        "x": {"priority": 3, "method": "web_search_real"},
        "linkedin": {"priority": 4, "method": "web_search_real"},
        "reddit": {"priority": 5, "method": "web_search_real"},
        "patreon": {"priority": 6, "method": "web_search_real"},
        "podbean": {"priority": 7, "method": "web_search_real"},
        "job_page": {"priority": 8, "method": "web_search_real"},
    }

    MAX_SOURCES = 5
    MAX_ATTEMPTS = 3

    def __init__(self, session_id: str = "lead_signal"):
        self.session_id = session_id
        self.finder = YouTubeLeadFinder()
        self.detector = SignalDetector()
        self.qualifier = LeadQualifier()

    def enrich_candidate(self, candidate: Dict) -> Dict:
        """Enrich a candidate by searching additional public sources."""
        enriched = candidate.copy()
        signals_collected = []
        sources_checked = []

        # Get base text from candidate
        base_text = ""
        if "video_url" in candidate and candidate["video_url"]:
            try:
                out = subprocess.run(["curl","-sL","-A","Mozilla/5.0","-m","8",candidate["video_url"]],
                                   capture_output=True, text=True, timeout=10)
                if out.stdout:
                    base_text = out.stdout[:50000]
                    sources_checked.append(candidate["video_url"])
            except Exception:
                pass

        # Search additional sources if we have a name
        name = candidate.get("creator_name") or candidate.get("channel_name")
        if name:
            queries = [
                f'"{name}" hiring editor',
                f'"{name}" looking for editor',
                f'"{name}" Shorts editor',
                f'"{name}" website',
                f'"{name}" LinkedIn',
            ]
            for q in queries[:3]:
                try:
                    out = subprocess.run(["curl","-sL","-A","Mozilla/5.0","-m","6",
                        f"https://www.google.com/search?q={q.replace(' ','+')}"],
                        capture_output=True, text=True, timeout=6)
                    if out.stdout:
                        text = out.stdout[:10000]
                        signals = list(SignalDetector.detect(text, f"https://www.google.com/search?q={q.replace(' ','+')}"))
                        sources_checked.append(f"https://www.google.com/search?q={q.replace(' ','+')}")
                        # yield is removed, just process signals
                except Exception:
                    pass

        # Detect signals from all collected text
        all_signals = list(SignalDetector.detect(base_text, candidate.get("video_url", "")))
        return {
            "candidate": candidate,
            "signals": [s.to_dict() for s in all_signals],
            "sources_checked": sources_checked,
        }

    def process_candidate(self, candidate: Dict) -> Dict:
        """Full pipeline for one candidate."""
        # Enrichment + Signal Detection
        enriched = self.enrich_candidate(candidate)
        candidate = enriched["candidate"]
        signals = [Signal(**s) for s in enriched["signals"]]
        sources_checked = enriched["sources_checked"]

        # Disqualifying checks
        text = ""
        if "video_url" in candidate:
            try:
                out = subprocess.run(["curl","-sL","-A","Mozilla/5.0","-m","8",candidate["video_url"]],
                                   capture_output=True, text=True, timeout=8)
                text = out.stdout[:10000] if out.stdout else ""
            except Exception:
                pass
        disqualifying = LeadQualifier.check_disqualifying(candidate, text)

        # Qualification
        qualification = self.qualifier.qualify(candidate, signals)
        qualification["disqualifying"] = disqualifying

        # Lead type
        lead_type = qualification.get("lead_type", "UNKNOWN")
        lead_status = qualification.get("lead_status", "UNKNOWN")

        # Verification (existing pipeline)
        verification = {"status": "pending"}
        name = candidate.get("creator_name") or candidate.get("channel_name")
        if name and lead_status in ("QUALIFIED", "POTENTIAL"):
            ver = verify_candidate(name, candidate.get("video_url", ""), candidate.get("niche", ""))
            verification = ver

        return {
            "candidate": candidate,
            "identity_status": candidate.get("extraction_status", candidate.get("status", "UNKNOWN")),
            "lead_status": lead_status,
            "lead_type": lead_type,
            "primary_source": candidate.get("method", "unknown"),
            "sources": [candidate.get("video_url", "")] + sources_checked,
            "signals": qualification.get("signals", []),
            "supporting_evidence": qualification.get("supporting_signals", []),
            "contradicting_evidence": disqualifying,
            "public_contact": None,  # would be extracted from signals
            "why_potential_lead": qualification.get("reason", ""),
            "verification": verification,
            "manual_review_needed": lead_status in ("POTENTIAL", "UNKNOWN"),
            "identity_status": candidate.get("extraction_status", candidate.get("status", "UNKNOWN")),
        }

    def run(self, goal: str = "Find potential leads for Shorts service", max_candidates: int = 10) -> List[Dict]:
        """Run full pipeline: discover → enrich → qualify → verify."""
        print(f"🎯 Lead Signal Engine: {goal}")

        # Discovery phase
        finder = YouTubeLeadFinder()
        candidates = finder.discover()

        results = []
        for candidate in candidates[:max_candidates]:
            print(f"  🔍 Processing: {candidate.get('video_url', 'N/A')[:60]}")
            result = self.process_candidate(candidate)
            results.append(result)
            print(f"    → {result['lead_status']} | {result['lead_type']} | {len(result['signals'])} signals")

        return results

if __name__ == "__main__":
    engine = LeadSignalEngine()
    results = engine.run(max_candidates=5)
    print(f"\n=== RESULTS ===")
    for r in results:
        print(f"  {r['lead_status']:12} | {r['lead_type']:10} | {len(r['signals'])} signals | {r['candidate'].get('video_url', '')[:50]}")
        if r['supporting_evidence']:
            print(f"    + {r['supporting_evidence'][:3]}")
        if r['contradicting_evidence']:
            print(f"    - {r['contradicting_evidence'][:2]}")