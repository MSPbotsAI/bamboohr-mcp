import contextvars
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import BambooHRClient
from .config import Settings

# ─────────────────────────────────────────────────────────────────────────────
# Per-request credential contextvars for gateway mode.
# GatewayCredsMiddleware sets these before the MCP handler runs.
# Python asyncio copies context per task, so concurrent requests are isolated.
# ─────────────────────────────────────────────────────────────────────────────
_domain_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bamboohr_domain", default=None
)
_api_key_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bamboohr_api_key", default=None
)


def get_client_from_context(settings: Settings) -> BambooHRClient | None:
    """Resolve the active BambooHRClient for the current request context."""
    if settings.auth_mode == "gateway":
        domain = _domain_var.get()
        api_key = _api_key_var.get()
    else:
        domain = settings.bamboohr_domain
        api_key = settings.bamboohr_api_key

    if not domain or not api_key:
        return None
    return BambooHRClient(
        api_key,
        domain,
        settings.bamboohr_api_root,
        settings.bamboohr_basic_password,
    )


class GatewayCredsMiddleware:
    """ASGI middleware for gateway mode.

    Reads the domain and api-key headers from each /mcp request and stores them
    in contextvars for the duration of that request. Both headers are required;
    returns 401 if either is missing.
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        # Header lookup is case-insensitive in Starlette
        domain = request.headers.get(self.settings.domain_header.lower())
        api_key = request.headers.get(self.settings.api_key_header.lower())

        missing = [
            name
            for name, value in (
                (self.settings.domain_header, domain),
                (self.settings.api_key_header, api_key),
            )
            if not value
        ]
        if missing:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        "Gateway mode requires the "
                        f"{self.settings.domain_header} and {self.settings.api_key_header} headers"
                    ),
                    "required_headers": [
                        self.settings.domain_header,
                        self.settings.api_key_header,
                    ],
                    "missing_headers": missing,
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        domain_ctx = _domain_var.set(domain)
        api_key_ctx = _api_key_var.set(api_key)
        try:
            await self.app(scope, receive, send)
        finally:
            _domain_var.reset(domain_ctx)
            _api_key_var.reset(api_key_ctx)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all tools."""
    # DNS-rebinding protection is disabled because the container runs behind
    # mcp-gateway on an internal Docker network and is never publicly exposed.
    mcp = FastMCP(
        name="bamboohr-mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    def client_factory() -> BambooHRClient | None:
        return get_client_from_context(settings)

    if not settings.has_credentials:
        # Graceful degradation: register only a diagnostic tool when no credentials are available.
        @mcp.tool()
        async def bamboohr_test_connection() -> str:
            """Diagnostic tool shown when credentials are missing; lists config requirements."""
            return (
                "Error: Missing BambooHR credentials.\n\n"
                "Set the required environment variables (env mode):\n"
                "  BAMBOOHR_DOMAIN=your_company_domain\n"
                "  BAMBOOHR_API_KEY=your_api_key\n\n"
                "Or use gateway mode (per-request credentials):\n"
                "  AUTH_MODE=gateway\n"
                f"  Send headers: {settings.domain_header}: <domain>, "
                f"{settings.api_key_header}: <apiKey>"
            )

        print(
            "Warning: No BambooHR credentials found. Only the diagnostic tool is available.",
            file=sys.stderr,
        )
        return mcp

    # Register all tool modules here.
    from .tools import employees

    employees.register(mcp, client_factory)

    return mcp
