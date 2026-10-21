import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
os.environ["CAREERPILOT_DB"] = str(Path(_tmp) / "test.db")
for k in ("ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "NOTION_TOKEN"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CV = """# Test Person
## Technical Skills
Python, Django, SQL, MySQL, Docker, Git, REST APIs, Linux
## Experience
- Built Django apps; optimised SQL; automated workflows with REST APIs.
"""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from careerpilot import config, db, evaluate, reports
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.yml")
    monkeypatch.setattr(config, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(reports, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(evaluate, "cv_text", lambda: CV)
    monkeypatch.setattr(reports, "cv_text", lambda: CV)
    dbfile = tmp_path / "t.db"
    monkeypatch.setattr(db, "DB_PATH", dbfile)
    s = config.DEFAULT_SETTINGS
    import copy
    s = copy.deepcopy(s)
    s["profile"].update(name="Test Person", email="t@example.com", phone="99999", linkedin="https://linkedin.com/in/t",
                        github="https://github.com/t", years_experience=2.5, location="Chennai")
    config.save_settings(s)
    yield tmp_path
