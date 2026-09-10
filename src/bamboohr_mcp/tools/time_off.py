"""BambooHR time-off request tools (read-only).

Tool naming convention: <vendor>_<action>_<resource>
Endpoint (BambooHR gateway.php v1):
  - GET /time_off/requests   list time-off requests
"""

import json
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..api_client import BambooHRClient, BambooHRError

_NO_CREDS = (
    "Error: No BambooHR credentials configured. "
    "Set BAMBOOHR_DOMAIN + BAMBOOHR_API_KEY, or use AUTH_MODE=gateway with the "
    "domain and api-key headers."
)


def _dump(result) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)


def register(mcp: FastMCP, client_factory: Callable[[], BambooHRClient | None]) -> None:
    @mcp.tool()
    async def bamboohr_list_time_off_requests(
        start: str,
        end: str,
        status: str | None = None,
        employee_id: str | None = None,
        time_off_type_id: str | None = None,
    ) -> str:
        """List BambooHR time-off requests in a date range (GET /time_off/requests).

        Lets attendance SOPs populate the Leave Status section from real
        BambooHR data instead of manual input. `start`/`end` accept a single
        day (equal values) or a range spanning multiple days. Filters are
        optional and passed through to BambooHR unvalidated — this tool does
        not locally check enum values or date ordering; BambooHR's own
        response (including its error responses) is authoritative.

        Args:
            start: Range start date, YYYY-MM-DD (required).
            end: Range end date, YYYY-MM-DD (required).
            status: Optional BambooHR status filter, e.g. "approved",
                "requested", "denied", "canceled", "superseded".
            employee_id: Optional BambooHR employee id to filter to one
                employee (mapped to the upstream `employeeId` query param).
            time_off_type_id: Optional BambooHR time-off type id (the numeric
                id, not the display name) to filter to one leave type (mapped
                to the upstream `type` query param).
        """
        client = client_factory()
        if client is None:
            return _NO_CREDS
        try:
            result = await client.get(
                "/time_off/requests",
                params={
                    "start": start,
                    "end": end,
                    "status": status,
                    "employeeId": employee_id,
                    "type": time_off_type_id,
                },
            )
            return _dump(result)
        except BambooHRError as e:
            return f"Error: {e}"
