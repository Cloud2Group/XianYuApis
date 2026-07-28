# ADR-0021：资源式 Query、统一 Command 入口和统一 Event 流

- 状态：Accepted
- 日期：2026-07-28

## 背景

查询会话、商品和订单适合使用清晰的资源路径；写操作又需要统一的幂等、Operation、权限、确认和审计语义。若每项操作都设计独立特殊接口，能力数量增加后会产生大量重复协议。

## 决策

标准 API 使用混合形式：Query 使用资源式 HTTP 接口；所有写操作通过 `POST /v1/commands` 提交 Capability Command；执行状态通过 Operation 资源查询；主动变化和执行结果通过统一 Event 流输出。

## 结果

- Query 保持直观和可缓存。
- 所有写操作复用同一执行、幂等和审计模型。
- 新 Capability 可以直接注册成内部工具或未来 AI Tool。
