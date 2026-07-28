# XianYuApis 当前上下文

更新时间：2026-07-28

## 顶层设计状态

- L0 项目总纲已经确认，见 `docs/PROJECT_CHARTER.md`。
- 第一阶段产品定位为“完整、稳定、可独立调用的闲鱼能力 API 基座”。
- API 能力层只负责可靠执行，AI、业务规则、多账号策略和人工接管属于上层组合层。
- 第一阶段只覆盖闲鱼卖家运营核心能力，并以单账号可靠执行为北极星。
- 账号按逻辑 `Account Runtime` 建模，与物理设备解耦；账号状态和凭证保持隔离。
- 产品负责人和 Agent 的跨会话协作规则见 `docs/WORKING_AGREEMENT.md`。
- 生产架构已经确认仅使用 App 原生链路；当前是真实 App Worker，长期目标是 Headless App Worker。`ADR-0001` 已被 `ADR-0011` 替代。
- 已新增架构决策：`ADR-0002` 能力 API 与 AI 分层，`ADR-0003` 逻辑账号运行时与物理设备解耦。
- 已确认初始同步 API v1：按“商品 → 会话与消息 → 订单与评价”分域执行；每个域独立 `SyncJob`、游标、检查点、缺口和重试，见 `docs/api/SYNC_V1.md` 与 `ADR-0024`。
- 已确认账号状态拆分：`account_lifecycle_state` 表示托管关系，`runtime_state` 表示 Worker、连接和认证健康，见 `docs/api/SESSION_RUNTIME_V1.md` 与 `ADR-0025`。
- 已确认 Headless Worker 边界：Worker 只负责单账号 App 原生连接与调用；Account Runtime 持有队列、同步、Operation 和账本，见 `docs/HEADLESS_WORKER.md` 与 `ADR-0026`。
- 已确认文档治理规则：每个会话结束时同步专题文档、`CONTEXT.md`、必要时的 `PROJECT_MAP.md` 和 ADR，见 `docs/DOCUMENTATION_GOVERNANCE.md` 与 `ADR-0027`。
- 根目录重组已经形成正式 Git 提交；README 导航、忽略规则和工作区移动结果已复核，本地重新克隆验证通过。
- L1 产品领域模型和能力地图已经建立，见 `docs/DOMAIN_MODEL.md` 与 `docs/CAPABILITY_MAP.md`。
- L2 总体架构已经建立初稿，见 `docs/ARCHITECTURE.md`；第一阶段部署确定为单台 Mac、单个账号、私有 API、本地 DB 和 Native Bridge。
- L3 总路线已经建立，见 `docs/ROADMAP.md`；Attached App 单账号 IM → 标准 API/代表性能力 → Headless App Worker → 多 Runtime。
- 顶层设计下一步：L0-L4 设计已收口，进入 Milestone 1 的真实 Attached App 动态验证。

## 项目目标

为闲鱼卖家运营提供完整、稳定、可独立调用的 App 原生能力 API。当前最重要的垂直切片是：

> 单个账号通过闲鱼 Mac App 的原生 AIM/ACCS 链路，实时接收买家消息，并通过标准 Command 调用 App 原生能力回复。

现有 Web/Cookie WebSocket 实现集中在 `xianyu_web/`，只作为历史研究、数据导出和对照资料，不参与生产 Query、Command、Event 或故障回退。

## App 原生执行路线

```text
标准 API
  → Account Runtime
  → AppNativeTransport
  → 当前：真实闲鱼 App + Native Bridge
  → 长期：Headless App Worker
  → 闲鱼平台
```

当前真实 App 链路：

```text
闲鱼 App AIM 长连接
  → 原生消息回调
  → Unix Socket / Frida RPC 桥
  → Python 业务服务
  → 原生 sendMessage / replyMessage
  → 闲鱼 App AIM 长连接
```

## 已验证事实

### App 基线

- 安装路径：`/Applications/闲鱼.app`
- Bundle ID：`com.taobao.fleamarket`
- 当前版本：`7.27.30`（Build `56437047`）
- 主二进制：`Wrapper/Runner.app/Runner`
- 技术形态：Flutter AOT + Objective-C/C++ Alibaba AIM/ACCS 组件 + MTop
- AIM 网络字符串包含 `tls-goofish.dingtalk.com` 和 `PNM`
- 可复现证据位于 `xianyu_app/research/generated/`

### 原生 IM 入口

静态元数据和二进制字符串已经确认以下入口族：

- 收消息：`AIMPubMsgService addMsgListener:`、`AIMMsgListenerImpl::OnAddedMessages`、`AIMMsgNotify::NotifyAddedNewMsg`、`AIMMsgServiceHookImpl::PreReceiveMessage`
- 发消息：`AIMPubMsgService sendMessageWithBlock:onProgress:onSuccess:onFailure:userData:`、`AIMMsgServiceEx::SendMessage`
- 回复：`AIMPubMsgService replyMessageWithBlock:onProgress:onSuccess:onFailure:userData:`、`AIMMsgServiceEx::ReplyMessage`
- 已读更新：`updateMessageToRead:mids:`

消息对象构造器：

```text
AIMPubMsgTextContent initWithText:encryptedText:extension:
AIMPubMsgContent initWithContentType:textContent:imageContent:audioContent:...
AIMPubMsgSendMessage initWithAppCid:content:receivers:extension:localExtension:callbackCtx:customLocalid:
AIMPubMsgSendReplyMessage initWithAppCid:referenceMid:replyContent:receivers:extension:localExtension:callbackCtx:
```

### 本地 IM 存储

已观察到三类文件：

1. `Documents/fleamarket_idlefish_im_<UID>.db`：明文备用库，表 `Message`、`SessionInfo`、`UserInfo`。
2. `Library/Caches/if_msg_xstore_user_<UID>.db`：xstore 备用库，表 `PMessage`、`PSessionInfo`、`XMessageCenterItem`。
3. `Documents/AIMData/<UID>@goofish/database/im.sqlite`：AIM 主库，由 `CipherDB` 加密，系统 sqlite3 直接打开会报数据库格式错误。

实时主路径优先接原生回调；数据库监听只用于回放、字段对照和落库观测。

### 当前工具

- `xianyu_app/tools/watch_db.py`：只读数据库监听器。
- `xianyu_app/hooks/enum_aim.js`：Frida 元数据和符号枚举探针，默认只读。
- `xianyu_app/tools/extract_static_evidence.sh`：刷新静态证据。
- `xianyu_app/tools/snapshot_environment.sh`：刷新本机 App/工具/数据库快照。
- `xianyu_app/research/raw/`：本轮从 `/private/tmp` 复制的原始 strings/classes/actions/domains 资料（本地忽略）。
- `xianyu_app/bridge/`：Unix Socket + JSONL 单账号桥 POC；包含 native/business/observer
  握手、消息事件、文字发送命令、去重、会话串行队列和断线状态。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| App 静态分析和入口整理 | 已完成第一轮 |
| 明文备用库只读监听 | POC 已完成 |
| AIM 加密库直接读取 | 暂不作为主路线 |
| 原生收消息回调注册 | 待动态插桩验证 |
| 原生文字发送/回复 | 待端到端验证 |
| Python ↔ App 本地桥 | Unix Socket/JSONL POC 已完成；待接入真实 AIM 回调 |
| 单账号标准 App API | 下一阶段 |
| 三域初始/增量同步契约 | 已确认；实现待开发 |
| 账号生命周期与 Runtime 状态契约 | 已确认；实现待开发 |
| Headless Worker 边界与内部接口 | 已确认；Attached/Headless 实现待开发 |
| 文档治理与会话自动同步 | 已确认；规则已生效 |
| 仓库目录与 Git 收口 | 已完成；工作树干净，重新克隆结构完整 |
| Headless App Worker | 单账号真实 App 闭环之后 |
| 多账号矩阵化 | 暂缓 |

当前 Mac 的权限、签名和工具状态见本地忽略文件：
`xianyu_app/docs/ENVIRONMENT.local.md`。公开说明见
`xianyu_app/docs/ENVIRONMENT.md`。

动态插桩摘要：原始 Runner 在 iOS-on-Mac/RunningBoard 环境中运行；直接 Frida
attach 目前会被 task-for-pid 权限拦截，原始 `/Applications/闲鱼.app` 保持原样。
`native_aim_bridge.js` 和 `frida_adapter.py` 默认处于观察模式，真实发送调用开关保持关闭。

## 本轮整理结果

- 资料入口固定为 `AGENTS.md` → `docs/PROJECT_CHARTER.md` → `docs/WORKING_AGREEMENT.md` → `CONTEXT.md` → `docs/PROJECT_MAP.md`。
- 根目录已完成物理收口，业务实现只位于 `xianyu_app/` 与 `xianyu_web/`。
- App 端入口固定为 `xianyu_app/README.md` → `docs/REVERSE_ENGINEERING.md` →
  `docs/IM_BRIDGE.md` → `docs/ROADMAP.md`。
- 公开静态证据放在 `xianyu_app/research/generated/`；原始大文件、运行日志、账号和
  环境快照均放在 Git 忽略路径，不混入代码提交。
- 桥 POC 已通过本地合成闭环测试；当前没有打开真实原生发送调用。
- 目录重组已经正式提交；旧根目录 Web 文件由 Git 识别为迁移到 `xianyu_web/`，本地重新克隆后根目录、文档入口和 App/Web 工作区均完整。

## 下一次接手的最短路径

1. 读本文件、`xianyu_app/README.md` 和 `xianyu_app/docs/ROADMAP.md`。
2. 运行 `xianyu_app/tools/snapshot_environment.sh`，确认 App 版本和当前 PID。
3. 先运行桥回归：`.venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v`。
4. 系统开发者工具权限准备好后，在可插桩测试副本中运行
   `xianyu_app/hooks/enum_aim.js`，确认 `AIMPubMsgListener` 回调参数。
5. 手工发送一条测试文字，记录 `appCid`、`content`、`receivers`、`extension`、
   `customLocalid` 和成功/失败回调。
6. 只在上述字段确认后开启 `--invoke-enabled`，完成单账号
   `message.received` → 标准 Command → `send_text` 的闭环，再接入单账号标准 App API。

标准 API 设计补充：同步 API v1 已确认并记录在 `docs/api/SYNC_V1.md`；实现阶段先落地本地 `SyncJob`、检查点和查询/事件，再接入真实 App 分页与游标。
