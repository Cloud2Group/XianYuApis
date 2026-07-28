# Order API v1

- 状态：Draft
- 标准 API：v1
- 更新时间：2026-07-28

## 范围

第一版覆盖订单查询、交易状态事件和已确认的履约动作。退款、取消、售后等写操作先完成状态观察和权限验证，再逐项开放。

## 对象

```json
{
  "id": "ORDER_ID",
  "account_id": "ACCOUNT_ID",
  "buyer_id": "BUYER_ID",
  "item_id": "ITEM_ID",
  "conversation_id": "CONVERSATION_ID",
  "status": "created|paid|cancelled|shipped|completed|refund_pending|refunded|unknown",
  "amount": 99,
  "logistics": null,
  "observed_at": "TIMESTAMP",
  "version": 1
}
```

## Query

```http
GET /v1/accounts/{account_id}/orders
GET /v1/accounts/{account_id}/orders/{order_id}
GET /v1/conversations/{conversation_id}/orders
```

## Events

```text
order.created
order.paid
order.cancelled
order.shipped
order.completed
order.refund_changed
```

每个订单事件携带 `account_id`、`buyer_id`、`item_id`、`conversation_id`、前后状态和观察时间。

## Commands

### `order.ship`

```json
{
  "order_id": "ORDER_ID",
  "logistics": {
    "company": "COMPANY",
    "tracking_number": "TRACKING_NUMBER"
  },
  "expected_version": 1
}
```

### `order.logistics.update`

用于平台允许的物流信息更新，参数和权限以 App 原生动态验证结果为准。

## 验收重点

- 订单与卖家账号、买家、商品和会话关系完整；
- 状态以闲鱼观察结果为准；
- 发货成功必须有平台回调或状态确认；
- 退款、取消和售后写操作在权限、状态机和错误码确认前保持不可用状态。
