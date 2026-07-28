# ADR-0019：标准 API 版本与 App 版本解耦

- 状态：Accepted
- 日期：2026-07-28

## 背景

闲鱼 App 会持续升级，AIM、MTop、类结构和参数可能随版本变化。若标准 API 直接跟随 App 版本变化，上层脚本和未来 AI 工具会频繁破坏。

## 决策

标准 API 使用独立版本和稳定领域 schema。Capability Registry 记录每项能力支持的 App 版本范围、Worker 版本、验证状态和失配原因。App 升级先在测试副本验证，能力失配时返回结构化不可用状态，不猜测新参数或改变字段含义。

## 结果

- App 版本适配集中在 AppNativeTransport 和 App Worker。
- 上层可以通过能力状态判断当前账号是否可用。
- 新旧 Worker 可以在迁移期间短暂并存。
