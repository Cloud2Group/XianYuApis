# XianYuApis 总路线图

- 层级：L3
- 状态：Active
- 更新时间：2026-07-28

## 路线原则

- 先把单账号能力基座做实，再扩大能力范围和账号数量。
- 先验证 Attached App、标准 API 和业务账本的共同契约，再建设 Headless App Worker。
- 不以 API 数量或账号数量作为单独验收标准；每个阶段都需要真实结果、失败状态、恢复路径和审计记录。
- AI、业务规则、多账号策略和合作账号平台建立在 API 基座之上，后置建设。

## 阶段总览

```text
L0 项目总纲                         已完成
L1 领域模型与能力地图               已完成初稿
L2 App-only 总体架构                已完成初稿
L3 Attached App 单账号闭环          当前主线
L4 标准 API 与代表性能力             下一阶段
L5 单账号 Headless App Worker       L4 通过后
L6 能力扩展与多 Runtime              Headless 稳定后
L7 控制平面、AI 和合作账号平台       基础设施稳定后
```

## Milestone 0：项目总纲与协作基础（已完成）

- 确认项目第一身份：内部闲鱼运营能力 API 基座；
- 确认 App-only 生产架构和 Headless App Worker 长期目标；
- 确认 API 能力层与 AI 决策层分离；
- 建立领域模型、能力地图、总体架构和协作协议；
- 固定跨会话文档同步规则。
- 固定文档分层、会话完成标准和自动同步清单。

## Milestone 1：Attached App 单账号原生 IM（当前主线）

目标：真实闲鱼 App 完成一个账号的收发和状态闭环。

验收：

- 注册真实原生消息回调；
- 收到一条消息并转成标准 Event；
- 通过标准 Command 发送或回复文字；
- 收到 App 成功/失败回调；
- 本地业务账本可追踪完整时序；
- 重复回调只产生一次业务事实；
- 断线、重连和人工操作状态可观察。

## Milestone 2：标准 API 执行内核

目标：让业务调用者不直接接触 App 对象或 Native Bridge。

范围：

- HTTP/JSON Query、Command、Capability Discovery；
- SSE Event；
- Capability Registry；
- Operation Manager；
- Actor、权限、幂等和高影响操作确认；
- 本地业务 DB、Operation/Event 账本；
- 三域独立 SyncJob、游标、检查点、缺口和重试；
- Account Runtime 状态机和单账号执行租约。

验收：

- Command 先落库，再进入 Runtime；
- `accepted` 与最终 `succeeded` 清晰区分；
- 离线默认快速返回，显式等待有截止时间；
- 服务重启后可以恢复或结束未完成 Operation；
- Query 返回数据来源、观察时间和同步状态。
- 首次同步可按“商品 → 会话与消息 → 订单与评价”创建独立任务，单域失败不影响其他域；
- Query 分别返回账号托管生命周期与 Runtime 状态，命令门禁覆盖暂停、掉线、登录失效、验证和人工操作模式；

## Milestone 3：代表性 App 能力（Milestone 2 后）

在 Attached App 上验证三类代表性能力：

1. **消息能力**：Query、收到消息、发送、回复、已读。
2. **商品能力**：Query 商品、改价或状态变更，确认状态观察。
3. **Session 能力**：App 重启、登录恢复、游标补偿和状态失效。

目标不是一次覆盖所有 API，而是证明标准契约可以覆盖消息、业务写操作和账号生命周期。

Message API v1 只包含会话/消息 Query、文字发送、文字回复、标记已读和对应 Event；图片、商品卡片、语音和文件在文字闭环稳定后扩展。

## Milestone 4：单账号 Headless App Worker

目标：在不运行真实 App 图形进程的条件下，复现已验证的 App 原生能力。

门槛：

- Attached App 的字段、时序、错误和 Session 状态已记录；
- Headless Worker 只实现单账号原生执行契约，Runtime 继续持有队列、同步和账本；
- Headless 使用独立稳定的 Device Profile；
- Headless 与 Attached 对同一 Capability 返回一致的标准结果；
- 登录、重新验证、心跳、断线和增量同步可恢复；
- 出现差异时可以回到 Attached App 对照。

## Milestone 5：卖家核心能力扩展

按依赖顺序扩展：

1. 平台素材和账号媒体实例；
2. 商品模板、发布、编辑、擦亮、上下架；
3. 订单、物流、发货和支持的履约动作；
4. 商品评论和交易评价；
5. 完整历史同步、补偿和数据导出。

每项能力都必须进入 Capability Registry，并完成 Query、Command、Event、错误和验收记录。

## Milestone 6：多 Runtime

目标：在同一基础设施上运行多个逻辑账号。

门槛：

- 单账号 Headless 冷启动和恢复稳定；
- 每个账号 Session、Device Profile、队列、游标和日志隔离；
- 一个账号只有一个活动执行租约；
- Worker 故障迁移和人工操作模式可观测；
- 账号主结束托管后的凭证清除和数据生命周期可执行。

## Milestone 7：控制平面与上层自动化

后置建设：

- 多账号调度和批量 Command 编排；
- AI Tool Adapter；
- AI 规则、价格策略和人工接管；
- 商品模板批量发布和同步；
- 合作账号主门户、收益归因和结算；
- 对外 API、租户、配额和计费。

## 当前下一步

1. 在可插桩测试副本完成 Attached App AIM listener/send/reply 动态确认；
2. 把现有 Native Bridge POC 接到真实 App 回调；
3. 固定第一版标准 Message Query/Command/Event schema；
4. 再实现商品代表性能力和 Session 恢复验收。
