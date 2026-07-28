# Media API v1

- 状态：Draft
- 标准 API：v1
- 更新时间：2026-07-28

## 范围

第一版只覆盖图片素材、账号级闲鱼媒体实例和商品图片引用。

## 对象

### 平台素材

```json
{
  "id": "ASSET_ID",
  "type": "image",
  "sha256": "HASH",
  "mime_type": "image/jpeg",
  "size": 0,
  "width": 0,
  "height": 0,
  "created_at": "TIMESTAMP"
}
```

### 闲鱼媒体实例

```json
{
  "id": "MEDIA_INSTANCE_ID",
  "asset_id": "ASSET_ID",
  "account_id": "ACCOUNT_ID",
  "status": "pending|uploading|available|failed|expired",
  "platform_url": null,
  "observed_at": "TIMESTAMP"
}
```

## Query

```http
GET /v1/assets/{asset_id}
GET /v1/accounts/{account_id}/media
GET /v1/accounts/{account_id}/media/{media_instance_id}
```

## Commands

```text
media.image.upload
media.image.reupload
item.media.attach
item.media.detach
```

- 上传 Command 指定 `asset_id` 和目标 `account_id`；
- 相同账号和素材可以复用已存在且有效的媒体实例；
- 上传和重新上传使用 Operation 返回最终结果；
- 商品附加图片使用 `expected_version` 防止覆盖并发编辑。

## Events

```text
media.upload_started
media.available
media.upload_failed
media.expired
item.media_changed
```

## 后续范围

- 视频、音频和文件；
- 消息媒体；
- 自动压缩、转码和格式适配。

## 验收重点

- 原始图片只存一份并按哈希去重；
- 每个账号的闲鱼上传结果独立；
- 平台 URL 失效后可以从原素材恢复；
- 商品引用的媒体实例属于同一个目标账号。
