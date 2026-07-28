# ADR-0018：标准 API 隐藏 App 原始对象

- 状态：Accepted
- 日期：2026-07-28

## 背景

App 内部 AIM、MTop、Objective-C 和 Flutter 对象会随版本变化。若直接把这些字段暴露给调用者，上层程序会与某个 App 版本绑定，版本升级时大量接口同时破坏。

## 决策

标准 API 只返回稳定的领域对象和 schema。AppNativeTransport 负责把当前 App 版本的原始对象转换为标准对象。原始字段和回调证据保存在内部记录中，通过 `raw_ref` 关联，只供诊断和版本适配使用。

## 结果

- 上层调用者不依赖 App 内部类名和字段。
- App 版本适配集中在 AppNativeTransport 和 Worker。
- 诊断时仍可以追溯标准对象对应的原始证据。
