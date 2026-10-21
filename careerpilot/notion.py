"""Two-way sync with your Notion "Job Tracker" database.

Needs NOTION_TOKEN (an internal integration shared with the database) and
NOTION_DATABASE_ID. The "Login ID" and "Password" columns are dropped the moment
a page is read and are never stored, logged, written or sent anywhere.
"""
import json
import urllib.request

from . import db
from .config import env

API = "https://api.notion.com/v1"
NEVER_READ = {"Login ID", "Password"}


def _req(method, path, body=None):
    token = env("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN not set (see README → Notion)")
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _plain(prop):
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in v or [])
    if t == "select":
        return (v or {}).get("name")
    if t == "multi_select":
        return [o["name"] for o in v or []]
    if t == "date":
        return (v or {}).get("start")
    return v


def pages():
    dbid, out, cursor = env("NOTION_DATABASE_ID"), [], None
    while True:
        body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        r = _req("POST", f"/databases/{dbid}/query", body)
        for p in r["results"]:
            props = {k: _plain(v) for k, v in p["properties"].items() if k not in NEVER_READ}
            out.append({"id": p["id"], "url": p["url"], **props})
        if not r.get("has_more"):
            return out
        cursor = r["next_cursor"]


def pull_companies():
    """Company rows (no Job Name) → companies table. Returns count."""
    n = 0
    with db.conn() as c:
        for p in pages():
            if not p.get("Company") or p.get("Job Name"):
                continue
            c.execute("""INSERT INTO companies(name, tiers, priority, careers_url, notion_url, updated_at)
                         VALUES (?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET tiers=excluded.tiers,
                         priority=excluded.priority, careers_url=COALESCE(excluded.careers_url, companies.careers_url),
                         notion_url=excluded.notion_url, updated_at=excluded.updated_at""",
                      (p["Company"], json.dumps(p.get("COMPANY TYPE") or []), p.get("Priority"),
                       p.get("Careers Portal"), p["url"], db.now()))
            n += 1
    db.audit("notion_pull", f"{n} companies")
    return n


def push_applications():
    """One Notion row per application (Company + Job Name). Creates or updates. Returns count."""
    dbid = env("NOTION_DATABASE_ID")
    apps = db.rows("""SELECT a.*, j.company, j.title, j.url, j.external_id, j.match_score, c.tiers
                      FROM applications a JOIN jobs j ON j.id=a.job_id
                      LEFT JOIN companies c ON c.name=j.company""")
    n = 0
    for a in apps:
        props = {
            "Company": {"title": [{"text": {"content": a["company"]}}]},
            "Job Name": {"rich_text": [{"text": {"content": a["title"][:200]}}]},
            "Job URL": {"url": a["url"] or None},
            "Job Code": {"rich_text": [{"text": {"content": str(a["external_id"] or "")[:100]}}]},
            "Status": {"select": {"name": a["status"]}},
            "Notes": {"rich_text": [{"text": {"content": f"Match {a['match_score']}% · {a['next_step'] or ''}"[:1900]}}]},
        }
        if a["applied_at"]:
            props["Date Applied"] = {"date": {"start": a["applied_at"][:10]}}
        if a["tiers"]:
            props["COMPANY TYPE"] = {"multi_select": [{"name": t} for t in json.loads(a["tiers"])]}
        if a["notion_page"]:
            _req("PATCH", f"/pages/{a['notion_page']}", {"properties": props})
        else:
            page = _req("POST", "/pages", {"parent": {"database_id": dbid}, "properties": props})
            with db.conn() as c:
                c.execute("UPDATE applications SET notion_page=? WHERE id=?", (page["id"], a["id"]))
        n += 1
    db.audit("notion_push", f"{n} applications")
    return n
