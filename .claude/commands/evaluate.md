---
description: Evaluate one JD against my CV (grade, match table, gaps, talking points)
argument-hint: <jd name | url | pasted JD>
---
Target: $ARGUMENTS
1. If it is a URL or pasted text, save it first: `python3 -m jhb add <url>` (or write it to `jds/<company>-<role>.md`). If WebFetch is available and the page is JS-heavy, fetch it with that instead.
2. Run `python3 -m jhb evaluate <jd> --print-prompt` and follow the printed prompt exactly, using cv.md and profile.yml. Never invent experience.
3. Save the result to `reports/<jd>-evaluation.md` and run `python3 -m jhb track <jd> evaluated`.
