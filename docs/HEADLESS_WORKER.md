# Headless App Worker 内部执行契约

- 层级：L2/L4
- 状态：Draft
- 版本：v1
- 更新时间：2026-07-28

## 文档职责

本文件定义 Headless App Worker 在系统中的位置、责任边界和内部调用接口。它是 App 原生执行适配器，不是对外业务 API，也不是 AI 或多账号控制平面。

## 固定边界

```text
标准 API / 执行内核
        ↓
Account Runtime
        ↓
Headless App Worker
        ↓
闲鱼原生协议与平台
```

### Account Runtime 持有的职责

- `account_lifecycle_state` 和 `runtime_state`；
- 单账号 Operation 队列、资源串行和执行租约；
- SyncJob、游标、检查点和业务 DB；
- Command 幂等、权限、确认、超时和审计；
- 标准领域对象、Event 账本和调用者响应；
- Attached Worker 与 Headless Worker 的切换。

### Headless Worker 持有的职责

- 使用指定账号的 Session Vault 引用和稳定 Device Profile；
- 建立和维护 App 原生登录态、AIM/ACCS、MTop、心跳和重连；
- 执行已经在 Capability Registry 注册且由 Runtime 下发的单账号原生调用；
- 把原生回调、平台结果、错误码和连接状态转换成内部传输结果；
- 保存与本次原生调用对应的脱敏 `raw_ref` 和诊断证据；
- 在一个账号范围内报告健康状态和事件。

AI 回复、价格策略、商业规则、HTTP API、业务账本和跨账号调度由上层组件持有。Worker 只执行收到的能力和参数。

## Worker 与 Attached App 的关系

`Attached App Worker` 和 `Headless App Worker` 都实现同一个 `AppNativeTransport` 契约：

```text
AppNativeTransport
  ├── AttachedAppWorker   当前真实 App + Native Bridge
  └── HeadlessAppWorker   目标原生协议进程
```

上层只依赖标准的 Query、Command、Operation 和 Event。Worker 类型、版本和原生证据进入 Operation/Capability 元数据，业务 schema 保持稳定。

## 内部接口 v1

接口是逻辑契约，当前 Attached 阶段使用 Unix Domain Socket + JSONL；Headless 阶段可以替换传输实现，但保留方法语义和版本隔离。

### `start_session`

```json
{
  "protocol": "worker/1",
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID",
  "session_ref": "SESSION_VAULT_REF",
  "device_profile_ref": "DEVICE_PROFILE_REF",
  "runtime_generation": 3
}
```

作用：加载指定账号的私密会话引用，启动原生连接和心跳。Worker 不接收明文票据。

### `health`

```json
{
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID"
}
```

返回当前 Worker 版本、账号绑定、连接状态、认证摘要、最后心跳、重连次数和支持的传输能力。

### `query`

```json
{
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID",
  "capability": "conversation.list",
  "parameters": {},
  "consistency": "local|fresh"
}
```

作用：通过当前 App 原生能力读取或刷新一个账号的标准化结果。业务副本和最终查询响应由 Runtime/执行内核落账。

### `execute`

```json
{
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID",
  "operation_id": "OPERATION_ID",
  "capability": "message.send",
  "idempotency_key": "IDEMPOTENCY_KEY",
  "parameters": {}
}
```

作用：执行一个已经过 Runtime 校验的单账号原生调用。Worker 返回已接收、进行中、平台成功、平台失败、需要登录或需要验证等结果；业务上的重试和最终 Operation 归并由 Runtime 处理。

### `subscribe`

```json
{
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID",
  "cursor": "OPAQUE_CURSOR"
}
```

作用：订阅原生消息回调、状态变化、平台主动事件和执行回调。Worker 只发出原生观察结果，Runtime 负责去重、归属、排序、账本和标准 Event。

### `stop_session`

```json
{
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID",
  "reason": "pause|end_hosting|migration|shutdown",
  "drain_deadline_at": "TIMESTAMP"
}
```

作用：停止接收新调用，按截止时间排空或结束当前连接，并释放账号执行租约。

## 结果信封

所有方法返回统一的内部信封：

```json
{
  "protocol": "worker/1",
  "request_id": "REQUEST_ID",
  "account_id": "ACCOUNT_ID",
  "operation_id": "OPERATION_ID",
  "status": "accepted|running|succeeded|failed|needs_login|needs_verification",
  "result": {},
  "error": {
    "code": "NATIVE_ERROR_CODE",
    "message": "REDACTED_MESSAGE",
    "retryable": true
  },
  "raw_ref": "INTERNAL_RAW_REF",
  "worker": {
    "type": "attached_app|headless_app",
    "version": "WORKER_VERSION"
  }
}
```

`raw_ref` 只指向内部脱敏证据。对外标准 API 由 Runtime 转换为领域对象和稳定错误码。

## 事件与顺序

Worker 事件至少包括：

```text
worker.started
worker.health_changed
worker.session_state_changed
worker.native_event
worker.operation_progress
worker.operation_result
worker.cursor_advanced
worker.stopped
```

- 同一账号、同一会话内按原生观察顺序发送；
- 事件携带 `account_id`、Worker 世代、事件时间和传输序号；
- Runtime 以 `event_id`、`message_id`、`operation_id` 做去重；
- Worker 重启后由 Runtime 用游标和 Query 补偿缺口；
- 传输序号不是对外业务 Event 游标。

## 失败和恢复

- Session 缺失或失效：报告 `needs_login`，等待登录协调器更新 Session Vault；
- 平台验证：报告 `needs_verification`，保留原因和交互会话引用；
- 网络或心跳异常：Worker 自行执行连接级重连，并持续报告 `connecting`/`degraded`；
- 原生调用失败：返回平台错误和 `raw_ref`，由 Runtime 决定是否重试；
- Worker 崩溃：Runtime 回收租约、记录状态并按策略重新启动或结束 Operation；
- App 版本失配：能力标记为不可用，Worker 不猜测新参数。

## 安全与隔离

- 一个 Worker 实例只绑定一个 `account_id` 和一个活动 Runtime 租约；
- 请求只携带 `session_ref`、`device_profile_ref` 等引用，不在 JSONL、日志或 Operation 中传递明文凭证；
- Worker 进程权限、Socket 端点和缓存目录按账号隔离；
- 结束托管时先停止 Worker、清除进程缓存，再由 Session Vault 清除私密资料；
- Worker 不直接接受跨账号批量请求。

## 第一版验收

1. Attached App Worker 可以实现全部 v1 方法的模拟闭环；
2. 单账号真实 AIM 收发结果可以映射到统一结果信封；
3. Runtime 可在 Attached 与 Headless 实现之间切换，标准 API 保持稳定；
4. 登录失效、验证、断线、重连、超时和原生错误均可观察；
5. 同一账号只有一个活动租约，重启后可从游标和 Operation 检查点恢复；
6. Worker 不持有 AI、商业策略或跨账号调度逻辑；
7. Headless 与 Attached 对同一 Capability 的标准结果、错误和事件语义一致。
