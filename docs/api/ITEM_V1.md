# Item API v1

- 状态：Draft
- 标准 API：v1
- 更新时间：2026-07-28

## 范围

第一批商品能力按以下顺序验证：

1. 查询商品；
2. 改价；
3. 修改标题和文案；
4. 擦亮；
5. 上架和下架；
6. 后续建设完整的商品模板、媒体上传和新品发布流程。

## 对象

```json
{
  "id": "ITEM_ID",
  "account_id": "ACCOUNT_ID",
  "template_id": "TEMPLATE_ID",
  "title": "商品标题",
  "description": "商品文案",
  "price": 99,
  "status": "online|offline|draft|pending|rejected|unknown",
  "media": [],
  "observed_at": "TIMESTAMP",
  "version": 1
}
```

## Query

```http
GET /v1/accounts/{account_id}/items
GET /v1/accounts/{account_id}/items/{item_id}
```

## Commands

### `item.price.update`

```json
{
  "item_id": "ITEM_ID",
  "price": 99,
  "expected_version": 1
}
```

### `item.content.update`

```json
{
  "item_id": "ITEM_ID",
  "title": "新标题",
  "description": "新文案",
  "expected_version": 1
}
```

### `item.refresh`

```json
{
  "item_id": "ITEM_ID"
}
```

### `item.publish` / `item.unpublish`

第一批只覆盖已有草稿或已有商品的状态操作。完整新品发布需要后续接入 `ProductTemplate`、平台素材和字段校验。

### `item.template.sync`

模板修改不自动传播到在售商品。同步 Command 必须显式指定目标账号和商品，并为每个目标商品生成独立 Operation；执行前可以请求变更预览。

## Event

```text
item.updated
item.price_changed
item.status_changed
item.publish_succeeded
item.publish_failed
item.refresh_succeeded
```

## 验收重点

- API 返回的成功状态对应闲鱼实际状态变化；
- 改价、文案和状态操作支持版本冲突检测；
- 重复 Command 不产生重复操作；
- 通过 Query 可以验证最终商品状态；
- 每次变化保留前后版本和来源。
