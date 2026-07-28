# App 研究产物

## generated/

这里放可以由当前 App 二进制重新生成的静态证据。运行：

```bash
xianyu_app/tools/extract_static_evidence.sh
```

重点文件：

- `aim_static_strings.txt`：AIM、消息对象、回调和 CipherDB 相关字符串。
- `aim_class_inventory.txt`：AIM 类、会话、扩展服务的小型类清单。
- `aim_action_focus.txt`：发送、回复、会话创建和 LiteMessage 路径的方法线索。
- `aim_objc_types.txt`：`otool -ov` 提取的 AIM 消息对象和服务的 Objective-C
  selector/type encoding，供动态探针核对参数 ABI。
- `mtop_all.txt`：从 Runner 二进制提取的全部 `mtop.*` 名称。
- `mtop_relevant.txt`：IM、会话、商品、履约和登录相关筛选结果。
- `mtop_idle_related.txt`：本轮早期静态提取保留的 525 行快照，用于和新版本对照。
- `network_endpoints.txt`：Goofish/DingTalk/Taobao/Alibaba 相关端点线索。

静态目录只证明客户端表面存在对应名称；参数、签名、权限和实际调用路径需要动态验证。

`aim_objc_types.txt` 可单独刷新：

```bash
xianyu_app/tools/extract_aim_objc_types.sh
```

## raw/

原始 strings+offsets 文件体积较大，当前以压缩文件保存在本机：

```text
raw/Runner.strings.offsets.txt.gz
```

该目录还保留了本轮逆向命令生成的本地原始目录：

- `xianyu_focus_1785005247/`：Runner 和各 Framework 的 classes/actions/domains/mtop 筛选结果。
- `xianyu_strings_1785005200/`：按模块拆分的 strings、URL 和关键词结果。
- `runner_strings_focus.txt`、`app_strings_context.txt`、`target_contexts.txt`：针对 AIM、MTop、登录和业务模块的上下文摘录。
- `MANIFEST.txt`：本地文件大小和哈希清单。

该目录已加入 Git 忽略。若要重新生成原始文件，可使用系统 `strings` 对 Runner 二进制输出并自行压缩。
