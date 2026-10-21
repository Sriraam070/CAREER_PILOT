"""Paths, secrets (.env) and user settings (settings.yml)."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
DB_PATH = Path(os.environ.get("CAREERPILOT_DB", DATA / "careerpilot.db"))


def load_env(path=ROOT / ".env"):
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

DEFAULT_SETTINGS = {
    "profile": {
        "name": "", "email": "", "phone": "", "location": "",
        "linkedin": "", "github": "", "years_experience": 0,
        "resume_path": "resume.pdf",
    },
    "preferences": {
        "target_roles": ["Python Developer", "Backend Developer", "Software Engineer"],
        "keywords": ["python", "django", "backend", "software engineer"],
        "exclude_keywords": ["senior staff", "principal", "director", "intern"],
        "locations": ["Chennai", "Bangalore", "Bengaluru", "Hyderabad", "Remote", "India"],
        "max_years_required": 4,
        "min_salary_lpa": None,          # only used to filter jobs that state a salary
        "company_tiers": ["MARQUEE", "SUPER DREAM", "DREAM", "PRIME", "NEW", "DAY SHARING"],
        "min_match_to_notify": 50,
        "min_match_to_queue": 60,
    },
    "automation": {
        "discover": True,
        "queue_for_approval": True,      # good matches go to the approval queue
        "auto_submit_simple_forms": False,  # never on unless you turn it on
        "notify_email": False,
        "notify_whatsapp": False,
        "check_inbox": False,
        "notion_sync": False,
    },
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


SETTINGS_PATH = ROOT / "settings.yml"


def settings():
    user = yaml.safe_load(SETTINGS_PATH.read_text()) if SETTINGS_PATH.exists() else {}
    return _merge(DEFAULT_SETTINGS, user or {})


def save_settings(s):
    SETTINGS_PATH.write_text(yaml.safe_dump(s, sort_keys=False, allow_unicode=True))


def cv_text():
    p = ROOT / "cv.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def env(name, default=None):
    return os.environ.get(name, default)
