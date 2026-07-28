# App 原生路线图

## Milestone 0：资料和边界（已完成）

- 建立 App 独立目录和 Web 导航目录。
- 保存版本、二进制哈希、依赖、AIM 符号、MTop 名称和数据库观察。
- 固定 App 工具入口为 `xianyu_app.tools.*`。
- 形成单账号 IM 桥接事件/命令契约。
- 完成 Unix Socket/JSONL 桥 POC、Frida 临时适配器和无网络合成回归测试。

## Milestone 1：单账号动态确认（当前进行前置准备）

- 准备可插桩测试副本。
- 枚举 `AIMPubMsgListener` 协议和 `AIMPubMsgService` 实例。
- 手工接收一条消息并记录回调对象字段。
- 手工发送文字并记录 `appCid`、接收者、扩展字段、localid 和成功/失败回调。
- 确认已读更新入口。

### 当前前置条件

- 原始签名 Runner 当前直接 attach 会被系统拦截：`get-task-allow` 缺失，SIP 开启，
  系统 Developer Mode/调试权限尚未完成。
- 在权限准备好之前只维护静态证据、桥协议和只读探针；不启用真实发送调用。

## Milestone 2：单账号本地桥（POC 已完成，待接入真实 AIM）

- [x] 实现 `message.received` JSONL/Socket 事件。
- [x] 实现 `send_text` 和 `reply_text` 命令。
- [x] 加入请求 ID、消息 ID 去重、会话串行队列和发送结果。
- [ ] 接入真实 AIM listener/send/reply 回调。
- [ ] 记录收到、业务处理、原生发送和本地落库四个时间点。

回归命令：

```bash
.venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v
```

## Milestone 3：标准 App 能力 API

- 定义 Query、Command、Event 和 Operation 共同契约。
- 抽取 Attached App Worker 使用的 `AppNativeTransport` 接口。
- 增加 App 在线状态、重连、同步补偿和人工操作模式。
- Web/Cookie 只保留历史研究和字段对照，不进入生产执行或回退。

## Milestone 4：单账号会话管理

- 记录登录成功、刷新、失效、重登录事件。
- 把会话包和设备状态放进本地私有 Session Vault。
- 验证 App 更新、进程重启和网络切换后的恢复行为。

## Milestone 5：Headless App Worker

只有 Milestone 1–4 全部通过后，才实现复用 App 原生协议、登录态和设备态的单账号 Headless App Worker。Worker 先按根目录 `docs/HEADLESS_WORKER.md` 实现单账号原生执行契约；单账号 Headless 与 Attached App Worker 行为一致后，再评估多 Runtime、账号分片和 Session Vault 集群。当前阶段不以账号数量作为验收指标。

## 当前单账号 Definition of Done

```text
买家发消息
  → 原生回调
  → Python 事件
  → 业务生成回复
  → 原生 send/reply
  → 成功回调
  → 买家收到
  → 本地落库可追踪
```
