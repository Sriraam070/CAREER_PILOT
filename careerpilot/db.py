"""SQLite store: companies, jobs, applications, status history, approvals, audit log."""
import datetime as dt
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  name TEXT PRIMARY KEY, tiers TEXT, priority TEXT, careers_url TEXT,
  ats TEXT, ats_params TEXT, notion_url TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, source TEXT, external_id TEXT,
  company TEXT, title TEXT, location TEXT, url TEXT, description TEXT,
  posted_at TEXT, discovered_at TEXT, salary_text TEXT, years_required INTEGER,
  skills TEXT, match_score INTEGER, gaps TEXT, probability INTEGER, fit_notes TEXT,
  state TEXT DEFAULT 'new'   -- new | queued | skipped | applied | closed
);
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY, job_id INTEGER UNIQUE REFERENCES jobs(id),
  status TEXT, applied_at TEXT, updated_at TEXT, next_step TEXT,
  deadline TEXT, interview_at TEXT, notes TEXT, notion_page TEXT
);
CREATE TABLE IF NOT EXISTS status_history (
  id INTEGER PRIMARY KEY, application_id INTEGER, status TEXT, at TEXT, source TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY, job_id INTEGER, kind TEXT, payload TEXT,
  sensitive_fields TEXT, state TEXT DEFAULT 'pending',  -- pending | approved | rejected | done
  created_at TEXT, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, at TEXT, action TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS seen_emails (msg_id TEXT PRIMARY KEY, at TEXT);
"""

STATUSES = ["Not Applied", "Applied", "OA/Test", "Interview", "Offer", "Rejected", "Withdrawn"]


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def rows(sql, params=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def audit(action, detail=""):
    with conn() as c:
        c.execute("INSERT INTO audit(at, action, detail) VALUES (?,?,?)", (now(), action, str(detail)[:2000]))


# ── dedup ────────────────────────────────────────────────────────────

def _norm(s):
    s = (s or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def fingerprint(company, title, location="", external_id=""):
    """Same company + normalised title + city = same opening, whatever site it came from."""
    city = _norm(location).split(" ")[0] if location else ""
    key = f"{_norm(company)}|{_norm(title)}|{city}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def upsert_job(job):
    """Insert a job unless an equivalent one exists. Returns (id, is_new)."""
    fp = fingerprint(job["company"], job["title"], job.get("location", ""))
    with conn() as c:
        r = c.execute("SELECT id FROM jobs WHERE fingerprint=? OR (url=? AND url!='')",
                      (fp, job.get("url", ""))).fetchone()
        if r:
            return r["id"], False
        cols = ["fingerprint", "source", "external_id", "company", "title", "location", "url",
                "description", "posted_at", "salary_text", "discovered_at"]
        vals = [fp, job.get("source"), job.get("external_id"), job["company"], job["title"],
                job.get("location"), job.get("url", ""), job.get("description", ""),
                job.get("posted_at"), job.get("salary_text"), now()]
        cur = c.execute(f"INSERT INTO jobs({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        return cur.lastrowid, True


def update_job(job_id, **fields):
    if not fields:
        return
    fields = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in fields.items()}
    with conn() as c:
        c.execute(f"UPDATE jobs SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", [*fields.values(), job_id])


def get_job(job_id):
    r = rows("SELECT * FROM jobs WHERE id=?", (job_id,))
    return r[0] if r else None


def set_status(job_id, status, source="manual", detail="", **extra):
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with conn() as c:
        app = c.execute("SELECT id, status FROM applications WHERE job_id=?", (job_id,)).fetchone()
        if app and app["status"] == status and not extra:
            return app["id"], False
        if app:
            app_id = app["id"]
            sets = {"status": status, "updated_at": now(), **extra}
            c.execute(f"UPDATE applications SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", [*sets.values(), app_id])
        else:
            cur = c.execute("INSERT INTO applications(job_id, status, applied_at, updated_at) VALUES (?,?,?,?)",
                            (job_id, status, now() if status != "Not Applied" else None, now()))
            app_id = cur.lastrowid
            if extra:
                c.execute(f"UPDATE applications SET {', '.join(f'{k}=?' for k in extra)} WHERE id=?", [*extra.values(), app_id])
        if status == "Applied":
            c.execute("UPDATE applications SET applied_at=COALESCE(applied_at, ?) WHERE id=?", (now(), app_id))
            c.execute("UPDATE jobs SET state='applied' WHERE id=?", (job_id,))
        c.execute("INSERT INTO status_history(application_id, status, at, source, detail) VALUES (?,?,?,?,?)",
                  (app_id, status, now(), source, detail))
    return app_id, True


def already_applied(job_id):
    r = rows("SELECT status FROM applications WHERE job_id=? AND status!='Not Applied'", (job_id,))
    return bool(r)
