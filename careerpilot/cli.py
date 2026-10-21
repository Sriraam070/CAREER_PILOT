"""careerpilot CLI. Run `python -m careerpilot --help`."""
import argparse
import json
import subprocess
import sys

from . import apply, companies, db, discover, evaluate, reports
from .config import ROOT, settings


def p(obj):
    print(json.dumps(obj, indent=2, default=str) if not isinstance(obj, str) else obj)


def cmd_init(a):
    from .config import SETTINGS_PATH, DEFAULT_SETTINGS, save_settings
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        print("Created settings.yml: fill in the profile section.")
    env = ROOT / ".env"
    if not env.exists():
        env.write_text((ROOT / ".env.example").read_text())
        print("Created .env from .env.example: add your keys.")
    print(f"{companies.sync_to_db()} companies loaded from companies.yml")


def cmd_doctor(a):
    from .sources import ADAPTERS
    kw = settings()["preferences"]["keywords"][:1]
    cos = companies.load()
    for co in cos:
        if a.company and a.company.lower() not in co["name"].lower():
            continue
        fetch = ADAPTERS.get(co.get("ats"))
        if not fetch:
            print(f"  –  {co['name']:<24} {co.get('ats')}: no automatic source"); continue
        try:
            n = len(fetch(co["name"], co.get("params", {}), kw))
            co["verified"] = True
            print(f"  ✓  {co['name']:<24} {co['ats']}: OK ({n} '{kw[0]}' jobs)")
        except Exception as e:
            co["verified"] = False
            print(f"  ✗  {co['name']:<24} {co['ats']}: {type(e).__name__}: {str(e)[:90]}")
    companies.save(cos)


def cmd_discover(a):
    print("Discovering…")
    p(discover.run(company_filter=a.company))


def cmd_jobs(a):
    from .api import search_jobs
    for j in search_jobs(query=a.q or "", company=a.company or "", min_match=a.min, state=a.state or "", limit=a.limit):
        print(f"#{j['id']:<5} {j['match_score'] or 0:>3}%  est {j['probability'] or 0:>2}%  {j['state']:<8} "
              f"{j['company'][:18]:<18} {j['title'][:55]:<55} {j['location'] or ''}")
    print(f"\n* {evaluate.DISCLAIMER}")


def cmd_add(a):
    desc = sys.stdin.read() if a.description == "-" else (a.description or "")
    job_id, new, ev = discover.add_manual(a.company, a.title, a.url or "", desc, a.location or "")
    p({"job_id": job_id, "new": new, **ev})


def cmd_approvals(a):
    for r in apply.pending():
        print(f"[{r['id']}] {r['state']:<14} {r['match_score']}%  {r['company']} — {r['title']}\n      {r['url']}")


def cmd_approve(a):
    print(apply.decide(a.id, not a.reject))


def cmd_assist(a):
    p(apply.assist(a.id, headless=a.headless))


def cmd_submitted(a):
    apply.mark_submitted(a.id); print("Marked Applied.")


def cmd_queue(a):
    print(apply.queue(a.job) or "Not queued (already applied or already queued).")


def cmd_status(a):
    db.set_status(a.job, a.status, source="cli", detail=a.note or "")
    from . import notify
    notify.status_change(a.job)
    print("OK")


def cmd_inbox(a):
    from . import inbox
    p(inbox.check(days=a.days))


def cmd_report(a):
    path = reports.excel(a.period, a.start, a.end)
    print(f"Excel → {path}")
    print(f"Power BI CSVs → {reports.powerbi()}")


def cmd_prep(a):
    from . import prep
    path, md = prep.generate(a.job)
    print(md if path is None else f"Saved → {path}\n\n{md}")


def cmd_notion(a):
    from . import notion
    if a.direction == "pull":
        print(f"{notion.pull_companies()} companies pulled; {companies.sync_to_db()} in companies.yml")
    else:
        print(f"{notion.push_applications()} applications pushed to Notion")


def cmd_daily(a):
    """Everything a scheduled run does, each step independent."""
    s = settings()["automation"]
    steps = []
    if s["notion_sync"]:
        steps.append(("notion pull", lambda: __import__("careerpilot.notion", fromlist=["x"]).pull_companies()))
    if s["discover"]:
        steps.append(("discover", lambda: discover.run(log=lambda *_: None)))
    if s["check_inbox"]:
        steps.append(("inbox", lambda: __import__("careerpilot.inbox", fromlist=["x"]).check(days=3, log=lambda *_: None)))
    if s["notion_sync"]:
        steps.append(("notion push", lambda: __import__("careerpilot.notion", fromlist=["x"]).push_applications()))
    steps.append(("daily report", lambda: str(reports.excel("daily"))))
    for name, fn in steps:
        try:
            print(f"✓ {name}: {fn()}")
        except Exception as e:
            print(f"✗ {name}: {type(e).__name__}: {e}")
            db.audit("daily_error", f"{name}: {e}")


def cmd_chat(a):
    from . import assistant
    hist = []
    print("CareerPilot chat (Ctrl+C to quit)")
    while True:
        try:
            msg = input("\nyou › ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if msg:
            reply, hist = assistant.chat(hist, msg, on_tool=lambda n, i: print(f"  · {n}({json.dumps(i)[:80]})"))
            print(f"\ncareerpilot › {reply}")


def cmd_ui(a):
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "streamlit_app.py"),
                    "--server.address", "127.0.0.1", "--server.port", str(a.port)])


def cmd_mcp(a):
    from . import mcp_server
    mcp_server.main()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="careerpilot", description="AI job search & application assistant")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help, *args):
        sp = sub.add_parser(name, help=help)
        for flags, kw in args:
            sp.add_argument(*flags, **kw)
        sp.set_defaults(fn=fn)

    add("init", cmd_init, "create settings.yml / .env and load companies")
    add("doctor", cmd_doctor, "test each company's job source", (["--company"], {}))
    add("discover", cmd_discover, "fetch new jobs from target companies", (["--company"], {}))
    add("jobs", cmd_jobs, "list jobs", (["-q"], {}), (["--company"], {}), (["--min"], {"type": int, "default": 0}),
        (["--state"], {}), (["--limit"], {"type": int, "default": 30}))
    add("add-job", cmd_add, "add a job by hand", (["company"], {}), (["title"], {}), (["--url"], {}),
        (["--location"], {}), (["--description"], {"help": "text, or - for stdin"}))
    add("queue", cmd_queue, "queue a job for your approval", (["job"], {"type": int}))
    add("approvals", cmd_approvals, "list applications awaiting you")
    add("approve", cmd_approve, "approve (or --reject) an application", (["id"], {"type": int}), (["--reject"], {"action": "store_true"}))
    add("assist", cmd_assist, "open + pre-fill an APPROVED application (sensitive fields left for you)",
        (["id"], {"type": int}), (["--headless"], {"action": "store_true"}))
    add("submitted", cmd_submitted, "record that you submitted an application", (["id"], {"type": int}))
    add("status", cmd_status, "set application status", (["job"], {"type": int}), (["status"], {"choices": db.STATUSES}), (["--note"], {}))
    add("inbox", cmd_inbox, "scan Gmail for status updates and job alerts", (["--days"], {"type": int, "default": 7}))
    add("report", cmd_report, "Excel + Power BI report", (["--period"], {"choices": ["daily", "weekly", "monthly", "all", "custom"], "default": "weekly"}),
        (["--start"], {}), (["--end"], {}))
    add("prep", cmd_prep, "interview prep for a job", (["job"], {"type": int}))
    add("notion", cmd_notion, "sync with Notion", (["direction"], {"choices": ["pull", "push"]}))
    add("daily", cmd_daily, "run the full daily pipeline (for cron / Task Scheduler)")
    add("chat", cmd_chat, "chat in the terminal")
    add("ui", cmd_ui, "open the web app (chat + dashboard)", (["--port"], {"type": int, "default": 8501}))
    add("mcp", cmd_mcp, "run as an MCP server (Claude Desktop / Jarvis)")
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
