# Web 数据工具

这些命令用于聊天与商品导出、语料清洗、需求分析和阅读器生成。
所有命令均从仓库根目录执行：

```bash
.venv/bin/python -m xianyu_web.tools.<module> --help
```

## 导出

```bash
.venv/bin/python -m xianyu_web.tools.export_chats --qrcode --format both
.venv/bin/python -m xianyu_web.tools.export_chats --format both --this-year --only-my-items
.venv/bin/python -m xianyu_web.tools.export_items
```

## 清洗与分析

```bash
.venv/bin/python -m xianyu_web.tools.clean_buyer_dialogues
.venv/bin/python -m xianyu_web.tools.analyze_chat_needs
.venv/bin/python -m xianyu_web.tools.compress_chat_corpus
```

## 阅读器

```bash
.venv/bin/python -m xianyu_web.tools.build_chat_reader
.venv/bin/python -m xianyu_web.tools.build_chat_reader_app

cd xianyu_web/chat_reader
npm install
npm run dev
```

默认导出位置为 `xianyu_web/exports/`，登录态位于 `xianyu_web/runtime/`；
两处均由 Git 忽略规则隔离。
