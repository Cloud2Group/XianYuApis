# XianYuApis agent entry

这是闲鱼客服项目的根目录工作说明。根目录只承担导航；每次开始新任务时，先阅读：

1. [`docs/PROJECT_CHARTER.md`](docs/PROJECT_CHARTER.md)：项目使命、产品边界和长期原则。
2. [`docs/WORKING_AGREEMENT.md`](docs/WORKING_AGREEMENT.md)：产品负责人和 Agent 的协作方式。
3. [`docs/DOCUMENTATION_GOVERNANCE.md`](docs/DOCUMENTATION_GOVERNANCE.md)：文档分层和会话结束同步清单。
4. [`CONTEXT.md`](CONTEXT.md)：当前目标、已验证事实和下一步。
5. [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md)：目录边界和接手顺序。
6. 若任务涉及 App 原生链路，再阅读 [`xianyu_app/README.md`](xianyu_app/README.md)。
7. 若任务涉及现有 Cookie/WebSocket 链路，阅读 [`xianyu_web/README.md`](xianyu_web/README.md)。

## 当前优先级

- 先完成单账号原生 IM 的收消息、发消息和可观测性闭环。
- App 原生协议是唯一生产执行路线，长期目标是 Headless App Worker。
- 现有 Web/Cookie 代码只作为历史研究、数据导出和对照资料，不作为生产回退。
- 多账号、无界面运行和大规模调度放在单账号端到端验证之后。

## 工作规则

- 先看 `CONTEXT.md` 和已有研究记录，再动代码；把新的静态事实、动态观察和推测分别标记。
- 讨论新需求时，先复述理解并区分“明确内容”和“推测”；得到确认后再进入设计和执行。
- Web 代码统一维护在 `xianyu_web/`，App 原生代码统一维护在 `xianyu_app/`。
- 凭证、Cookie、个人聊天数据和本机环境快照只放在 Git 忽略的本地文件中。
- 原生 App 研究默认使用一次性测试副本和只读探针；真实收发验证前先记录回调、参数和错误码。
- 每完成一个研究阶段，更新 `CONTEXT.md`、`xianyu_app/docs/` 或 `xianyu_app/research/` 中对应记录。
- 每个会话结束前按 `docs/DOCUMENTATION_GOVERNANCE.md` 同步决策、事实、验证结果和下一步。
- 用户未指定其他目标时，默认执行 `CONTEXT.md` 中的“当前唯一下一任务”；完成后由 Agent 选择并写入新的下一任务。

## 常用入口

```bash
# 历史 Web/Cookie 数据工具
.venv/bin/python -m xianyu_web.goofish_live

# 本地明文 IM 备用监听
.venv/bin/python -m xianyu_app.tools.watch_db --uid ACCOUNT_UID --human

# 刷新 App 静态证据和本机环境快照
xianyu_app/tools/extract_static_evidence.sh
xianyu_app/tools/snapshot_environment.sh
```
