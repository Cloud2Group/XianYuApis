# XianYuApis

闲鱼客服与运营能力研究项目。仓库已经按运行形态拆成两个独立工作区：

- [`xianyu_app/`](xianyu_app/)：Mac App 原生 AIM/ACCS，当前主路线。
- [`xianyu_web/`](xianyu_web/)：历史 Cookie/WebSocket 研究、聊天导出和阅读器，不属于生产执行架构。

## 根目录

```text
XianYuApis/
├── AGENTS.md       # 新任务自动接手入口
├── docs/PROJECT_CHARTER.md     # 项目使命、产品边界和长期原则
├── docs/WORKING_AGREEMENT.md   # 产品负责人和 Agent 的协作方式
├── docs/DOCUMENTATION_GOVERNANCE.md # 文档分层和会话同步规则
├── CONTEXT.md      # 当前目标、事实、状态和下一步
├── README.md       # 项目导航
├── docs/           # 项目地图和架构决策
├── xianyu_app/     # App 原生工作区
└── xianyu_web/     # Web/Cookie 工作区
```

## 当前优先级

先完成单账号 App 原生 IM 闭环：

```text
实时收消息 → Python 业务处理 → 原生 send/reply → 发送结果
```

生产执行只走 App 原生链路。当前先通过真实 App 完成单账号闭环，长期演进为 Headless App Worker。多账号放在单账号闭环之后。

## 快速入口

```bash
# App 桥回归
.venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v

# App 明文备用库监听
.venv/bin/python -m xianyu_app.tools.watch_db --human

# 历史 Web 实时工具
.venv/bin/python -m xianyu_web.goofish_live

# Web 聊天导出
.venv/bin/python -m xianyu_web.tools.export_chats --qrcode --format both
```

开始新任务时依次阅读 [`AGENTS.md`](AGENTS.md)、
[`docs/PROJECT_CHARTER.md`](docs/PROJECT_CHARTER.md)、
[`docs/WORKING_AGREEMENT.md`](docs/WORKING_AGREEMENT.md)、
[`docs/DOCUMENTATION_GOVERNANCE.md`](docs/DOCUMENTATION_GOVERNANCE.md)、
[`CONTEXT.md`](CONTEXT.md) 和 [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md)。

文档领导结构：

```text
PROJECT_CHARTER → DOMAIN_MODEL / CAPABILITY_MAP
                → ARCHITECTURE → ROADMAP
                → API_CONTRACT / docs/api/
                → CONTEXT（当前状态）
```

关键架构取舍记录在 `docs/decisions/`；每个会话结束时按
`docs/DOCUMENTATION_GOVERNANCE.md` 同步结果。
