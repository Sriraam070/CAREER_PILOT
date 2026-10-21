"""Greenhouse job boards. params: {"board": "companyslug"}"""
import html

from . import http_json, matches_keywords, strip_html


def fetch(company, params, keywords):
    # the API returns job content as escaped HTML, hence html.unescape below
    data = http_json(f"https://boards-api.greenhouse.io/v1/boards/{params['board']}/jobs?content=true")
    return [{"company": company, "title": j["title"], "location": (j.get("location") or {}).get("name", ""),
             "url": j.get("absolute_url", ""), "description": strip_html(html.unescape(j.get("content", ""))),
             "posted_at": j.get("updated_at"), "external_id": str(j["id"]), "source": "greenhouse",
             "apply_kind": "greenhouse"}
            for j in data.get("jobs", []) if matches_keywords(j["title"], keywords)]
