import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import plan_draft as draft_svc


@pytest.mark.asyncio
async def test_plan_draft_confirm_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "plan@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        from app.db import async_session

        user_id = verify.json()["user_id"]
        today = date.today()
        meeting_at = datetime.combine(today, datetime.min.time()).replace(
            hour=16, tzinfo=timezone.utc
        )
        swim_at = datetime.combine(today, datetime.min.time()).replace(
            hour=18, tzinfo=timezone.utc
        )
        async with async_session() as db:
            await draft_svc.save_draft(
                db,
                uuid.UUID(user_id),
                {
                    "intent": "plan_day",
                    "proposed_tasks": [
                        {
                            "title": "Meeting",
                            "due_at": meeting_at.isoformat(),
                            "estimated_minutes": 60,
                            "priority": 2,
                            "category": "work",
                        },
                        {
                            "title": "Swimming",
                            "due_at": swim_at.isoformat(),
                            "estimated_minutes": 45,
                            "priority": 1,
                            "category": "health",
                        },
                    ],
                },
            )

        draft = await client.get("/api/v2/tasks/plan-draft", headers=headers)
        assert draft.status_code == 200
        assert len(draft.json()["proposed_tasks"]) == 2

        confirm = await client.post("/api/v2/tasks/plan-draft/confirm", headers=headers)
        assert confirm.status_code == 200
        assert len(confirm.json()["created"]) == 2

        view = await client.get("/api/v2/tasks/today-view", headers=headers)
        assert view.status_code == 200
        assert view.json()["summary"]["total"] >= 2


@pytest.mark.asyncio
async def test_text_turn_multi_session():
    transport = ASGITransport(app=app)
    today = date.today()
    meeting_at = datetime.combine(today, datetime.min.time()).replace(
        hour=16, tzinfo=timezone.utc
    )
    fake_plan = {
        "intent": "plan_day",
        "proposed_tasks": [
            {
                "title": "Meeting",
                "due_at": meeting_at.isoformat(),
                "estimated_minutes": 60,
                "priority": 2,
                "category": "work",
            }
        ],
        "clarifying_question": None,
    }
    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock) as mock_extract,
        patch("app.modules.brain.context_builder.memory_search", return_value=[]),
        patch("app.routers.turn.remember_turn"),
    ):
        mock_llm.side_effect = [
            "Got it — meeting at 4pm. Add to Today?",
            "Sure, we can move swimming to 7pm instead.",
        ]
        mock_extract.return_value = fake_plan

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "multi@example.com"})
            token = reg.json()["dev_token"]
            verify = await client.post("/api/v2/auth/verify", json={"token": token})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            sid = "test-session-123"

            r1 = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "meeting by 4pm", "session_id": sid},
            )
            assert r1.status_code == 200
            assert r1.json()["session_id"] == sid
            assert r1.json()["plan_draft"] is not None

            r2 = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "actually swim at 7", "session_id": sid},
            )
            assert r2.status_code == 200
            assert mock_llm.call_count == 2
            second_call_messages = mock_llm.call_args_list[1][0][0]
            assert len(second_call_messages) >= 2
