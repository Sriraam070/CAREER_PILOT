"""Public API: plain functions + JSON-schema tool definitions.

This is the integration surface for the chatbot, the MCP server, and later
Jarvis: register TOOLS with any LLM and dispatch calls through `call(name, args)`.
Nothing here can submit an application or read sensitive data; approving is
a separate, explicitly user-driven function (`approve`) that the chatbot is NOT given.
"""
import datetime as dt
import json

from . import apply, companies, db, discover, evaluate, reports
from .config import settings, save_settings


def search_jobs(query="", company="", min_match=0, state="", limit=20):
    sql = "SELECT id, company, title, location, match_score, probability, state, posted_at, url FROM jobs WHERE 1=1"
    p = []
    if query:
        sql += " AND (title LIKE ? OR description LIKE ?)"; p += [f"%{query}%"] * 2
    if company:
        sql += " AND company LIKE ?"; p.append(f"%{company}%")
    if min_match:
        sql += " AND match_score >= ?"; p.append(min_match)
    if state:
        sql += " AND state = ?"; p.append(state)
    sql += " ORDER BY match_score DESC, discovered_at DESC LIMIT ?"; p.append(min(limit, 100))
    return db.rows(sql, p)


def job_details(job_id):
    j = db.get_job(job_id)
    if not j:
        return {"error": "not found"}
    j["skills"] = json.loads(j["skills"] or "[]"); j["gaps"] = json.loads(j["gaps"] or "[]")
    j["description"] = (j["description"] or "")[:6000]
    j["application"] = (db.rows("SELECT status, applied_at, next_step, interview_at, deadline FROM applications WHERE job_id=?", (job_id,)) or [None])[0]
    j["probability_note"] = evaluate.DISCLAIMER
    return j


def list_companies(tier=""):
    companies.sync_to_db()
    out = []
    for c in companies.all_companies():
        if tier and tier.upper() not in c["tiers"]:
            continue
        n = db.rows("SELECT COUNT(*) n, MAX(match_score) best FROM jobs WHERE company=?", (c["name"],))[0]
        out.append({"company": c["name"], "tiers": c["tiers"], "source": c["ats"], "jobs": n["n"], "best_match": n["best"]})
    return out


def pipeline_stats(days=30):
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    stage = {r["status"]: r["n"] for r in db.rows("SELECT status, COUNT(*) n FROM applications GROUP BY status")}
    return {"jobs_discovered": db.rows("SELECT COUNT(*) n FROM jobs WHERE discovered_at>=?", (since,))[0]["n"],
            "awaiting_approval": len(apply.pending()), "by_status": stage,
            "recent_changes": db.rows("""SELECT j.company, j.title, h.status, h.at, h.source FROM status_history h
                                         JOIN applications a ON a.id=h.application_id JOIN jobs j ON j.id=a.job_id
                                         ORDER BY h.at DESC LIMIT 10""")}


def skill_insights(days=30):
    start = dt.date.today() - dt.timedelta(days=days)
    m = reports.metrics(*reports.collect(start, dt.date.today()))
    return {"jobs_analysed": m["n_jobs"], "top_skills": [{"skill": s, "jobs": c, "pct": p, "in_cv": h} for s, _, c, p, h in m["top"][:20]],
            "gaps_to_learn": [{"skill": s, "jobs": c, "how": reports.LEARN.get(s, ("Official docs", ""))[0]} for s, _, c, _ in m["gaps"][:10]]}


def salary_info(company=""):
    jobs = search_jobs(company=company, limit=100)
    out = []
    for j in jobs:
        full = db.get_job(j["id"])
        sal = evaluate.parse_salary_lpa(full["salary_text"] or full["description"] or "")
        if sal:
            out.append({"company": j["company"], "title": j["title"], "lpa_min": sal[0], "lpa_max": sal[1], "text": full["salary_text"]})
    return out or {"note": "No salary stated in the jobs found. Most Indian postings omit it; check Glassdoor/AmbitionBox."}


def update_status(job_id, status, note=""):
    """Track a status change you report (e.g. 'I got an interview at X')."""
    _, changed = db.set_status(job_id, status, source="chat", detail=note)
    return {"ok": True, "changed": changed}


def add_job(company, title, url="", description="", location=""):
    job_id, new, ev = discover.add_manual(company, title, url, description, location)
    return {"job_id": job_id, "new": new, **ev}


def get_preferences():
    s = settings()
    return {"preferences": s["preferences"], "automation": s["automation"]}


def set_preference(section, key, value):
    if section not in ("preferences", "automation"):
        return {"error": "section must be preferences or automation"}
    s = settings()
    if key not in s[section]:
        return {"error": f"unknown key; valid: {list(s[section])}"}
    if section == "automation" and key == "auto_submit_simple_forms" and value:
        return {"error": "Turning on auto-submit must be done by you in Settings, not by chat."}
    s[section][key] = value
    save_settings(s)
    db.audit("settings", f"{section}.{key}={value!r} via chat")
    return {"ok": True, section: s[section]}


def pending_approvals():
    return [{"approval_id": a["id"], "job_id": a["job_id"], "company": a["company"], "title": a["title"],
             "match": a["match_score"], "state": a["state"]} for a in apply.pending()]


def run_discovery(company=""):
    return discover.run(company_filter=company or None, log=lambda *_: None)


def make_report(period="weekly", start="", end=""):
    return {"excel": str(reports.excel(period, start or None, end or None)), "powerbi_folder": str(reports.powerbi())}


def interview_prep(job_id):
    from . import prep
    path, md = prep.generate(job_id)
    return {"saved_to": str(path) if path else None, "prep": md[:12000]}


# approve() is deliberately not exposed as a chat tool.
def approve(approval_id, ok=True):
    return apply.decide(approval_id, ok, by="user")


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


S, I = {"type": "string"}, {"type": "integer"}
TOOLS = [
    {"name": "search_jobs", "description": "Search discovered jobs by keyword, company, minimum skill-match % or state (new/queued/applied/skipped).",
     "input_schema": _schema({"query": S, "company": S, "min_match": I, "state": S, "limit": I})},
    {"name": "job_details", "description": "Full details of one job: JD, skills, gaps, match, estimated response probability, application status.",
     "input_schema": _schema({"job_id": I}, ["job_id"])},
    {"name": "list_companies", "description": "Target companies from the user's Notion list with tier (MARQUEE, SUPER DREAM, DREAM, PRIME, NEW, DAY SHARING) and job counts.",
     "input_schema": _schema({"tier": S})},
    {"name": "pipeline_stats", "description": "Application pipeline: counts by status, jobs awaiting approval, recent status changes.",
     "input_schema": _schema({"days": I})},
    {"name": "skill_insights", "description": "Most requested skills across recent jobs, which the user has, and the top gaps to learn.",
     "input_schema": _schema({"days": I})},
    {"name": "salary_info", "description": "Salary ranges stated in discovered jobs, optionally for one company.",
     "input_schema": _schema({"company": S})},
    {"name": "update_status", "description": "Record an application status the user reports. status: Not Applied, Applied, OA/Test, Interview, Offer, Rejected, Withdrawn.",
     "input_schema": _schema({"job_id": I, "status": S, "note": S}, ["job_id", "status"])},
    {"name": "add_job", "description": "Add a job the user found (paste of JD and/or link) and score it.",
     "input_schema": _schema({"company": S, "title": S, "url": S, "description": S, "location": S}, ["company", "title"])},
    {"name": "get_preferences", "description": "Current job-search preferences and automation settings.", "input_schema": _schema({})},
    {"name": "set_preference", "description": "Change one preference (section 'preferences') or automation toggle (section 'automation'). Cannot enable auto-submit.",
     "input_schema": _schema({"section": S, "key": S, "value": {}}, ["section", "key", "value"])},
    {"name": "pending_approvals", "description": "Applications waiting for the user's approval. The user approves them in the Approvals tab, not via chat.",
     "input_schema": _schema({})},
    {"name": "run_discovery", "description": "Fetch new openings now from the target companies (optionally one company).",
     "input_schema": _schema({"company": S})},
    {"name": "make_report", "description": "Generate the Excel + Power BI report. period: daily, weekly, monthly, all, custom (with start/end YYYY-MM-DD).",
     "input_schema": _schema({"period": S, "start": S, "end": S})},
    {"name": "interview_prep", "description": "Generate a company- and role-specific interview prep pack for a job.",
     "input_schema": _schema({"job_id": I}, ["job_id"])},
]
FUNCS = {t["name"]: globals()[t["name"]] for t in TOOLS}


def call(name, args):
    if name not in FUNCS:
        return {"error": f"unknown tool {name}"}
    try:
        return FUNCS[name](**(args or {}))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
