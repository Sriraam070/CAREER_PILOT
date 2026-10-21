"""Adzuna job search API (free key: developer.adzuna.com). Covers companies without
a public careers API (TCS, Infosys, Zoho, ...) by searching their name.
params: {"what_or": "...", "where": "Chennai"}  · needs ADZUNA_APP_ID / ADZUNA_APP_KEY
"""
import os

from . import http_json, matches_keywords, q


def fetch(company, params, keywords):
    app_id, key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and key):
        raise RuntimeError("ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
    out = []
    for kw in keywords or ["developer"]:
        url = (f"https://api.adzuna.com/v1/api/jobs/in/search/1?app_id={app_id}&app_key={key}"
               f"&results_per_page=50&what={q(kw)}&company={q(params.get('company', company))}"
               f"&max_days_old={params.get('max_days_old', 30)}")
        if params.get("where"):
            url += f"&where={q(params['where'])}"
        for j in http_json(url).get("results", []):
            if any(o["external_id"] == j["id"] for o in out) or not matches_keywords(j["title"], keywords):
                continue
            sal = ""
            if j.get("salary_min"):
                sal = f"₹{j['salary_min'] / 1e5:.1f}L–₹{(j.get('salary_max') or j['salary_min']) / 1e5:.1f}L"
                sal += " (estimated)" if j.get("salary_is_predicted") == "1" else ""
            out.append({"company": company, "title": j["title"], "location": (j.get("location") or {}).get("display_name", ""),
                        "url": j.get("redirect_url", ""), "description": j.get("description", ""),
                        "posted_at": j.get("created"), "external_id": str(j["id"]), "source": "adzuna", "salary_text": sal})
    return out
