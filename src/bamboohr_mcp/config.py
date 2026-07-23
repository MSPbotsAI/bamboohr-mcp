from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Transport
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"

    # Auth mode:
    # "gateway" — production/SOP-compliant: credentials from HTTP headers per request (no globals)
    # "env"     — local dev only: shared credentials from env vars (not SOP-compliant)
    auth_mode: Literal["env", "gateway"] = "gateway"

    # BambooHR API gateway root. The company domain is inserted per request:
    #   {api_root}/{domain}/v1/...
    bamboohr_api_root: str = "https://api.bamboohr.com/api/gateway.php"

    # BambooHR uses HTTP Basic auth: username = API key, password = fixed value.
    bamboohr_basic_password: str = "mspbots"

    # Header names the MCP client uses in gateway mode. Both are required.
    #   domain_header  -> BambooHR company subdomain (path segment)
    #   api_key_header -> BambooHR API key (Basic-auth username)
    domain_header: str = "domain"
    api_key_header: str = "api-key"

    # Shared credentials for env mode (local dev only).
    bamboohr_domain: str | None = None
    bamboohr_api_key: str | None = None

    @property
    def has_credentials(self) -> bool:
        """Returns True if the server can serve API calls.

        Gateway mode always returns True — each request carries its own credentials.
        Env mode requires both BAMBOOHR_DOMAIN and BAMBOOHR_API_KEY to be set.
        """
        if self.auth_mode == "gateway":
            return True
        return bool(self.bamboohr_domain and self.bamboohr_api_key)


def get_settings() -> Settings:
    return Settings()
