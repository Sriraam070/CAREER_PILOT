"""Company list: companies.yml (ATS settings) merged with the Notion-synced table."""
import json
import re

import yaml

from . import db
from .config import ROOT

PATH = ROOT / "companies.yml"


def load():
    data = yaml.safe_load(PATH.read_text()) if PATH.exists() else {"companies": []}
    return data.get("companies") or []


def save(companies):
    header = "".join(l for l in PATH.read_text().splitlines(True) if l.startswith("#")) if PATH.exists() else ""
    PATH.write_text(header + yaml.safe_dump({"companies": companies}, sort_keys=False, allow_unicode=True, width=120))


def sync_to_db():
    """companies.yml → companies table (Notion pull may have added rows; yml adds ATS)."""
    with db.conn() as c:
        for co in load():
            c.execute("""INSERT INTO companies(name, tiers, careers_url, ats, ats_params, updated_at)
                         VALUES (?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET ats=excluded.ats,
                         ats_params=excluded.ats_params,
                         careers_url=COALESCE(NULLIF(excluded.careers_url,''), companies.careers_url),
                         tiers=COALESCE(companies.tiers, excluded.tiers)""",
                      (co["name"], json.dumps(co.get("tiers", [])), co.get("careers_url", ""),
                       co.get("ats", "manual"), json.dumps(co.get("params", {})), db.now()))
    # Notion-only companies get added to the yml as manual so you can map them
    known = {c["name"] for c in load()}
    extra = [r for r in db.rows("SELECT * FROM companies") if r["name"] not in known]
    if extra:
        save(load() + [{"name": r["name"], "tiers": json.loads(r["tiers"] or "[]"), "careers_url": r["careers_url"] or "",
                        "ats": "adzuna", "params": {"company": r["name"].title()}, "verified": False} for r in extra])
    return len(load())


def all_companies():
    out = []
    for r in db.rows("SELECT * FROM companies ORDER BY name"):
        r["tiers"] = json.loads(r["tiers"] or "[]")
        r["ats_params"] = json.loads(r["ats_params"] or "{}")
        out.append(r)
    return out


def _n(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def resolve(name):
    """Map a company name as written in a job posting to your list entry (name or alias, prefix match)."""
    n = _n(name)
    for co in load():
        keys = [_n(co["name"])] + [_n(a) for a in co.get("aliases", [])]
        if any(k and (n == k or len(k) >= 3 and n.startswith(k) or len(n) >= 4 and k.startswith(n)) for k in keys):
            return co
    return None


def tier_of(name):
    co = resolve(name)
    return co.get("tiers", []) if co else []
