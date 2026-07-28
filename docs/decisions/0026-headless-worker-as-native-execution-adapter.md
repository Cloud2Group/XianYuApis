# ADR-0026：Headless Worker 作为单账号原生执行适配器

- 状态：Accepted
- 日期：2026-07-28

## 背景

项目需要从当前真实闲鱼 App 逐步演进到无界面运行，但上层标准 API、Operation、同步和账本不应随着 Worker 形态变化。若把业务队列、AI 策略或多账号调度塞进 Worker，Attached 与 Headless 的替换会牵动整个系统。

## 决策

Headless App Worker 只负责一个账号的 App 原生执行：Session/Device Profile 使用、AIM/ACCS/MTop 连接、心跳、重连、已验证 Capability 调用和原生事件输出。

Account Runtime 负责账号状态、队列、租约、同步、幂等、Operation、Event 和业务账本。标准 API、AI、商业规则和跨账号调度在更上层运行。

Attached App Worker 与 Headless App Worker 必须实现同一个 `AppNativeTransport` 内部契约。当前使用 UDS + JSONL 验证，传输方式可以演进，方法语义和版本边界保持独立。

## 结果

- 上层 API 对 Worker 类型透明；
- 单账号状态、凭证、队列和账本保持集中管理；
- Headless 研发可以逐项对照 Attached App 的字段、错误和时序；
- 多账号调度成为控制平面职责，不进入单账号 Worker；
- Worker 崩溃、迁移或 App 升级不会改变标准 API schema。

## 相关文档

- `docs/HEADLESS_WORKER.md`
- `docs/ARCHITECTURE.md`
- `xianyu_app/docs/IM_BRIDGE.md`
