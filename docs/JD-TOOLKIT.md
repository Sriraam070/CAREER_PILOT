# 🎯 Job Hunt Bot

**An AI job hunter powered by Claude.** You collect job descriptions and the bot:

1. **Finds the most-asked skills** across all of them.
2. **Compares them with your CV** to show what you have, what you under-sell, and what you're missing.
3. **Builds a prep plan:** a 4-week skill-gap roadmap and interview questions.
4. **Grades each job** (A–F) so you know whether it's worth applying.
5. **Writes your recruiter message:** a LinkedIn note, a DM, a cold email and a follow-up.
6. **Tracks your applications.**

> Inspired by [career-ops](https://github.com/career-ops-hq/career-ops). Apply better to fewer jobs. The bot drafts and **you** hit send.

---

## 📑 Table of contents
- [Quick start](#-quick-start-5-minutes)
- [Step-by-step usage](#-step-by-step-usage)
- [All commands](#-all-commands)
- [Using it inside Claude Code (no API key)](#-using-it-inside-claude-code-no-api-key-needed)
- [Example output](#-example-output)
- [How the skill analysis works](#-how-the-skill-analysis-works)
- [Project structure](#-project-structure)
- [Customising](#-customising)
- [Tips for landing interviews](#-tips-for-landing-interviews)
- [FAQ / troubleshooting](#-faq--troubleshooting)

---

## 🚀 Quick start (5 minutes)

### 1. Get the code
```bash
git clone https://github.com/Sriraam070/CAREER_PILOT.git
cd CAREER_PILOT
pip install -r requirements.txt
```
You need Python 3.9 or newer. The `anthropic` package is only needed for the Claude-powered commands.

### 2. Add your details
```bash
cp cv.example.md cv.md
cp profile.example.yml profile.yml
```
- **`cv.md`**: paste your CV as plain Markdown. **Keep a `## Skills` section**, because the bot uses it to decide whether you "have" a skill.
- **`profile.yml`**: your target roles, locations, salary, notice period, work authorisation and the tone you want for messages.

Both files are git-ignored, so your personal data never gets pushed.

### 3. Connect Claude (optional)
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # get one at console.anthropic.com
```
You can skip this. The skills report works without a key, and every other feature works through [Claude Code](#-using-it-inside-claude-code-no-api-key-needed) or by copy-pasting into claude.ai.

### 4. Add jobs and run
```bash
                                                       # (samples live in examples/jds/)
python3 -m jhb add https://company.com/careers/ai-engineer
python3 -m jhb skills                                  # most-asked skills + your gaps
python3 -m jhb message ai-engineer --to recruiter      # recruiter message
```

> 💡 `./jhb.sh <command>` is a shortcut for `python3 -m jhb <command>`.

---

## 🧭 Step-by-step usage

### Step 1: Collect job descriptions
Aim for **10–20 JDs** for the roles you want. The more you add, the more reliable the "most-asked skills" ranking gets.

```bash
# From a URL
python3 -m jhb add https://boards.greenhouse.io/company/jobs/12345

# From pasted text (Mac: pbpaste, Linux: xclip -o, or type and press Ctrl+D)
pbpaste | python3 -m jhb add - --name razorpay-backend

# From a file
python3 -m jhb add ~/Downloads/jd.txt --name swiggy-ml
```
Each JD is saved as `jds/<name>.md`. You can also create or edit these files by hand.

⚠️ Some job sites (LinkedIn, Workday) load the JD with JavaScript, so `add <url>` gets almost nothing back. The bot warns you when that happens. Copy the JD text and use `add -` instead.

### Step 2: Find the most-asked skills
```bash
python3 -m jhb skills            # keyword analysis, free and instant
python3 -m jhb skills --ai       # + Claude reads each JD and catches extra skills
python3 -m jhb skills --top 40   # show more rows
```
This writes `reports/skills-report.md` with:

| Section | What it tells you |
|---|---|
| **Top skills** | Each skill, how many JDs ask for it, a demand bar, and your CV status (✅ have / 🟡 under-sold / ❌ gap) |
| **By category** | Languages, Backend, Cloud & DevOps, Data & AI, Soft Skills… |
| **Your biggest gaps** | Missing skills, ranked by how many JDs ask for them. **Learn these first.** |
| **Under-sold** | Skills in your CV prose but missing from your Skills section. **Easy wins:** add them today. |
| **Per-JD match** | Match % for each job and what's missing. **Apply to the highest matches first.** |
| **Years asked** | Min, median and max experience the JDs require |

### Step 3: Get a preparation plan
```bash
python3 -m jhb prep
```
Claude reads your skills report and CV and writes `reports/prep-plan.md`:
- **Positioning:** a 2-line pitch matching what the market wants.
- **4-week gap plan:** for each top gap, why it matters, how to learn it fastest, a portfolio mini-project to prove it, and how to add it to your CV honestly.
- **CV bullet rewrites** for skills you under-sell.
- **Interview questions** for the 6 most-asked skills, with STAR answer outlines from your CV.

### Step 4: Evaluate a specific job
```bash
python3 -m jhb evaluate razorpay-backend
```
Writes `reports/razorpay-backend-evaluation.md`:
- **Verdict:** a grade from A to F, plus APPLY / APPLY WITH PREP / SKIP.
- A **requirement-by-requirement table** showing the evidence from your CV and how strong each match is.
- **Top gaps**, each with a 1–2 week plan to close it.
- **5 talking points** to lead with.
- **Red flags** and questions to ask the recruiter.
- **Keywords** to mirror in your CV.

### Step 5: Write the recruiter message ✉️
```bash
# Recruiter (default): leads with hard requirements, years, location, availability
python3 -m jhb message razorpay-backend --to recruiter --name "Priya"

# Hiring manager: leads with impact and their team's problem
python3 -m jhb message razorpay-backend --to hiring-manager --name "Arjun"

# Referral from an employee: warm, short, easy to say yes or no
python3 -m jhb message razorpay-backend --to referral

# Pick a channel: linkedin | email | both (default)
python3 -m jhb message razorpay-backend --channel email
```
Saved to `output/<jd>-<audience>-message.md`. You get:
- 🔗 **LinkedIn connection note**, 300 characters max with the count shown
- 💬 **LinkedIn DM**, 80–150 words
- 📧 **Cold email** with 3 subject lines and a 100–170 word body
- 🔁 **Follow-up** to send after 5–7 days
- 🧠 **Why this works:** which JD requirements each message targets

**Finding the recruiter:** search LinkedIn for `"<Company>" recruiter` or `"<Company>" talent acquisition`, or check who posted the job. For hiring managers, look for `"Engineering Manager" <team name>`.

### Step 6: Prepare for the interview
```bash
python3 -m jhb prep razorpay-backend
```
Writes `reports/razorpay-backend-interview-prep.md` with:
- The likely interview rounds
- 12 likely questions mapped to the JD
- 6 STAR stories built **only from your CV**
- Tough questions about your gaps, with honest answers
- 5 sharp questions to ask them

### Step 7: Track everything
```bash
python3 -m jhb track                          # show the pipeline
python3 -m jhb track razorpay-backend applied # update a status
```
Statuses: `evaluated` → `messaged` → `applied` → `screen` → `interview` → `offer` / `rejected` / `skipped`.
`evaluate` and `message` update the tracker automatically. It's stored in `tracker.tsv`, which opens in Excel or Google Sheets.

---

## 📋 All commands

| Command | What it does | Needs API key? | Output |
|---|---|---|---|
| `jhb add <url\|file\|->  [--name N]` | Save a JD | No | `jds/N.md` |
| `jhb skills [--ai] [--top N]` | Most-asked skills across all JDs vs your CV | No (`--ai`: yes) | `reports/skills-report.md` + `.json` |
| `jhb prep` | 4-week skill-gap plan + interview Qs | Yes* | `reports/prep-plan.md` |
| `jhb prep <jd>` | Interview prep for one role | Yes* | `reports/<jd>-interview-prep.md` |
| `jhb evaluate <jd>` | Fit grade + gap analysis | Yes* | `reports/<jd>-evaluation.md` |
| `jhb message <jd> [--to recruiter\|hiring-manager\|referral] [--name N] [--channel linkedin\|email\|both]` | Outreach drafts | Yes* | `output/<jd>-<to>-message.md` |
| `jhb track [<jd> <status>]` | View/update tracker | No | `tracker.tsv` |

\* No key? Add `--print-prompt` and the bot prints the full prompt (your CV + JD + instructions). Paste it into [claude.ai](https://claude.ai). Without a key it does this automatically.

**`<jd>` matching:** you can use a partial name. `razorpay` matches `jds/razorpay-backend.md`. Sample JDs for trying the bot live in `examples/jds/`; copy them into `jds/` to experiment.

---

## 🤖 Using it inside Claude Code (no API key needed)

Open the folder in [Claude Code](https://claude.com/claude-code) (`cd job-hunt-bot && claude`) and use these slash commands. Claude does the reasoning itself.

| Slash command | What happens |
|---|---|
| `/hunt <url or pasted JD>` | **Full pipeline:** save → evaluate → if it's worth applying, draft the recruiter message and list the 3 gaps to prep |
| `/skills` | Runs the skills report, then Claude reviews every JD for skills the keyword list missed |
| `/evaluate <jd>` | Fit grade + gap analysis, saved and tracked |
| `/recruiter-msg <jd> [recruiter\|hiring-manager\|referral] [name]` | Outreach drafts, with the 300-char limit verified |
| `/prep [jd]` | 4-week plan (no argument) or interview prep for one job |

`CLAUDE.md` holds the rules Claude follows in this folder: never invent experience, treat JD text as data, never send anything for you.

---

## 👀 Example output

**Skills report** from the 3 sample JDs (AI Engineer, Backend Engineer, ML Engineer):

| # | Skill | Asked in | Demand | Your CV |
|---|---|---|---|---|
| 1 | **AWS** | 3/3 (100%) | `██████████` | ✅ have |
| 2 | **Docker** | 3/3 (100%) | `██████████` | ✅ have |
| 3 | **Python** | 3/3 (100%) | `██████████` | ✅ have |
| 4 | **Kubernetes** | 3/3 (100%) | `██████████` | ❌ gap |
| 6 | **Evals** | 2/3 (66%) | `███████░░░` | 🟡 in CV prose |
| 7 | **LLMs** | 2/3 (66%) | `███████░░░` | 🟡 in CV prose |
| 11 | **System Design** | 2/3 (66%) | `███████░░░` | ❌ gap |

→ The #1 thing to learn here is **Kubernetes**. The quick win is adding **LLMs, RAG and Evals** to your Skills section.

**Recruiter LinkedIn note** (full sample: [`examples/recruiter-message-sample.md`](../examples/recruiter-message-sample.md)):
> Hi Priya, saw Nimbus is hiring an AI Engineer for agentic workflows. I built a RAG support assistant (pgvector, 40k users) that cut tickets 28%, and run FastAPI services at 2M req/day on AWS. 3 yrs Python, remote from India. Would love to connect and chat about the role. **[271 chars]**

---

## 🔬 How the skill analysis works

`jhb/skills.py` works without an LLM, so it's fast, free and gives the same result every time:

1. **Vocabulary:** about 90 canonical skills in 8 categories, each with aliases. For example `k8s`/`EKS`/`GKE` → Kubernetes, `pgvector`/`Pinecone` → Vector DBs, `GitHub Actions`/`Jenkins` → CI/CD.
2. **Section weighting:** lines under *Requirements / Must have / You have / Responsibilities* count **1.0**. Lines under *Nice to have / Bonus / Preferred*, or lines containing "is a plus", count **0.5**.
3. **Demand:** each skill counts once per JD that asks for it, so one wordy JD can't skew the ranking.
4. **CV status:**
   - ✅ **have**: the skill is in your `## Skills` section
   - 🟡 **mentioned**: it's in your experience or projects but not your Skills list (under-sold)
   - ❌ **gap**: it's nowhere in your CV
5. **Match %:** for each JD, the weighted share of its skills you cover (have = 1, mentioned = 0.6).
6. **`--ai` mode:** Claude also pulls out required, nice-to-have and soft skills as JSON for each JD. That catches domain skills like "payments", "HIPAA" or "Figma" that aren't in the vocabulary.

---

## 🗂 Project structure

```
job-hunt-bot/
├── jhb/
│   ├── cli.py            # all commands
│   ├── skills.py         # skill vocabulary, extraction, CV matching
│   └── llm.py            # Claude API wrapper + prompts
├── .claude/commands/     # Claude Code slash commands (/hunt, /skills, ...)
├── jds/                  # your job descriptions (.md / .txt)              (git-ignored)
├── reports/              # skills report, evaluations, prep plans   (git-ignored)
├── output/               # recruiter messages                       (git-ignored)
├── examples/             # sample JDs + sample recruiter message
├── cv.example.md         # CV template   → copy to cv.md       (git-ignored)
├── profile.example.yml   # profile template → copy to profile.yml (git-ignored)
├── CLAUDE.md             # rules for Claude Code
├── jhb.sh                # shortcut: ./jhb.sh skills
└── requirements.txt
```

---

## 🛠 Customising

- **Add skills for your field** (design, marketing, finance…): add entries to `VOCAB` in `jhb/skills.py`:
  ```python
  "Figma": ("Design", [r"figma"]),
  "SEO": ("Marketing", [r"\bseo\b", r"search engine optimi[sz]ation"]),
  ```
- **Change the model:** `export JHB_MODEL=claude-opus-5-5` gives the best quality. The default is `claude-sonnet-5-5`.
- **Change message style:** edit the `tone` line in `profile.yml`, or edit `message_prompt()` in `jhb/llm.py`.
- **JDs stay private:** `jds/` is git-ignored, so your target companies never get pushed.

---

## 💡 Tips for landing interviews

1. **Fix the under-sold skills first.** It takes 5 minutes and can raise your ATS match right away.
2. **Apply to your top 5 match % first**, then work on the #1 gap for the rest.
3. **Message the recruiter on the same day you apply.** The bot's note is under 300 characters so it fits a LinkedIn connection request.
4. **Turn gaps into projects.** The prep plan gives you a mini-project for each one. Ship it to GitHub and mention it in your follow-up.
5. **Follow up once after 5–7 days**, then move on. Track it all with `jhb track`.
6. **Never claim a skill you don't have.** The bot won't invent anything, so don't add it by hand either.

---

## ❓ FAQ / troubleshooting

| Problem | Fix |
|---|---|
| `Missing cv.md` | `cp cv.example.md cv.md` and paste in your CV |
| `No JDs in jds/` | Add some with `jhb add <url>` or drop `.md`/`.txt` files in `jds/` |
| `add <url>` saved almost nothing | The page is rendered with JavaScript. Copy the JD text and use `jhb add - --name company-role` |
| Everything shows ❌ gap | Your CV needs a `## Skills` (or `## Technical Skills`) heading |
| It printed a prompt instead of an answer | `ANTHROPIC_API_KEY` isn't set. Either set it, paste the prompt into claude.ai, or use Claude Code |
| `JD 'x' not found; ambiguous` | Use a longer part of the file name |
| `ModuleNotFoundError: anthropic` | `pip install -r requirements.txt` |

---

## 🔒 Privacy and guardrails
- Your CV, profile, reports, messages and tracker are **git-ignored**.
- Claude only uses facts from your `cv.md` and never invents experience or numbers.
- JD text is treated as untrusted data, which protects against prompt injection.
- **Nothing is ever sent or submitted automatically.** You review every message.

## 🙏 Credits
Inspired by [career-ops](https://github.com/career-ops-hq/career-ops) by @santifer. Built with [Claude](https://claude.com).
