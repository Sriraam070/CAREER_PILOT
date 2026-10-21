"""SmartRecruiters (Visa, Freshworks, ...). params: {"company_id": "Visa", "country": "in"}"""
from . import http_json, matches_keywords, q, strip_html


def fetch(company, params, keywords, max_jobs=60):
    cid = params["company_id"]
    out = []
    for kw in keywords or [""]:
        url = f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?limit=50&q={q(kw)}"
        if params.get("country"):
            url += f"&country={params['country']}"
        for p in http_json(url).get("content", []):
            if any(o["external_id"] == p["id"] for o in out) or not matches_keywords(p["name"], keywords):
                continue
            loc = p.get("location") or {}
            out.append({"company": company, "title": p["name"],
                        "location": ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                        "url": f"https://jobs.smartrecruiters.com/{cid}/{p['id']}",
                        "posted_at": p.get("releasedDate"), "external_id": p["id"], "source": "smartrecruiters"})
    for j in out[:max_jobs]:
        try:
            d = http_json(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings/{j['external_id']}")
            secs = (d.get("jobAd") or {}).get("sections", {})
            j["description"] = "\n\n".join(strip_html(s.get("text", "")) for s in secs.values() if isinstance(s, dict))
        except Exception:
            pass
    return out[:max_jobs]
