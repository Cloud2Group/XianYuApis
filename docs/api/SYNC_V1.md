# XianYuApis 同步 API v1

- 层级：L4
- 状态：Draft
- 版本：v1
- 更新时间：2026-07-28

## 文档职责

本文件定义账号首次接入、断线补偿和本地状态校准的同步契约。它只负责把闲鱼已有状态可靠地拉入本地标准化账本，不负责业务判断、商品策略或 AI 编排。

## 核心结论

初始同步按三个业务域执行，默认顺序是：

```text
商品
  → 会话与消息
  → 订单与评价
```

三个域各自拥有独立的 `SyncJob`、游标、进度、缺口记录和重试状态。顺序是默认调度顺序，不把三个域绑成一个不可拆分的长事务；某个域失败或部分完成时，其他域仍可独立查询、重试和补齐。

账号在基本登录和 Runtime 可用后即可提供已完成域的 Query 和 Event，不必等待全部历史同步结束。未完成部分通过 `sync_status=partial|syncing` 明确返回。

## 同步模式

| 模式 | 作用 |
| --- | --- |
| `initial_snapshot` | 首次接入时导入指定历史范围，建立本地初始快照 |
| `incremental` | 根据该业务域最后游标拉取新增和变化 |
| `repair_gap` | 针对已记录的数据缺口重拉指定范围 |
| `reconcile` | 重新读取平台状态，校正本地副本与平台差异 |

## 业务域

### `item`

同步账号下可访问的闲鱼商品实例、价格、文案、上下架状态和平台观察字段。平台商品模板属于本地对象，不由闲鱼历史快照直接生成。

### `conversation_message`

同步会话、买家标识、主商品关系、未读状态和消息历史。会话唯一性仍遵循：

```text
seller_account_id + buyer_uid + primary_item_id
```

### `order_review`

同步订单、订单状态、物流观察结果、商品评论和交易评价。商品评论与交易评价保持两个独立对象，但在同一个同步域中调度。

## Query

### 查询账号同步概况

```http
GET /v1/accounts/{account_id}/sync-status
```

响应示意：

```json
{
  "data": {
    "account_id": "ACCOUNT_ID",
    "domains": {
      "item": {
        "status": "succeeded|running|partial|failed|needs_login|needs_verification",
        "last_success_at": "TIMESTAMP",
        "cursor": "OPAQUE_CURSOR",
        "gap_count": 0,
        "observed_at": "TIMESTAMP"
      },
      "conversation_message": {},
      "order_review": {}
    }
  },
  "meta": {
    "source": "local",
    "observed_at": "TIMESTAMP",
    "sync_status": "complete|partial|stale|syncing"
  }
}
```

### 查询同步任务

```http
GET /v1/accounts/{account_id}/sync-jobs
GET /v1/sync-jobs/{sync_job_id}
```

列表支持按 `domain`、`mode`、`status` 和时间范围过滤。响应至少包含：

- `sync_job_id`、`account_id`、`domain`、`mode`；
- 当前状态和状态变更时间；
- 已发现、已写入、跳过、失败的记录数；
- 当前游标和检查点；
- 缺口列表或缺口数量；
- 最近错误、是否可重试和下一次重试时间；
- `observed_at`、`started_at`、`finished_at`。

游标是平台无关的不透明值。标准 API 不暴露 AIM、MTop 或 App 原始分页字段。

## Command

同步写操作仍走统一入口：

```http
POST /v1/commands
```

### 启动初始同步

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "sync.initial.start",
  "idempotency_key": "IDEMPOTENCY_KEY",
  "parameters": {
    "domains": ["item", "conversation_message", "order_review"],
    "history": {
      "scope": "all|window|since_hosting",
      "from": null,
      "to": null
    },
    "priority": "normal|background"
  }
}
```

该 Command 只针对一个 `account_id`。系统为每个请求域建立独立 `SyncJob`；返回值包含父 Operation 和各域任务标识（若调用者只请求一个域，则只建立一个任务）。重复的幂等键返回原任务，不重复导入。

### 启动增量同步

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "sync.incremental.start",
  "idempotency_key": "IDEMPOTENCY_KEY",
  "parameters": {
    "domain": "item|conversation_message|order_review"
  }
}
```

### 修复缺口或重新校准

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "sync.gap.repair|sync.reconcile",
  "idempotency_key": "IDEMPOTENCY_KEY",
  "parameters": {
    "domain": "item|conversation_message|order_review",
    "gap_ids": ["GAP_ID"],
    "from": "TIMESTAMP",
    "to": "TIMESTAMP"
  }
}
```

只有一个 `domain` 时，重试和校准只影响该域，不重置其他域的游标。

## SyncJob 状态

```text
accepted
  → queued
  → running
  → succeeded
  → partial
  → failed
  → needs_login
  → needs_verification
  → cancelled
```

- `succeeded`：请求范围已完整导入，游标已保存；
- `partial`：部分记录已导入，但存在平台不可访问、分页缺口或可重试失败；
- `failed`：本次任务未能取得可用结果；
- `needs_login` / `needs_verification`：需要账号生命周期流程先恢复；
- 任务完成后仍保留检查点，重试从最后可靠位置继续。

`partial` 不回滚已写入数据；调用者可以只修复失败范围。

## 进度和缺口

进度事件使用计数和阶段，不用一个未经平台确认的百分比冒充完成度：

```json
{
  "domain": "conversation_message",
  "phase": "discovering|fetching|normalizing|committing|repairing",
  "discovered": 120,
  "committed": 118,
  "skipped": 1,
  "failed": 1,
  "cursor": "OPAQUE_CURSOR",
  "gap_count": 1
}
```

缺口至少记录：`gap_id`、业务域、原因、时间或游标范围、可重试标志、当前状态和最近错误。缺口修复成功后保留修复记录，不删除原始失败审计。

## Event

同步事件进入统一 Event 账本和 SSE 流：

```text
sync.started
sync.progress
sync.domain.succeeded
sync.domain.partial
sync.domain.failed
sync.gap.detected
sync.gap.repaired
sync.completed
```

事件至少一次投递，调用者按 `event_id` 去重。每个业务域的游标提交和业务记录写入必须在本地账本中形成可恢复检查点。

## 数据一致性规则

- 闲鱼平台观察结果是真实业务状态来源；本地预期状态不得覆盖平台确认状态；
- 使用平台稳定 ID 或项目定义的复合键幂等写入，重复同步不产生重复业务事实；
- 新消息按 `message_id` 去重，会话按账号、买家和主商品定位，订单按 `order_id` 去重；
- 同步发现的平台外部变化要生成标准 Event，并标记来源为 `platform_observed`；
- Query 返回最后观察时间、游标和完整性状态；调用者可以用 `consistency=fresh` 请求先刷新目标域；
- App 断线、进程重启或 Worker 迁移后，从最近可靠检查点恢复，不把未提交页当作已完成。

## 第一版验收

1. 首次接入可以按默认顺序创建三个独立 `SyncJob`；
2. 每个域都能查询独立进度、游标、缺口和最终状态；
3. 一个域失败时，其他域的结果和游标不被回滚；
4. 重复 Command 或重复平台记录不会产生重复业务事实；
5. 服务或 Worker 重启后可以从检查点继续；
6. `partial`、登录失效和验证要求可以被调用者明确识别并重试；
7. 历史同步未完成时，已完成域的基本 Query/Event 仍可用；
8. 所有同步过程可通过 Operation、Event 和审计记录追踪。

## 暂不纳入 v1

- 跨账号统一同步任务和批量运营策略；
- 商品模板自动传播；
- AI 根据同步结果自动决策；
- 对平台不可访问历史的猜测性补全；
- 视频、音频和文件媒体的历史内容同步。
