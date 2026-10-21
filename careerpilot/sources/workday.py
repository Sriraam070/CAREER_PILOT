"""Workday career sites (Adobe, Salesforce, Walmart, PayPal, Mastercard, ...).

params: {"host": "adobe.wd5.myworkdayjobs.com", "tenant": "adobe", "site": "external_experienced"}
Uses the same public JSON endpoint the career site's own search page calls.
"""
from . import http_json, matches_keywords, strip_html


def fetch(company, params, keywords, max_jobs=60):
    host, tenant, site = params["host"], params["tenant"], params["site"]
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    jobs, seen = [], set()
    for kw in keywords or [""]:
        data = http_json(f"{base}/jobs", {"appliedFacets": {}, "limit": 20, "offset": 0,
                                         "searchText": f"{kw} {params.get('location', '')}".strip()})
        for p in data.get("jobPostings", []):
            path = p.get("externalPath", "")
            if path in seen or not matches_keywords(p.get("title", ""), keywords):
                continue
            seen.add(path)
            jobs.append({"company": company, "title": p.get("title", ""), "location": p.get("locationsText", ""),
                         "url": f"https://{host}/{site}{path}", "posted_at": p.get("postedOn"),
                         "external_id": (p.get("bulletFields") or [path])[0], "source": "workday", "_path": path})
    for j in jobs[:max_jobs]:
        try:  # detail call for the full JD
            d = http_json(f"{base}{j.pop('_path')}").get("jobPostingInfo", {})
            j["description"] = strip_html(d.get("jobDescription", ""))
            j["location"] = d.get("location", j["location"])
        except Exception:
            j.pop("_path", None)
    return jobs[:max_jobs]
