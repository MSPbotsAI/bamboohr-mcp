from typing import Any

import httpx

DEFAULT_API_ROOT = "https://api.bamboohr.com/api/gateway.php"
DEFAULT_BASIC_PASSWORD = "mspbots"


class BambooHRError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"BambooHR API error {status_code}: {message}")


class BambooHRClient:
    """Async httpx client for the BambooHR API (gateway.php form).

    Auth is carried per request (stateless — a fresh AsyncClient per call):
      - HTTP Basic: username = API key, password = fixed value (default "mspbots")
      - The company domain is a path segment: {api_root}/{domain}/v1/...
      - `Accept: application/json` forces JSON responses (BambooHR defaults to XML).
    """

    def __init__(
        self,
        api_key: str,
        domain: str,
        api_root: str = DEFAULT_API_ROOT,
        basic_password: str = DEFAULT_BASIC_PASSWORD,
    ):
        self._auth = httpx.BasicAuth(api_key, basic_password)
        self._base_url = f"{api_root.rstrip('/')}/{domain.strip('/')}/v1"

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _clean_params(self, params: dict | None) -> dict:
        if not params:
            return {}
        return {k: v for k, v in params.items() if v is not None}

    async def get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}{path}",
                auth=self._auth,
                headers=self._headers(),
                params=self._clean_params(params),
            )
            self._raise_for_status(resp)
            return resp.json() if resp.status_code != 204 else None

    async def post(self, path: str, body: Any = None) -> httpx.Response:
        """POST and return the raw response.

        BambooHR's create-employee returns 201 with an empty body and a
        `Location` header pointing at the new record, so callers need the
        response object rather than a parsed body.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}{path}",
                auth=self._auth,
                headers=self._headers(json_body=True),
                json=body,
            )
            self._raise_for_status(resp)
            return resp

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            # BambooHR often puts a human-readable reason in this header.
            reason = resp.headers.get("X-BambooHR-Error-Message")
            if reason:
                detail = f"{detail} ({reason})" if detail else reason
            raise BambooHRError(resp.status_code, str(detail))
