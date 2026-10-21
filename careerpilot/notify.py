"""Gmail (SMTP + app password) and WhatsApp (Twilio or CallMeBot) notifications.

Notifications never include sensitive data (CTC, notice period, IDs, passwords).
"""
import json
import smtplib
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import db
from .config import env, settings
from .evaluate import DISCLAIMER


def _job_block(j, html=False):
    skills = ", ".join(json.loads(j.get("skills") or "[]")[:12])
    gaps = ", ".join(json.loads(j.get("gaps") or "[]")[:8]) or "none"
    lines = [
        f"{j['company']} — {j['title']}",
        f"Location: {j.get('location') or '—'}   Posted: {(j.get('posted_at') or '—')[:10]}",
        f"Skill match: {j.get('match_score')}%   Est. response chance*: {j.get('probability')}%",
        f"Required skills: {skills or '—'}",
        f"Your gaps: {gaps}",
        f"Status: {j.get('status') or 'New: waiting for your approval'}",
    ]
    if j.get("next_step"):
        lines.append(f"Next step: {j['next_step']}")
    if j.get("interview_at"):
        lines.append(f"Interview: {j['interview_at']}")
    if j.get("deadline"):
        lines.append(f"Deadline: {j['deadline']}")
    lines.append(f"Link: {j.get('url')}")
    jd = (j.get("description") or "")[:1200]
    if html:
        body = "<br>".join(lines).replace(f"Link: {j.get('url')}", f"<a href='{j.get('url')}'>Open job ↗</a>")
        return f"<div style='margin:0 0 18px;padding:12px;border:1px solid #ddd;border-radius:8px'>{body}" \
               f"<details><summary>Job description</summary><pre style='white-space:pre-wrap'>{jd}</pre></details></div>"
    return "\n".join(lines) + (f"\n\nJD (excerpt):\n{jd}" if jd else "")


def send_email(subject, text, html=None):
    user, pwd = env("GMAIL_ADDRESS"), env("GMAIL_APP_PASSWORD")
    to = env("NOTIFY_EMAIL_TO", user)
    if not (user and pwd):
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set")
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())


def send_whatsapp(text):
    text = text[:1500]
    if env("TWILIO_ACCOUNT_SID"):
        sid, tok = env("TWILIO_ACCOUNT_SID"), env("TWILIO_AUTH_TOKEN")
        data = urllib.parse.urlencode({"From": f"whatsapp:{env('TWILIO_WHATSAPP_FROM')}",
                                       "To": f"whatsapp:{env('WHATSAPP_TO')}", "Body": text}).encode()
        req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data)
        import base64
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode())
        urllib.request.urlopen(req, timeout=30).read()
    elif env("CALLMEBOT_APIKEY"):
        url = (f"https://api.callmebot.com/whatsapp.php?phone={urllib.parse.quote(env('WHATSAPP_TO', ''))}"
               f"&text={urllib.parse.quote(text)}&apikey={env('CALLMEBOT_APIKEY')}")
        urllib.request.urlopen(url, timeout=30).read()
    else:
        raise RuntimeError("Set TWILIO_* or CALLMEBOT_APIKEY for WhatsApp")


def _dispatch(subject, jobs):
    auto = settings()["automation"]
    sent = []
    text = "\n\n----\n\n".join(_job_block(j) for j in jobs) + f"\n\n* {DISCLAIMER}"
    if auto["notify_email"]:
        html = "".join(_job_block(j, html=True) for j in jobs) + f"<p><small>* {DISCLAIMER}</small></p>"
        try:
            send_email(subject, text, html); sent.append("email")
        except Exception as e:
            db.audit("notify_error", f"email: {e}")
    if auto["notify_whatsapp"]:
        short = "\n\n".join(_job_block(j).split("\n\nJD")[0] for j in jobs[:5])
        try:
            send_whatsapp(f"*{subject}*\n\n{short}\n\n_{DISCLAIMER}_"); sent.append("whatsapp")
        except Exception as e:
            db.audit("notify_error", f"whatsapp: {e}")
    db.audit("notify", f"{subject} → {sent or 'disabled'}")
    return sent


def new_jobs(job_ids):
    jobs = [db.get_job(i) for i in job_ids]
    jobs.sort(key=lambda j: -(j["match_score"] or 0))
    return _dispatch(f"CareerPilot: {len(jobs)} new matching job(s)", jobs)


def status_change(job_id):
    j = db.rows("""SELECT j.*, a.status, a.next_step, a.interview_at, a.deadline
                   FROM jobs j JOIN applications a ON a.job_id=j.id WHERE j.id=?""", (job_id,))[0]
    return _dispatch(f"CareerPilot: {j['company']} — {j['status']}", [j])
