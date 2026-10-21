"""Runs the real assisted-apply flow in Chromium against a local mock form."""
import os
from pathlib import Path

import pytest

from careerpilot import apply, config, db

pw = pytest.importorskip("playwright.sync_api")
if Path("/opt/pw-browsers/chromium").exists():
    os.environ.setdefault("CAREERPILOT_CHROMIUM", "/opt/pw-browsers/chromium")
FORM = (Path(__file__).parent / "fixtures" / "apply_form.html").read_text()
SENSITIVE = ('<label for="ctc">Current CTC *</label><input id="ctc" required>'
             '<label><input type="checkbox" id="dec" required> I hereby declare the above is true</label>')


def _launch_ok():
    try:
        with pw.sync_playwright() as p:
            p.chromium.launch(headless=True, executable_path=os.environ.get("CAREERPILOT_CHROMIUM") or None).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _launch_ok(), reason="Chromium not available")


def _setup(tmp_path, html, monkeypatch, source="greenhouse", auto=False):
    f = tmp_path / "form.html"; f.write_text(html)
    (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4 test")
    monkeypatch.setattr(apply, "ROOT", tmp_path)
    s = config.settings(); s["profile"]["resume_path"] = "resume.pdf"; s["automation"]["auto_submit_simple_forms"] = auto
    config.save_settings(s)
    jid, _ = db.upsert_job({"company": "ACME", "title": "Python Developer", "url": f.as_uri(), "source": source})
    aid = apply.queue(jid)
    apply.decide(aid, True)
    return jid, aid


def test_sensitive_form_is_prefilled_but_never_submitted(tmp_path, monkeypatch):
    jid, aid = _setup(tmp_path, FORM.replace("SENSITIVE_BLOCK", SENSITIVE), monkeypatch, auto=True)
    r = apply.assist(aid, headless=True, wait_for_user=False, log=lambda *_: None)
    assert set(r["filled"]) >= {"First Name *", "Last Name *", "Email *", "Phone", "LinkedIn Profile"}
    assert "Current CTC *" in r["sensitive"] and any("declare" in s for s in r["sensitive"])
    assert r["submitted"] is False and not db.already_applied(jid)


def test_simple_approved_form_can_auto_submit_when_enabled(tmp_path, monkeypatch):
    jid, aid = _setup(tmp_path, FORM.replace("SENSITIVE_BLOCK", ""), monkeypatch, auto=True)
    r = apply.assist(aid, headless=True, wait_for_user=False, log=lambda *_: None)
    assert r["sensitive"] == [] and r["unknown"] == [] and r["submitted"] is True
    assert db.already_applied(jid)


def test_auto_submit_off_by_default(tmp_path, monkeypatch):
    jid, aid = _setup(tmp_path, FORM.replace("SENSITIVE_BLOCK", ""), monkeypatch, auto=False)
    r = apply.assist(aid, headless=True, wait_for_user=False, log=lambda *_: None)
    assert r["submitted"] is False and not db.already_applied(jid)
