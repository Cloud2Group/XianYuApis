# ADR-0012：登录允许交互，日常运行保持 Headless

- 状态：Accepted
- 日期：2026-07-28

## 背景

闲鱼首次登录、异常验证和会话失效可能需要账号主扫码或完成平台交互。把 Headless 理解为所有阶段完全无人参与，会让账号接入和重新授权缺少现实入口。

## 决策

首次接入和平台要求重新验证时，允许账号主参与临时交互式登录。登录成功后，把 App Session 和设备态加密保存到 Session Vault，由 Headless App Worker 接管长期运行。会话失效时 Runtime 返回 `needs_login` 或 `needs_verification`，完成交互后继续运行。

## 结果

- 日常 Query、Command 和 Event 由 Headless App Worker 执行。
- 登录和验证成为独立、可观察的账号生命周期流程。
- 系统需要提供短时登录会话、通知和重新授权入口。
