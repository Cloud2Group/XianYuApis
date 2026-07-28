# Web/Cookie 路线工作说明

本工作区是历史研究和数据工具区，不参与生产 Query、Command、Event 或 App 链路回退。除非任务明确涉及历史导出、清洗、阅读器或字段对照，否则生产能力统一进入 `xianyu_app/` 和后续标准 App API 模块。

开始 Web 相关任务前依次阅读：

1. [`../CONTEXT.md`](../CONTEXT.md)
2. [`README.md`](README.md)
3. [`tools/README.md`](tools/README.md)

运行入口统一采用 Python package 形式：

```bash
.venv/bin/python -m xianyu_web.goofish_live
.venv/bin/python -m xianyu_web.tools.export_chats --help
```

运行数据集中在 `runtime/` 与 `exports/`，代码引用统一使用 `xianyu_web.*` 包路径。
