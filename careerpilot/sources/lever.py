"""Lever job boards. params: {"site": "companyslug"}"""
import datetime as dt

from . import http_json, matches_keywords, strip_html


def fetch(company, params, keywords):
    data = http_json(f"https://api.lever.co/v0/postings/{params['site']}?mode=json")
    out = []
    for j in data:
        if not matches_keywords(j.get("text", ""), keywords):
            continue
        desc = j.get("descriptionPlain", "") + "\n\n" + "\n\n".join(
            f"{l.get('text', '')}\n{strip_html(l.get('content', ''))}" for l in j.get("lists", []))
        ts = j.get("createdAt")
        out.append({"company": company, "title": j["text"], "location": (j.get("categories") or {}).get("location", ""),
                    "url": j.get("hostedUrl", ""), "description": desc.strip(),
                    "posted_at": dt.datetime.fromtimestamp(ts / 1000).isoformat() if ts else None,
                    "external_id": j["id"], "source": "lever", "apply_kind": "lever"})
    return out
