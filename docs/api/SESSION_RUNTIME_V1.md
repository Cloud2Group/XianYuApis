# 账号生命周期与 Runtime 状态 API v1

- 层级：L4
- 状态：Draft
- 版本：v1
- 更新时间：2026-07-28

## 文档职责

本文件定义闲鱼账号的托管生命周期、Account Runtime 运行状态、登录恢复和人工操作状态。它解决“账号是否在托管”和“当前运行时是否能执行”两个不同问题。

## 核心结论

账号使用两个正交字段表达状态：

```text
account_lifecycle_state  = 托管关系处于什么阶段
runtime_state            = Worker / App 原生连接处于什么阶段
```

不把两者拼成一个巨大的枚举。这样可以明确表示：账号仍在托管，但 App 暂时掉线；或账号已暂停，但登录资料仍保留。

`Session Vault` 是凭证和设备状态的私密存储。Session 本身是 Runtime 使用的持久对象；登录是否有效通过 Runtime 状态和只读的认证摘要表达，普通 API 永远不返回原始票据。

## 账号生命周期状态

### 状态

| 状态 | 含义 |
| --- | --- |
| `pending` | 已登记账号，尚未开始授权 |
| `authorizing` | 账号主正在扫码、登录或完成平台验证 |
| `hosted` | 托管关系生效，平台可以按 Runtime 状态执行能力 |
| `paused` | 账号主或平台暂时暂停运营，凭证和业务记录保留 |
| `ending` | 正在停止任务、清理 Worker 和清除凭证 |
| `ended` | 当前托管关系结束，凭证已清除；这是终态 |

### 转移

```text
pending
  → authorizing
  → hosted
  → paused
  → hosted
  → ending
  → ended
```

补充规则：

- `authorizing` 失败或取消时回到 `pending`，保留失败审计；
- `hosted` 不等于 Runtime 在线，在线能力由 `runtime_state` 决定；
- `paused` 保留 Session Vault 引用，但暂停平台业务 Command；
- `ending` 先停止新任务并处理可结束的 Operation，再清除凭证；
- `ended` 不复用旧凭证。重新合作时建立新的托管关系并重新授权。

## Runtime 状态

### 状态

| 状态 | 含义 | 典型能力 |
| --- | --- | --- |
| `offline` | 没有可用 Worker 或连接 | 读取本地状态、启动/重连 |
| `starting` | 正在分配或启动 Worker | 等待状态事件 |
| `connecting` | 正在建立 App/AIM 原生连接 | 等待握手和心跳 |
| `online` | Session 有效、连接和心跳正常 | 执行已注册能力 |
| `degraded` | Worker 存活，但连接、同步或部分能力异常 | 按 Capability 限制执行 |
| `needs_login` | Session 缺失、过期或被平台拒绝 | 只提供授权和诊断流程 |
| `needs_verification` | 平台要求账号主完成验证 | 等待交互式验证 |
| `manual_control` | 账号主正在 App 中直接操作 | 冲突 Command 暂停 |
| `draining` | 正在排空队列并停止或迁移 Worker | 不接收新的业务 Command |

### 转移

```text
offline
  → starting
  → connecting
  → online
  → degraded
  → connecting
  → online

online / degraded
  → needs_login
  → needs_verification
  → connecting

online / degraded
  → manual_control
  → online

online / degraded / manual_control
  → draining
  → offline
```

断线、Worker 崩溃或心跳超时进入 `offline` 或 `connecting`，具体取决于是否已经开始恢复。账号生命周期进入 `paused` 时，Runtime 默认经过 `draining` 回到 `offline`；恢复托管后重新连接。

## 状态组合

状态组合示例：

| account lifecycle | runtime | 含义 |
| --- | --- | --- |
| `hosted` | `online` | 正常托管和执行 |
| `hosted` | `degraded` | 仍在托管，部分能力受限 |
| `hosted` | `needs_login` | 托管关系仍在，等待账号主重新授权 |
| `hosted` | `manual_control` | 账号主暂时直接操作，冲突任务暂停 |
| `paused` | `offline` | 暂停运营，资料保留 |
| `ending` | `draining` | 正在结束托管 |
| `ended` | `offline` | 终态，凭证已清除 |

规范状态不允许 `ended + online`、`ended + manual_control` 或 `paused +` 新业务执行。状态变化和非法组合都进入审计记录。

## Query

```http
GET /v1/accounts/{account_id}
GET /v1/accounts/{account_id}/runtime
GET /v1/accounts/{account_id}/session
GET /v1/accounts/{account_id}/state-events
```

账号摘要响应：

```json
{
  "data": {
    "account_id": "ACCOUNT_ID",
    "account_lifecycle_state": "hosted",
    "runtime_state": "online",
    "session": {
      "auth_status": "valid|refreshing|expired|revoked|unknown",
      "generation": 3,
      "device_profile_version": "DEVICE_PROFILE_VERSION",
      "last_validated_at": "TIMESTAMP",
      "vault_ref": "INTERNAL_VAULT_REF"
    },
    "health": {
      "last_heartbeat_at": "TIMESTAMP",
      "last_event_at": "TIMESTAMP",
      "active_worker_id": "WORKER_ID",
      "manual_operator_id": null
    },
    "command_gate": {
      "mode": "allow|restricted|blocked",
      "reason": null
    }
  },
  "meta": {
    "source": "local|app_native",
    "observed_at": "TIMESTAMP"
  }
}
```

`vault_ref` 只作为内部关联标识；外部响应不包含登录票据、Cookie、密钥或设备私密字段。

## Command

所有状态改变仍使用 `POST /v1/commands`。第一版候选 Capability：

| Capability | 作用 |
| --- | --- |
| `account.hosting.start` | `pending → authorizing`，创建短时授权流程 |
| `account.hosting.pause` | 暂停运营并排空 Runtime |
| `account.hosting.resume` | `paused → hosted`，重新启动 Runtime |
| `account.hosting.end` | `hosted/paused → ending → ended` |
| `session.authorization.start` | 创建扫码或交互式登录会话 |
| `session.reauthorize` | 在 `needs_login` 或 `needs_verification` 后恢复授权 |
| `runtime.reconnect` | 请求当前账号重新建立原生连接 |
| `runtime.manual.enter` | 标记账号主进入人工操作模式 |
| `runtime.manual.exit` | 结束人工操作并触发状态同步 |

登录 Command 只返回短时授权会话 ID、过期时间和交互提示引用，不返回凭证内容。`account.hosting.end` 属于 `destructive`，需要目标版本、明确确认和原因。

## Command 门禁

- `pending`：只允许开始授权和查询；
- `authorizing`：只允许继续/取消授权和查询；
- `hosted + online`：按 Capability Registry 执行；
- `hosted + degraded`：只执行声明允许降级运行的能力；
- `hosted + needs_login|needs_verification`：业务 Command 进入结构化登录/验证错误；
- `hosted + manual_control`：与人工操作冲突的 Command 暂停，非冲突 Query 继续；
- `paused`：暂停业务 Command，允许恢复、结束托管和查询；
- `ending|ended`：拒绝新的业务 Command。

## Event

状态变化先写入 Event 账本，再通过 SSE 投递：

```text
account.lifecycle.changed
runtime.state.changed
session.authorization.started
session.authorization.required
session.authorization.succeeded
session.authorization.failed
runtime.heartbeat
runtime.manual_control.entered
runtime.manual_control.exited
```

事件至少一次投递，携带前状态、后状态、触发原因、来源 Actor、Worker 标识和观察时间。重复事件按 `event_id` 去重。

## 恢复和租约

- 状态写入和状态事件使用同一个本地检查点；服务重启后按最后检查点恢复；
- 一个账号同时只有一个活动 Runtime 执行租约；
- Worker 迁移先进入 `draining`，释放旧租约后再启动新 Worker；
- Session Vault 只由 Runtime/登录协调器访问，普通业务模块只读取认证摘要；
- 进入 `needs_login` 或 `needs_verification` 时，未执行的时效性 Command 快速结束，适合延迟的任务按显式等待策略处理；
- 结束托管时先撤销租约和清除凭证，再发出 `ended` 事件。

## 第一版验收

1. Query 同时返回两个正交状态字段；
2. 可以观察 `hosted + needs_login`、`hosted + degraded` 和 `hosted + manual_control` 等组合；
3. 暂停、恢复、重新授权和结束托管均有明确 Operation 终态；
4. Runtime 断线、重连、验证和人工操作都会产生可重放 Event；
5. 冲突 Command 在人工模式和暂停状态下按门禁处理；
6. Worker 重启或迁移后只保留一个活动租约；
7. 结束托管后凭证和 Worker 缓存已清除，业务账本仍可查询；
8. 状态机行为可以用 Attached App 观察结果与 Headless Worker 对照验证。

## 暂不纳入 v1

- 跨账号统一 Runtime 状态；
- 多 Worker 共享一个账号的并行执行；
- 自动替账号主完成扫码或平台验证；
- 将认证摘要暴露为可直接调用的凭证接口。
