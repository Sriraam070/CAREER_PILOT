"""amazon.jobs public search. params: {"country": "IND"}"""
from . import http_json, matches_keywords, q, strip_html


def fetch(company, params, keywords):
    out = []
    for kw in keywords or ["software"]:
        url = (f"https://www.amazon.jobs/en/search.json?base_query={q(kw)}&result_limit=50"
               f"&normalized_country_code[]={params.get('country', 'IND')}&sort=recent")
        for j in http_json(url).get("jobs", []):
            if any(o["external_id"] == j["id_icims"] for o in out) or not matches_keywords(j["title"], keywords):
                continue
            desc = "\n\n".join([strip_html(j.get("description", "")), "Basic qualifications:\n" + strip_html(j.get("basic_qualifications", "")),
                                "Preferred qualifications:\n" + strip_html(j.get("preferred_qualifications", ""))])
            out.append({"company": company, "title": j["title"], "location": j.get("normalized_location", ""),
                        "url": "https://www.amazon.jobs" + j.get("job_path", ""), "description": desc,
                        "posted_at": j.get("posted_date"), "external_id": j["id_icims"], "source": "amazon"})
    return out
