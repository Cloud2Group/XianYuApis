# App 原生路线工作说明

开始 App 相关任务前，依次阅读：

1. [`../CONTEXT.md`](../CONTEXT.md)
2. [`README.md`](README.md)
3. [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md)
4. [`docs/IM_BRIDGE.md`](docs/IM_BRIDGE.md)
5. [`docs/ROADMAP.md`](docs/ROADMAP.md)

研究记录使用三种标签：

- **已验证**：可以由当前版本二进制、运行日志或本地数据库复现。
- **静态发现**：客户端中出现了类、符号或 API 名称，参数和权限仍待动态确认。
- **待验证**：下一次测试需要实际回调、请求或错误码。

单账号端到端闭环是当前唯一主里程碑。大规模 Session Vault、无界面 Worker 和矩阵调度只记录设计，不提前实现。
