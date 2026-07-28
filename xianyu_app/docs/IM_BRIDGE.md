# 单账号原生 IM 桥接契约

## 目标

让业务服务只处理统一事件和命令，App 进程负责登录态、AIM/ACCS 连接、编码、发送和回调。

```text
App callback → Native bridge → Business service
Business command → Native bridge → App AIM service
```

第一版优先使用 Unix Domain Socket；Frida RPC 作为插桩阶段的临时通道。Socket 端点、权限和序列化格式在单账号 POC 中固定后，再抽象为长期服务。

## 当前 POC 的线协议

- 每帧为 UTF-8 JSONL（一个 JSON 对象加一个换行）。
- `protocol` 固定为 `1`，单帧上限 256 KiB，文字上限 64 KiB。
- 首帧为 `hello`，`role` 为 `native`、`business` 或 `observer`。
- Socket 父目录权限 `0700`，Socket 权限 `0600`；账号之间不复用端点。
- App 侧只发送 AIM 事件和接收命令；业务侧不直接读取 App 数据库或登录态。

Python 实现位于 [`../bridge/`](../bridge/)；它已经包含本地模拟闭环和测试，
真实动态插桩可直接使用 `frida_adapter.py`，后续再替换为签名 helper。

该桥是 Attached App Worker 的当前传输实现。它遵循根目录
`docs/HEADLESS_WORKER.md` 的内部方法语义；桥协议版本与标准 HTTP API 版本分别管理。

## 事件格式

### 收到消息

```json
{
  "event": "message.received",
  "account_id": "ACCOUNT_ID",
  "message_id": "MID",
  "sid": "SID",
  "app_cid": "APP_CID",
  "peer_uid": "USER_UID",
  "direction": "in",
  "content_type": "text",
  "text": "TEXT",
  "created_at_ms": 0,
  "raw_ref": "OPTIONAL_LOCAL_REFERENCE"
}
```

### 发送文字

```json
{
  "action": "send_text",
  "request_id": "REQ",
  "account_id": "ACCOUNT_ID",
  "app_cid": "APP_CID",
  "peer_uid": "USER_UID",
  "text": "TEXT",
  "reply_to_mid": "OPTIONAL_MID"
}
```

`reply_to_mid` 有值时优先构造 `AIMPubMsgSendReplyMessage`，否则构造 `AIMPubMsgSendMessage`。

### 结果和状态

```json
{
  "event": "message.send.result",
  "request_id": "REQ",
  "message_id": "MID",
  "status": "accepted",
  "error_code": null,
  "error_message": null
}
```

发送结果的 `status` 分为：

- `accepted`：桥已把命令交给原生端，尚未代表服务器确认。
- `sent`：原生 AIM 成功回调，带有可用的 `message_id` 时记录它。
- `failed`、`timeout`：终态；附带 `error_code` 和 `error_message`。

业务端等待终态，不把 `accepted` 当成买家已收到。

```json
{
  "event": "transport.status",
  "account_id": "ACCOUNT_ID",
  "state": "connected",
  "last_heartbeat_ms": 0,
  "reconnect_count": 0
}
```

## 桥接传输状态机（Runtime 内部）

```text
starting
  → app_ready
  → aim_connecting
  → connected
  → reconnecting
  → auth_refreshing
  → connected
```

业务层应观察状态事件，不直接读取 App 内部连接对象。

该状态机只描述 Attached App/AIM 传输过程。标准 API 对外仍使用 `account_lifecycle_state` 和 `runtime_state` 两个正交字段，映射规则见根目录 `docs/api/SESSION_RUNTIME_V1.md`。

## 必备处理

- 以 `message_id` 做幂等去重；备用数据库和原生回调可能重复报告同一条消息。
- 每个会话串行发送，维护 `app_cid`、`sid` 和 `referenceMid`。
- 发送请求设置超时，区分“已交给 App”“服务器确认”和“失败”。
- AI 回复设置截止时间，超时进入人工队列。
- App 重连时保存最后消息游标，恢复后做一次补偿读取。
- 业务服务退出时保留未完成请求和人工接管标记。

## 第一版验收

1. 手工发来一条文字，Python 收到一条 `message.received`。
2. Python 返回一条 `send_text`，App 原生成功回调。
3. 买家侧收到文字，且本地备用库出现对应落库行。
4. 重复回调只触发一次业务处理。
5. 断线后恢复连接，消息游标和发送队列状态可观测。
