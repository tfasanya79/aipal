from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from app.main import request_logging_middleware
from app.shared.config import Settings


def test_settings_rejects_insecure_production_defaults() -> None:
    try:
        Settings(aipal_env="production", jwt_secret="dev-secret-change-in-production")
    except ValueError as exc:
        assert "JWT_SECRET" in str(exc)
    else:
        raise AssertionError("Expected production settings validation to fail")


def test_settings_accepts_secure_production_values() -> None:
    settings = Settings(
        aipal_env="production",
        jwt_secret="super-secret-production-key",
        magic_link_dev_return_token=False,
        deepseek_api_key="demo-key",
    )
    assert settings.aipal_env == "production"


def test_request_logging_middleware_sets_observability_headers() -> None:
    test_app = FastAPI()
    test_app.middleware("http")(request_logging_middleware)

    @test_app.get("/ping")
    async def ping() -> PlainTextResponse:
        return PlainTextResponse("ok")

    client = TestClient(test_app)
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Response-Time-Ms"].isdigit()
