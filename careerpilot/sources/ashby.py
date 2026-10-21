"""Ashby job boards. params: {"board": "companyslug"}"""
from . import http_json, matches_keywords


def fetch(company, params, keywords):
    data = http_json(f"https://api.ashbyhq.com/posting-api/job-board/{params['board']}?includeCompensation=true")
    return [{"company": company, "title": j["title"], "location": j.get("location", ""),
             "url": j.get("jobUrl", ""), "description": j.get("descriptionPlain", ""),
             "posted_at": j.get("publishedAt"), "external_id": j.get("id", ""), "source": "ashby",
             "salary_text": ((j.get("compensation") or {}).get("compensationTierSummary") or "")}
            for j in data.get("jobs", []) if matches_keywords(j["title"], keywords)]
