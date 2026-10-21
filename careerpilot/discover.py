"""Discover → dedupe → evaluate → queue → notify."""
import json

from . import companies, db, evaluate as ev, notify
from .config import settings
from .sources import ADAPTERS


def run(company_filter=None, notify_new=True, log=print):
    s = settings()
    prefs, auto = s["preferences"], s["automation"]
    companies.sync_to_db()
    summary = {"companies": 0, "fetched": 0, "new": 0, "duplicates": 0, "queued": 0, "errors": {}}
    new_good = []
    for co in companies.all_companies():
        if company_filter and company_filter.lower() not in co["name"].lower():
            continue
        if not set(co["tiers"]) & set(prefs["company_tiers"]) and co["tiers"]:
            continue
        fetch = ADAPTERS.get(co["ats"] or "")
        if not fetch:
            continue
        summary["companies"] += 1
        try:
            jobs = fetch(co["name"], co["ats_params"], prefs["keywords"])
        except Exception as e:  # one broken source must not stop the run
            summary["errors"][co["name"]] = f"{type(e).__name__}: {e}"[:200]
            log(f"  ✗ {co['name']}: {e}")
            continue
        log(f"  {co['name']}: {len(jobs)} matching jobs")
        for j in jobs:
            summary["fetched"] += 1
            job_id, is_new = db.upsert_job(j)
            if not is_new:
                summary["duplicates"] += 1
                continue
            summary["new"] += 1
            r = ev.evaluate(job_id)
            if r["passes"] and r["match"] >= prefs["min_match_to_queue"] and auto["queue_for_approval"]:
                from . import apply
                apply.queue(job_id)
                summary["queued"] += 1
            if r["passes"] and r["match"] >= prefs["min_match_to_notify"]:
                new_good.append(job_id)
    if notify_new and new_good:
        notify.new_jobs(new_good)
    db.audit("discover", json.dumps({k: v for k, v in summary.items() if k != "errors"}))
    return summary


def add_manual(company, title, url="", description="", location="", salary_text=""):
    job_id, is_new = db.upsert_job({"company": company, "title": title, "url": url, "description": description,
                                    "location": location, "salary_text": salary_text, "source": "manual"})
    r = ev.evaluate(job_id)
    prefs = settings()["preferences"]
    if is_new and r["passes"] and r["match"] >= prefs["min_match_to_queue"] and settings()["automation"]["queue_for_approval"]:
        from . import apply
        r["queued"] = bool(apply.queue(job_id))
    return job_id, is_new, r
