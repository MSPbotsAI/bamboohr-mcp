# bamboohr-mcp

A **stateless HTTP MCP service** that exposes the **BambooHR** employee APIs as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools consumable by Claude and other MCP clients.

Focused on **employee creation**, plus supporting reads (get / list / field discovery). It calls the BambooHR gateway API:

```
https://api.bamboohr.com/api/gateway.php/{domain}/v1/...
```

## Architecture

- **Stateless** — no user state, no credential storage, no session persistence between requests.
- **Concurrent-safe** — per-request credential isolation via Python `contextvars`; concurrent requests never bleed credentials.
- **Dual auth modes** — per-request credentials via HTTP headers (`gateway` mode, default, SOP-compliant) or shared credentials from env vars (`env` mode, local dev only).
- **Two transports** — HTTP server (`MCP_TRANSPORT=http`) for production, stdio (`MCP_TRANSPORT=stdio`) for local development.

### Credential mapping

The MCP client sends credentials to **this service** via headers; the service maps them to what the **BambooHR API** expects:

| Client → this service (header) | This service → BambooHR (upstream)             |
|--------------------------------|------------------------------------------------|
| `domain: <companyDomain>`      | path segment: `.../gateway.php/<domain>/v1/...` |
| `api-key: <apiKey>`            | HTTP Basic auth username                        |
| — (fixed)                      | HTTP Basic auth password: `mspbots`             |

BambooHR uses **HTTP Basic auth** with the API key as the username and a fixed password (`mspbots`, configurable via `BAMBOOHR_BASIC_PASSWORD`). The service also sends `Accept: application/json` so responses are JSON.

## Endpoints

| Method | Path      | Description              |
|--------|-----------|--------------------------|
| POST   | `/mcp`    | MCP protocol entry point |
| GET    | `/health` | Health check             |

Default port: **8080** (configurable via `MCP_HTTP_PORT`).

## HEADER 授权参数说明

In `gateway` mode (default), every `POST /mcp` request must include the following headers. Missing either one returns `401`.

### `domain`

| 项目 | 说明 |
|------|------|
| 类型 | string |
| 是否必填 | 必填 |
| 默认值 | 无 |
| 枚举值 | 无 |
| 字段描述 | BambooHR 公司子域（company domain），作为 URL 路径段：`.../gateway.php/{domain}/v1/...`。 |
| Example | `acmeinc` |

### `api-key`

| 项目 | 说明 |
|------|------|
| 类型 | string |
| 是否必填 | 必填 |
| 默认值 | 无 |
| 枚举值 | 无 |
| 字段描述 | BambooHR API key，作为 HTTP Basic auth 的用户名（密码固定为 `mspbots`）。 |
| Example | `a1b2c3d4e5f6...` |

## Configuration

| Variable                  | Required      | Default                                    | Description                                                                |
|---------------------------|---------------|--------------------------------------------|----------------------------------------------------------------------------|
| `AUTH_MODE`               | No            | `gateway`                                  | `gateway` (per-request headers, SOP-compliant) or `env` (shared, dev only) |
| `DOMAIN_HEADER`           | No            | `domain`                                   | Header name carrying the company domain in gateway mode                    |
| `API_KEY_HEADER`          | No            | `api-key`                                  | Header name carrying the API key in gateway mode                           |
| `BAMBOOHR_API_ROOT`       | No            | `https://api.bamboohr.com/api/gateway.php` | BambooHR gateway root (domain is inserted per request)                     |
| `BAMBOOHR_BASIC_PASSWORD` | No            | `mspbots`                                  | Fixed HTTP Basic-auth password                                             |
| `BAMBOOHR_DOMAIN`         | env mode only | —                                          | Company domain used in `env` mode (local dev only)                         |
| `BAMBOOHR_API_KEY`        | env mode only | —                                          | API key used in `env` mode (local dev only)                                |
| `MCP_TRANSPORT`           | No            | `stdio`                                    | Transport: `http` or `stdio`                                               |
| `MCP_HTTP_PORT`           | No            | `8080`                                     | HTTP listen port                                                           |
| `MCP_HTTP_HOST`           | No            | `0.0.0.0`                                  | HTTP listen host                                                           |

## Tool List

Naming convention: `<vendor>_<action>_<resource>`.

| Tool                        | Description                                              | Parameters                                                                                                                    |
|-----------------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `bamboohr_create_employee`  | Create a new employee (`POST /employees/`)               | `first_name` (str, **required**), `last_name` (str, **required**), `work_email`, `job_title`, `department`, `division`, `location`, `hire_date` (YYYY-MM-DD), `employee_number`, `status`, `additional_fields` (dict) — all optional |
| `bamboohr_get_employee`     | Get one employee (`GET /employees/{id}`)                 | `employee_id` (str, required; `"0"` = self), `fields` (str, optional comma-separated field names)                            |
| `bamboohr_list_employees`   | List the employee directory (`GET /employees/directory`) | none                                                                                                                          |
| `bamboohr_list_fields`      | List available field names (`GET /meta/fields`)          | none                                                                                                                          |
| `bamboohr_list_time_off_requests` | List time-off requests in a date range (`GET /time_off/requests`) | `start` (str, **required**, YYYY-MM-DD), `end` (str, **required**, YYYY-MM-DD), `status`, `employee_id`, `time_off_type_id` — all optional |

**Notes**
- `bamboohr_create_employee` requires only `first_name` + `last_name`. Any other writable field can be passed via `additional_fields` using BambooHR field names (e.g. `{"homeEmail": "a@b.com"}`) — call `bamboohr_list_fields` to discover valid names. On success it returns the new `employee_id` (parsed from the `201` `Location` header).
- `bamboohr_get_employee` returns only `id` unless fields are requested; a sensible default set is applied when `fields` is omitted.
- `bamboohr_list_time_off_requests` requires `start` + `end` (a single day or a range); `status`/`employee_id`/`time_off_type_id` are passed through to BambooHR unvalidated — no local enum or date-order checking is done, the upstream response (including its errors) is authoritative.

## Quick Start

### Local development (stdio, env mode)

```bash
cp .env.example .env
# Edit .env: set BAMBOOHR_DOMAIN, BAMBOOHR_API_KEY, MCP_TRANSPORT=stdio, AUTH_MODE=env
uv sync
python -m bamboohr_mcp
```

### HTTP server (gateway mode — default, SOP-compliant)

```bash
MCP_TRANSPORT=http uv run bamboohr-mcp
# Pass credentials per-request via the domain and api-key headers
```

### Docker

```bash
docker compose up --build
```

## Test Examples

### Health check

```bash
curl http://localhost:8080/health
```

Expected:
```json
{"status": "ok", "transport": "http", "auth_mode": "gateway"}
```

### Missing credentials → 401

```bash
curl -i -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Expected `401` body:
```json
{
  "error": "Missing credentials",
  "message": "Gateway mode requires the domain and api-key headers",
  "required_headers": ["domain", "api-key"],
  "missing_headers": ["domain", "api-key"]
}
```

### List MCP tools

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "domain: <DOMAIN>" \
  -H "api-key: <API_KEY>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Create an employee

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "domain: <DOMAIN>" \
  -H "api-key: <API_KEY>" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "bamboohr_create_employee",
      "arguments": {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "work_email": "ada@example.com",
        "job_title": "Engineer",
        "hire_date": "2026-08-01"
      }
    }
  }'
```

### Get an employee

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "domain: <DOMAIN>" \
  -H "api-key: <API_KEY>" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "bamboohr_get_employee",
      "arguments": {"employee_id": "123", "fields": "firstName,lastName,workEmail"}
    }
  }'
```

### List employees

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "domain: <DOMAIN>" \
  -H "api-key: <API_KEY>" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"bamboohr_list_employees","arguments":{}}}'
```

### List time-off requests

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "domain: <DOMAIN>" \
  -H "api-key: <API_KEY>" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "bamboohr_list_time_off_requests",
      "arguments": {"start": "2026-09-01", "end": "2026-09-07", "status": "approved"}
    }
  }'
```

## Security

- Credentials are never stored globally or persisted between requests.
- Each request's domain and API key are isolated in `contextvars.ContextVar` and reset after the request completes.
- A fresh `httpx.AsyncClient` is used per upstream call — no session/cookie state.
- The service runs as a non-root user (`bamboohr`, uid 1001) inside the container.
- Never commit real API keys or domains — `.gitignore` excludes `.env`.
