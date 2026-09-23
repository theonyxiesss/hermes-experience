#!/usr/bin/env python3
"""
Official Website Enrichment Strategy
Enriches YouTube candidates with evidence from their official public websites.
Integrates with existing Lead Signal Engine without modifying core pipeline.
"""

import sys
import os
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
from datetime import datetime

sys.path.insert(0, os.path.expanduser('~/AppData/Local/hermes/skills/research/goal-driven-research/scripts'))
from lead_signal_engine import SignalDetector, LeadQualifier, Signal


class WebsiteIdentityMatcher:
    """Matches a website to a candidate using evidence-based approach."""
    
    @staticmethod
    def evaluate_identity(candidate: Dict, website_url: str, pages_content: Dict[str, str]) -> Dict:
        """
        Evaluate if a website belongs to the candidate.
        Returns identity_status: VERIFIED | PARTIAL | UNKNOWN | FAILURE
        """
        evidence = []
        candidate_name = candidate.get("creator_name") or candidate.get("channel_name") or ""
        channel_name = candidate.get("channel_name") or ""
        youtube_url = candidate.get("video_url") or candidate.get("channel_url") or ""
        
        # Combine all page content
        all_text = " ".join(pages_content.values()).lower()
        candidate_name_lower = candidate_name.lower() if candidate_name else ""
        channel_name_lower = channel_name.lower() if channel_name else ""
        
        strong_evidence = 0
        weak_evidence = 0
        
        # Strong evidence checks
        # 1. Candidate name on About page
        if candidate_name and candidate_name_lower in all_text:
            strong_evidence += 1
            evidence.append({"type": "name_on_site", "evidence": f"Candidate name '{candidate_name}' found on site", "strength": "strong"})
        
        # 2. Channel name on site
        if channel_name and channel_name.lower() in all_text:
            strong_evidence += 1
            evidence.append({"type": "channel_name_on_site", "evidence": f"Channel name '{channel_name}' found on site", "strength": "strong"})
        
        # 3. YouTube link back
        if youtube_url:
            youtube_domain = urlparse(youtube_url).netloc
            if youtube_domain in all_text or "youtube.com" in all_text:
                strong_evidence += 1
                evidence.append({"type": "youtube_link", "evidence": "Site links back to YouTube channel", "strength": "strong"})
        
        # 4. Matching social profiles
        social_platforms = ["linkedin", "twitter", "x.com", "patreon", "podbean"]
        for platform in social_platforms:
            if platform in all_text:
                evidence.append({"type": "social_profile", "evidence": f"Site references {platform}", "strength": "medium"})
                weak_evidence += 1
        
        # 5. Business name match
        business_match = re.search(r'(?:company|business|agency|studio|inc|llc|ltd)[\s:]*([A-Z][a-zA-Z\s]+)', all_text, re.IGNORECASE)
        if business_match:
            evidence.append({"type": "business_name", "evidence": f"Business name found: {business_match.group(1)[:50]}", "strength": "medium"})
            weak_evidence += 1
        
        # Weak evidence: domain similarity
        domain = urlparse(website_url).netloc
        if candidate_name and any(word in domain for word in candidate_name.lower().split() if len(word) > 3):
            weak_evidence += 1
            evidence.append({"type": "domain_similarity", "evidence": f"Domain '{domain}' contains candidate name part", "strength": "weak"})
        
        # Determine status
        if strong_evidence >= 2:
            status = "VERIFIED"
        elif strong_evidence >= 1 or weak_evidence >= 2:
            status = "PARTIAL"
        elif weak_evidence >= 1:
            status = "UNKNOWN"
        else:
            status = "FAILURE"
            return {
                "identity_status": "FAILURE",
                "identity_evidence": evidence,
                "reason": "No matching evidence found"
            }
        
        return {
            "identity_status": status,
            "identity_evidence": evidence,
            "reason": f"Strong evidence: {strong_evidence}, Weak evidence: {weak_evidence}"
        }


class WebsiteCrawler:
    """Bounded website crawler for public pages only."""
    
    PRIORITY_PATHS = [
        "/", "/about", "/about-us", "/aboutme", "/about-me",
        "/team", "/team/", "/services", "/services/",
        "/contact", "/contact/", "/contact-us", "/contact-us/",
        "/careers", "/careers/", "/jobs", "/jobs/",
        "/work", "/work/", "/portfolio", "/portfolio/",
        "/blog", "/blog/", "/podcast", "/podcast/",
        "/about-us/", "/about/", "/home", "/home/"
    ]
    
    def __init__(self, max_pages: int = 8, timeout: int = 8):
        self.max_pages = max_pages
        self.timeout = timeout
    
    def discover_website(self, candidate: Dict) -> List[str]:
            """Discover candidate's official website via search - prioritize non-YouTube domains."""
            urls = []
            name = candidate.get("creator_name") or candidate.get("channel_name") or ""
            channel_name = candidate.get("channel_name") or ""
        
            if not name:
                return []
        
            # Search queries for official website (not YouTube channel)
            queries = [
                f'"{name}" official website',
                f'"{name}" official site',
                f'"{name}" website',
                f'"{name}" business',
                f'"{name}" podcast',
            ]
        
            urls = []
            for query in queries[:3]:  # Limit to 3 queries
                try:
                    out = subprocess.run(
                        ["curl", "-sL", "-A", "Mozilla/5.0", "-m", "8",
                         f"https://www.google.com/search?q={query.replace(' ', '+')}"],
                        capture_output=True, text=True, timeout=8
                    )
                    if out.stdout:
                        # Extract domains from search results
                        urls_found = re.findall(r'https?://([a-zA-Z0-9.-]+\.[a-z]{2,})', out.stdout)
                        for domain in urls_found:
                            # Filter out Google, social media, YouTube, etc.
                            if not any(excluded in domain for excluded in ["google", "youtube", "facebook", "twitter", "x.com", "linkedin", "reddit", "instagram", "tiktok", "wikipedia"]):
                                full_url = f"https://{domain}"
                                if full_url not in urls:
                                    urls.append(full_url)
                except Exception:
                    pass
        
            # Also try direct known patterns for known creators
            # This is a fallback - if search doesn't find it, try known patterns
            return urls[:5]  # Max 5 candidate websites
    
    def crawl(self, base_url: str) -> Dict[str, str]:
        """Crawl public pages up to max_pages."""
        pages = {}
        base = base_url.rstrip("/")
        paths = self.PRIORITY_PATHS[:self.max_pages]
        
        for path in self.PRIORITY_PATHS:
            if len(pages) >= self.max_pages:
                break
            url = urljoin(base + "/", path.lstrip("/"))
            try:
                out = subprocess.run(
                    ["curl", "-sL", "-A", "Mozilla/5.0", "-m", "8", url],
                    capture_output=True, text=True, timeout=8
                )
                if out.stdout and len(out.stdout) > 100:
                    # Basic validation - not error page
                    content = out.stdout[:50000]
                    if "404" not in out.stdout[:200] and "not found" not in out.stdout[:200].lower():
                        pages[url] = content
            except Exception:
                pass
        
        return pages


class OfficialWebsiteEnrichment:
    """Main enrichment strategy."""
    
    def __init__(self):
        self.crawler = WebsiteCrawler(max_pages=8)
        self.matcher = WebsiteIdentityMatcher()
        # Reuse existing signal detector
        from lead_signal_engine import SignalDetector, LeadQualifier
        self.detector = SignalDetector()
        self.qualifier = LeadQualifier()
    
    def enrich_candidate(self, candidate: Dict) -> Dict:
        """Enrich a single candidate with website evidence."""
        result = {
            "candidate_id": candidate.get("video_url", candidate.get("channel_url", "unknown")),
            "website": {"url": None, "domain": None, "identity_status": "FAILURE", "identity_evidence": []},
            "pages_checked": [],
            "signals": [],
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "public_contacts": [],
            "extraction_status": "FAILURE",
            "verification_needed": False,
            "failure_reason": None,
            "source_urls": []
        }
        
        # Step 1: Discover website
        website_urls = self.crawler.discover_website(candidate)
        if not website_urls:
            result["failure_reason"] = "NO_WEBSITE_FOUND"
            result["extraction_status"] = "FAILURE"
            return result
        
        # Use first discovered URL
        website_url = website_urls[0]
        result["website"]["url"] = website_url
        result["website"]["domain"] = urlparse(website_url).netloc
        result["source_urls"].append(website_url)
        
        # Step 2: Crawl website
        pages_content = self.crawler.crawl(website_url)
        if not pages_content:
            result["failure_reason"] = "NO_RELEVANT_PAGES"
            result["extraction_status"] = "FAILURE"
            return result
        
        result["pages_checked"] = [{"url": url, "length": len(content)} for url, content in list(pages_content.items())]
        result["source_urls"].extend(list(pages_content.keys()))
        
        # Step 3: Identity matching
                # Step 3: Identity matching
        identity_result = self.matcher.evaluate_identity(candidate, website_url, pages_content)
        result["website"]["identity_status"] = identity_result["identity_status"]
        result["website"]["identity_evidence"] = identity_result["identity_evidence"]
        result["extraction_status"] = identity_result["identity_status"]
        
        if identity_result["identity_status"] == "FAILURE":
            result["failure_reason"] = "IDENTITY_UNCERTAIN"
            return result
        
        # Step 3b: Extract signals from all pages
        all_text = " ".join(pages_content.values())
        
        # Detect contact signals
        contact_signals = []
        all_text = " ".join(pages_content.values())
        contact_patterns = {
            "public_email": {"strength": "strong", "patterns": [r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"]},
            "contact_page": {"strength": "strong", "patterns": [r"contact", r"hire me", r"work with me", r"business inquiry"]},
            "public_linkedin": {"strength": "medium", "patterns": [r"linkedin\.com/in/", r"linkedin\.com/company/"]},
            "public_x": {"strength": "medium", "patterns": [r"x\.com/", r"twitter\.com/"]}
        }
        
        contact_signals = []
        all_text = " ".join(pages_content.values())
        for sig_type, cfg in {
            "public_email": {"strength": "strong", "patterns": [r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"]},
            "contact_page": {"strength": "strong", "patterns": [r"contact", r"hire me", r"work with me", r"business inquiry"]},
            "public_linkedin": {"strength": "medium", "patterns": [r"linkedin\.com/in/", r"linkedin\.com/company/"]},
            "public_x": {"strength": "medium", "patterns": [r"x\.com/", r"twitter\.com/"]}
        }.items():
            for pattern in cfg["patterns"]:
                matches = re.findall(pattern, all_text, re.IGNORECASE)
                if matches:
                    for match in matches[:3]:
                        contact_signals.append(Signal(
                            type=f"contact:{sig_type}",
                            strength=cfg["strength"],
                            value=True,
                            source_url=website_url,
                            evidence=f"Found: {match}",
                            method="regex_extract",
                            verified=True
                        ))
        
        # Detect signals from all pages using detector
        all_signals = list(self.detector.detect(all_text, website_url))
        all_signals.extend(contact_signals)
        
        # Check for intent signals specifically
        intent_found = any(s.type.startswith("intent:") for s in all_signals)
        
        # Contradicting evidence check
        contradicting = []
        text = " ".join(pages_content.values()).lower()
        if "personal blog" in all_text.lower() and "no business" in all_text:
            result["contradicting_evidence"].append({
                "type": "personal_only",
                "evidence": "Site describes project as personal blog with no business/services",
                "severity": "medium"
            })
        
        # Build final result
        result["extraction_status"] = "VERIFIED" if candidate.get("identity_status") == "VERIFIED" else "PARTIAL"
        result["signals"] = []  # Will be populated by Lead Signal Engine
        result["supporting_evidence"] = []
        result["contradicting_evidence"] = result.get("contradicting_evidence", [])
        result["public_contacts"] = []  # Would be extracted from signals
        result["extraction_status"] = "VERIFIED" if candidate.get("identity_status") == "VERIFIED" else "PARTIAL"
        result["verification_needed"] = True
        result["failure_reason"] = None
        
        return result


if __name__ == "__main__":
    # Quick test with existing candidate
    test_candidate = {
        "video_url": "https://www.youtube.com/watch?v=yi6l3WwUQ7k",
        "channel_name": "Test Channel",
        "creator_name": None
    }
    
    enrichment = OfficialWebsiteEnrichment()
    result = enrichment.enrich_candidate({
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "channel_name": "Rick Astley",
        "creator_name": "Rick Astley"
    })
    
    print(json.dumps(result, indent=2, default=str))