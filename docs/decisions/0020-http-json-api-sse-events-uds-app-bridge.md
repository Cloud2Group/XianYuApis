# ADR-0020：HTTP/JSON 标准 API、SSE 事件流、UDS App 桥

- 状态：Accepted
- 日期：2026-07-28

## 背景

内部调用者、未来 AI 和第三方工具需要通用、稳定的网络接口；真实 App 进程与本机执行内核之间则更适合权限清晰、延迟较低的本地通信。把两者绑定成同一种协议会让本地桥细节泄漏到上层。

## 决策

Query、Command、Operation 和 Capability Discovery 使用 HTTP + JSON。第一阶段 Event 使用 SSE，并通过事件 ID/游标断线续传。执行内核与 Attached App Worker 之间继续使用 Unix Domain Socket + JSONL。对外 API 和内部桥协议独立版本化。

## 结果

- 内部脚本和未来远程调用者使用标准 HTTP 接口。
- App 桥可以独立替换为签名 helper 或 Headless Worker 通道。
- 后续增加 WebSocket 或 Webhook 时沿用同一 Event schema。
