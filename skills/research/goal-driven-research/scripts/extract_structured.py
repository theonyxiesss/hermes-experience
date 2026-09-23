#!/usr/bin/env python3
"""
GDIR Structured Web Extractor
Returns structured records WITHOUT fabrication.
Prefers APIs / structured endpoints > browser DOM > explicit failure.
"""
import json, re, os, sys, subprocess, urllib.parse
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/AppData/Local/hermes/skills/research/goal-driven-research/scripts'))

class ExtractionFailure(Exception):
    pass

def extract_entity(url: str, source_hint: str = None) -> dict:
    """
    Try structured sources; return explicit failure if nothing verifiable.
    NEVER invent name/description/metrics.
    """
    result = {
        "name": None,
        "url": url,
        "description": None,
        "relevant_metrics": {},
        "evidence": None,
        "source": source_hint or url,
        "extraction_method": None,
        "verified": False
    }

    # 1. Try YouTube oEmbed (structured endpoint — preferred)
    if "youtube.com" in url or "youtu.be" in url:
        try:
            video_id = None
            if "v=" in url:
                video_id = url.split("v=")[1].split("&")[0]
            elif "/embed/" in url:
                video_id = url.split("/embed/")[1].split("?")[0]
            elif "youtu.be/" in url:
                video_id = url.split("youtu.be/")[1].split("?")[0]
            if video_id and len(video_id) == 11:
                oembed = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                out = subprocess.run(
                    ["curl", "-sL", "-A", "Mozilla/5.0", oembed],
                    capture_output=True, text=True, timeout=10
                )
                data = json.loads(out.stdout) if out.stdout.startswith("{") else {}
                if data.get("title"):
                    result["name"] = data["title"]
                    result["description"] = data.get("author_name", "YouTube")
                    result["extraction_method"] = "youtube_oembed_json"
                    result["verified"] = True
                    result["evidence"] = f"oEmbed JSON title={data.get('title')} author={data.get('author_name')}"
                    result["relevant_metrics"]["video_id"] = video_id
                    return result
        except Exception as e:
            result["evidence"] = f"oEmbed failed: {e}"

    # 2. Try YouTube Data / structured page JSON-LD (no key -> skip, don't fabricate)
    if "youtube.com/watch" in url:
        # Without API key we cannot get structured data reliably
        result["extraction_method"] = "youtube_structured_unavailable"
        result["evidence"] = "YouTube Data API requires key; page HTML requires browser parsing. No structured endpoint available without auth."

    # 3. Try LinkedIn structured endpoint (LinkedIn requires auth; public pages block scraping)
    if "linkedin.com" in url:
        result["extraction_method"] = "linkedin_structured_unavailable"
        result["evidence"] = "LinkedIn requires authentication / agreement; public profile pages block automated extraction by robots. No open structured endpoint for entities."

    # 4. General browser extraction attempt (only if no structured source)
    # Use browser_navigate -> extract visible text ONLY if clearly verifiable
    # But per rules: if unverified, return failure, not fabricated record.
    if result["verified"] is False:
        raise ExtractionFailure(
            f"No verified structured source for {url} (source={source_hint}). "
            f"Methods tried: oEmbed/API (if applicable), structured endpoint (unavailable/needs auth). "
            f"Result: UNKNOWN — manual review of original URL required. "
            f"Evidence collected: {result['evidence']}"
        )
    return result

def test_real():
    # Real YouTube URL
    yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    try:
        r = extract_entity(yt, "youtube_test")
        print("YOUTUBE OK:", r["name"], r["verified"], r["extraction_method"])
    except ExtractionFailure as e:
        print("YOUTUBE FAILURE (expected if oEmbed blocked):", str(e)[:200])

    # LinkedIn URL (will fail — correct behavior)
    li = "https://www.linkedin.com/company/example/"
    try:
        r = extract_entity(li, "linkedin_test")
        print("LINKEDIN OK:", r["name"])
    except ExtractionFailure as e:
        print("LINKEDIN FAILURE (expected — requires auth):", str(e)[:200])

if __name__ == "__main__":
    test_real()
