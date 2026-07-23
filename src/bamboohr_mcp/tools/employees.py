"""BambooHR employee tools (creation-focused, plus supporting reads).

Tool naming convention: <vendor>_<action>_<resource>
Endpoints (BambooHR gateway.php v1):
  - POST /employees/            create an employee
  - GET  /employees/{id}        get one employee (requires `fields`)
  - GET  /employees/directory   list the employee directory
  - GET  /meta/fields           list available field names (helps creation)
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

# Sensible default field set for get-employee (BambooHR returns only `id` otherwise).
_DEFAULT_GET_FIELDS = (
    "firstName,lastName,displayName,workEmail,jobTitle,department,division,"
    "location,hireDate,employeeNumber,status,mobilePhone,supervisor"
)


def _dump(result) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)


def register(mcp: FastMCP, client_factory: Callable[[], BambooHRClient | None]) -> None:
    @mcp.tool()
    async def bamboohr_create_employee(
        first_name: str,
        last_name: str,
        work_email: str | None = None,
        job_title: str | None = None,
        department: str | None = None,
        division: str | None = None,
        location: str | None = None,
        hire_date: str | None = None,
        employee_number: str | None = None,
        status: str | None = None,
        additional_fields: dict | None = None,
    ) -> str:
        """Create a new employee in BambooHR (POST /employees/).

        Only first_name and last_name are required. Any other writable BambooHR
        field can be supplied via `additional_fields` using BambooHR field names
        (e.g. {"homeEmail": "a@b.com", "gender": "Male"}); call
        `bamboohr_list_fields` to discover valid names.

        Args:
            first_name: Legal first name (required).
            last_name: Legal last name (required).
            work_email: Work email address.
            job_title: Job title.
            department: Department name.
            division: Division name.
            location: Location name.
            hire_date: Hire date in YYYY-MM-DD format.
            employee_number: Employee number.
            status: Employment status, e.g. "Active" or "Inactive".
            additional_fields: Extra writable fields keyed by BambooHR field name.
        """
        client = client_factory()
        if client is None:
            return _NO_CREDS

        body: dict = {"firstName": first_name, "lastName": last_name}
        optional = {
            "workEmail": work_email,
            "jobTitle": job_title,
            "department": department,
            "division": division,
            "location": location,
            "hireDate": hire_date,
            "employeeNumber": employee_number,
            "status": status,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        if additional_fields:
            body.update(additional_fields)

        try:
            resp = await client.post("/employees/", body)
        except BambooHRError as e:
            return f"Error: {e}"

        # BambooHR returns 201 with an empty body; the new record's URL is in the
        # Location header (…/employees/{id}). Parse the trailing id when present.
        location = resp.headers.get("Location", "")
        new_id = location.rstrip("/").rsplit("/", 1)[-1] if location else None
        return _dump(
            {
                "status": "created",
                "status_code": resp.status_code,
                "employee_id": new_id,
                "location": location or None,
            }
        )

    @mcp.tool()
    async def bamboohr_get_employee(employee_id: str, fields: str | None = None) -> str:
        """Get a single employee's details from BambooHR (GET /employees/{id}).

        BambooHR requires an explicit list of fields — with none, only `id` is
        returned. A sensible default set is used when `fields` is omitted.

        Args:
            employee_id: The employee ID. Use "0" to resolve to the API key's own
                employee record.
            fields: Comma-separated BambooHR field names to return (overrides the
                default set). Example: "firstName,lastName,workEmail".
        """
        client = client_factory()
        if client is None:
            return _NO_CREDS
        try:
            result = await client.get(
                f"/employees/{employee_id}",
                params={"fields": fields or _DEFAULT_GET_FIELDS},
            )
            return _dump(result)
        except BambooHRError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def bamboohr_list_employees() -> str:
        """List the full employee directory from BambooHR (GET /employees/directory).

        Returns an object with `fields` (the columns present) and `employees`
        (the roster). The directory feature must be enabled for the account.
        """
        client = client_factory()
        if client is None:
            return _NO_CREDS
        try:
            result = await client.get("/employees/directory")
            return _dump(result)
        except BambooHRError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def bamboohr_list_fields() -> str:
        """List all available BambooHR field names (GET /meta/fields).

        Useful for discovering valid field names to pass to
        `bamboohr_create_employee` (via `additional_fields`) or to
        `bamboohr_get_employee` (via `fields`).
        """
        client = client_factory()
        if client is None:
            return _NO_CREDS
        try:
            result = await client.get("/meta/fields")
            return _dump(result)
        except BambooHRError as e:
            return f"Error: {e}"
