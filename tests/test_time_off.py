"""Tests for bamboohr_list_time_off_requests — see docs/tickets/PRD-18270.ac.json.

Each test function name matches the `tests` entry for its TC-BTO-### case in
that ac.json; the auto-type cases (TC-BTO-012/014/016/020 are manual and
executed separately during self-test) are all covered here via respx mocks.
"""

import asyncio
import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from bamboohr_mcp.config import Settings
from bamboohr_mcp.server import (
    GatewayCredsMiddleware,
    _api_key_var,
    _domain_var,
    create_mcp_server,
)
from bamboohr_mcp.tools import time_off as time_off_tools

ROOT = "https://api.bamboohr.com/api/gateway.php"


def _base(domain: str) -> str:
    return f"{ROOT}/{domain}/v1"


def _text(call_result) -> str:
    """Normalize FastMCP call_tool return into a single string (see test_tools.py)."""
    content = call_result[0] if isinstance(call_result, tuple) else call_result
    parts = []
    for item in content:
        parts.append(getattr(item, "text", str(item)))
    return "\n".join(parts)


def _env_settings(domain: str = "acmeinc", api_key: str = "key123") -> Settings:
    return Settings(auth_mode="env", bamboohr_domain=domain, bamboohr_api_key=api_key)


# TC-BTO-001 --------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_single_day_query_passes_through_all_fields():
    body = [
        {
            "id": "1204",
            "employeeId": "37",
            "name": "Ada Lovelace",
            "status": {"status": "approved", "lastChanged": "2026-08-20"},
            "start": "2026-09-08",
            "end": "2026-09-08",
            "type": {"id": "1", "name": "Vacation"},
            "amount": {"unit": "days", "amount": "1"},
        }
    ]
    respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=body)
    )
    mcp = create_mcp_server(_env_settings())

    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
    )
    parsed = json.loads(_text(result))
    record = parsed[0]
    assert record["employeeId"] == "37"
    assert record["name"] == "Ada Lovelace"
    assert record["type"]["name"] == "Vacation"
    assert record["status"]["status"] == "approved"
    assert record["start"] == "2026-09-08"
    assert record["end"] == "2026-09-08"
    assert record["amount"]["amount"] == "1"


# TC-BTO-002 --------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_weekly_range_query_forwards_full_range():
    body = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=body)
    )
    mcp = create_mcp_server(_env_settings())

    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-01", "end": "2026-09-07"}
    )
    parsed = json.loads(_text(result))
    assert len(parsed) == 3
    req = route.calls.last.request
    assert req.url.params["start"] == "2026-09-01"
    assert req.url.params["end"] == "2026-09-07"


# TC-BTO-003 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_status_filter_forwarded_when_present():
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())
    await mcp.call_tool(
        "bamboohr_list_time_off_requests",
        {"start": "2026-09-01", "end": "2026-09-07", "status": "approved"},
    )
    assert route.calls.last.request.url.params["status"] == "approved"


@pytest.mark.asyncio
@respx.mock
async def test_status_omitted_when_not_passed():
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())
    await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-01", "end": "2026-09-07"}
    )
    assert "status" not in route.calls.last.request.url.params


# TC-BTO-004 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_employee_id_filter_maps_to_employeeId_param():
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())
    await mcp.call_tool(
        "bamboohr_list_time_off_requests",
        {"start": "2026-09-01", "end": "2026-09-07", "employee_id": "42"},
    )
    assert route.calls.last.request.url.params["employeeId"] == "42"


# TC-BTO-005 ----------------------------------------------------------------
@respx.mock
def test_missing_both_headers_returns_401_before_tool_runs():
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    settings = Settings(auth_mode="gateway")
    mcp = create_mcp_server(settings)
    app = GatewayCredsMiddleware(mcp.streamable_http_app(), settings)
    client = TestClient(app)

    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "bamboohr_list_time_off_requests",
                "arguments": {"start": "2026-09-08", "end": "2026-09-08"},
            },
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert set(body["missing_headers"]) == {"domain", "api-key"}
    # The middleware must short-circuit before the tool ever runs — no upstream call.
    assert route.calls.call_count == 0


# TC-BTO-006 ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_env_mode_missing_credentials_returns_no_creds_text():
    # Exercise the tool in isolation with a client_factory that returns None —
    # this is exactly what get_client_from_context() yields when env-mode
    # credentials are missing (create_mcp_server() itself gates on
    # settings.has_credentials before registering any real tool, so the tool
    # function's own guard is tested directly here).
    mcp = FastMCP(name="test-no-creds")
    time_off_tools.register(mcp, lambda: None)

    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
    )
    assert _text(result) == time_off_tools._NO_CREDS


# TC-BTO-007 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_upstream_400_forwarded_verbatim():
    respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(400, json={"message": "invalid start date"})
    )
    mcp = create_mcp_server(_env_settings())
    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
    )
    text = _text(result)
    assert text.startswith("Error: BambooHR API error 400")
    assert "invalid start date" in text


# TC-BTO-008 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_upstream_401_forwarded():
    respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(401, json={"message": "invalid api key"})
    )
    mcp = create_mcp_server(_env_settings())
    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
    )
    text = _text(result)
    assert "401" in text
    assert "invalid api key" in text


# TC-BTO-009 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_upstream_403_includes_reason_header():
    respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(
            403,
            headers={"X-BambooHR-Error-Message": "Access denied for this report"},
            text="Forbidden",
        )
    )
    mcp = create_mcp_server(_env_settings())
    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
    )
    text = _text(result)
    assert "Access denied for this report" in text


# TC-BTO-010 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_empty_result_returns_empty_array_not_error():
    respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())
    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
    )
    text = _text(result)
    assert not text.startswith("Error")
    assert json.loads(text) == []


# TC-BTO-011 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_concurrent_calls_do_not_leak_credentials_across_tenants():
    respx.get(f"{_base('tenanta')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[{"employeeId": "1"}])
    )
    respx.get(f"{_base('tenantb')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[{"employeeId": "2"}])
    )
    mcp = create_mcp_server(Settings(auth_mode="gateway"))

    async def call_as(domain: str, api_key: str) -> str:
        # Mirrors what GatewayCredsMiddleware does per-request; asyncio.Task
        # copies context at creation, so this mutation is local to this task.
        _domain_var.set(domain)
        _api_key_var.set(api_key)
        result = await mcp.call_tool(
            "bamboohr_list_time_off_requests", {"start": "2026-09-08", "end": "2026-09-08"}
        )
        return _text(result)

    text_a, text_b = await asyncio.gather(
        asyncio.create_task(call_as("tenanta", "keyA")),
        asyncio.create_task(call_as("tenantb", "keyB")),
    )
    assert json.loads(text_a) == [{"employeeId": "1"}]
    assert json.loads(text_b) == [{"employeeId": "2"}]


# TC-BTO-013 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_malformed_date_format_forwarded_as_upstream_400():
    respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(400, json={"message": "start is not a valid date"})
    )
    mcp = create_mcp_server(_env_settings())
    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests", {"start": "09/08/2026", "end": "2026-09-08"}
    )
    text = _text(result)
    assert text.startswith("Error: BambooHR API error 400")
    assert "start is not a valid date" in text


# TC-BTO-015 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_injection_like_params_are_passed_through_as_literal_strings():
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())
    injected_employee = "1' OR '1'='1"
    injected_status = "<script>alert(1)</script>"

    result = await mcp.call_tool(
        "bamboohr_list_time_off_requests",
        {
            "start": "2026-09-08",
            "end": "2026-09-08",
            "employee_id": injected_employee,
            "status": injected_status,
        },
    )
    assert not _text(result).startswith("Error")
    req = route.calls.last.request
    assert req.url.params["employeeId"] == injected_employee
    assert req.url.params["status"] == injected_status


# TC-BTO-017 ----------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_unknown_enum_value_forwarded_unvalidated():
    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())
    await mcp.call_tool(
        "bamboohr_list_time_off_requests",
        {"start": "2026-09-08", "end": "2026-09-08", "status": "bogus_status"},
    )
    assert route.calls.last.request.url.params["status"] == "bogus_status"


# TC-BTO-018 / TC-BTO-019 -----------------------------------------------------
# FastMCP validates arguments against the tool's pydantic-derived schema before
# the function body runs, raising ToolError with a "Field required" message —
# confirmed empirically (mcp.server.fastmcp.exceptions.ToolError) rather than
# assumed, since `mcp.call_tool`'s failure mode isn't otherwise documented here.
@pytest.mark.asyncio
@respx.mock
async def test_missing_required_start_param_rejected_before_upstream_call():
    from mcp.server.fastmcp.exceptions import ToolError

    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())

    with pytest.raises(ToolError, match="start"):
        await mcp.call_tool("bamboohr_list_time_off_requests", {"end": "2026-09-08"})

    assert route.calls.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_missing_required_end_param_rejected_before_upstream_call():
    from mcp.server.fastmcp.exceptions import ToolError

    route = respx.get(f"{_base('acmeinc')}/time_off/requests").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = create_mcp_server(_env_settings())

    with pytest.raises(ToolError, match="end"):
        await mcp.call_tool("bamboohr_list_time_off_requests", {"start": "2026-09-08"})

    assert route.calls.call_count == 0
