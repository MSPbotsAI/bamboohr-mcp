# 模块：BambooHR MCP 工具（`bamboohr-mcp` 仓库）

`docs/modules/` 是累积事实层，永不冻结，按单追加小节。读它的时候要核对 `path:line`
是否还成立，对不上按「未覆盖」处理，不要照抄——见 `references/docs-tree.md` §6。

## PRD-18270 · 2026-09-10

**上下文**：这是本仓库第一次接入本流水线的 `docs/` 体系，此前既没有 `docs/modules/`
也没有 `docs/tickets-index.md`；本条目是首次建立索引，覆盖当前全部 5 个工具（4 个既有 +
本单新增 1 个），不是只记本单的增量。

**认证与多租户模型**（本单未改动，原样确认仍成立）：
- `src/bamboohr_mcp/config.py:21` `Settings.auth_mode`：`"gateway"`（生产默认，per-request
  header 传凭据）或 `"env"`（本地开发，共享环境变量）。
- `src/bamboohr_mcp/server.py:18-23` 用 `contextvars` 隔离每个请求的 `domain`/`api-key`，
  `GatewayCredsMiddleware`（`server.py:45-105`）在请求进 MCP handler 之前校验两个 header
  都在，缺一个直接 401（工具代码不会被执行）。
- `src/bamboohr_mcp/api_client.py:15-32` `BambooHRClient`：无状态、每次调用新建
  `httpx.AsyncClient`，HTTP Basic Auth（用户名=api-key，固定密码 `mspbots`），域名是路径
  segment（`gateway.php/{domain}/v1/...`）。

**工具清单**（截至 commit `91bcb08`，`dev01.mbagent/PRD-18270` 分支）：

| 工具 | 端点 | 定义位置 |
|---|---|---|
| `bamboohr_create_employee` | `POST /employees/` | `src/bamboohr_mcp/tools/employees.py:37` |
| `bamboohr_get_employee` | `GET /employees/{id}` | `src/bamboohr_mcp/tools/employees.py:108` |
| `bamboohr_list_employees` | `GET /employees/directory` | `src/bamboohr_mcp/tools/employees.py:133` |
| `bamboohr_list_fields` | `GET /meta/fields` | `src/bamboohr_mcp/tools/employees.py:149` |
| `bamboohr_list_time_off_requests` **[PRD-18270 新增]** | `GET /time_off/requests` | `src/bamboohr_mcp/tools/time_off.py:27` |

注册入口：`src/bamboohr_mcp/server.py` 的 `create_mcp_server()`（约 144-148 行），
新增工具模块只需要在这里加一行 `import` + 一行 `register()`。

**已知未验证假设（PRD-18270 引入，尚未闭环）**：
`bamboohr_list_time_off_requests` 的响应字段名（`employeeId`/`name`/`type.name`/`start`/
`end`/`status.status`/`amount`）来自 BambooHR 公开 API 文档，**没有对本组织真实租户验证过**
——对应 `docs/tickets/PRD-18270.md` 的 TC-BTO-020，本轮自测环境没有真实/sandbox 凭据，
未执行。下一次有人拿到真实凭据核验这条时，请回来更新本条目（核对通过就删掉这句「未验证」，
核对不通过就更新上面的字段名并注明实际来源）。

**行为边界**：这个工具不做任何本地参数校验（日期顺序、枚举合法性、SQL/XSS 特殊字符）——
所有过滤参数原样透传给 BambooHR，由上游决定接受还是报错。`start > end`、性能 SLA 这两点
产品尚未定义（见工单 Open Questions），当前实现按「透传给上游」处理，不在工具层拦截。
