# ADR-0013：每个账号绑定独立且稳定的 Device Profile

- 状态：Accepted
- 日期：2026-07-28

## 背景

Headless App Worker 需要在重启、升级和机器迁移后恢复账号运行。如果每次启动都重新生成设备身份，账号会话和设备关系会频繁变化；如果多个账号共享设备身份，账号隔离也会失去清晰边界。

## 决策

每个闲鱼账号绑定独立且稳定的 Device Profile。Worker 重启时继续使用原设备身份；Runtime 迁移时，Session 与 Device Profile 一起迁移。设备身份变化必须作为显式操作执行并记录，必要时进入重新登录流程。

## 结果

- Worker 是可替换的执行载体，账号设备身份是持久状态。
- Session Vault 需要保存 Device Profile 版本和迁移资料。
- 多账号 Worker 不能在账号之间复用同一 Device Profile。
