"""Job source adapters.

Every adapter is `fetch(company_name, params, keywords) -> list[dict]` returning
normalised jobs: company, title, location, url, description, posted_at,
external_id, source. All of them use public, unauthenticated endpoints that the
companies' own career sites use; none log in or scrape behind a login.
"""
import html
import json
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (CareerPilot personal job-search assistant)"


def http_json(url, data=None, headers=None, timeout=30):
    body = json.dumps(data).encode() if data is not None else None
    h = {"User-Agent": UA, "Accept": "application/json"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def strip_html(s):
    s = re.sub(r"(?i)<(br|/p|/li|/h\d|/div)\s*/?>", "\n", s or "")
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def matches_keywords(title, keywords):
    t = title.lower()
    return not keywords or any(k.lower() in t for k in keywords)


def q(s):
    return urllib.parse.quote(s)


from . import adzuna, amazon, ashby, greenhouse, lever, smartrecruiters, workday  # noqa: E402

ADAPTERS = {
    "workday": workday.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "ashby": ashby.fetch,
    "amazon": amazon.fetch,
    "adzuna": adzuna.fetch,
}
