---
description: Draft a recruiter / hiring-manager / referral message for a JD
argument-hint: <jd> [recruiter|hiring-manager|referral] [recipient name]
---
Arguments: $ARGUMENTS  (default audience: recruiter)
1. Run `python3 -m jhb message <jd> --to <audience> [--name "<name>"] --print-prompt` and follow the printed prompt exactly.
2. Verify the LinkedIn connection note is ≤300 characters (count it with `python3 -c "print(len('''...'''))"`) and every claim is backed by cv.md.
3. Save to `output/<jd>-<audience>-message.md`, run `python3 -m jhb track <jd> messaged`, and show the messages ready to copy-paste.
