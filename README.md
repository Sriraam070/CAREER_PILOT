# 🎯 Job Hunt Bot

An AI job hunter built on Claude, inspired by [career-ops](https://github.com/career-ops-hq/career-ops).
Collect job descriptions → find the **most-asked skills** → see your **gaps** → get a **prep plan** → send a sharp **recruiter message**.

Apply better to fewer jobs. The bot drafts and **you** hit send.

## Setup (2 min)
```bash
pip install -r requirements.txt
cp cv.example.md cv.md            # paste YOUR CV (keep a "## Skills" section)
cp profile.example.yml profile.yml # targets, location, salary, notice period
export ANTHROPIC_API_KEY=sk-ant-... # optional, see "No API key?" below
```
Delete the three `jds/example-*.md` files once you've added real ones.

## Daily loop
```bash
# 1. Collect JDs (URL, file, or paste)
python3 -m jhb add https://jobs.company.com/ai-engineer
pbpaste | python3 -m jhb add - --name stripe-backend

# 2. Most-asked skills across ALL JDs vs your CV (no API key needed)
python3 -m jhb skills            # add --ai for Claude to catch skills outside the keyword list

# 3. A 4-week plan to close the top gaps, plus interview Qs for the top skills
python3 -m jhb prep

# 4. Should I apply? Grade A–F, requirement-by-requirement match, talking points
python3 -m jhb evaluate stripe-backend

# 5. Recruiter message: LinkedIn note (≤300 chars), DM, cold email, follow-up
python3 -m jhb message stripe-backend --to recruiter --name "Priya"
python3 -m jhb message stripe-backend --to hiring-manager --channel email
python3 -m jhb message stripe-backend --to referral

# 6. Interview prep for one role: questions, STAR stories, tough questions
python3 -m jhb prep stripe-backend

# 7. Track your pipeline
python3 -m jhb track stripe-backend applied
```
Outputs: `reports/` (skills report, evaluations, prep), `output/` (messages), `tracker.tsv`.
See `examples/recruiter-message-sample.md` for a sample message.

## No API key? Use Claude Code (like career-ops)
Open this folder in Claude Code and use the slash commands:

| Command | What it does |
|---|---|
| `/hunt <url or paste>` | save → evaluate → recruiter message if it's worth applying |
| `/skills` | most-asked skills + gaps, with Claude reviewing every JD |
| `/evaluate <jd>` | fit grade and gap analysis |
| `/recruiter-msg <jd> [recruiter\|hiring-manager\|referral] [name]` | outreach drafts |
| `/prep [jd]` | 4-week study plan, or interview prep for one role |

You can also add `--print-prompt` to any Claude command and paste the output into claude.ai.

## How the skill analysis works
- `jhb/skills.py` has around 90 canonical skills with aliases (`k8s`→Kubernetes, `pgvector`→Vector DBs…).
- It counts **how many JDs ask for each skill**. Lines under "Requirements" count 1.0 and lines under "Nice to have / Bonus / a plus" count 0.5.
- It compares each skill against your CV: ✅ in your Skills section · 🟡 only in your prose (under-sold) · ❌ gap.
- It gives each JD a weighted match %. `--ai` adds Claude's structured extraction for anything the keyword list misses.

To add skills for your field, edit `VOCAB` in `jhb/skills.py`.

## Guardrails
- Claude may only use facts from `cv.md` and won't invent experience or metrics.
- JD text is treated as untrusted data (it's protected against prompt injection).
- Nothing gets sent or submitted automatically.

Model: `claude-sonnet-5-5` by default. Override it with `JHB_MODEL=claude-opus-5-5`.
