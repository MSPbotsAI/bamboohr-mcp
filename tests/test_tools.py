"""Client + tool tests — verify URL/auth/params/body via a mocked BambooHR API (respx)."""

import base64

import httpx
import pytest
import respx

from bamboohr_mcp.api_client import BambooHRClient, BambooHRError
from bamboohr_mcp.config import Settings
from bamboohr_mcp.server import create_mcp_server

ROOT = "https://api.bamboohr.com/api/gateway.php"
BASE = f"{ROOT}/acmeinc/v1"


def _client() -> BambooHRClient:
    return BambooHRClient(api_key="key123", domain="acmeinc", api_root=ROOT)


def _basic(req: httpx.Request) -> tuple[str, str]:
    raw = req.headers["Authorization"].split(" ", 1)[1]
    user, _, pwd = base64.b64decode(raw).decode().partition(":")
    return user, pwd


@pytest.mark.asyncio
@respx.mock
async def test_get_uses_basic_auth_and_domain_path():
    route = respx.get(f"{BASE}/employees/123").mock(
        return_value=httpx.Response(200, json={"id": "123", "firstName": "Ada"})
    )
    result = await _client().get("/employees/123", params={"fields": "firstName"})

    assert result == {"id": "123", "firstName": "Ada"}
    req = route.calls.last.request
    assert _basic(req) == ("key123", "mspbots")  # api-key as username, fixed password
    assert req.headers["Accept"] == "application/json"
    assert req.url.params["fields"] == "firstName"


@pytest.mark.asyncio
@respx.mock
async def test_create_returns_201_with_location():
    route = respx.post(f"{BASE}/employees/").mock(
        return_value=httpx.Response(
            201, headers={"Location": f"{BASE}/employees/999"}, content=b""
        )
    )
    resp = await _client().post("/employees/", {"firstName": "Ada", "lastName": "Lovelace"})

    assert resp.status_code == 201
    assert resp.headers["Location"].endswith("/employees/999")
    import json

    assert json.loads(route.calls.last.request.content) == {
        "firstName": "Ada",
        "lastName": "Lovelace",
    }


@pytest.mark.asyncio
@respx.mock
async def test_error_status_raises_with_reason_header():
    respx.post(f"{BASE}/employees/").mock(
        return_value=httpx.Response(
            409,
            headers={"X-BambooHR-Error-Message": "Invalid value for field 'status'"},
            text="Conflict",
        )
    )
    with pytest.raises(BambooHRError) as exc:
        await _client().post("/employees/", {"firstName": "A", "lastName": "B"})
    assert exc.value.status_code == 409
    assert "Invalid value" in str(exc.value)


def _text(call_result) -> str:
    """Normalize FastMCP call_tool return into a single string."""
    # Newer FastMCP returns (content_list, raw); older returns content_list.
    content = call_result[0] if isinstance(call_result, tuple) else call_result
    parts = []
    for item in content:
        parts.append(getattr(item, "text", str(item)))
    return "\n".join(parts)


@pytest.mark.asyncio
@respx.mock
async def test_create_employee_tool_parses_new_id():
    respx.post(f"{BASE}/employees/").mock(
        return_value=httpx.Response(201, headers={"Location": f"{BASE}/employees/42"})
    )
    settings = Settings(auth_mode="env", bamboohr_domain="acmeinc", bamboohr_api_key="key123")
    mcp = create_mcp_server(settings)

    result = await mcp.call_tool(
        "bamboohr_create_employee",
        {"first_name": "Ada", "last_name": "Lovelace"},
    )
    text = _text(result)
    assert '"employee_id": "42"' in text
    assert '"status": "created"' in text
