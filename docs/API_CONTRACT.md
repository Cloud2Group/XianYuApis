# XianYuApis 标准 API 契约

- 层级：L4
- 状态：Draft
- 版本：v1
- 更新时间：2026-07-28

## 文档职责

本文件定义所有业务域共用的 Query、Command、Operation、Event、错误和版本语义。具体消息、商品、订单等字段由对应能力契约补充。

## 基础协议

- HTTP + JSON；
- 路径前缀 `/v1`；
- 第一阶段只在本机、内网或 VPN 提供；
- Event 第一阶段通过 SSE 输出；
- 调用身份由内部 Token 或本机身份解析为 Actor。

## Query

Query 使用资源式接口：

```http
GET /v1/accounts/{account_id}
GET /v1/accounts/{account_id}/runtime
GET /v1/accounts/{account_id}/session
GET /v1/accounts/{account_id}/state-events
GET /v1/accounts/{account_id}/capabilities
GET /v1/accounts/{account_id}/conversations
GET /v1/conversations/{conversation_id}/messages
GET /v1/operations/{operation_id}
GET /v1/accounts/{account_id}/sync-status
GET /v1/accounts/{account_id}/sync-jobs
GET /v1/sync-jobs/{sync_job_id}
```

通用参数：

```text
consistency=local|fresh
cursor=CURSOR
limit=NUMBER
```

响应：

```json
{
  "data": {},
  "meta": {
    "source": "local|app_native",
    "observed_at": "TIMESTAMP",
    "sync_status": "complete|partial|stale|syncing",
    "next_cursor": null
  }
}
```

## Command

所有写操作通过统一入口提交：

```http
POST /v1/commands
```

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "message.send",
  "idempotency_key": "IDEMPOTENCY_KEY",
  "expected_version": null,
  "wait_policy": {
    "mode": "fail_fast|wait_until_online",
    "deadline_at": null
  },
  "confirmation": null,
  "reason": null,
  "parameters": {}
}
```

规则：

- 一个 Command 只包含一个 `account_id`；
- 所有写 Command 都需要 `idempotency_key`；
- 高影响 Capability 按声明要求 `expected_version`、`confirmation` 和 `reason`；
- Actor 从认证上下文获取，不由普通参数伪造；
- `wait_until_online` 必须提供截止时间。

接收响应：

```json
{
  "data": {
    "operation_id": "OPERATION_ID",
    "status": "accepted"
  }
}
```

`accepted` 只表示 Command 已持久化。

## Operation

```json
{
  "id": "OPERATION_ID",
  "account_id": "ACCOUNT_ID",
  "actor": {
    "id": "ACTOR_ID",
    "type": "operator|service|system|ai|third_party"
  },
  "capability": "message.send",
  "status": "accepted|queued|running|succeeded|failed|timed_out|needs_login|needs_verification|cancelled",
  "transport": "app_native",
  "worker_type": "attached_app|headless_app",
  "created_at": "TIMESTAMP",
  "started_at": null,
  "finished_at": null,
  "result": null,
  "error": null
}
```

## Capability Discovery

```http
GET /v1/accounts/{account_id}/capabilities
```

```json
{
  "name": "item.price.update",
  "status": "available|account_paused|needs_login|needs_verification|runtime_degraded|manual_control_conflict|app_version_unsupported|not_verified|temporarily_unavailable",
  "risk_level": "normal|sensitive|destructive",
  "app_version": "APP_VERSION",
  "worker_type": "attached_app|headless_app",
  "verification": "static_found|poc|dynamic_verified|api_ready"
}
```

## Event

```http
GET /v1/events/stream?account_id=ACCOUNT_ID&cursor=CURSOR
Accept: text/event-stream
```

SSE `id` 使用稳定 `event_id`：

```json
{
  "event_id": "EVENT_ID",
  "event_type": "message.received",
  "account_id": "ACCOUNT_ID",
  "occurred_at": "TIMESTAMP",
  "cursor": "CURSOR",
  "data": {}
}
```

规则：

- Event 先落账本，再进入 SSE；
- 采用至少一次投递；
- 调用者按 `event_id` 去重；
- 重连时使用 SSE `Last-Event-ID` 或显式 cursor。
- 同一 `conversation_id` 内按平台观察顺序投递；
- 不承诺不同会话之间的全局顺序；
- 消息以 `message_id` 做业务去重，Event 以 `event_id` 做传输去重；
- 发生乱序时以会话序号、平台时间和后续补偿查询校正。

## 错误

```json
{
  "error": {
    "code": "runtime_unavailable",
    "message": "Account Runtime is offline",
    "retryable": true,
    "operation_id": null,
    "details": {}
  }
}
```

第一批通用错误：

```text
invalid_request
actor_forbidden
account_not_found
account_paused
account_ending
account_ended
capability_unavailable
app_version_unsupported
runtime_unavailable
runtime_degraded
manual_control_conflict
needs_login
needs_verification
version_conflict
idempotency_conflict
operation_timed_out
platform_rejected
internal_error
```

## 原始 App 数据

- 标准 API 不返回 AIM、MTop、Objective-C 或 Flutter 原始对象；
- 标准对象可以携带内部 `raw_ref`，普通响应默认隐藏；
- 诊断工具按内部权限读取脱敏原始证据。

## 版本

- 标准 API 版本与闲鱼 App 版本独立；
- 兼容字段只新增，不改变已有字段语义；
- 破坏性契约变化进入新的 API 主版本；
- App 失配通过 Capability 状态和结构化错误表达。

## 同步契约

账号首次接入和断线补偿按 `item`、`conversation_message`、`order_review` 三个业务域分别维护 `SyncJob`、游标、检查点和缺口。默认调度顺序为“商品 → 会话与消息 → 订单与评价”，但域之间不组成不可拆分的长事务。详细请求、状态和事件见 [`docs/api/SYNC_V1.md`](api/SYNC_V1.md)。

## 账号与 Runtime 状态契约

账号对外同时返回 `account_lifecycle_state` 和 `runtime_state`。前者表示托管关系，后者表示 Worker、原生连接和认证健康；`hosted + needs_login`、`hosted + degraded` 等组合均为有效状态。登录摘要、状态门禁、人工操作和恢复规则见 [`docs/api/SESSION_RUNTIME_V1.md`](api/SESSION_RUNTIME_V1.md)。
