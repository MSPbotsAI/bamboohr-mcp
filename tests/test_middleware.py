"""Gateway middleware tests — verifies both credential headers are required."""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from bamboohr_mcp.config import Settings
from bamboohr_mcp.server import GatewayCredsMiddleware, _api_key_var, _domain_var


def _build_app(settings: Settings) -> Starlette:
    async def echo(_):
        # If we reach here, the middleware let the request through.
        return JSONResponse({"domain": _domain_var.get(), "api_key": _api_key_var.get()})

    app = Starlette(routes=[Route("/mcp", echo, methods=["POST"])])
    return GatewayCredsMiddleware(app, settings)


def test_missing_both_headers_returns_401():
    client = TestClient(_build_app(Settings(auth_mode="gateway")))
    resp = client.post("/mcp", json={})
    assert resp.status_code == 401
    body = resp.json()
    assert body["required_headers"] == ["domain", "api-key"]
    assert set(body["missing_headers"]) == {"domain", "api-key"}


def test_missing_api_key_returns_401():
    client = TestClient(_build_app(Settings(auth_mode="gateway")))
    resp = client.post("/mcp", json={}, headers={"domain": "acmeinc"})
    assert resp.status_code == 401
    assert resp.json()["missing_headers"] == ["api-key"]


def test_both_headers_pass_through_and_isolate():
    client = TestClient(_build_app(Settings(auth_mode="gateway")))
    resp = client.post(
        "/mcp",
        json={},
        headers={"domain": "acmeinc", "api-key": "key123"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"domain": "acmeinc", "api_key": "key123"}
    # Contextvars must be reset after the request completes.
    assert _domain_var.get() is None
    assert _api_key_var.get() is None
