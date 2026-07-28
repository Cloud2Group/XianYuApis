# Chat Reader

React + Vite + Ant Design 聊天记录阅读器。

```bash
cd xianyu_web/chat_reader
npm install
npm run dev
```

`src/chat_data.json` 由以下命令生成，并由 Git 忽略规则隔离：

```bash
.venv/bin/python -m xianyu_web.tools.build_chat_reader_app
```
