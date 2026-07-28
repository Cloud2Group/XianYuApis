# ADR-0025：账号生命周期与 Runtime 运行状态正交建模

- 状态：Accepted
- 日期：2026-07-28

## 背景

“账号是否仍由平台托管”和“App/Worker 当前是否在线”是两个不同问题。把登录失效、网络掉线、暂停运营和结束托管塞进一个状态枚举，会让恢复、命令门禁和审计语义混在一起。

## 决策

账号公开状态拆成两个正交字段：

1. `account_lifecycle_state`：`pending`、`authorizing`、`hosted`、`paused`、`ending`、`ended`，表示托管关系；
2. `runtime_state`：`offline`、`starting`、`connecting`、`online`、`degraded`、`needs_login`、`needs_verification`、`manual_control`、`draining`，表示 Worker、连接和认证健康。

Session Vault 作为 Runtime 使用的私密凭证包独立保存。认证摘要可以出现在 Query 中，但原始票据不进入业务 API、日志或普通数据库记录。

## 结果

- `hosted + needs_login` 可以清楚表示托管关系仍在、但等待账号主重新授权；
- `hosted + manual_control` 可以暂停冲突命令，同时保留查询和状态观察；
- `paused`、`ending` 和 `ended` 的命令门禁不再依赖网络连接状态猜测；
- Worker 重启、迁移和 Headless 演进只改变 Runtime 实现，不改变账号生命周期；
- 状态变化可以独立审计、重放和恢复。

## 相关文档

- `docs/api/SESSION_RUNTIME_V1.md`
- `docs/DOMAIN_MODEL.md`
- `docs/ARCHITECTURE.md`
