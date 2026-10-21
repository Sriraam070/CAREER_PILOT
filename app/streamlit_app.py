"""CareerPilot web app. Run: python -m careerpilot ui  (binds to 127.0.0.1 only)."""
import datetime as dt
import hmac
import json
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careerpilot import ai, api, apply, assistant, companies, db, discover, evaluate, reports  # noqa: E402
from careerpilot.config import save_settings, settings  # noqa: E402

st.set_page_config(page_title="CareerPilot", page_icon="🧭", layout="wide")

# ── access gate ──────────────────────────────────────────────────────
pw = os.environ.get("CAREERPILOT_APP_PASSWORD")
if pw and not st.session_state.get("authed"):
    st.title("🧭 CareerPilot")
    entered = st.text_input("App password", type="password")
    if entered and hmac.compare_digest(entered, pw):
        st.session_state.authed = True
        st.rerun()
    elif entered:
        st.error("Wrong password")
    st.stop()

companies.sync_to_db()
S = settings()


def hbar(df, label, value, color=None):
    """Horizontal bar chart sorted by value (largest on top)."""
    enc = {"y": alt.Y(f"{label}:N", sort="-x", title=None), "x": alt.X(f"{value}:Q", title=None),
           "tooltip": list(df.columns)}
    if color:
        enc["color"] = alt.Color(f"{color}:N", title="In your CV",
                                 scale=alt.Scale(domain=["Yes", "In CV text", "No"], range=["#2e7d32", "#f9a825", "#c62828"]))
    return alt.Chart(df).mark_bar().encode(**enc).properties(height=max(120, 24 * len(df)))
st.sidebar.title("🧭 CareerPilot")
st.sidebar.caption(f"Model: {ai.model() if ai.available() else 'no API key: chat & AI prep off'}")
stats = api.pipeline_stats()
st.sidebar.metric("Awaiting your approval", stats["awaiting_approval"])
st.sidebar.metric("Jobs found (30 days)", stats["jobs_discovered"])
if st.sidebar.button("🔎 Discover now", use_container_width=True):
    with st.spinner("Checking your target companies…"):
        st.sidebar.json(discover.run(log=lambda *_: None))

tabs = st.tabs(["💬 Chat", "📊 Dashboard", "🗂 Jobs", "✅ Approvals", "📈 Reports", "🎤 Interview prep", "🏢 Companies", "⚙️ Settings"])

# ── Chat ─────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Ask about openings, companies, salaries, skills, your pipeline or interview prep")
    st.session_state.setdefault("api_history", [])
    st.session_state.setdefault("display", [])
    box = st.container(height=520)
    for role, text in st.session_state.display:
        box.chat_message(role).markdown(text)
    if q := st.chat_input("e.g. Which Super Dream companies have Python roles I match 60%+?"):
        box.chat_message("user").markdown(q)
        with box.chat_message("assistant"):
            status = st.status("Thinking…", expanded=False)
            reply, st.session_state.api_history = assistant.chat(
                st.session_state.api_history, q, on_tool=lambda n, i: status.write(f"`{n}` {json.dumps(i)[:120]}"))
            status.update(label="Done", state="complete")
            st.markdown(reply)
        st.session_state.display += [("user", q), ("assistant", reply)]
    if st.button("Clear chat"):
        st.session_state.api_history, st.session_state.display = [], []
        st.rerun()

# ── Dashboard ────────────────────────────────────────────────────────
with tabs[1]:
    by = stats["by_status"]
    applied = sum(v for k, v in by.items() if k != "Not Applied")
    c = st.columns(6)
    c[0].metric("Applied", applied)
    c[1].metric("OA / Test", by.get("OA/Test", 0))
    c[2].metric("Interview", by.get("Interview", 0))
    c[3].metric("Offer", by.get("Offer", 0))
    c[4].metric("Rejected", by.get("Rejected", 0))
    c[5].metric("Response rate", f"{round(100 * (by.get('OA/Test', 0) + by.get('Interview', 0) + by.get('Offer', 0)) / applied) if applied else 0}%")
    left, right = st.columns(2)
    ins = api.skill_insights(30)
    with left:
        st.markdown("**Most-requested skills (last 30 days)**")
        if ins["top_skills"]:
            st.altair_chart(hbar(pd.DataFrame(ins["top_skills"][:15]), "skill", "jobs", "in_cv"), use_container_width=True)
        st.markdown("**Learn next (highest-demand gaps)**")
        st.dataframe(pd.DataFrame(ins["gaps_to_learn"]), hide_index=True, use_container_width=True)
    with right:
        cos = pd.DataFrame(db.rows("SELECT company, COUNT(*) jobs FROM jobs WHERE state != 'closed' GROUP BY company ORDER BY jobs DESC LIMIT 15"))
        if not cos.empty:
            st.markdown("**Open positions by company**")
            st.altair_chart(hbar(cos, "company", "jobs"), use_container_width=True)
        st.markdown("**Recent status changes**")
        st.dataframe(pd.DataFrame(stats["recent_changes"]), hide_index=True, use_container_width=True)
    st.markdown("**Application pipeline**")
    apps = db.rows("""SELECT j.id job, j.company, j.title, a.status, a.applied_at, a.next_step, a.interview_at, j.match_score, j.url
                      FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.updated_at DESC""")
    if apps:
        df = pd.DataFrame(apps)
        edited = st.data_editor(df, hide_index=True, use_container_width=True, disabled=[c for c in df.columns if c != "status"],
                                column_config={"status": st.column_config.SelectboxColumn(options=db.STATUSES),
                                               "url": st.column_config.LinkColumn("link")}, key="pipeline")
        for old, new in zip(apps, edited.to_dict("records")):
            if old["status"] != new["status"]:
                db.set_status(old["job"], new["status"], source="ui")
                st.toast(f"{old['company']}: {new['status']}")
    else:
        st.info("No applications yet. Approve one in the Approvals tab.")

# ── Jobs ─────────────────────────────────────────────────────────────
with tabs[2]:
    f = st.columns([2, 2, 1, 1])
    q = f[0].text_input("Search title / JD")
    co = f[1].selectbox("Company", [""] + [c["name"] for c in companies.all_companies()])
    mn = f[2].slider("Min match %", 0, 100, 0)
    state = f[3].selectbox("State", ["", "new", "queued", "applied", "skipped"])
    jobs = api.search_jobs(q, co, mn, state, 100)
    st.caption(f"{len(jobs)} jobs · *Est. response % = {evaluate.DISCLAIMER}*")
    if jobs:
        st.dataframe(pd.DataFrame(jobs), hide_index=True, use_container_width=True,
                     column_config={"url": st.column_config.LinkColumn("link"),
                                    "match_score": st.column_config.ProgressColumn("match %", min_value=0, max_value=100),
                                    "probability": st.column_config.NumberColumn("est. response %*")})
        pick = st.number_input("Job # for details", min_value=0, step=1)
        if pick:
            d = api.job_details(int(pick))
            if "error" not in d:
                st.markdown(f"### {d['company']} — {d['title']}\n{d['location'] or ''} · [open posting]({d['url']})")
                st.write(f"**Match:** {d['match_score']}% · **Est. response:** {d['probability']}%* · **Years asked:** {d['years_required'] or '—'}")
                st.write(f"**Skills asked:** {', '.join(d['skills'])}")
                st.write(f"**Your gaps:** {', '.join(d['gaps']) or 'none'}")
                st.caption(f"Why: {d['fit_notes']}")
                if st.button("Queue for my approval"):
                    st.success("Queued" if apply.queue(d["id"]) else "Already queued or applied")
                with st.expander("Job description"):
                    st.text(d["description"])
    with st.expander("➕ Add a job manually (paste a JD)"):
        with st.form("add"):
            a1, a2 = st.columns(2)
            comp, title = a1.text_input("Company"), a2.text_input("Title")
            url, loc = a1.text_input("Link"), a2.text_input("Location")
            desc = st.text_area("Job description", height=200)
            if st.form_submit_button("Add & score") and comp and title:
                st.json(api.add_job(comp, title, url, desc, loc))

# ── Approvals ────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Review & approve")
    st.caption("Nothing is submitted without you. Approving lets the bot open the form and pre-fill only non-sensitive "
               "fields (name, email, phone, links, resume). CTC, notice period, declarations, consent, signatures and "
               "passwords are always left for you.")
    pend = apply.pending()
    if not pend:
        st.info("Nothing waiting. New matches above your queue threshold land here.")
    for r in pend:
        with st.container(border=True):
            st.markdown(f"**{r['company']} — {r['title']}** · match {r['match_score']}% · est. response {r['probability']}%* · "
                        f"[posting]({r['url']}) · state: `{r['state']}`")
            pl = r["payload"]
            st.caption("Will pre-fill: " + ", ".join(k for k, v in pl["fields"].items() if v) + f" · attach {pl['resume']}")
            if pl["gaps"]:
                st.caption("Gaps to address in your note/interview: " + ", ".join(pl["gaps"]))
            if r["sensitive_fields"]:
                sf = r["sensitive_fields"]
                st.warning("Left for you → 🔒 " + ", ".join(sf.get("sensitive", [])) + "  ✋ " + ", ".join(sf.get("unknown", [])))
            b = st.columns(4)
            if r["state"] == "pending":
                if b[0].button("✅ Approve", key=f"ok{r['id']}"):
                    apply.decide(r["id"], True); st.rerun()
                if b[1].button("❌ Reject", key=f"no{r['id']}"):
                    apply.decide(r["id"], False); st.rerun()
            else:
                b[0].code(f"python -m careerpilot assist {r['id']}", language="bash")
                b[1].caption("Run this on your computer: it opens the form in a browser and pre-fills it.")
                if b[2].button("I submitted it", key=f"done{r['id']}"):
                    apply.mark_submitted(r["id"]); st.rerun()

# ── Reports ──────────────────────────────────────────────────────────
with tabs[4]:
    c1, c2, c3 = st.columns(3)
    period = c1.selectbox("Period", ["daily", "weekly", "monthly", "all", "custom"], index=1)
    start = c2.date_input("From", dt.date.today() - dt.timedelta(days=7), disabled=period != "custom")
    end = c3.date_input("To", dt.date.today(), disabled=period != "custom")
    if st.button("Generate Excel + Power BI files"):
        path = reports.excel(period, str(start), str(end))
        pbi = reports.powerbi()
        st.success(f"Saved {path.name}; Power BI CSVs in {pbi}")
        st.download_button("⬇️ Download Excel", path.read_bytes(), file_name=path.name)
    st.caption("Power BI: Get Data → Text/CSV (or Folder) → reports/powerbi/. Relate fact_jobs.job_id ↔ bridge_job_skill.job_id, "
               "fact_jobs.company ↔ dim_company.company. Refresh after each run.")

# ── Interview prep ───────────────────────────────────────────────────
with tabs[5]:
    options = {f"#{j['id']} {j['company']} — {j['title']}": j["id"] for j in api.search_jobs(limit=100)}
    choice = st.selectbox("Job", list(options) or ["(no jobs yet)"])
    if options and st.button("Generate prep pack"):
        from careerpilot import prep
        with st.spinner("Preparing (can take a minute)…"):
            path, md = prep.generate(options[choice])
        if path:
            st.markdown(md)
            st.download_button("⬇️ Download", md, file_name=Path(path).name)
        else:
            st.info("No API key: copy this prompt into claude.ai")
            st.code(md)

# ── Companies ────────────────────────────────────────────────────────
with tabs[6]:
    st.caption("From your Notion Job Tracker. Login IDs and passwords are never read. Edit job sources in companies.yml.")
    st.dataframe(pd.DataFrame(api.list_companies()), hide_index=True, use_container_width=True)

# ── Settings ─────────────────────────────────────────────────────────
with tabs[7]:
    with st.form("settings"):
        st.markdown("**Profile** (only non-sensitive fields; the bot never stores CTC, notice period or IDs)")
        prof = S["profile"]
        pc = st.columns(3)
        for i, k in enumerate(["name", "email", "phone", "location", "linkedin", "github"]):
            prof[k] = pc[i % 3].text_input(k.title(), prof.get(k, ""))
        prof["years_experience"] = pc[0].number_input("Years of experience", 0.0, 40.0, float(prof.get("years_experience") or 0), 0.5)
        prof["resume_path"] = pc[1].text_input("Resume file (in repo folder)", prof.get("resume_path", "resume.pdf"))
        st.markdown("**Preferences**")
        pr = S["preferences"]
        pr["keywords"] = [x.strip() for x in st.text_input("Title keywords", ", ".join(pr["keywords"])).split(",") if x.strip()]
        pr["exclude_keywords"] = [x.strip() for x in st.text_input("Exclude", ", ".join(pr["exclude_keywords"])).split(",") if x.strip()]
        pr["locations"] = [x.strip() for x in st.text_input("Locations", ", ".join(pr["locations"])).split(",") if x.strip()]
        pr["company_tiers"] = st.multiselect("Company tiers", ["MARQUEE", "SUPER DREAM", "DREAM", "PRIME", "NEW", "DAY SHARING"], pr["company_tiers"])
        sc = st.columns(3)
        pr["max_years_required"] = sc[0].number_input("Max years required", 0, 20, int(pr["max_years_required"]))
        pr["min_match_to_queue"] = sc[1].slider("Queue for approval at match ≥", 0, 100, int(pr["min_match_to_queue"]))
        pr["min_match_to_notify"] = sc[2].slider("Notify at match ≥", 0, 100, int(pr["min_match_to_notify"]))
        st.markdown("**Automation**")
        au = S["automation"]
        ac = st.columns(3)
        for i, k in enumerate(["discover", "queue_for_approval", "notify_email", "notify_whatsapp", "check_inbox", "notion_sync"]):
            au[k] = ac[i % 3].toggle(k.replace("_", " ").title(), au[k])
        au["auto_submit_simple_forms"] = st.toggle(
            "Allow the bot to click Submit on simple Greenhouse/Lever forms you approved, when they have NO sensitive or unknown fields",
            au["auto_submit_simple_forms"])
        if st.form_submit_button("Save"):
            save_settings(S)
            db.audit("settings", "saved via UI")
            st.success("Saved")
    with st.expander("Audit log (last 50 actions)"):
        st.dataframe(pd.DataFrame(db.rows("SELECT * FROM audit ORDER BY id DESC LIMIT 50")), hide_index=True, use_container_width=True)
