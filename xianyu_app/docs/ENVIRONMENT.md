# App 端环境说明

## 目标环境

当前研究针对 macOS 上的闲鱼 Mac App（iOS/Flutter 形态），默认样本路径：

```text
/Applications/闲鱼.app
/Applications/闲鱼.app/Wrapper/Runner.app/Runner
```

版本、二进制哈希、运行 PID、账号 UID、容器 UUID 和数据库绝对路径属于本机动态信息，记录在 Git 忽略的 `ENVIRONMENT.local.md`。

## 刷新本机快照

```bash
xianyu_app/tools/snapshot_environment.sh
```

快照包含：

- Bundle ID、版本、Build、架构和 SHA-256；
- Frida、Python、Node 版本；
- SIP、Developer Mode 和签名 entitlement 状态；
- 当前 Runner PID；
- 发现的 IM 数据库路径和账号 UID。

## 刷新静态分析

```bash
xianyu_app/tools/extract_static_evidence.sh
```

输出到 `xianyu_app/research/generated/`：

- `app_metadata.txt`
- `linked_libraries.txt`
- `codesign_entitlements.plist`
- `aim_static_strings.txt`
- `mtop_all.txt`
- `mtop_relevant.txt`
- `network_endpoints.txt`
- `SHA256SUMS`

## 当前插桩前提

原始签名 App 的调试权限受 macOS 代码签名和系统安全设置影响。动态探针优先在一次性测试副本、可调试构建或具备明确调试权限的进程上运行；当前 `enum_aim.js` 默认只做元数据枚举，不打印凭证、正文或回调参数。

## 数据分层

| 数据 | 位置 | Git 状态 |
| --- | --- | --- |
| 公开静态报告 | `xianyu_app/research/generated/` | 可跟踪 |
| 原始 strings 大文件 | `xianyu_app/research/raw/` | 本地忽略 |
| 本机环境快照 | `xianyu_app/docs/ENVIRONMENT.local.md` | 本地忽略 |
| 登录 Cookie/认证文件 | `xianyu_web/runtime/` | 本地忽略 |
| 聊天导出和个人数据 | `xianyu_web/exports/` | 本地忽略 |
