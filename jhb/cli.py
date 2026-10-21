"""Job Hunt Bot CLI.

  jhb add <url|file|->            save a JD into jds/
  jhb skills [--ai]               most-asked skills across all JDs + your gaps
  jhb evaluate <jd>               fit score + gap analysis for one JD
  jhb message <jd> [--to ...]     recruiter / hiring-manager / referral outreach
  jhb prep [<jd>]                 study plan (all JDs) or interview prep (one JD)
  jhb track [<jd> <status>]       view / update the application tracker

Any Claude-powered command accepts --print-prompt to print the prompt instead
of calling the API (paste it into claude.ai, or use the Claude Code commands).
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

from . import llm, skills

ROOT = Path(__file__).resolve().parent.parent
JDS, REPORTS, OUTPUT = ROOT / "jds", ROOT / "reports", ROOT / "output"
TRACKER = ROOT / "tracker.tsv"
STATUSES = ["evaluated", "messaged", "applied", "screen", "interview", "offer", "rejected", "skipped"]


# ── helpers ─────────────────────────────────────────────────────────

def read(path, required=True):
    p = ROOT / path
    if p.exists():
        return p.read_text(encoding="utf-8")
    if required:
        sys.exit(f"Missing {path}. Copy {path.replace('.md', '.example.md').replace('.yml', '.example.yml')} and fill it in.")
    return ""


def load_jds():
    files = sorted(p for p in JDS.glob("*") if p.suffix in (".md", ".txt"))
    if not files:
        sys.exit("No JDs in jds/. Add some with: jhb add <url> or drop .md/.txt files in jds/")
    return {p.stem: p.read_text(encoding="utf-8") for p in files}


def find_jd(name):
    for cand in (Path(name), JDS / name, JDS / f"{name}.md", JDS / f"{name}.txt"):
        if cand.exists():
            return cand.stem, cand.read_text(encoding="utf-8")
    matches = [p for p in JDS.glob(f"*{name}*") if p.suffix in (".md", ".txt")]
    if len(matches) == 1:
        return matches[0].stem, matches[0].read_text(encoding="utf-8")
    sys.exit(f"JD '{name}' not found" + (f"; ambiguous: {[m.name for m in matches]}" if matches else ""))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "jd"


def run_llm(prompt, args, out_path=None):
    if args.print_prompt or not llm.available():
        if not args.print_prompt:
            print("# ANTHROPIC_API_KEY not set: printing the prompt instead.\n"
                  "# Paste it into Claude, or run the matching /command in Claude Code.\n", file=sys.stderr)
        print(llm.SYSTEM + "\n\n" + prompt)
        return None
    print(f"… asking Claude ({llm.MODEL})", file=sys.stderr)
    out = llm.ask(prompt)
    if out_path:
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(out + "\n", encoding="utf-8")
        print(f"\nSaved → {out_path.relative_to(ROOT)}\n", file=sys.stderr)
    print(out)
    return out


def track_set(jd_name, status, score=None):
    rows = {}
    if TRACKER.exists():
        for line in TRACKER.read_text().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 4:
                rows[parts[0]] = parts
    row = rows.get(jd_name, [jd_name, "", "", ""])
    row[1] = status
    if score is not None:
        row[2] = str(score)
    row[3] = dt.date.today().isoformat()
    rows[jd_name] = row
    TRACKER.write_text("jd\tstatus\tmatch%\tupdated\n" + "".join("\t".join(r) + "\n" for r in rows.values()))


# ── commands ────────────────────────────────────────────────────────

def cmd_add(args):
    src = args.source
    if src == "-":
        text = sys.stdin.read()
    elif re.match(r"https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0 job-hunt-bot"})
        raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
        raw = re.sub(r"(?i)<(br|/p|/li|/h\d|/div)>", "\n", raw)
        raw = re.sub(r"(?i)<li[^>]*>", "\n- ", raw)
        text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        text = f"Source: {src}\n\n{text}"
        if len(text) < 400:
            print("⚠ Very little text came back (JS-rendered page?). Paste the JD instead: jhb add - < jd.txt", file=sys.stderr)
    else:
        text = Path(src).read_text(encoding="utf-8")
    name = slug(args.name or (text.splitlines()[0] if src == "-" else Path(src).stem if not src.startswith("http") else src.rstrip("/").split("/")[-1]))
    dest = JDS / f"{name}.md"
    JDS.mkdir(exist_ok=True)
    dest.write_text(text + "\n", encoding="utf-8")
    print(f"Saved {dest.relative_to(ROOT)} ({len(text)} chars)")


def cmd_skills(args):
    jds = load_jds()
    cv = read("cv.md", required=False)
    stats = skills.aggregate(jds, cv)
    n = len(jds)
    lines = [f"# Most-asked skills across {n} job description{'s' * (n != 1)}",
             f"_Generated {dt.date.today()} · weight: required=1, nice-to-have=0.5_", ""]

    def bar(k):
        return "█" * round(10 * k / n) + "░" * (10 - round(10 * k / n))

    status_icon = {"have": "✅ have", "mentioned": "🟡 in CV prose", "gap": "❌ gap"}
    lines += ["## Top skills", "", "| # | Skill | Category | Asked in | Demand | Your CV |", "|---|---|---|---|---|---|"]
    for i, s in enumerate(stats[: args.top], 1):
        lines.append(f"| {i} | **{s.name}** | {s.category} | {s.jd_count}/{n} ({100 * s.jd_count // n}%) | `{bar(s.jd_count)}` | {status_icon[s.cv_status] if cv else '—'} |")

    lines += ["", "## By category", ""]
    cats = {}
    for s in stats:
        cats.setdefault(s.category, []).append(s)
    for cat, items in cats.items():
        lines.append(f"- **{cat}:** " + ", ".join(f"{s.name} ({s.jd_count})" for s in items))

    if cv:
        gaps = [s for s in stats if s.cv_status == "gap" and s.category != "Soft Skills"]
        weak = [s for s in stats if s.cv_status == "mentioned"]
        lines += ["", "## Your biggest gaps (by market demand)", ""]
        lines += [f"{i}. **{s.name}** — asked in {s.jd_count}/{n} JDs: {', '.join(s.jds[:5])}" for i, s in enumerate(gaps[:10], 1)] or ["None 🎉"]
        lines += ["", "## Under-sold (in your CV prose but not your Skills section)", ""]
        lines += [f"- **{s.name}** ({s.jd_count}/{n}) — add it to Skills" for s in weak[:10]] or ["None"]
        lines += ["", "## Per-JD match", "", "| JD | Match | Missing |", "|---|---|---|"]
        rows = []
        for name, text in jds.items():
            score, _, miss = skills.match_score(text, cv)
            rows.append((score, name, miss))
        for score, name, miss in sorted(rows, reverse=True):
            lines.append(f"| {name} | {score}% | {', '.join(miss[:6]) or '—'} |")

    yrs = [y for y in (skills.years_required(t) for t in jds.values()) if y]
    if yrs:
        lines += ["", f"_Years of experience asked: min {min(yrs)}, median {sorted(yrs)[len(yrs) // 2]}, max {max(yrs)}_"]

    if args.ai:
        if not llm.available():
            print("⚠ --ai needs ANTHROPIC_API_KEY; skipping AI extraction.", file=sys.stderr)
        else:
            lines += _ai_skills(jds, n)

    report = "\n".join(lines) + "\n"
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "skills-report.md").write_text(report, encoding="utf-8")
    (REPORTS / "skills-report.json").write_text(json.dumps(
        [s.__dict__ for s in stats], indent=2), encoding="utf-8")
    print(report)
    print("Saved → reports/skills-report.md  (next: jhb prep)", file=sys.stderr)


def _ai_skills(jds, n):
    from collections import Counter
    req, nice, soft = Counter(), Counter(), Counter()
    for name, text in jds.items():
        print(f"… Claude extracting skills: {name}", file=sys.stderr)
        try:
            d = llm.ask_json(llm.skills_ai_prompt(name, text[:15000]), 1500)
        except Exception as e:  # keep going on one bad JD
            print(f"  skipped ({e})", file=sys.stderr)
            continue
        req.update({s.strip().title(): 1 for s in d.get("required", [])})
        nice.update({s.strip().title(): 1 for s in d.get("nice_to_have", [])})
        soft.update({s.strip().title(): 1 for s in d.get("soft_skills", [])})
    out = ["", "## Claude-extracted skills (catches anything outside the keyword list)", ""]
    for label, c in (("Required", req), ("Nice to have", nice), ("Soft skills", soft)):
        out.append(f"**{label}:** " + ", ".join(f"{k} ({v}/{n})" for k, v in c.most_common(25)))
        out.append("")
    return out


def cmd_evaluate(args):
    name, jd = find_jd(args.jd)
    cv, profile = read("cv.md"), read("profile.yml", required=False)
    score, hits, gaps = skills.match_score(jd, cv)
    print(f"Keyword match: {score}%  |  gaps: {', '.join(gaps) or 'none'}", file=sys.stderr)
    out = run_llm(llm.evaluate_prompt(cv, profile, jd, {"score": score, "hits": hits, "gaps": gaps}),
                  args, REPORTS / f"{name}-evaluation.md")
    if out is not None:
        track_set(name, "evaluated", score)


def cmd_message(args):
    name, jd = find_jd(args.jd)
    cv, profile = read("cv.md"), read("profile.yml", required=False)
    out = run_llm(llm.message_prompt(cv, profile, jd, args.to, args.name, args.channel),
                  args, OUTPUT / f"{name}-{args.to}-message.md")
    if out is not None:
        track_set(name, "messaged", skills.match_score(jd, cv)[0])


def cmd_prep(args):
    cv, profile = read("cv.md"), read("profile.yml", required=False)
    if args.jd:
        name, jd = find_jd(args.jd)
        run_llm(llm.interview_prompt(cv, profile, jd), args, REPORTS / f"{name}-interview-prep.md")
        return
    rp = REPORTS / "skills-report.md"
    if not rp.exists():
        sys.exit("Run `jhb skills` first.")
    run_llm(llm.prep_prompt(cv, profile, rp.read_text()), args, REPORTS / "prep-plan.md")


def cmd_track(args):
    if args.jd:
        if args.status not in STATUSES:
            sys.exit(f"status must be one of {STATUSES}")
        track_set(find_jd(args.jd)[0], args.status)
    print(TRACKER.read_text() if TRACKER.exists() else "Tracker empty.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jhb", description="Job Hunt Bot — AI job hunting with Claude")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def llm_cmd(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--print-prompt", action="store_true", help="print the prompt instead of calling Claude")
        return p

    p = sub.add_parser("add", help="save a JD from a URL, file, or stdin (-)")
    p.add_argument("source"); p.add_argument("--name")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("skills", help="most-asked skills across all JDs vs your CV")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--ai", action="store_true", help="also let Claude extract skills (needs API key)")
    p.set_defaults(fn=cmd_skills)

    p = llm_cmd("evaluate", help="fit score + gap analysis for one JD")
    p.add_argument("jd"); p.set_defaults(fn=cmd_evaluate)

    p = llm_cmd("message", help="draft a recruiter / hiring manager / referral message")
    p.add_argument("jd")
    p.add_argument("--to", choices=["recruiter", "hiring-manager", "referral"], default="recruiter")
    p.add_argument("--name", help="recipient's name")
    p.add_argument("--channel", choices=["linkedin", "email", "both"], default="both")
    p.set_defaults(fn=cmd_message)

    p = llm_cmd("prep", help="4-week study plan from skills report, or interview prep for one JD")
    p.add_argument("jd", nargs="?"); p.set_defaults(fn=cmd_prep)

    p = sub.add_parser("track", help="view or update the application tracker")
    p.add_argument("jd", nargs="?"); p.add_argument("status", nargs="?")
    p.set_defaults(fn=cmd_track)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
