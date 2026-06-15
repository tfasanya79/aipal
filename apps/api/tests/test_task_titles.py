import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import plan_draft as draft_svc
from app.services import plan_extractor
from app.services import plan_intent
from app.services import tasks as task_svc


def test_compact_title_truncates_long_phrases():
    title, notes = plan_extractor._compact_title(
        "It To Today So You Can Remind Me To Go To Bed"
    )
    assert len(title.split()) <= 4
    assert notes is not None


def test_heuristic_bedtime():
    assert plan_extractor._heuristic_title("go to bed at night") == "Bedtime"


def test_confirm_intent_detected():
    assert plan_intent.is_confirm_intent("yes add it to today")
    assert plan_intent.is_confirm_intent("sounds good")
    assert not plan_intent.is_confirm_intent("remind me at 8")


@pytest.mark.asyncio
async def test_regex_fallback_no_silent_create():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "titles@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        with patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Want me to add bedtime to Today?"
            with patch(
                "app.routers.turn.plan_extractor.extract_plan",
                new_callable=AsyncMock,
            ) as mock_extract:
                mock_extract.return_value = {
                    "intent": "plan_day",
                    "proposed_tasks": [
                        {
                            "title": "Bedtime",
                            "notes": "go to bed",
                            "due_at": datetime.combine(
                                date.today(), datetime.min.time()
                            )
                            .replace(hour=20, tzinfo=timezone.utc)
                            .isoformat(),
                            "estimated_minutes": 30,
                            "priority": 1,
                            "category": "health",
                        }
                    ],
                    "clarifying_question": None,
                }
                r = await client.post(
                    "/api/v2/turn/text",
                    headers=headers,
                    json={"text": "add it to today remind me to go to bed at 8pm"},
                )
                assert r.status_code == 200
                assert "Created task" not in " ".join(r.json().get("tool_actions") or [])

        view = await client.get("/api/v2/tasks/today-view", headers=headers)
        assert view.json()["summary"]["total"] == 0

        confirm = await client.post("/api/v2/tasks/plan-draft/confirm", headers=headers)
        assert confirm.status_code == 200
        assert len(confirm.json()["created"]) == 1
        assert confirm.json()["created"][0]["title"] == "Bedtime"


@pytest.mark.asyncio
async def test_voice_confirm_via_text():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "vconfirm@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        user_id = uuid.UUID(verify.json()["user_id"])
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        from app.db import async_session

        today = date.today()
        due = datetime.combine(today, datetime.min.time()).replace(
            hour=20, tzinfo=timezone.utc
        )
        async with async_session() as db:
            await draft_svc.save_draft(
                db,
                user_id,
                {
                    "intent": "plan_day",
                    "proposed_tasks": [
                        {
                            "title": "Bedtime",
                            "notes": "sleep",
                            "due_at": due.isoformat(),
                            "estimated_minutes": 30,
                            "priority": 1,
                            "category": "health",
                        }
                    ],
                },
            )

        with patch("app.routers.turn.llm_chat", new_callable=AsyncMock):
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "yes add to today"},
            )
        assert r.status_code == 200
        assert any("Confirmed plan" in a for a in r.json().get("tool_actions") or [])

        view = await client.get("/api/v2/tasks/today-view", headers=headers)
        assert view.json()["summary"]["total"] >= 1


@pytest.mark.asyncio
async def test_task_nudge_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "nudge@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
        user_id = uuid.UUID(verify.json()["user_id"])

        from app.db import async_session
        from app.schemas import TaskCreate

        async with async_session() as db:
            task = await task_svc.create_task(
                db,
                user_id,
                TaskCreate(title="Bedtime", source="test"),
            )
            task_id = task.id

        with patch(
            "app.routers.daily.nudge_svc.build_nudge_message",
            new_callable=AsyncMock,
        ) as mock_nudge:
            mock_nudge.return_value = "Hi friend, 12 minutes to Bedtime."
            r = await client.get(
                f"/api/v2/daily/task-nudge?task_id={task_id}&minutes=12",
                headers=headers,
            )
        assert r.status_code == 200
        body = r.json()
        assert "Bedtime" in body["text"]
        assert body["task_id"] == task_id
