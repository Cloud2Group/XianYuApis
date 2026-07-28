# 闲鱼 Web/Cookie 工作区

这里集中保存原有 Web 端全部实现：MTop HTTP、Cookie 登录、WebSocket IM、数据导出、
聊天清洗分析和离线阅读器。App 原生路线位于 [`../xianyu_app/`](../xianyu_app/)。

该工作区不属于 XianYuApis 的生产执行架构，也不作为 App 原生链路的故障回退。现有代码只用于历史研究、字段对照、聊天/商品导出和离线数据工具。

## 目录

```text
xianyu_web/
├── goofish_apis.py       # MTop、登录、商品、媒体
├── goofish_live.py       # WebSocket 实时收发
├── message/              # 消息与商品类型
├── utils/                # Cookie、签名、设备与 JS 辅助
├── static/               # 签名算法 JavaScript
├── tools/                # 导出、清洗、分析、阅读器生成
├── chat_reader/          # React + Vite 离线阅读器
├── exports/              # 本地导出数据
├── runtime/              # 本地 Cookie、认证状态
├── requirements.txt
└── Dockerfile
```

## 安装

从仓库根目录执行：

```bash
.venv/bin/pip install -r xianyu_web/requirements.txt
```

## 常用命令

```bash
# WebSocket 实时收发
.venv/bin/python -m xianyu_web.goofish_live

# 扫码登录并导出聊天
.venv/bin/python -m xianyu_web.tools.export_chats --qrcode --format both

# 复用本地登录态
.venv/bin/python -m xianyu_web.tools.export_chats --format both

# 导出商品
.venv/bin/python -m xianyu_web.tools.export_items

# 清洗买卖双方对话
.venv/bin/python -m xianyu_web.tools.clean_buyer_dialogues

# 生成离线阅读器
.venv/bin/python -m xianyu_web.tools.build_chat_reader
```

默认数据位置：

- 登录态：`xianyu_web/runtime/`
- 导出结果：`xianyu_web/exports/`
- 阅读器源码：`xianyu_web/chat_reader/`

以上本地运行数据均由 Git 忽略规则隔离。

## 阅读器开发

```bash
cd xianyu_web/chat_reader
npm install
npm run dev
```

## Docker

从仓库根目录构建：

```bash
docker build -f xianyu_web/Dockerfile -t xianyuapis-web .
docker run -it --env-file xianyu_web/.env.dev xianyuapis-web
```
