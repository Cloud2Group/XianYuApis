# Native bridge（单账号 POC）

这里是 App 进程与业务服务之间的本地桥接实现。第一版采用 Unix Domain
Socket + JSONL；Frida RPC 或原生 helper 只负责把 AIM 对象转换成这里的事件和命令。
桥本身不处理登录、Cookie、Token，也不打开 App 的数据库。

## 模块

```text
protocol.py        # JSON 事件/命令 schema、长度和字段校验
server.py          # 本地 Socket 服务；native ↔ business 路由
client.py          # BusinessBridgeClient / NativeBridgeClient
queueing.py        # 会话串行、请求幂等缓存
test_bridge.py     # 无账号、无网络的闭环测试
```

## 启动桥

```bash
.venv/bin/python -m xianyu_app.bridge.server \
  --socket /tmp/xianyu_app_native/bridge.sock \
  --account-id ACCOUNT_ID
```

Socket 父目录为 `0700`，Socket 本身为 `0600`。建议每个账号使用独立路径，
不要把 Socket 暴露到 TCP 或共享目录。

## 原生端握手

第一帧必须是：

```json
{"type":"hello","protocol":1,"role":"native","account_id":"ACCOUNT_ID"}
```

原生端收到业务命令后，调用已确认的 `AIMPubMsgService` 方法，再把结果发回：

```json
{"event":"message.send.result","account_id":"ACCOUNT_ID","request_id":"REQ","status":"sent","message_id":"MID"}
```

收到消息时发 `message.received`；连接和心跳发 `transport.status`。完整字段见
[`../docs/IM_BRIDGE.md`](../docs/IM_BRIDGE.md)。

## 业务端示例

```python
import asyncio
from xianyu_app.bridge.client import BusinessBridgeClient

async def main():
    client = BusinessBridgeClient("/tmp/xianyu_app_native/bridge.sock", "ACCOUNT_ID")
    await client.connect()
    result = await client.send_text(
        app_cid="APP_CID",
        peer_uid="USER_UID",
        text="您好，我马上为您确认。",
    )
    print(result)
    await client.close()

asyncio.run(main())
```

同一 `app_cid` 的发送会串行化；`message_id` 和 `request_id` 会做有限时长去重。
原生端掉线时，未完成请求会收到 `NATIVE_DISCONNECTED`，业务层可据此转人工或重试。

## Frida 临时适配器

```bash
# 可插桩进程使用系统 Python（当前 .venv 不必安装 Frida）
python3 -m xianyu_app.bridge.frida_adapter \
  --pid TARGET_PID \
  --account-id ACCOUNT_ID \
  --register-listener \
  --capture-text
```

适配器把脚本的 `native.event` 转成 Socket 事件，把业务端命令通过
`script.post({type: "native.command"})` 送回 App。脚本默认不调用发送方法；
确认 `contentTypeText` 和回调 ABI 后才打开 `--invoke-enabled`。

当前 Mac 的原始 iOS-on-Mac Runner 受 task-for-pid/Developer Mode 限制，
直接 attach 的失败日志会写入本地 runtime 目录，不会写入凭证或正文。

## 本地验证

```bash
.venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v
```

测试只使用合成账号和消息，不连接闲鱼网络。
