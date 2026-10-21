"""Review-and-approve application flow.

  queue(job)      → an approval request (state=pending) with the prepared,
                    NON-sensitive answers and a tailored note.
  decide(id, ok)  → you approve or reject it (UI / CLI). Nothing happens before this.
  assist(id)      → opens the application form in a real browser, fills ONLY
                    non-sensitive fields from your profile, uploads your resume,
                    and lists every sensitive / unknown field for you to fill.

Hard rules (not settings):
  * Sensitive fields (CTC, expected salary, notice period, declarations,
    consent, e-signatures, passwords, IDs, demographics, ...) are never filled.
  * The bot never clicks Submit when any sensitive or unknown required field
    exists. It only may click Submit on a plain Greenhouse/Lever form when
    automation.auto_submit_simple_forms is true AND you approved this exact
    application. Otherwise you press Submit yourself.
  * Duplicate guard: an application already marked Applied is never re-queued.
"""
import json
import os
import re

from . import db
from .config import ROOT, settings

SENSITIVE = re.compile(
    r"ctc|salary|compensation|remuneration|pay\b|stipend|lpa|expected|notice|joining date|"
    r"declar|certif|i agree|agree to|consent|terms|privacy|acknowledg|attest|undertak|"
    r"signature|e-?sign|sign here|initials|password|passcode|otp|"
    r"aadha?ar|\bpan\b|passport|ssn|social security|national id|tax id|bank|account number|ifsc|"
    r"date of birth|\bdob\b|\bage\b|gender|sex\b|marital|religion|caste|race|ethnic|disab|veteran|"
    r"criminal|convict|background check|visa|sponsor|work authori[sz]ation|citizenship|nationality|"
    r"current employer|reason for (leaving|change)|reference",
    re.I)

SAFE_FIELDS = [  # (label regex, profile key)
    (r"first name|given name", "first_name"),
    (r"last name|surname|family name", "last_name"),
    (r"^\s*(full )?name\b|full name|your name|candidate name", "name"),
    (r"e-?mail", "email"),
    (r"phone|mobile|contact number", "phone"),
    (r"linkedin", "linkedin"),
    (r"github", "github"),
    (r"city|location|current location", "location"),
    (r"portfolio|website|personal site", "github"),
]
RESUME = re.compile(r"resume|cv\b|curriculum", re.I)


def is_sensitive(label):
    return bool(SENSITIVE.search(label or ""))


def _profile():
    p = dict(settings()["profile"])
    parts = (p.get("name") or "").split()
    p.setdefault("first_name", parts[0] if parts else "")
    p.setdefault("last_name", " ".join(parts[1:]) if len(parts) > 1 else "")
    return p


def queue(job_id, note=None):
    if db.already_applied(job_id):
        return None
    if db.rows("SELECT id FROM approvals WHERE job_id=? AND kind='apply' AND state IN ('pending','approved')", (job_id,)):
        return None
    job = db.get_job(job_id)
    p = _profile()
    payload = {"job": {"company": job["company"], "title": job["title"], "url": job["url"]},
               "fields": {k: p.get(k, "") for k in ("name", "email", "phone", "linkedin", "github", "location")},
               "resume": p.get("resume_path"), "note": note or "",
               "match": job["match_score"], "gaps": json.loads(job["gaps"] or "[]")}
    with db.conn() as c:
        cur = c.execute("INSERT INTO approvals(job_id, kind, payload, sensitive_fields, created_at) VALUES (?,?,?,?,?)",
                        (job_id, "apply", json.dumps(payload), "[]", db.now()))
        c.execute("UPDATE jobs SET state='queued' WHERE id=?", (job_id,))
    db.set_status(job_id, "Not Applied", source="bot", detail="queued for your approval")
    db.audit("queue", f"job {job_id}")
    return cur.lastrowid


def pending():
    out = db.rows("""SELECT a.*, j.company, j.title, j.url, j.match_score, j.probability
                     FROM approvals a JOIN jobs j ON j.id=a.job_id
                     WHERE a.state IN ('pending','approved','awaiting_user') ORDER BY j.match_score DESC""")
    for r in out:
        r["payload"] = json.loads(r["payload"])
        r["sensitive_fields"] = json.loads(r["sensitive_fields"] or "[]")
    return out


def decide(approval_id, approve, by="user"):
    state = "approved" if approve else "rejected"
    with db.conn() as c:
        row = c.execute("SELECT job_id FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not row:
            raise ValueError("no such approval")
        c.execute("UPDATE approvals SET state=?, decided_at=? WHERE id=?", (state, db.now(), approval_id))
        if not approve:
            c.execute("UPDATE jobs SET state='skipped' WHERE id=?", (row["job_id"],))
    db.audit(f"approval_{state}", f"approval {approval_id} by {by}")
    return state


def mark_submitted(approval_id, by="user"):
    """You pressed Submit yourself → record it."""
    a = db.rows("SELECT job_id FROM approvals WHERE id=?", (approval_id,))[0]
    with db.conn() as c:
        c.execute("UPDATE approvals SET state='done', decided_at=? WHERE id=?", (db.now(), approval_id))
    db.set_status(a["job_id"], "Applied", source=by, detail="submitted")
    db.audit("submitted", f"approval {approval_id} by {by}")


# ── browser assist ──────────────────────────────────────────────────

COLLECT_JS = """
() => Array.from(document.querySelectorAll('input, textarea, select')).filter(e =>
  !['hidden','submit','button','image','reset'].includes((e.type||'').toLowerCase())).map((e, i) => {
  e.setAttribute('data-cp-idx', i);
  let label = e.getAttribute('aria-label') || '';
  if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) label = label || l.innerText; }
  if (!label) { const l = e.closest('label'); if (l) label = l.innerText; }
  if (!label) { const f = e.closest('.field, .application-question, .form-group, li, div'); if (f) { const t = f.querySelector('label, legend'); if (t) label = t.innerText; } }
  label = (label || e.placeholder || e.name || '').replace(/\\s+/g, ' ').trim();
  return {idx: i, tag: e.tagName.toLowerCase(), type: (e.type||'').toLowerCase(), label,
          required: e.required || /\\*\\s*$/.test(label), name: e.name || ''};
})
"""


def plan_fields(fields, profile):
    """Pure function (unit-tested): decide what to fill and what to leave for you."""
    fill, sensitive, unknown, resume = [], [], [], None
    for f in fields:
        label = f["label"]
        if f["type"] == "file":
            if RESUME.search(label) or resume is None and not is_sensitive(label):
                resume = f
            continue
        if is_sensitive(label) or f["type"] == "password":
            sensitive.append(label or f["name"])
            continue
        if f["type"] in ("checkbox", "radio") or f["tag"] == "select":
            if f["required"]:
                unknown.append(label or f["name"])
            continue
        for pat, key in SAFE_FIELDS:
            if re.search(pat, label, re.I) and profile.get(key):
                fill.append((f["idx"], profile[key], label))
                break
        else:
            if f["required"]:
                unknown.append(label or f["name"])
    return fill, sensitive, unknown, resume


def assist(approval_id, headless=False, wait_for_user=True, log=print):
    a = db.rows("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not a:
        raise ValueError("no such approval")
    a = a[0]
    if a["state"] not in ("approved", "awaiting_user"):
        raise PermissionError("Approve this application first (it is '%s')." % a["state"])
    job = db.get_job(a["job_id"])
    if db.already_applied(job["id"]):
        raise RuntimeError("Already applied to this job.")
    s = settings()
    profile = _profile()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, executable_path=os.environ.get("CAREERPILOT_CHROMIUM") or None)
        page = browser.new_page()
        url = job["url"]
        if job["source"] == "lever" and not url.rstrip("/").endswith("/apply"):
            url = url.rstrip("/") + "/apply"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        fields = page.evaluate(COLLECT_JS)
        fill, sensitive, unknown, resume = plan_fields(fields, profile)
        for idx, value, label in fill:
            page.locator(f"[data-cp-idx='{idx}']").fill(str(value))
            log(f"  ✓ filled {label}")
        resume_path = ROOT / (profile.get("resume_path") or "")
        if resume and resume_path.is_file():
            page.locator(f"[data-cp-idx='{resume['idx']}']").set_input_files(str(resume_path))
            log(f"  ✓ attached resume {resume_path.name}")
        with db.conn() as c:
            c.execute("UPDATE approvals SET sensitive_fields=?, state='awaiting_user' WHERE id=?",
                      (json.dumps({"sensitive": sensitive, "unknown": unknown}), approval_id))
        for label in sensitive:
            log(f"  🔒 left for you (sensitive): {label}")
        for label in unknown:
            log(f"  ✋ left for you (needs your answer): {label}")
        simple = job["source"] in ("greenhouse", "lever")
        may_submit = (s["automation"]["auto_submit_simple_forms"] and simple and not sensitive and not unknown
                      and a["state"] == "approved")
        if may_submit:
            btn = page.locator("button[type=submit], input[type=submit], #submit_app, button:has-text('Submit')").first
            btn.click()
            page.wait_for_timeout(3000)
            mark_submitted(approval_id, by="bot (approved, simple form)")
            log("  ✅ submitted (simple form, no sensitive fields, approved by you)")
        elif wait_for_user and not headless:
            log("\n  Review the form, fill the fields above, and press Submit yourself.")
            input("  Press Enter here after you've submitted (or closed) it... ")
            if input("  Did you submit it? [y/N] ").strip().lower() == "y":
                mark_submitted(approval_id)
        browser.close()
    db.audit("assist", f"approval {approval_id}: filled {len(fill)}, sensitive {len(sensitive)}, unknown {len(unknown)}")
    return {"filled": [l for _, _, l in fill], "sensitive": sensitive, "unknown": unknown, "submitted": may_submit}
