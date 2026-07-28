# Comment / Review API v1

- 状态：Draft
- 标准 API：v1
- 更新时间：2026-07-28

## 两类对象

### 商品评论

公开出现在闲鱼商品下的留言或评论，直接归属 `item_id`，可以没有订单。

### 交易评价

订单完成后产生的买家评价、卖家评价和后续评价内容，直接归属 `order_id`。

## Query

```http
GET /v1/accounts/{account_id}/items/{item_id}/comments
GET /v1/accounts/{account_id}/orders/{order_id}/reviews
```

## Events

```text
item.comment.created
item.comment.status_changed
order.review.created
order.review.status_changed
```

## Commands

候选 Capability：

```text
item.comment.reply
item.comment.manage
order.review.reply
order.review.manage
```

这些 Command 只有在 App 原生实际确认参数、权限和结果后，才进入 `available`。平台未开放或尚未验证的动作返回结构化 Capability 状态。

## 验收重点

- 评论和评价保持独立模型；
- 评论归属商品，评价归属订单；
- 事件携带账号、商品/订单、买家和观察时间；
- 每个写能力有明确平台结果和审计记录。
