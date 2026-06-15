import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MAGIC_LINK_DEV_RETURN_TOKEN", "true")
os.environ.setdefault("MEM0_ENABLED", "false")


@pytest.fixture(scope="session", autouse=True)
async def _init_test_db():
    from app.db import init_db

    await init_db()
