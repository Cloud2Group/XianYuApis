# Project Map

## 根目录原则

根目录只做导航和上下文交接，实际实现集中在两个工作区：

```text
XianYuApis/
├── AGENTS.md
├── CONTEXT.md
├── README.md
├── docs/
├── xianyu_app/
└── xianyu_web/
```

- `xianyu_app/`：唯一生产执行路线；当前真实 App，长期 Headless App Worker。
- `xianyu_web/`：历史 Cookie/MTop/WebSocket 研究、导出与阅读器，不参与生产回退。
- `docs/`：跨路线的项目地图和架构决策。

## 项目级文档

| 文档 | 作用 |
| --- | --- |
| `docs/PROJECT_CHARTER.md` | L0 项目使命、产品边界和长期原则 |
| `docs/DOMAIN_MODEL.md` | L1 核心角色、业务对象和关系 |
| `docs/CAPABILITY_MAP.md` | L1 目标能力范围、优先级和当前状态 |
| `docs/ARCHITECTURE.md` | L2 总体分层、组件边界、数据流和部署演进 |
| `docs/ROADMAP.md` | L3 项目总路线和阶段验收门槛 |
| `docs/API_CONTRACT.md` | L4 标准 Query、Command、Operation、Event 和错误契约 |
| `docs/api/` | 各业务域的具体 API 契约 |
| `docs/api/SYNC_V1.md` | 初始快照、增量同步、缺口修复和同步任务契约 |
| `docs/api/SESSION_RUNTIME_V1.md` | 账号托管生命周期、Runtime 状态、登录恢复和人工操作契约 |
| `docs/HEADLESS_WORKER.md` | Attached/Headless Worker 的原生执行边界和内部接口 |
| `docs/WORKING_AGREEMENT.md` | 产品负责人和 Agent 的协作规则 |
| `docs/DOCUMENTATION_GOVERNANCE.md` | 文档分层、会话完成标准和自动同步规则 |
| `CONTEXT.md` | 当前状态、已验证事实和下一步 |
| `docs/PROJECT_MAP.md` | 目录边界和接手顺序 |
| `docs/decisions/` | 重要且难以逆转的架构决策 |

## 新任务接手顺序

1. `AGENTS.md`
2. `docs/PROJECT_CHARTER.md`
3. `docs/WORKING_AGREEMENT.md`
4. `CONTEXT.md`
5. 本文件
6. App 任务进入 `xianyu_app/README.md`
7. Web 任务进入 `xianyu_web/README.md`

## App 工作区

| 路径 | 作用 |
| --- | --- |
| `xianyu_app/bridge/` | Unix Socket/JSONL 桥与 Frida 临时 Adapter |
| `xianyu_app/hooks/` | Frida 动态探针 |
| `xianyu_app/tools/` | 数据库监听、环境快照、静态证据提取 |
| `xianyu_app/research/generated/` | 可重复生成的静态证据 |
| `xianyu_app/research/raw/` | 本机原始研究文件，Git 忽略 |
| `xianyu_app/docs/` | 逆向、IM 契约、登录态和路线图 |

App 版本兼容性报告：
[`xianyu_app/docs/APP_UPDATE_7.27.50.md`](../xianyu_app/docs/APP_UPDATE_7.27.50.md)。

常用命令：

```bash
.venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v
.venv/bin/python -m xianyu_app.tools.watch_db --human
xianyu_app/tools/extract_static_evidence.sh
xianyu_app/tools/snapshot_environment.sh
```

## Web 工作区

| 路径 | 作用 |
| --- | --- |
| `xianyu_web/goofish_apis.py` | MTop、登录、商品和媒体 |
| `xianyu_web/goofish_live.py` | WebSocket 实时收发 |
| `xianyu_web/message/` | 消息与商品类型 |
| `xianyu_web/utils/`、`static/` | Cookie、签名、设备和 JavaScript |
| `xianyu_web/tools/` | 导出、清洗、分析和阅读器生成 |
| `xianyu_web/chat_reader/` | React 离线聊天阅读器 |
| `xianyu_web/exports/` | 本地导出数据，Git 忽略 |
| `xianyu_web/runtime/` | 本地凭证与认证状态，Git 忽略 |

常用命令：

```bash
.venv/bin/python -m xianyu_web.goofish_live
.venv/bin/python -m xianyu_web.tools.export_chats --qrcode --format both
.venv/bin/python -m xianyu_web.tools.export_items
```

App 原生收发验收标准见
[`xianyu_app/docs/IM_BRIDGE.md`](../xianyu_app/docs/IM_BRIDGE.md)。
