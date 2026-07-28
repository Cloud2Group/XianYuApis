# Message API v1

- 状态：Draft
- 标准 API：v1
- 更新时间：2026-07-28

## 范围

第一版只覆盖文字消息和对应会话能力：

- 查询会话列表和详情；
- 查询消息历史和未读状态；
- 发送文字；
- 回复文字；
- 标记已读；
- 接收文字和状态 Event。

图片、商品卡片、语音和文件在后续版本扩展。消息内容始终使用 `content.type`，避免锁死为文字结构。

## 会话唯一关系

```text
seller_account_id + buyer_uid + primary_item_id
                    ↓
                唯一会话
```

每个会话绑定一个主商品。消息可以引用其他商品卡片，但不改变 `primary_item_id`。

## Query

```http
GET /v1/accounts/{account_id}/conversations
GET /v1/conversations/{conversation_id}
GET /v1/conversations/{conversation_id}/messages
```

会话标准字段：

```json
{
  "id": "CONVERSATION_ID",
  "account_id": "ACCOUNT_ID",
  "buyer_id": "BUYER_ID",
  "buyer_uid": "XIANYU_BUYER_UID",
  "primary_item_id": "ITEM_ID",
  "unread_count": 0,
  "last_message_at": "TIMESTAMP",
  "version": 1
}
```

消息标准字段：

```json
{
  "id": "MESSAGE_ID",
  "conversation_id": "CONVERSATION_ID",
  "account_id": "ACCOUNT_ID",
  "direction": "in|out",
  "sender_uid": "XIANYU_UID",
  "content": {
    "type": "text",
    "text": "TEXT"
  },
  "reply_to_message_id": null,
  "created_at": "TIMESTAMP",
  "observed_at": "TIMESTAMP"
}
```

## Command：发送文字

Capability：`message.send`

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "message.send",
  "idempotency_key": "KEY",
  "parameters": {
    "conversation_id": "CONVERSATION_ID",
    "content": {
      "type": "text",
      "text": "你好"
    }
  }
}
```

## Command：回复文字

Capability：`message.reply`

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "message.reply",
  "idempotency_key": "KEY",
  "parameters": {
    "conversation_id": "CONVERSATION_ID",
    "reply_to_message_id": "MESSAGE_ID",
    "content": {
      "type": "text",
      "text": "我来确认一下"
    }
  }
}
```

## Command：标记已读

Capability：`conversation.mark_read`

```json
{
  "account_id": "ACCOUNT_ID",
  "capability": "conversation.mark_read",
  "idempotency_key": "KEY",
  "parameters": {
    "conversation_id": "CONVERSATION_ID",
    "through_message_id": "MESSAGE_ID"
  }
}
```

## Event

第一版事件：

```text
message.received
message.sent
message.send_failed
conversation.unread_changed
conversation.status_changed
```

`message.sent` 只在闲鱼成功回调或状态观察确认后产生。Operation 的状态事件仍通过通用 `operation.*` Event 输出。

同一会话内保持消息观察顺序；跨会话不承诺全局顺序。Event 可以重复投递，调用者按 `event_id` 和 `message_id` 去重。

## v1 验收

1. Query 可以定位卖家账号、买家和主商品对应的唯一会话；
2. 收到真实文字后只产生一个 `message.received`；
3. `message.send` 和 `message.reply` 获得最终 Operation 结果；
4. 买家侧收到消息，本地业务账本出现对应出站消息；
5. `conversation.mark_read` 在 App 和本地状态中可观察；
6. 断线恢复后可以按游标补齐遗漏消息。
