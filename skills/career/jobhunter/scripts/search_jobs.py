"""
Unified job search across all enabled sources (see references/job_sources.json).

Each adapter returns a list of dicts:
{
    "id": "source:12345", "source": "SourceName", "title": "...",
    "company": "...", "salary": "...", "url": "https://...",
    "description": "...", "published_at": "...",
}

Usage:
    python search_jobs.py --text "python developer"
"""

import argparse
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from hashlib import md5

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("search_jobs")

SOURCES_FILE = Path(__file__).resolve().parent.parent / "references" / "job_sources.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
TIMEOUT = 25


# =====================================================================
# Helpers
# =====================================================================

def load_enabled_sources() -> set[str]:
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    enabled = set()
    for cat in data["categories"]:
        for src in cat["sources"]:
            if src.get("enabled"):
                enabled.add(src["name"])
    return enabled


def _get(url, params=None, headers=None, **kw):
    h = {**HEADERS, **(headers or {})}
    try:
        r = requests.get(url, params=params, headers=h, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning("GET %s → %s", url, e)
        return None


def _post(url, headers=None, **kw):
    h = {**HEADERS, **(headers or {})}
    try:
        r = requests.post(url, headers=h, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning("POST %s → %s", url, e)
        return None


def _rss(url):
    r = _get(url)
    if not r:
        return []
    root = ET.fromstring(r.content)
    return [
        {
            "title": i.findtext("title", ""),
            "link": i.findtext("link", ""),
            "desc": (i.findtext("description", "") or "")[:500],
            "guid": i.findtext("guid", i.findtext("link", "")),
            "date": i.findtext("pubDate", ""),
        }
        for i in root.findall(".//item")
    ]


def _soup(url, params=None):
    r = _get(url, params=params)
    if not r:
        return None
    return BeautifulSoup(r.text, "lxml")


def _hid(text):
    return md5(text.encode()).hexdigest()[:12]


def _kw_match(text, keyword):
    if not keyword:
        return True
    return keyword.lower() in text.lower()


# =====================================================================
# FREE API (no key)
# =====================================================================

def search_remoteok(kw=""):
    r = _get("https://remoteok.com/api")
    if not r:
        return []
    out = []
    for it in r.json():
        if not isinstance(it, dict) or "id" not in it:
            continue
        if not _kw_match(f"{it.get('position','')} {it.get('description','')}", kw):
            continue
        out.append({"id": f"remoteok:{it['id']}", "source": "RemoteOK",
                     "title": it.get("position", ""), "company": it.get("company", ""),
                     "salary": it.get("salary", "") or "",
                     "url": it.get("url", ""),
                     "description": (it.get("description", "") or "")[:500],
                     "published_at": it.get("date", "")})
    return out


def search_remotive(kw=""):
    r = _get("https://remotive.com/api/remote-jobs", params={"search": kw} if kw else {})
    if not r:
        return []
    return [{"id": f"remotive:{j['id']}", "source": "Remotive",
             "title": j.get("title", ""), "company": j.get("company_name", ""),
             "salary": j.get("salary", "") or "", "url": j.get("url", ""),
             "description": (j.get("description", "") or "")[:500],
             "published_at": j.get("publication_date", "")}
            for j in r.json().get("jobs", [])]


def search_working_nomads(kw=""):
    r = _get("https://www.workingnomads.com/api/exposed_jobs/")
    if not r:
        return []
    out = []
    for j in r.json():
        if not _kw_match(f"{j.get('title','')} {j.get('description','')}", kw):
            continue
        out.append({"id": f"wnomads:{j.get('slug', j.get('id',''))}", "source": "Working Nomads",
                     "title": j.get("title", ""), "company": j.get("company_name", ""),
                     "salary": "", "url": j.get("url", ""),
                     "description": (j.get("description", "") or "")[:500],
                     "published_at": j.get("pub_date", "")})
    return out


def search_themuse(kw=""):
    out = []
    for pg in range(1, 11):
        r = _get("https://www.themuse.com/api/public/jobs", params={"page": pg, "descending": "true"})
        if not r:
            break
        for j in r.json().get("results", []):
            locs = ", ".join(l.get("name", "") for l in j.get("locations", []))
            t = j.get("name", "")
            co = (j.get("company") or {}).get("name", "")
            if not _kw_match(f"{t} {co} {locs}", kw):
                continue
            out.append({"id": f"muse:{j['id']}", "source": "The Muse",
                         "title": t, "company": co,
                         "salary": "", "url": (j.get("refs") or {}).get("landing_page", ""),
                         "description": f"{t} — {locs}" if locs else t,
                         "published_at": j.get("publication_date", "")})
    return out


def search_arbeitnow(kw=""):
    r = _get("https://arbeitnow.com/api/job-board-api")
    if not r:
        return []
    out = []
    for j in r.json().get("data", []):
        if not _kw_match(f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))}", kw):
            continue
        out.append({"id": f"arbeitnow:{j.get('slug','')}", "source": "Arbeitnow",
                     "title": j.get("title", ""), "company": j.get("company_name", ""),
                     "salary": "", "url": j.get("url", ""),
                     "description": (j.get("description", "") or "")[:500],
                     "published_at": j.get("created_at", "")})
    return out


def search_himalayas(kw=""):
    out = []
    for page in range(10):
        r = _get("https://himalayas.app/jobs/api", params={"limit": 50, "offset": page * 50})
        if not r:
            break
        jobs = r.json().get("jobs", [])
        if not jobs:
            break
        for j in jobs:
            title = j.get("title", "")
            co = j.get("companyName", "")
            excerpt = j.get("excerpt", "")
            if not _kw_match(f"{title} {co} {excerpt}", kw):
                continue
            sal = ""
            if j.get("minSalary") or j.get("maxSalary"):
                sal = f"${j.get('minSalary','')}-${j.get('maxSalary','')} {j.get('salaryPeriod','')}"
            link = j.get("applicationLink", "") or j.get("guid", "")
            if link and not link.startswith("http"):
                link = f"https://himalayas.app/jobs/{link}"
            out.append({"id": f"himalayas:{_hid(title+co)}", "source": "Himalayas",
                         "title": title, "company": co, "salary": sal,
                         "url": link or "https://himalayas.app",
                         "description": excerpt[:500],
                         "published_at": j.get("pubDate", "")})
        if len(out) >= 50:
            break
    return out


def search_hn_hiring(kw=""):
    sr = _get("https://hn.algolia.com/api/v1/search",
              params={"query": '"Ask HN: Who is hiring?"', "tags": "ask_hn", "hitsPerPage": 1})
    if not sr:
        return []
    hits = sr.json().get("hits", [])
    if not hits:
        return []
    sid = hits[0]["objectID"]
    cr = _get("https://hn.algolia.com/api/v1/search",
              params={"tags": f"comment,story_{sid}", "hitsPerPage": 200})
    if not cr:
        return []
    out = []
    for c in cr.json().get("hits", []):
        if str(c.get("parent_id")) != str(sid):
            continue
        raw = c.get("comment_text", "") or ""
        if not _kw_match(raw, kw):
            continue
        fl = re.sub(r"<[^>]+>", "", raw.split("<p>")[0] if raw else "")
        parts = [p.strip() for p in fl.split("|")]
        out.append({"id": f"hn:{c['objectID']}", "source": "HN Who Is Hiring",
                     "title": parts[1] if len(parts) > 1 else fl,
                     "company": parts[0] if parts else "",
                     "salary": "", "url": f"https://news.ycombinator.com/item?id={c['objectID']}",
                     "description": re.sub(r"<[^>]+>", " ", raw)[:500],
                     "published_at": c.get("created_at", "")})
    return out


def search_jobicy(kw=""):
    params = {"count": 100}
    if kw:
        params["tag"] = kw
    r = _get("https://jobicy.com/api/v2/remote-jobs", params=params)
    if not r:
        return []
    out = []
    for j in r.json().get("jobs", []):
        title = j.get("jobTitle", "")
        co = j.get("companyName", "")
        if not kw and not _kw_match(title, kw):
            continue
        out.append({"id": f"jobicy:{j.get('id','')}", "source": "Jobicy",
                     "title": title, "company": co, "salary": "",
                     "url": j.get("url", ""),
                     "description": (j.get("jobExcerpt", "") or "")[:500],
                     "published_at": j.get("pubDate", "")})
    return out


def search_landingjobs(kw=""):
    r = _get("https://landing.jobs/api/v1/offers", params={"limit": 50})
    if not r:
        return []
    out = []
    for j in r.json() if isinstance(r.json(), list) else []:
        title = j.get("title", "")
        tags = " ".join(t.get("name", "") if isinstance(t, dict) else str(t) for t in (j.get("tags", []) or []))
        if not _kw_match(f"{title} {tags}", kw):
            continue
        sal = ""
        if j.get("gross_salary_low") or j.get("gross_salary_high"):
            cur = j.get("currency_code", "EUR")
            sal = f"{cur} {j.get('gross_salary_low','')}-{j.get('gross_salary_high','')}"
        locs = ", ".join(l.get("name", "") if isinstance(l, dict) else str(l) for l in (j.get("locations", []) or []))
        out.append({"id": f"landingjobs:{j.get('id','')}", "source": "Landing.jobs",
                     "title": title, "company": "",
                     "salary": sal,
                     "url": j.get("url", ""),
                     "description": f"{title} | {locs} | {tags}"[:500],
                     "published_at": j.get("published_at", "")})
    return out


# =====================================================================
# RSS
# =====================================================================

def search_wwr():
    return [{"id": f"wwr:{i['guid']}", "source": "We Work Remotely",
             "title": i["title"], "company": "", "salary": "",
             "url": i["link"], "description": i["desc"], "published_at": i["date"]}
            for i in _rss("https://weworkremotely.com/categories/remote-programming-jobs.rss")]


def search_authentic_jobs():
    return [{"id": f"authjobs:{i['guid']}", "source": "Authentic Jobs",
             "title": i["title"], "company": "", "salary": "",
             "url": i["link"], "description": i["desc"], "published_at": i["date"]}
            for i in _rss("https://authenticjobs.com/rss/index.xml")]


def search_cryptocurrencyjobs_rss():
    return [{"id": f"ccjobs:{i['guid']}", "source": "CryptoCurrencyJobs",
             "title": i["title"], "company": "", "salary": "",
             "url": i["link"], "description": i["desc"], "published_at": i["date"]}
            for i in _rss("https://cryptocurrencyjobs.co/feed/")]


def search_dribbble_rss():
    return [{"id": f"dribbble:{i['guid']}", "source": "Dribbble Jobs",
             "title": i["title"], "company": "", "salary": "",
             "url": i["link"], "description": i["desc"], "published_at": i["date"]}
            for i in _rss("https://dribbble.com/jobs.rss")]


def search_pythonjobs_rss():
    return [{"id": f"pyjobs:{i['guid']}", "source": "Python.org Jobs",
             "title": i["title"], "company": "", "salary": "",
             "url": i["link"], "description": i["desc"], "published_at": i["date"]}
            for i in _rss("https://www.python.org/jobs/feed/rss/")]


def search_larajobs_rss():
    return [{"id": f"larajobs:{i['guid']}", "source": "LaraJobs",
             "title": i["title"], "company": "", "salary": "",
             "url": i["link"], "description": i["desc"], "published_at": i["date"]}
            for i in _rss("https://larajobs.com/feed")]


# =====================================================================
# KEY-BASED API (env vars)
# =====================================================================

def search_jooble(kw=""):
    key = os.environ.get("JOOBLE_API_KEY")
    if not key:
        return []
    r = _post(f"https://jooble.org/api/{key}", json={"keywords": kw, "location": ""})
    if not r:
        return []
    return [{"id": f"jooble:{j.get('id','')}", "source": "Jooble",
             "title": j.get("title", ""), "company": j.get("company", ""),
             "salary": j.get("salary", "") or "", "url": j.get("link", ""),
             "description": (j.get("snippet", "") or "")[:500],
             "published_at": j.get("updated", "")}
            for j in r.json().get("jobs", [])]


def search_adzuna(kw=""):
    aid = os.environ.get("ADZUNA_APP_ID")
    ak = os.environ.get("ADZUNA_API_KEY")
    if not aid or not ak:
        return []
    country = os.environ.get("ADZUNA_COUNTRY", "us")
    r = _get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
             params={"app_id": aid, "app_key": ak, "results_per_page": 50, "what": kw})
    if not r:
        return []
    out = []
    for j in r.json().get("results", []):
        sal = ""
        if j.get("salary_min") or j.get("salary_max"):
            sal = f"{j.get('salary_min','')}-{j.get('salary_max','')}"
        out.append({"id": f"adzuna:{j.get('id','')}", "source": "Adzuna",
                     "title": j.get("title", ""), "company": (j.get("company") or {}).get("display_name", ""),
                     "salary": sal, "url": j.get("redirect_url", ""),
                     "description": (j.get("description", "") or "")[:500],
                     "published_at": j.get("created", "")})
    return out


def search_careerjet(kw=""):
    affid = os.environ.get("CAREERJET_AFFID")
    if not affid:
        return []
    locale = os.environ.get("CAREERJET_LOCALE", "en_US")
    r = _get("http://public.api.careerjet.net/search",
             params={"locale_code": locale, "keywords": kw, "affid": affid, "pagesize": 50, "sort": "date"})
    if not r:
        return []
    d = r.json()
    if d.get("type") != "JOBS":
        return []
    return [{"id": f"careerjet:{j.get('url','')}", "source": "CareerJet",
             "title": j.get("title", ""), "company": j.get("company", ""),
             "salary": j.get("salary", "") or "", "url": j.get("url", ""),
             "description": (j.get("description", "") or "")[:500],
             "published_at": j.get("date", "")}
            for j in d.get("jobs", [])]


def search_reed(kw=""):
    key = os.environ.get("REED_API_KEY")
    if not key:
        return []
    r = _get("https://www.reed.co.uk/api/1.0/search",
             params={"keywords": kw, "resultsToTake": 50}, auth=(key, ""))
    if not r:
        return []
    out = []
    for j in r.json().get("results", []):
        sal = ""
        if j.get("minimumSalary") or j.get("maximumSalary"):
            sal = f"{j.get('minimumSalary','')}-{j.get('maximumSalary','')} GBP"
        out.append({"id": f"reed:{j.get('jobId','')}", "source": "Reed.co.uk",
                     "title": j.get("jobTitle", ""), "company": j.get("employerName", ""),
                     "salary": sal, "url": j.get("jobUrl", ""),
                     "description": (j.get("jobDescription", "") or "")[:500],
                     "published_at": j.get("date", "")})
    return out


def search_findwork(kw=""):
    key = os.environ.get("FINDWORK_API_KEY")
    if not key:
        return []
    r = _get("https://findwork.dev/api/jobs/", params={"search": kw},
             headers={"Authorization": f"Token {key}"})
    if not r:
        return []
    return [{"id": f"findwork:{j.get('id','')}", "source": "Findwork.dev",
             "title": j.get("role", ""), "company": j.get("company_name", ""),
             "salary": "", "url": j.get("url", ""),
             "description": (j.get("text", "") or "")[:500],
             "published_at": j.get("date_posted", "")}
            for j in r.json().get("results", [])]


def search_usajobs(kw=""):
    key = os.environ.get("USAJOBS_API_KEY")
    if not key:
        return []
    email = os.environ.get("USAJOBS_EMAIL", "jobhunter@example.com")
    r = _get("https://data.usajobs.gov/api/Search",
             params={"Keyword": kw, "ResultsPerPage": 50},
             headers={"Authorization-Key": key, "User-Agent": email, "Host": "data.usajobs.gov"})
    if not r:
        return []
    out = []
    for item in r.json().get("SearchResult", {}).get("SearchResultItems", []):
        d = item.get("MatchedObjectDescriptor", {})
        sal = ""
        rems = d.get("PositionRemuneration", [])
        if rems:
            rm = rems[0]
            sal = f"${rm.get('MinimumRange','')}-${rm.get('MaximumRange','')} {rm.get('RateIntervalCode','')}"
        out.append({"id": f"usajobs:{item.get('MatchedObjectId','')}", "source": "USAJobs",
                     "title": d.get("PositionTitle", ""), "company": d.get("OrganizationName", ""),
                     "salary": sal, "url": d.get("PositionURI", ""),
                     "description": d.get("QualificationSummary", "")[:500],
                     "published_at": d.get("PublicationStartDate", "")})
    return out


# =====================================================================
# SCRAPE — JSON endpoints (undocumented but public)
# =====================================================================

def search_nofluffjobs(kw=""):
    r = _get("https://nofluffjobs.com/api/posting")
    if not r:
        return []
    out = []
    for j in r.json().get("postings", r.json() if isinstance(r.json(), list) else []):
        title = j.get("title", "") or j.get("name", "")
        if not _kw_match(f"{title} {' '.join(j.get('technology',[]))} {j.get('category','')}", kw):
            continue
        sal = ""
        salary_data = j.get("salary", {})
        if salary_data:
            sal = f"{salary_data.get('from','')}-{salary_data.get('to','')} {salary_data.get('currency','')}"
        slug = j.get("url", j.get("id", ""))
        out.append({"id": f"nfj:{slug}", "source": "NoFluffJobs",
                     "title": title, "company": j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else j.get("company", ""),
                     "salary": sal,
                     "url": f"https://nofluffjobs.com/job/{slug}" if not slug.startswith("http") else slug,
                     "description": f"{title} | {j.get('category','')} | {', '.join(j.get('technology',[]))}",
                     "published_at": j.get("posted", j.get("renewedAt", ""))})
    return out


def search_dice(kw=""):
    return _scrape_site(f"https://www.dice.com/jobs?q={kw}&countryCode=US&radius=30&radiusUnit=mi&page=1&pageSize=50" if kw else "https://www.dice.com/jobs", "dice", "Dice", kw)


def search_crossover(kw=""):
    r = _get("https://kontent-proxy.crossover.com/items",
             params={"system.type": "pipeline", "limit": 100})
    if not r:
        return []
    out = []
    for item in r.json().get("items", []):
        sys_info = item.get("system", {})
        el = item.get("elements", {})
        title = sys_info.get("name", "")
        hook = re.sub(r"<[^>]+>", "", el.get("hook", {}).get("value", ""))
        reqs = re.sub(r"<[^>]+>", "", el.get("requirements", {}).get("value", ""))
        if not _kw_match(f"{title} {hook} {reqs}", kw):
            continue
        code = el.get("pipeline_code", {}).get("value", "")
        loc = el.get("work_location", {}).get("value", "") or el.get("location_override", {}).get("value", "")
        schedule = el.get("schedule", {}).get("value", "")
        desc_parts = [hook[:300]]
        if loc:
            desc_parts.append(f"Location: {loc}")
        if schedule:
            desc_parts.append(schedule)
        out.append({"id": f"crossover:{code or _hid(title)}", "source": "Crossover",
                     "title": title, "company": "Crossover",
                     "salary": "",
                     "url": f"https://www.crossover.com/jobs/{code}" if code else "https://www.crossover.com/jobs",
                     "description": " | ".join(desc_parts)[:500],
                     "published_at": sys_info.get("last_modified", "")})
    return out


def search_web3career(kw=""):
    return _scrape_site("https://web3.career", "web3career", "Web3.career", kw)


def search_cryptojobslist(kw=""):
    r = _get("https://cryptojobslist.com/api/jobs", params={"limit": 50})
    if not r:
        s = _soup("https://cryptojobslist.com")
        if not s:
            return []
        return _parse_job_cards(s, "cjl", "CryptoJobsList", "https://cryptojobslist.com", kw)
    jobs = r.json() if isinstance(r.json(), list) else r.json().get("jobs", r.json().get("data", []))
    out = []
    for j in jobs:
        title = j.get("title", "")
        if not _kw_match(title, kw):
            continue
        out.append({"id": f"cjl:{j.get('id','')}", "source": "CryptoJobsList",
                     "title": title, "company": j.get("company", j.get("companyName", "")),
                     "salary": j.get("salary", "") or "", "url": j.get("url", j.get("link", "")),
                     "description": (j.get("description", "") or "")[:500],
                     "published_at": j.get("date", j.get("createdAt", ""))})
    return out


# =====================================================================
# SCRAPE — HTML (BeautifulSoup)
# =====================================================================

def _parse_job_cards(soup, prefix, source, base_url, kw=""):
    """Generic: find job cards in HTML by common patterns."""
    out = []
    for card in soup.select("article, .job-card, .job-listing, .job-item, .job, .posting, [class*='job']"):
        a = card.select_one("a[href*='job'], a[href*='position'], a[href*='career'], h2 a, h3 a, .title a, a")
        if not a:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        if not _kw_match(title, kw):
            continue
        href = a.get("href", "")
        if href and not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")
        company_el = card.select_one(".company, .company-name, .employer, [class*='company']")
        company = company_el.get_text(strip=True) if company_el else ""
        sal_el = card.select_one(".salary, [class*='salary'], [class*='compensation']")
        sal = sal_el.get_text(strip=True) if sal_el else ""
        desc_el = card.select_one(".description, .snippet, .summary, p")
        desc = desc_el.get_text(strip=True)[:500] if desc_el else ""
        out.append({"id": f"{prefix}:{_hid(href or title)}", "source": source,
                     "title": title, "company": company, "salary": sal,
                     "url": href, "description": desc, "published_at": ""})
    return out


def _scrape_site(url, prefix, source, kw=""):
    s = _soup(url)
    if not s:
        return []
    return _parse_job_cards(s, prefix, source, url.split("/")[0] + "//" + url.split("/")[2], kw)


def search_wellfound(kw=""):
    return _scrape_site("https://wellfound.com/jobs", "wellfound", "Wellfound (AngelList)", kw)

def search_stackoverflow(kw=""):
    return _scrape_site(f"https://stackoverflow.com/jobs?q={kw}" if kw else "https://stackoverflow.com/jobs", "so", "StackOverflow Jobs", kw)

def search_builtin(kw=""):
    return _scrape_site(f"https://builtin.com/jobs?search={kw}" if kw else "https://builtin.com/jobs", "builtin", "BuiltIn", kw)

def search_arcdev(kw=""):
    return _scrape_site("https://arc.dev/remote-jobs", "arcdev", "Arc.dev", kw)

def search_ycjobs(kw=""):
    return _scrape_site("https://www.ycombinator.com/jobs", "ycjobs", "YCombinator Jobs", kw)

def search_keyvalues(kw=""):
    return _scrape_site("https://keyvalues.com", "keyvalues", "Key Values", kw)

def search_glassdoor(kw=""):
    return _scrape_site(f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={kw}" if kw else "https://www.glassdoor.com/Job/jobs.htm", "glassdoor", "Glassdoor Jobs", kw)

def search_devitjobs(kw=""):
    return _scrape_site(f"https://devitjobs.com/jobs?q={kw}" if kw else "https://devitjobs.com/jobs", "devitjobs", "DevITjobs", kw)

def search_relocateme(kw=""):
    return _scrape_site("https://relocate.me/search", "relocateme", "Relocate.me", kw)

def search_swissdevjobs(kw=""):
    return _scrape_site(f"https://swissdevjobs.ch/jobs/{kw}" if kw else "https://swissdevjobs.ch/jobs", "swissdev", "SwissDevJobs", kw)

def search_germantechjobs(kw=""):
    return _scrape_site(f"https://germantechjobs.de/jobs/{kw}" if kw else "https://germantechjobs.de/jobs", "germtech", "GermanTech Jobs", kw)

def search_4dayweek(kw=""):
    params = {"q": kw} if kw else {}
    out = []
    for pg in range(1, 5):
        params["page"] = pg
        r = _get("https://4dayweek.io/api/jobs", params=params)
        if not r:
            break
        data = r.json()
        for j in data.get("jobs", []):
            title = j.get("title", "")
            co = j.get("company_name", "")
            sal = j.get("salary", "") or ""
            slug = j.get("slug", "")
            out.append({"id": f"4dw:{j.get('id','')}", "source": "4dayweek.io",
                         "title": title, "company": co, "salary": sal,
                         "url": f"https://4dayweek.io/job/{slug}" if slug else "https://4dayweek.io",
                         "description": f"{title} | {j.get('work_arrangement','')} | {j.get('category','')}",
                         "published_at": ""})
        if not data.get("has_more"):
            break
    return out

def search_remoteco(kw=""):
    return _scrape_site("https://remote.co/remote-jobs/developer/", "remoteco", "Remote.co", kw)

def search_justremote(kw=""):
    return _scrape_site(f"https://justremote.co/remote-developer-jobs?search={kw}" if kw else "https://justremote.co/remote-developer-jobs", "justremote", "JustRemote", kw)

def search_jobspresso(kw=""):
    return _scrape_site("https://jobspresso.co/remote-work/", "jobspresso", "Jobspresso", kw)

def search_dailyremote(kw=""):
    return _scrape_site(f"https://dailyremote.com/remote-software-development-jobs?search={kw}" if kw else "https://dailyremote.com/remote-software-development-jobs", "dailyremote", "DailyRemote", kw)

def search_pangian(kw=""):
    return _scrape_site("https://pangian.com/job-travel-remote/", "pangian", "Pangian", kw)

def search_nodesk(kw=""):
    return _scrape_site("https://nodesk.co/remote-jobs/", "nodesk", "Nodesk", kw)

def search_remotecom(kw=""):
    return _scrape_site("https://remote.com/jobs", "remotecom", "Remote.com", kw)

def search_dynamitejobs(kw=""):
    return _scrape_site("https://dynamitejobs.com/remote-jobs", "dynamite", "Dynamite Jobs", kw)

def search_powertofly(kw=""):
    return _scrape_site("https://powertofly.com/jobs", "ptf", "PowerToFly", kw)

def search_turingcom(kw=""):
    return _scrape_site("https://turing.com/remote-developer-jobs", "turing", "Turing.com", kw)

def search_contra(kw=""):
    return _scrape_site("https://contra.com/opportunities", "contra", "Contra", kw)

def search_remotersnet(kw=""):
    return _scrape_site("https://remoters.net/jobs/", "remoters", "Remoters.net", kw)

def search_remotehub(kw=""):
    return _scrape_site("https://remotehub.com/remote-jobs", "remotehub", "RemoteHub", kw)

def search_euroremote(kw=""):
    return _scrape_site("https://euroremote.com", "euroremote", "EuroRemote", kw)

def search_talentcom(kw=""):
    return _scrape_site(f"https://www.talent.com/jobs?k={kw}" if kw else "https://www.talent.com/jobs", "talent", "Talent.com (Neuvoo)", kw)

def search_simplyhired(kw=""):
    return _scrape_site(f"https://www.simplyhired.com/search?q={kw}" if kw else "https://www.simplyhired.com/search", "simplyhired", "SimplyHired", kw)

def search_ziprecruiter(kw=""):
    return _scrape_site(f"https://www.ziprecruiter.com/jobs-search?search={kw}" if kw else "https://www.ziprecruiter.com/jobs", "zipr", "ZipRecruiter", kw)

def search_trovit(kw=""):
    return _scrape_site(f"https://www.trovit.com/index.php/cod.search_jobs/what_d.{kw}/" if kw else "https://www.trovit.com/job-offers", "trovit", "Trovit", kw)

def search_jobrapido(kw=""):
    return _scrape_site(f"https://us.jobrapido.com/?q={kw}" if kw else "https://us.jobrapido.com/", "jobrapido", "Jobrapido", kw)

def search_monster(kw=""):
    return _scrape_site(f"https://www.monster.com/jobs/search?q={kw}" if kw else "https://www.monster.com/jobs/search", "monster", "Monster", kw)

def search_careerbuilder(kw=""):
    return _scrape_site(f"https://www.careerbuilder.com/jobs?keywords={kw}" if kw else "https://www.careerbuilder.com/jobs", "cb", "CareerBuilder", kw)

def search_ladders(kw=""):
    return _scrape_site(f"https://www.theladders.com/jobs?keywords={kw}" if kw else "https://www.theladders.com/jobs", "ladders", "Ladders", kw)

def search_totaljobs(kw=""):
    return _scrape_site(f"https://www.totaljobs.com/jobs?keywords={kw}" if kw else "https://www.totaljobs.com/jobs", "totaljobs", "Totaljobs", kw)

def search_stepstone(kw=""):
    return _scrape_site(f"https://www.stepstone.de/jobs/{kw}" if kw else "https://www.stepstone.de/jobs", "stepstone", "StepStone", kw)

def search_seek(kw=""):
    return _scrape_site(f"https://www.seek.com.au/{kw}-jobs" if kw else "https://www.seek.com.au/jobs", "seek", "Seek", kw)

def search_naukri(kw=""):
    return _scrape_site(f"https://www.naukri.com/{kw.replace(' ','-')}-jobs" if kw else "https://www.naukri.com/jobs", "naukri", "Naukri", kw)

def search_bayt(kw=""):
    return _scrape_site(f"https://www.bayt.com/en/international/jobs/{kw.replace(' ','-')}-jobs/" if kw else "https://www.bayt.com/en/international/jobs/", "bayt", "Bayt", kw)

def search_cvlibrary(kw=""):
    return _scrape_site(f"https://www.cv-library.co.uk/search-jobs?q={kw}" if kw else "https://www.cv-library.co.uk/search-jobs", "cvlib", "CV-Library", kw)

def search_infojobs(kw=""):
    return _scrape_site(f"https://www.infojobs.net/ofertas-trabajo/{kw.replace(' ','-')}" if kw else "https://www.infojobs.net/ofertas-trabajo/", "infojobs", "InfoJobs", kw)

def search_jobstreet(kw=""):
    return _scrape_site(f"https://www.jobstreet.com/jobs?q={kw}" if kw else "https://www.jobstreet.com/jobs", "jobstreet", "JobStreet", kw)

def search_blockchain_jobs(kw=""):
    return _scrape_site("https://blockchainjobs.co", "bcjobs", "Blockchain Jobs", kw)

def search_cryptojobs(kw=""):
    return _scrape_site("https://crypto.jobs", "cjobs", "Crypto Jobs", kw)

def search_aijobs(kw=""):
    return _scrape_site(f"https://aijobs.net/?q={kw}" if kw else "https://aijobs.net/", "aijobs", "AI Jobs", kw)

def search_mljobs(kw=""):
    return _scrape_site("https://mljobs.io", "mljobs", "MLJobs", kw)

def search_datajobs(kw=""):
    return _scrape_site("https://datajobs.com", "datajobs", "DataJobs", kw)

def search_kagglejobs(kw=""):
    return _scrape_site("https://kaggle.com/discussions?topic=jobs", "kaggle", "Kaggle Jobs", kw)

def search_dribbble(kw=""):
    return search_dribbble_rss()

def search_behance(kw=""):
    return _scrape_site("https://www.behance.net/joblist", "behance", "Behance Jobs", kw)

def search_producthunt(kw=""):
    return _scrape_site("https://www.producthunt.com/jobs", "ph", "Product Hunt Jobs", kw)

def search_angellist(kw=""):
    return _scrape_site("https://angel.co/jobs", "angel", "AngelList", kw)

def search_gamejobs(kw=""):
    return _scrape_site("https://gamejobs.co", "gamejobs", "GameJobs.co", kw)

def search_hitmarker(kw=""):
    return _scrape_site(f"https://hitmarker.net/jobs?search={kw}" if kw else "https://hitmarker.net/jobs", "hitmarker", "Hitmarker", kw)

def search_climatetechlist(kw=""):
    return _scrape_site("https://climatetechlist.com", "climate", "ClimateTechList", kw)

def search_ethicaljobs(kw=""):
    return _scrape_site(f"https://www.ethicaljobs.com.au/jobs?keywords={kw}" if kw else "https://www.ethicaljobs.com.au/jobs", "ethical", "EthicalJobs", kw)

def search_idealist(kw=""):
    return _scrape_site(f"https://www.idealist.org/en/jobs?q={kw}" if kw else "https://www.idealist.org/en/jobs", "idealist", "Idealist", kw)

def search_habrfreelance(kw=""):
    return _scrape_site("https://freelance.habr.com/tasks", "habrfl", "Habr Freelance", kw)

def search_flru(kw=""):
    return _scrape_site("https://www.fl.ru/projects/", "flru", "FL.ru", kw)

def search_kwork(kw=""):
    return _scrape_site(f"https://kwork.ru/projects?keyword={kw}" if kw else "https://kwork.ru/projects", "kwork", "Kwork", kw)

def search_guru(kw=""):
    return _scrape_site(f"https://www.guru.com/d/freelancer-jobs/q/{kw}/" if kw else "https://www.guru.com/d/freelancer-jobs/", "guru", "Guru.com", kw)

def search_peopleperhour(kw=""):
    return _scrape_site(f"https://www.peopleperhour.com/freelance-jobs?keyword={kw}" if kw else "https://www.peopleperhour.com/freelance-jobs", "pph", "PeoplePerHour", kw)


# =====================================================================
# ADAPTER REGISTRY
# =====================================================================

_RSS_ONLY = {"We Work Remotely", "Authentic Jobs", "CryptoCurrencyJobs",
             "Dribbble Jobs", "Python.org Jobs", "LaraJobs"}

ADAPTERS: dict[str, callable] = {
    # Free API
    "RemoteOK": search_remoteok,
    "Remotive": search_remotive,
    "Working Nomads": search_working_nomads,
    "The Muse": search_themuse,
    "Arbeitnow": search_arbeitnow,
    "Himalayas": search_himalayas,
    "HN Who Is Hiring": search_hn_hiring,
    "Jobicy": search_jobicy,
    "Landing.jobs": search_landingjobs,
    # RSS
    "We Work Remotely": search_wwr,
    "Authentic Jobs": search_authentic_jobs,
    "CryptoCurrencyJobs": search_cryptocurrencyjobs_rss,
    "Dribbble Jobs": search_dribbble_rss,
    "Python.org Jobs": search_pythonjobs_rss,
    "LaraJobs": search_larajobs_rss,
    # Key-based API
    "Jooble": search_jooble,
    "Adzuna": search_adzuna,
    "CareerJet": search_careerjet,
    "Reed.co.uk": search_reed,
    "Findwork.dev": search_findwork,
    "USAJobs": search_usajobs,
    # JSON endpoints
    "NoFluffJobs": search_nofluffjobs,
    "Dice": search_dice,
    "Crossover": search_crossover,
    "Web3.career": search_web3career,
    "CryptoJobsList": search_cryptojobslist,
    "SwissDevJobs": search_swissdevjobs,
    "GermanTech Jobs": search_germantechjobs,
    # Scrape (HTML)
    "Wellfound (AngelList)": search_wellfound,
    "StackOverflow Jobs": search_stackoverflow,
    "BuiltIn": search_builtin,
    "Arc.dev": search_arcdev,
    "YCombinator Jobs": search_ycjobs,
    "Key Values": search_keyvalues,
    "Glassdoor Jobs": search_glassdoor,
    "DevITjobs": search_devitjobs,
    "Relocate.me": search_relocateme,
    "4dayweek.io": search_4dayweek,
    "Remote.co": search_remoteco,
    "JustRemote": search_justremote,
    "Jobspresso": search_jobspresso,
    "DailyRemote": search_dailyremote,
    "Pangian": search_pangian,
    "Nodesk": search_nodesk,
    "Remote.com": search_remotecom,
    "Dynamite Jobs": search_dynamitejobs,
    "PowerToFly": search_powertofly,
    "Turing.com": search_turingcom,
    "Contra": search_contra,
    "Remoters.net": search_remotersnet,
    "RemoteHub": search_remotehub,
    "EuroRemote": search_euroremote,
    "Talent.com (Neuvoo)": search_talentcom,
    "SimplyHired": search_simplyhired,
    "ZipRecruiter": search_ziprecruiter,
    "Trovit": search_trovit,
    "Jobrapido": search_jobrapido,
    "Monster": search_monster,
    "CareerBuilder": search_careerbuilder,
    "Ladders": search_ladders,
    "Totaljobs": search_totaljobs,
    "StepStone": search_stepstone,
    "Seek": search_seek,
    "Naukri": search_naukri,
    "Bayt": search_bayt,
    "CV-Library": search_cvlibrary,
    "InfoJobs": search_infojobs,
    "JobStreet": search_jobstreet,
    "Blockchain Jobs": search_blockchain_jobs,
    "Crypto Jobs": search_cryptojobs,
    "AI Jobs": search_aijobs,
    "MLJobs": search_mljobs,
    "DataJobs": search_datajobs,
    "Kaggle Jobs": search_kagglejobs,
    "Behance Jobs": search_behance,
    "Product Hunt Jobs": search_producthunt,
    "AngelList": search_angellist,
    "GameJobs.co": search_gamejobs,
    "Hitmarker": search_hitmarker,
    "ClimateTechList": search_climatetechlist,
    "EthicalJobs": search_ethicaljobs,
    "Idealist": search_idealist,
    "Habr Freelance": search_habrfreelance,
    "FL.ru": search_flru,
    "Kwork": search_kwork,
    "Guru.com": search_guru,
    "PeoplePerHour": search_peopleperhour,
}


# =====================================================================
# Orchestrator
# =====================================================================

def search_all(text: str) -> list[dict]:
    enabled = load_enabled_sources()
    results: list[dict] = []
    for name in enabled:
        adapter = ADAPTERS.get(name)
        if not adapter:
            log.warning("No adapter for: %s", name)
            continue
        try:
            batch = adapter() if name in _RSS_ONLY else adapter(text)
            log.info("%s → %d", name, len(batch))
            results += batch
        except Exception as e:
            log.error("%s crashed: %s", name, e)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    a = p.parse_args()
    v = search_all(a.text)
    print(json.dumps(v, ensure_ascii=False, indent=2))
