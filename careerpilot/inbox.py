"""Read Gmail over IMAP (app password) to:
  1. detect application status changes (received / assessment / interview / rejection / offer)
  2. import jobs from LinkedIn / Naukri / Indeed job-alert emails

Only reads messages; never sends, deletes or marks anything. Message bodies are
treated as untrusted data.
"""
import email
import imaplib
import re
from email.header import decode_header, make_header

from . import db, notify
from .config import env, settings

RULES = [  # first match wins
    ("Offer", r"offer letter|pleased to offer|extend (you )?an offer|offer of employment"),
    ("Rejected", r"not (be )?moving forward|unfortunately|regret to inform|other candidates|not selected|position has been filled|decided not to proceed"),
    ("Interview", r"interview (invitation|schedule|invite)|schedule (an|your) interview|invite you (to|for) (an |a )?interview|calendly|meet the team|technical round|hr round"),
    ("OA/Test", r"assessment|online test|coding (test|challenge)|hackerrank|hackerearth|codility|codesignal|mettl|test link"),
    ("Applied", r"application (has been )?received|thank you for (applying|your application)|we have received your application|application submitted"),
]
ALERT_SENDERS = re.compile(r"linkedin|naukri|indeed|foundit|instahyre|glassdoor|wellfound", re.I)
DATE_RX = re.compile(r"\b(\d{1,2}(st|nd|rd|th)? (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{4}|(mon|tues|wednes|thurs|fri|satur|sun)day,? [a-z]+ \d{1,2})[^.\n]{0,25}", re.I)


def classify(subject, body):
    text = f"{subject}\n{body}".lower()
    for status, rx in RULES:
        if re.search(rx, text):
            return status
    return None


def _body(msg):
    parts = msg.walk() if msg.is_multipart() else [msg]
    out = []
    for p in parts:
        if p.get_content_type() in ("text/plain", "text/html") and not p.get_filename():
            try:
                out.append(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace"))
            except Exception:
                pass
    from .sources import strip_html
    return strip_html("\n".join(out))


def _match_application(sender, subject, body):
    """Find which open application an email is about, by company name."""
    apps = db.rows("SELECT a.job_id, j.company, j.title FROM applications a JOIN jobs j ON j.id=a.job_id")
    hay = f"{sender} {subject} {body[:3000]}".lower()
    best = None
    for a in apps:
        name = re.sub(r"[^a-z0-9 ]", "", a["company"].lower()).strip()
        if name and (name in hay or name.replace(" ", "") in hay.replace(" ", "")):
            if a["title"].lower()[:25] in hay:
                return a
            best = best or a
    return best


def check(days=7, log=print):
    user, pwd = env("GMAIL_ADDRESS"), env("GMAIL_APP_PASSWORD")
    if not (user and pwd):
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set")
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pwd)
    M.select("INBOX", readonly=True)
    import datetime as dt
    since = (dt.date.today() - dt.timedelta(days=days)).strftime("%d-%b-%Y")
    _, ids = M.search(None, f'(SINCE "{since}")')
    changes, alerts = [], 0
    for num in ids[0].split()[-400:]:
        _, data = M.fetch(num, "(BODY.PEEK[])")
        msg = email.message_from_bytes(data[0][1])
        mid = msg.get("Message-ID", num.decode())
        if db.rows("SELECT 1 FROM seen_emails WHERE msg_id=?", (mid,)):
            continue
        with db.conn() as c:
            c.execute("INSERT OR IGNORE INTO seen_emails VALUES (?,?)", (mid, db.now()))
        sender = str(make_header(decode_header(msg.get("From", ""))))
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        body = _body(msg)
        if ALERT_SENDERS.search(sender) and re.search(r"job alert|jobs? for you|new jobs|recommended jobs|matching jobs", subject, re.I):
            alerts += import_alert(body, sender)
            continue
        status = classify(subject, body)
        app = _match_application(sender, subject, body) if status else None
        if status and app:
            extra = {}
            if status == "Interview":
                m = DATE_RX.search(body)
                extra = {"interview_at": m.group(0) if m else None, "next_step": "Prepare: careerpilot prep %d" % app["job_id"]}
            elif status == "OA/Test":
                extra = {"next_step": "Complete the assessment (check the email for the deadline)"}
            elif status == "Rejected":
                extra = {"next_step": "Ask for feedback; review gaps in the report"}
            _, changed = db.set_status(app["job_id"], status, source="gmail", detail=subject[:200], **extra)
            if changed:
                changes.append((app["company"], status))
                log(f"  {app['company']}: → {status}  ({subject[:60]})")
                notify.status_change(app["job_id"])
    M.logout()
    db.audit("inbox", f"{len(changes)} status changes, {alerts} alert jobs")
    return {"status_changes": changes, "alert_jobs": alerts}


def import_alert(body, sender):
    """Pull 'Title · Company · Location' + link triples out of job-alert emails."""
    from . import evaluate as ev
    n = 0
    links = re.findall(r"https?://[^\s)>\]]+(?:/jobs?/view/\d+|jobid=\w+|/job-listings-[\w-]+|viewjob\?jk=\w+)[^\s)>\]]*", body)
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    for url in dict.fromkeys(links):
        idx = next((i for i, l in enumerate(lines) if url[:60] in l), None)
        ctx = lines[max(0, idx - 4): idx] if idx is not None else []
        if len(ctx) < 2:
            continue
        title, company = ctx[-3] if len(ctx) >= 3 else ctx[-2], ctx[-2] if len(ctx) >= 3 else ctx[-1]
        loc = ctx[-1] if len(ctx) >= 3 else ""
        if len(title) > 120 or len(company) > 80:
            continue
        job_id, new = db.upsert_job({"company": company, "title": title, "location": loc, "url": url.split("?")[0],
                                     "source": "email-alert:" + ALERT_SENDERS.search(sender).group(0).lower()})
        if new:
            ev.evaluate(job_id)
            n += 1
    return n
