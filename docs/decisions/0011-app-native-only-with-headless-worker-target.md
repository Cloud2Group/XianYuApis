# ADR-0011：生产架构仅使用 App 原生链路，长期目标为 Headless App Worker

- 状态：Accepted
- 日期：2026-07-28
- 替代：ADR-0001

## 背景

早期设计曾把 App 原生链路作为主路线、Web/Cookie 作为生产回退。项目的产品目标进一步明确后，核心价值来自稳定复用 App 登录态、设备态和原生协议；同时长期规模化需要摆脱真实 App 图形进程与账号一一绑定。

## 决策

XianYuApis 的生产执行架构只使用 App 原生体系：

1. 当前阶段通过真实闲鱼 App、Native Bridge 和 App 原生 AIM/MTop 能力完成验证。
2. 长期建设复用 App 原生协议、登录态和设备态的 Headless App Worker。
3. Web/Cookie 路线不参与生产 Query、Command、Event 或故障回退。
4. `xianyu_web/` 只保留为历史研究、数据导出和对照资料。

## 结果

- 标准 API 只面对 AppNativeTransport，不设计 Native/Web 双路线选择。
- 当前真实 App Worker 和未来 Headless App Worker 实现同一 App 原生执行契约。
- Headless 演进不会改变上层 Query、Command 和 Event API。
