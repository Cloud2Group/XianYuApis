# 登录态与 Headless 方向

## 当前判断

闲鱼 App 的登录凭证表现为一组相互关联的状态，而非一个永久 Token。单账号资料模型先按以下分层记录：

```text
AccountSession
├── login session       access/refresh 或 Cookie/登录票据
├── device identity     device ID、安装 ID、Keychain/密钥引用
├── AIM state            连接票据、endpoint、序列号、心跳和重连状态
├── MTop context         appKey、时间戳和签名上下文
└── account cursor       UID、会话游标、最后消息 ID、未读状态
```

精确字段名、保存位置和刷新时序以运行时观测为准。当前项目已经确认 App 内部有 AIM/ACCS 和 Havana/UCC 相关字符串，但独立复用登录流程仍属于待验证工作。

对外状态不直接等同于这些内部字段。标准 API 分别返回账号托管生命周期和 Runtime 运行状态；Session 作为私密凭证包存放在 Session Vault，详细门禁和恢复语义见根目录 `docs/api/SESSION_RUNTIME_V1.md`。

## 单账号优先的拆分顺序

1. 观察登录成功后的持久化变化：Keychain、偏好文件、AIMData 和缓存数据库。
2. 记录登录刷新前后状态差异，确认哪些值会轮换、哪些值固定绑定设备。
3. 定义本地私有 `AccountSession` schema，敏感值只放 Session Vault，不进入日志。
4. 在一个账号上恢复会话、建立 AIM 连接并完成收发。
5. 加入过期、重连、账号切换和重新登录状态机。
6. 用 `AppNativeTransport` 接入标准能力 API。

## 后续 Headless App Worker 形态

```text
少量交互式登录器
        ↓
加密 Session Vault
        ↓
单账号逻辑 Runtime
  ├── login/session refresh
  ├── AIM connection
  ├── heartbeat/reconnect
  ├── message queue
  └── local bridge
```

Headless App Worker 继续使用 App 原生协议、登录态、设备态、AIM/ACCS 和 MTop 能力，不引入 Web/Cookie 执行路线。

Worker 只负责单账号原生执行；Account Runtime 负责队列、同步、Operation、Event 和业务账本。内部方法和结果信封见根目录 `docs/HEADLESS_WORKER.md`。

一个逻辑账号环境可以由轻量 Worker 管理，物理进程数和账号数无需一一对应。每个账号的会话、设备状态、序列号和网络配置仍需隔离保存。

## 进入矩阵化前的门槛

以下项目全部通过后，再评估多账号：

- 单账号冷启动恢复成功；
- Token/票据刷新和失效原因可观测；
- AIM 心跳、重连和消息补偿稳定；
- 发送幂等、失败重试和人工接管完整；
- App 更新后静态证据和回归测试可重复；
- 每个账号的本地状态和日志有清晰隔离。

## 记录原则

- “出现了 Token 字符串”不等于“可以脱离 App 独立运行”。
- “出现了 MTop API 名称”不等于“参数、签名和权限已经掌握”。
- 先把一条真实消息的时序和回调字段记完整，再抽取通用协议。
