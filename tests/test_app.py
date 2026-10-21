from types import SimpleNamespace as NS

from careerpilot import ai, api, assistant, db, evaluate


def test_chat_tool_loop(monkeypatch):
    jid, _ = db.upsert_job({"company": "ZOHO", "title": "Python Developer", "url": "https://z/1", "description": "Python Django"})
    evaluate.evaluate(jid)
    calls = []
    replies = iter([
        NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="search_jobs", input={"company": "ZOHO"})]),
        NS(stop_reason="end_turn", content=[NS(type="text", text="Zoho has 1 Python role.")]),
    ])

    def fake_create(messages, **kw):
        calls.append(messages)
        return next(replies)

    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "create", fake_create)
    seen = []
    reply, hist = assistant.chat([], "zoho jobs?", on_tool=lambda n, i: seen.append(n))
    assert reply == "Zoho has 1 Python role." and seen == ["search_jobs"]
    tool_result = hist[2]["content"][0]
    assert tool_result["type"] == "tool_result" and "Python Developer" in tool_result["content"]


def test_streamlit_app_renders():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../app/streamlit_app.py", default_timeout=60).run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 8


def test_mcp_tool_list():
    import asyncio
    import mcp.types as types
    assert {t["name"] for t in api.TOOLS} >= {"search_jobs", "pipeline_stats", "skill_insights", "interview_prep"}
