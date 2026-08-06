# 闲鱼 App 7.27.50 兼容性检查

- 检查时间：2026-08-06
- 检查对象：`/Applications/闲鱼.app`
- 当前版本：`7.27.50`（Build `56832643`）
- 上一版基线：`7.27.30`（Build `56437047`）
- 当前 Runner SHA-256：`337b9cf1a4013db5512cf3f9e4f4e61b3c08d4f6970c7a9ecf54868feb50f18a`
- 上一版 Runner SHA-256：`930af66d0580ac8c8e8c578e0fe56aecbc108affbbb976873d51bb5a3b5f4a0e`

## 结论先说

**之前的项目基础大部分可以继续使用。** 新版本的 AIM 原生 IM 静态入口、消息对象和网络/依赖表面没有发现结构性变化；Python ↔ Native Bridge 的 5 项本地回归测试全部通过。

这次检查还没有证明真实收消息、发消息和回复调用在新版本上已经端到端可用。当前 Runner 可以启动，但 Frida attach 仍被 macOS 的 task-for-pid 权限拦截，所以动态验证继续作为下一项任务。

## 检查结果

本轮比较使用上一版静态证据备份
`/private/tmp/xianyu_evidence_before_20260806_232655/generated/`，与当前
`xianyu_app/research/generated/` 逐文件比对；AIM 类型报告先归一化地址和展示空白，再比较选择子、类型编码和字段。
当前证据由以下命令生成并通过校验：

```bash
xianyu_app/tools/extract_static_evidence.sh
(cd xianyu_app/research/generated && shasum -a 256 -c SHA256SUMS)
```

### 1. 原生 IM 入口

对 `7.27.30` 和 `7.27.50` 的 Objective-C AIM 类型证据做了地址归一化比较：类名、方法选择子、参数类型编码和字段布局保持一致。以下关键入口均仍在：

```text
AIMPubMsgService addMsgListener:
AIMPubMsgService sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:
AIMPubMsgService replyMessageWithBlock:onProgress:onSuccess:onFailure:userData:
AIMPubMsgService updateMessageToRead:mids:

AIMPubMsgTextContent initWithText:encryptedText:extension:
AIMPubMsgContent initWithContentType:textContent:imageContent:audioContent:videoContent:geoContent:customContent:structContent:fileContent:replyContent:combineForwardContent:
AIMPubMsgSendMessage initWithAppCid:content:receivers:extension:localExtension:callbackCtx:customLocalid:
AIMPubMsgSendReplyMessage initWithAppCid:referenceMid:replyContent:receivers:extension:localExtension:callbackCtx:
```

二进制地址整体发生位移，这是版本重新构建后的正常现象；当前桥代码按类名和选择子查找，没有依赖旧地址。

### 2. AIM/ACCS 网络和依赖

以下报告与上一版完全一致：

- `aim_static_strings.txt`
- `aim_class_inventory.txt`
- `aim_action_focus.txt`
- `linked_libraries.txt`
- `codesign_entitlements.plist`
- `network_endpoints.txt`

因此，`tls-goofish.dingtalk.com`、`wss-goofish.dingtalk.com`、AIM/ACCS 组件和现有观察路线仍有静态依据。

### 3. MTop 名称目录

发现两处与上一版不同：

```text
新增：mtop.idle.user.setting.save
移除：mtop.taobao.idle.fci.get.token
```

这两项不属于当前单账号 IM 收发主链路。IM/会话相关目录没有看到变化；涉及商品、登录、设备和履约的请求参数仍需按新版本分别动态核验。

### 4. 本地消息库

当前账号 `2201547722503` 仍能发现三类存储：

```text
Documents/fleamarket_idlefish_im_<UID>.db       Message
Library/Caches/if_msg_xstore_user_<UID>.db      PMessage
Documents/AIMData/<UID>@goofish/database/im.sqlite  CipherDB 主库
```

`watch_db.py --uid 2201547722503 --once --human` 成功扫描，且自动识别 `Message` 与 `PMessage` 两套 schema；AIM 主库仍标记为进程内加密库，继续只做对照观察。

### 5. Bridge 和工具

```text
.venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v
```

结果：`5/5 passed`。

Bridge、JSONL 协议、请求去重、会话串行队列、断线状态和只读数据库监听器没有发现版本绑定代码，现阶段可直接沿用。

## 复用分级

| 内容 | 处理 | 说明 |
| --- | --- | --- |
| 项目总纲、领域模型、API 契约、Bridge JSONL 协议 | 直接沿用 | App 更新没有改变项目分层或业务语义 |
| `bridge/` Python POC、队列、服务端、客户端 | 直接沿用 | 本地回归 5/5 通过 |
| `watch_db.py` | 继续沿用（只读） | 两套备用库 schema 仍可识别；主库仍需进程内观察 |
| 静态证据提取脚本和报告 | 继续沿用 | 已用 7.27.50 重新生成 |
| Frida 探针、原生 listener/send/reply 适配 | 静态层可沿用，运行层待验证 | 关键选择子仍在，但实例、回调参数和时序尚未取得 |
| 登录态、Session、设备态、MTop 参数 | 重新验证 | 版本更新可能影响票据刷新、签名上下文和错误码 |
| Headless Worker | 暂不推进 | 先完成 7.27.50 Attached App 单账号动态闭环 |

## 当前阻塞

本机实测：

- Runner 已实测可启动；本轮收尾后的环境快照显示当前无运行 PID；
- SIP：enabled；
- Developer Mode：disabled；
- `get-task-allow`：absent；
- Frida 17.15.3 attach 返回当前用户访问目标进程被拒绝的 task-for-pid 权限错误。

因此本轮只确认了静态兼容性和本地工具兼容性，真实原生收发仍保持观察模式，未开启发送调用。

## 下一步

唯一下一任务仍为 `M1-APP-IM-OBSERVE-01`：在具备调试权限的测试副本上，对 **7.27.50** 重新记录：

1. `AIMPubMsgListener` 的真实回调参数和对象字段；
2. 人工发一条测试文字时的 `appCid`、`receivers`、`extension`、`customLocalid`；
3. send/reply 成功、失败回调和本地落库时序；
4. 登录态、重连和版本更新后的恢复行为。

完成这些观察前，不把“静态入口仍在”当作“端到端调用已通过”。
