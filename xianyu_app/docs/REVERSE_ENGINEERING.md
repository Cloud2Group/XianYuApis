# App 原生逆向与静态分析记录

本文件记录闲鱼 Mac App 当前版本的可复现发现。除非标注“已验证”，其余内容只代表静态表面或工作假设。
版本更新后的逐项兼容性比较见 [`APP_UPDATE_7.27.50.md`](APP_UPDATE_7.27.50.md)。

## 目标样本

| 项目 | 值 |
| --- | --- |
| App | `/Applications/闲鱼.app` |
| Bundle ID | `com.taobao.fleamarket` |
| 当前版本 | `7.27.50`（Build `56832643`） |
| 上一版基线 | `7.27.30`（Build `56437047`） |
| Runner | `Wrapper/Runner.app/Runner` |
| 架构 | Apple Silicon arm64 |
| 技术栈 | Flutter AOT、Objective-C/C++、Alibaba AIM/ACCS、MTop |
| 证据目录 | `xianyu_app/research/generated/` |

每次 App 更新后运行：

```bash
xianyu_app/tools/extract_static_evidence.sh
```

上一版反编译输出保留在本地忽略目录
`xianyu_app/research/raw/xianyu_focus_1785005247/`：

- `Runner.classes`：Objective-C/类和构造器字符串。
- `Runner.actions`：方法、C++ 符号和调用行为线索。
- `Runner.mtop`：MTop 名称和账号/业务表面。
- `Frameworks_App.framework_App.*`：App.framework 的对照分析。

当前版本的公开静态证据由
`xianyu_app/tools/extract_static_evidence.sh` 重新生成，关键 AIM 类、选择子和
参数类型编码与 `7.27.30` 基线保持一致；二进制地址随版本重建发生位移，不作为桥接定位依据。

## AIM/ACCS IM 表面

### 接收

已从 Objective-C metadata、C++ 符号和字符串交叉确认的入口族：

```text
AIMPubMsgService addMsgListener:
AIMMsgListenerImpl::OnAddedMessages
AIMMsgNotify::NotifyAddedNewMsg
AIMMsgServiceHookImpl::PreReceiveMessage
```

首选顺序是先尝试高层 `addMsgListener:` 注册协议回调；协议实现成本较高时，再在 `OnAddedMessages` 或 `NotifyAddedNewMsg` 做窄范围探针。

### 发送和回复

```text
AIMPubMsgService sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:
AIMPubMsgService replyMessageWithBlock:onProgress:onSuccess:onFailure:userData:
AIMMsgServiceEx::SendMessage
AIMMsgServiceEx::ReplyMessage
updateMessageToRead:mids:
```

相邻服务还暴露出几条可作为桥接对照的高层路径：

```text
AIMMsgRPC::Send
AIMConvRPCService::CreateSingleConversation
AIMExtensionService handleReceivedLiteMessageWithBlock:onSuccess:onFailure:
AIMExtensionServiceEx::HandleReceivedLiteMessage
AIMExtensionServiceEx::SetLastMsg
AIMPubMsgService sendMessageTolocalWithBlock:onSuccess:onFailure:
```

`AIMExtensionService` 的 LiteMessage 入口和 `AIMMsgRPC::Send` 目前属于静态发现，
优先级低于已经明确的 `AIMPubMsgService` 收发方法；动态验证时可用来对照消息落库、会话创建和发送结果。

### 消息对象

```text
AIMPubMsgTextContent
  initWithText:encryptedText:extension:

AIMPubMsgContent
  initWithContentType:textContent:imageContent:audioContent:videoContent:geoContent:customContent:structContent:fileContent:replyContent:combineForwardContent:

AIMPubMsgSendMessage
  initWithAppCid:content:receivers:extension:localExtension:callbackCtx:customLocalid:

AIMPubMsgSendReplyMessage
  initWithAppCid:referenceMid:replyContent:receivers:extension:localExtension:callbackCtx:
```

这意味着第一版发送桥可以复用 App 内部对象和当前 AIM 会话，先抓取一次人工发送的参数，再建立 Python 到原生方法的命令桥。

## 网络和依赖线索

静态字符串出现：

- `tls-goofish.dingtalk.com`
- `wss-goofish.dingtalk.com`
- `PaaSAccsPlugin`
- `registerAccsModule`
- `paas_accs_channel`
- `PNM`

这些名称说明 IM 连接和 ACCS/PaaS 组件位于 App 内部；具体握手字段、票据生命周期和心跳参数仍要通过运行时观测确认。

## 本地数据库

### 备用明文库

```text
Documents/fleamarket_idlefish_im_<UID>.db
  Message
  SessionInfo
  UserInfo

Library/Caches/if_msg_xstore_user_<UID>.db
  PMessage
  PSessionInfo
  XMessageCenterItem
```

`xianyu_app/tools/watch_db.py` 支持这两套 schema，输出 JSONL，并按 `message_id` 去重。

### AIM 主库

```text
Documents/AIMData/<UID>@goofish/database/im.sqlite
```

该文件由 `CipherDB` 处理。系统 sqlite3 直接打开时会出现“file is not a database”类错误。进程内可观察到的入口：

```text
-[CipherDB initWithDBPath:version:key:]
-[CipherDB execQuery:error:]
```

数据库层实验优先级低于原生消息回调；主库只作为落盘时序和字段对照证据。

## MTop API 静态目录

完整字符串目录：[`../research/generated/mtop_all.txt`](../research/generated/mtop_all.txt)

本轮重点相关名称包括：

### IM/会话

```text
mtop.taobao.idlemessage.login.token
mtop.taobao.idlemessage.message.send
mtop.taobao.idlemessage.message.sync
mtop.taobao.idlemessage.message.check
mtop.taobao.idlemessage.message.del
mtop.taobao.idlemessage.message.query
mtop.taobao.idlemessage.message.read
mtop.taobao.idlemessage.message.topn
mtop.taobao.idlemessage.session.create
mtop.taobao.idlemessage.session.query
mtop.taobao.idlemessage.session.sync
mtop.taobao.idlemessage.session.service.headinfo2
mtop.taobao.idlemessage.session.unread.clean
mtop.idle.idleitem.message.send
mtop.taobao.idlemessage.profile.smart.list
mtop.taobao.idlemessage.profile.smart.edit
```

### 商品/履约表面

```text
mtop.idle.idleitem.publish
mtop.idle.idleitem.edit
mtop.idle.idleitem.draft.publish2
mtop.taobao.idle.item.downshelf
mtop.taobao.idle.finish.delivery2
mtop.taobao.idle.logistic.create.order.precheck
mtop.taobao.idle.logistic.create.online.order
mtop.taobao.idle.logistic.wait.consign.order.query
mtop.taobao.idle.item.management.query
```

### 登录/授权线索

```text
mtop.alibaba.havanaappiv.authenticate
mtop.alibaba.havana.login.akeytoken.update
mtop.alibaba.ucc.native.oauthLogin
mtop.alibaba.ucc.oauthLogin
mtop.alibaba.ucc.convertAuthCodeToAccessToken
mtop.alibaba.idlefish.getststoken
mtop.taobao.havana.mdevice.add
mtop.taobao.havana.mdevice.check
mtop.taobao.havana.mdevice.list
mtop.taobao.havana.mdevice.delete
```

这些名称只证明客户端包含相应能力的字符串或符号；请求结构、签名上下文和账号权限仍需逐项动态确认。
7.27.50 相比上一版新增 `mtop.idle.user.setting.save`，移除
`mtop.taobao.idle.fci.get.token`；当前 IM/会话相关名称未见变化。

## 动态插桩现状

探针：[`../hooks/enum_aim.js`](../hooks/enum_aim.js)

当前探针默认只枚举：

- Objective-C AIM 类和方法；
- `AIMPubMsgListener` 协议元数据；
- AIM 相关 native symbols。

原始签名 App 的 `get-task-allow` entitlement 缺失，当前系统 SIP 开启，Developer Mode
尚未完成启用，直接 attach 会受到 macOS task-for-pid 权限限制。测试副本、可调试构建或
其他受控插桩路径需要单独准备。

## 证据分级

| 标签 | 含义 |
| --- | --- |
| 已验证 | 可由当前本机文件、静态命令或已记录运行输出复现 |
| 静态发现 | 类、符号、构造器或 API 名称在二进制中出现 |
| 待动态确认 | 需要真实回调参数、发送结果、错误码或时序 |
| 工作假设 | 用于设计，不作为已具备能力对外承诺 |
