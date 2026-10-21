"""Score each job against the CV and preferences.

`probability` is a transparent heuristic ESTIMATE of getting a positive response
(screen/OA/interview invite). It is not a prediction of an offer and never a
guarantee; every place it is shown is labelled as an estimate.
"""
import datetime as dt
import re

from jhb import skills as sk

from . import companies, db
from .config import cv_text, settings

TIER_BASE = {"MARQUEE": 5, "SUPER DREAM": 8, "DREAM": 11, "PRIME": 15, "NEW": 16, "DAY SHARING": 22}
DISCLAIMER = "Estimated response probability: a heuristic estimate, not a guarantee."

_U = r"(?:l|lpa|lakhs?|lac)\b"
_N = r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)"
_RANGE = re.compile(_N + r"\s*(?:" + _U + r")?\s*(?:-|–|to)\s*" + _N + r"\s*" + _U, re.I)
_ONE = re.compile(_N + r"\s*" + _U, re.I)


def parse_salary_lpa(text):
    """'6 - 9 LPA' → (6.0, 9.0); '₹12L' → (12.0, 12.0); None if no salary in lakhs."""
    m = _RANGE.search(text or "")
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _ONE.search(text or "")
    return (float(m.group(1)),) * 2 if m else None


def _days_old(posted):
    if not posted:
        return None
    m = re.search(r"(\d+)\+?\s*days?\s*ago", str(posted), re.I)
    if m:
        return int(m.group(1))
    if re.search(r"today|just", str(posted), re.I):
        return 0
    if re.search(r"yesterday", str(posted), re.I):
        return 1
    try:
        return (dt.datetime.now() - dt.datetime.fromisoformat(str(posted)[:19].replace("Z", ""))).days
    except ValueError:
        return None


def probability(match, years_req, my_years, tiers, days_old):
    reasons = []
    base = max([TIER_BASE.get(t, 12) for t in tiers] or [12])
    reasons.append(f"base {base}% for tier {', '.join(tiers) or 'unknown'}")
    p = base * min(2.0, max(0.2, (match / 60) ** 1.5))
    reasons.append(f"skill match {match}%")
    if years_req is not None:
        if years_req > my_years + 1:
            p *= 0.35; reasons.append(f"asks {years_req}+ yrs vs your {my_years}")
        elif years_req <= my_years:
            p *= 1.2; reasons.append("experience fits")
    if days_old is not None:
        if days_old <= 7:
            p *= 1.3; reasons.append("posted in the last week")
        elif days_old > 30:
            p *= 0.6; reasons.append("posting is over a month old")
    return int(min(60, max(1, round(p)))), reasons


def passes_preferences(job, prefs):
    """Returns (ok, reason). Used to decide what gets queued and notified."""
    title, loc = job["title"].lower(), (job.get("location") or "").lower()
    if any(x.lower() in title for x in prefs["exclude_keywords"]):
        return False, "title has an excluded keyword"
    if prefs["locations"] and loc and not any(l.lower() in loc for l in prefs["locations"]):
        return False, f"location '{job.get('location')}' not in your list"
    yrs = job.get("years_required")
    if yrs is not None and yrs > prefs["max_years_required"]:
        return False, f"asks {yrs}+ years"
    if prefs.get("min_salary_lpa"):
        sal = parse_salary_lpa(job.get("salary_text") or job.get("description"))
        if sal and sal[1] < prefs["min_salary_lpa"]:
            return False, f"salary up to {sal[1]}L is below your {prefs['min_salary_lpa']}L"
    return True, "ok"


def evaluate(job_id):
    job = db.get_job(job_id)
    s = settings()
    cv = cv_text()
    text = f"{job['title']}\n{job['description'] or ''}"
    score, hits, gaps = sk.match_score(text, cv)
    found = sorted(sk.extract(text))
    years = sk.years_required(job["description"] or "")
    tiers = companies.tier_of(job["company"])
    prob, reasons = probability(score, years, s["profile"].get("years_experience") or 0, tiers, _days_old(job["posted_at"]))
    job.update(years_required=years)
    ok, why = passes_preferences(job, s["preferences"])
    db.update_job(job_id, match_score=score, skills=found, gaps=gaps, years_required=years, probability=prob,
                  fit_notes=("; ".join(reasons) + ("" if ok else f" | filtered: {why}")))
    return {"id": job_id, "match": score, "skills": found, "gaps": gaps, "years": years,
            "probability": prob, "reasons": reasons, "passes": ok, "why": why}
