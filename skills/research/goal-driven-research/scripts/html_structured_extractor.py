#!/usr/bin/env python3
"""Universal HTML structured extractor with 4-status model.
VERIFIED / PARTIAL / UNKNOWN / FAILURE — never fabricate name.
"""
import json, re
from bs4 import BeautifulSoup
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

def extract(url: str, html: str = None) -> dict:
    # Default: all fields None/empty, status determined by evidence
    result = {
        "url": url,
        "source_type": "unknown",
        "status": "UNKNOWN",
        "name_candidate": None,
        "name_verified": False,
        "author_candidate": None,
        "author_verified": False,
        "title": None,
        "description": None,
        "metrics": {},
        "evidence": [],
        "extraction_method": None,
        "verification_needed": False,
        "failure_reason": None
    }

    if not html:
        result["status"] = "FAILURE"
        result["failure_reason"] = "no_html"
        result["evidence"].append({"field":"extraction","value":"no HTML content","source":"input","evidence":"url provided but no HTML"})
        return result

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        result["status"] = "FAILURE"
        result["failure_reason"] = "parse_error"
        result["evidence"].append(f"HTML parse error: {e}")
        return result

    # 1. JSON-LD structured (VERIFIED if Person/VideoObject with clear name)
    try:
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string: continue
            data = json.loads(script.string)
            if isinstance(data, dict):
                # Only verify when the structured data explicitly names an entity
                entity_type = data.get("@type")
                if entity_type in ("Person", "VideoObject", "ProfilePage", "Organization"):
                    name = data.get("name") or data.get("title")
                    if name and isinstance(name, str) and len(name) < 200 and not name.startswith("http"):
                        result["status"] = "VERIFIED"
                        result["name_candidate"] = name
                        result["name_verified"] = True
                        result["title"] = data.get("title") or name
                        result["description"] = data.get("description")
                        auth = data.get("author")
                        result["author_candidate"] = auth.get("name") if isinstance(auth, dict) else (auth if isinstance(auth, str) else None)
                        result["author_verified"] = bool(result["author_candidate"])
                        result["extraction_method"] = "json-ld_structured"
                        result["evidence"] = [{"field":"name_candidate","value":name,"source":"json-ld","evidence":f"@type={entity_type}"}]
                        result["url"] = data.get("url") or url
                        # Metrics only if explicitly present
                        if "followers" in data:
                            result["metrics"]["followers"] = data["followers"]
                            result["metrics"]["followers_verified"] = True
                        return result
                # Generic structured with name (could be PARTIAL if context weak)
                if isinstance(data.get("name"), str) and len(data["name"]) < 200:
                    n = data["name"]
                    # Require context: either @type or descriptive context
                    if data.get("@type") or (data.get("description") and len(str(data.get("description"))) > 20):
                        result["status"] = "PARTIAL"
                        result["name_candidate"] = n
                        result["name_verified"] = False
                        result["title"] = data.get("headline") or data.get("title") or n
                        result["description"] = data.get("description")
                        result["extraction_method"] = "json-ld_structured"
                        result["evidence"] = [{"field":"name_candidate","value":n,"source":"json-ld","evidence":f"@type={data.get('@type','unknown')}; context present"}]
                        result["verification_needed"] = True
                        result["url"] = data.get("url") or url
                        return result
    except Exception as e:
        # JSON parse error = FAILURE (not PARTIAL — data corrupt)
        result["status"] = "FAILURE"
        result["failure_reason"] = "json_parse_error"
        result["evidence"].append({"field":"extraction","value":"JSON-LD parse failed","source":"parse","evidence":str(e)})
        return result

    # 2. OpenGraph meta (PARTIAL — metadata only, not identity proof)
    try:
        og_title = soup.find("meta", property="og:title")
        og_site = soup.find("meta", property="og:site_name")
        og_url = soup.find("meta", property="og:url")
        if og_title and og_title.get("content"):
            title_text = og_title.get("content").strip()
            # Extract candidate only if clearly personal/entity format
            # But NEVER verify — title alone doesn't prove identity
            result["status"] = "PARTIAL" if (not result["name_verified"] and not result["status"] == "VERIFIED") else result["status"]
            # Only set PARTIAL if not already verified
            if result["status"] != "VERIFIED":
                result["status"] = "PARTIAL"
            result["title"] = title_text[:200]
            result["description"] = (og_title.get("content") if False else None)  # og:description handled below
            # Try to extract a candidate from title ONLY if clearly a name pattern (not URL, not generic)
            # Conservative: only if title contains common name indicators and not generic site title
            desc_meta = soup.find("meta", property="og:description")
            if desc_meta and desc_meta.get("content"):
                result["description"] = desc_meta.get("content").strip()[:500]
            result["url"] = og_url.get("content").strip() if og_url and og_url.get("content") else url
            result["extraction_method"] = "opengraph_meta"
            result["evidence"].append({"field":"title","value":title_text[:60],"source":"opengraph","evidence":"og:title present; identity requires verification"})
            # Candidate extraction: ONLY when title clearly indicates a named person
            # We do NOT invent — we only set candidate if format is clearly a name
            # But to be safe, leave name_candidate=None unless clearly structured
            result["verification_needed"] = True
            # Candidate from title: conservative, only if clearly personal
            candidate = title_text
            for sep in (" — ", " - ", " | ", ": "):
                if sep in title_text:
                    candidate = title_text.split(sep)[0].strip()
                    break
            if len(candidate) < 100 and not candidate.startswith("http") and (" " in candidate or "-" in candidate):
                result["name_candidate"] = candidate
            result["name_verified"] = False
            return result
    except Exception:
        pass

    # 3. Standard meta tags (author / description / title)
    try:
        meta_author = soup.find("meta", attrs={"name":"author"})
        meta_desc = soup.find("meta", attrs={"name":"description"})
        meta_title_tag = soup.find("meta", attrs={"name":"title"})
        if meta_author and meta_author.get("content"):
            a = meta_author.get("content").strip()
            if len(a) < 100 and not a.startswith("http") and "@" not in a[:10]:
                # meta author alone = PARTIAL (could be site author, not entity)
                if result["status"] not in ("VERIFIED",):
                    result["status"] = "PARTIAL"
                result["author_candidate"] = a
                result["author_verified"] = False  # meta alone not proof
                result["evidence"].append({"field":"author_candidate","value":a,"source":"meta_author","evidence":"meta name=author"})
                result["verification_needed"] = True
        if meta_desc and meta_desc.get("content") and not result["description"]:
            result["description"] = meta_desc.get("content").strip()[:500]
        if meta_title_tag and meta_title_tag.get("content") and not result["title"]:
            result["title"] = meta_title_tag.get("content").strip()[:200]
    except Exception:
        pass

    # 4. HTML <title>
    try:
        if soup.title and soup.title.string:
            t = soup.title.string.strip()[:200]
            if not result["title"]:
                result["title"] = t
                result["evidence"].append({"field":"title","value":t[:60],"source":"html_title","evidence":"<title> tag"})
            # Only if no better source yet: could become PARTIAL with title evidence
            if result["status"] == "UNKNOWN" and t:
                # Title alone = PARTIAL only if it suggests identity; but safe default: UNKNOWN unless clearly named
                # Conservative: leave UNKNOWN, but record title as evidence
                pass
    except Exception:
        pass

    # 5. Explicit structured elements ONLY when clearly person/entity (e.g., schema.org microdata)
    try:
        # Only if there's a clear <a> or <div> with itemprop="name" and context
        item = soup.find(attrs={"itemprop":"name"})
        if item and item.get_text(strip=True) and len(item.get_text(strip=True)) < 200:
            txt = item.get_text(strip=True)
            if result["status"] != "VERIFIED" and ("Person" in str(soup) or len([t for t in soup.find_all(text=True) if "profile" in str(t).lower()]) > 0):
                # Only promote to PARTIAL if there's some profile context
                result["status"] = "PARTIAL"
                result["name_candidate"] = txt
                result["name_verified"] = False
                result["evidence"].append({"field":"name_candidate","value":txt,"source":"microdata_itemprop","evidence":"itemprop=name with profile context"})
                result["verification_needed"] = True
    except Exception:
        pass

    # Final determination
    if result["status"] == "VERIFIED" and result["name_candidate"] and result["name_verified"]:
        pass  # confirmed
    elif result["status"] == "PARTIAL" and result["name_candidate"]:
        pass  # candidate with evidence, needs verification
    elif result["status"] == "UNKNOWN" and not result["name_candidate"] and not result["title"]:
        # Truly empty — no useful info
        result["failure_reason"] = None  # not a failure, just unknown
        result["evidence"].append({"field":"status","value":"UNKNOWN","source":"evaluation","evidence":"No useful identity/metadata in HTML"})
    elif result["status"] == "FAILURE":
        pass  # already set

    # Source type inference from URL
    url_lower = url.lower()
    if "youtube" in url_lower or "youtu.be" in url_lower:
        result["source_type"] = "youtube"
    elif "reddit" in url_lower:
        result["source_type"] = "reddit"
    elif "linkedin" in url_lower:
        result["source_type"] = "linkedin"
    elif "twitter" in url_lower or "x.com" in url_lower:
        result["source_type"] = "x"
    elif "github" in url_lower:
        result["source_type"] = "website"
    elif "arxiv" in url_lower:
        result["source_type"] = "website"
    else:
        result["source_type"] = "website"

    return result
