# 闲鱼 App 原生路线

这里集中放置闲鱼 Mac App 的静态分析资料、动态插桩探针、IM 监听工具和单账号桥接设计。当前目标是先把一个账号的原生 IM 收发闭环做实，再向标准 App 能力 API 和 Headless App Worker 演进。

## 先读什么

1. [`../CONTEXT.md`](../CONTEXT.md)：项目总上下文。
2. [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md)：二进制、AIM/ACCS、数据库和 MTop 发现。
3. [`docs/IM_BRIDGE.md`](docs/IM_BRIDGE.md)：Python 与 App 的事件/命令契约。
4. [`docs/AUTH_HEADLESS.md`](docs/AUTH_HEADLESS.md)：登录态、设备态和后续 Headless 方向。
5. [`docs/ROADMAP.md`](docs/ROADMAP.md)：单账号里程碑和验证顺序。
6. [`docs/ENVIRONMENT.local.md`](docs/ENVIRONMENT.local.md)：本机私有环境快照（Git 忽略）。

## 目录

```text
xianyu_app/
├── hooks/                 # Frida/动态插桩探针
├── tools/                 # 只读监听、环境快照、静态证据提取
├── research/generated/    # 可重复生成的静态报告
├── research/raw/          # 本机原始大文件，Git 忽略
├── docs/                  # 逆向笔记、桥接契约、路线图
└── bridge/                # 单账号 Unix Socket/JSONL 桥 POC
```

## 当前工具

```bash
# 从本地明文备用库监听新增消息；UID 可由文件名自动发现
.venv/bin/python -m xianyu_app.tools.watch_db --human

# 回放已有行
.venv/bin/python -m xianyu_app.tools.watch_db --replay --human

# 刷新静态证据（默认分析 /Applications/闲鱼.app）
xianyu_app/tools/extract_static_evidence.sh

# 刷新本机私有快照
xianyu_app/tools/snapshot_environment.sh

# 在可插桩测试副本上枚举 AIM 类、协议和符号
frida -p TARGET_PID -l "$PWD/xianyu_app/hooks/enum_aim.js"

# 运行 Frida → Unix Socket 临时适配器（需要本机 Python 安装 frida）
python3 -m xianyu_app.bridge.frida_adapter \
  --pid TARGET_PID \
  --account-id ACCOUNT_ID \
  --register-listener \
  --capture-text
```

`xianyu_app/bridge/` 的 JSONL 服务和客户端已经用合成数据跑通；
`xianyu_app/hooks/native_aim_bridge.js` 默认只做探针。当前真实 App 仍受
macOS task-for-pid/Developer Mode 权限限制，只有在确认当前版本的 `listener`
参数、文字 content type 和回调时序后，才显式开启 `--invoke-enabled`。
