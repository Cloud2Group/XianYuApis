from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from xianyu_web.paths import EXPORTS_DIR

_DEFAULT_EXPORT_DIR = EXPORTS_DIR / "xianyu_chats_full_20260714"
DEFAULT_INPUT = str(_DEFAULT_EXPORT_DIR / "xianyu_chats.json")
DEFAULT_OUTPUT = str(_DEFAULT_EXPORT_DIR / "xianyu_chat_reader.html")


KEEP_CONVERSATION_FIELDS = (
    "cid",
    "title",
    "item_id",
    "peer_user_id",
    "owner_user_id",
    "modified_at",
    "modified_at_ms",
    "message_count",
)
KEEP_MESSAGE_FIELDS = (
    "message_id",
    "created_at",
    "created_at_ms",
    "direction",
    "sender_id",
    "sender_name",
    "type",
    "text",
    "content_type",
)


def build_slim_data(source: Dict[str, Any]) -> Dict[str, Any]:
    conversations: List[Dict[str, Any]] = []
    for conversation in source.get("conversations") or []:
        item = {key: conversation.get(key) for key in KEEP_CONVERSATION_FIELDS}
        item["messages"] = [
            {key: message.get(key) for key in KEEP_MESSAGE_FIELDS}
            for message in conversation.get("messages") or []
        ]
        conversations.append(item)

    return {
        "exported_at": source.get("exported_at"),
        "account": source.get("account") or {},
        "conversation_count": len(conversations),
        "message_count": sum(len(item["messages"]) for item in conversations),
        "conversations": conversations,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>闲鱼聊天记录阅读器</title>
  <style>
    :root {
      --ink: #1f2933;
      --muted: #718096;
      --line: #e6e1d8;
      --paper: #fbfaf7;
      --panel: #f3f0e9;
      --accent: #cc5a3d;
      --accent-dark: #9f3f2d;
      --buyer: #ffffff;
      --seller: #dcefe8;
      --shadow: 0 16px 40px rgba(42, 35, 25, .08);
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 0%, rgba(204, 90, 61, .12), transparent 28%),
        linear-gradient(135deg, #f4f0e8 0%, #fbfaf7 48%, #edf3ef 100%);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
    }

    button, input, select { font: inherit; }
    button { cursor: pointer; }
    .app { display: grid; grid-template-columns: 360px minmax(0, 1fr); height: 100vh; overflow: hidden; }
    .sidebar { display: flex; flex-direction: column; min-width: 0; background: rgba(251, 250, 247, .88); border-right: 1px solid var(--line); backdrop-filter: blur(18px); }
    .brand { padding: 26px 24px 18px; }
    .eyebrow { margin: 0 0 8px; color: var(--accent); font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
    h1, h2, p { margin: 0; }
    h1 { font-family: Georgia, "Songti SC", serif; font-size: 29px; letter-spacing: -.04em; }
    .subtitle { margin-top: 8px; color: var(--muted); font-size: 13px; line-height: 1.6; }
    .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 20px 18px; }
    .stat { padding: 12px 14px; background: var(--panel); border: 1px solid rgba(230, 225, 216, .8); border-radius: 14px; }
    .stat strong { display: block; font-size: 20px; }
    .stat span { color: var(--muted); font-size: 12px; }
    .controls { display: grid; gap: 8px; padding: 0 20px 14px; }
    .control, .toolbar-input { width: 100%; padding: 11px 13px; color: var(--ink); background: #fff; border: 1px solid var(--line); border-radius: 11px; outline: none; }
    .control:focus, .toolbar-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(204, 90, 61, .12); }
    .list-meta { display: flex; justify-content: space-between; align-items: center; padding: 0 22px 8px; color: var(--muted); font-size: 12px; }
    .conversation-list { min-height: 0; overflow: auto; padding: 0 12px 18px; }
    .conversation { display: block; width: 100%; padding: 13px 12px; color: inherit; text-align: left; background: transparent; border: 0; border-left: 3px solid transparent; border-radius: 12px; }
    .conversation:hover { background: #f4efe7; }
    .conversation.active { background: #f1e6dc; border-left-color: var(--accent); }
    .conversation-top, .conversation-bottom { display: flex; justify-content: space-between; gap: 10px; }
    .conversation-title { overflow: hidden; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
    .conversation-time, .conversation-bottom { color: var(--muted); font-size: 11px; }
    .conversation-preview { overflow: hidden; margin: 5px 0; color: #56616d; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
    .empty-list { padding: 32px 16px; color: var(--muted); text-align: center; font-size: 13px; }
    .main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 22px 30px 16px; background: rgba(251, 250, 247, .7); border-bottom: 1px solid var(--line); backdrop-filter: blur(14px); }
    .conversation-heading { min-width: 0; }
    .conversation-heading h2 { overflow: hidden; font-family: Georgia, "Songti SC", serif; font-size: 25px; text-overflow: ellipsis; white-space: nowrap; }
    .conversation-details { margin-top: 6px; color: var(--muted); font-size: 12px; }
    .toolbar { display: flex; flex: 0 1 400px; gap: 8px; align-items: center; }
    .toolbar-input { min-width: 150px; }
    .action { padding: 10px 12px; color: #fff; background: var(--accent); border: 0; border-radius: 10px; white-space: nowrap; }
    .action:hover { background: var(--accent-dark); }
    .message-pane { flex: 1; min-height: 0; overflow: auto; padding: 28px clamp(18px, 5vw, 72px) 48px; }
    .message-stack { max-width: 900px; margin: 0 auto; }
    .day-divider { display: flex; align-items: center; gap: 12px; margin: 20px 0 14px; color: var(--muted); font-size: 11px; }
    .day-divider::before, .day-divider::after { flex: 1; height: 1px; background: var(--line); content: ""; }
    .message-row { display: flex; margin: 10px 0; }
    .message-row.out { justify-content: flex-end; }
    .message-bubble { max-width: min(720px, 86%); padding: 11px 14px 12px; background: var(--buyer); border: 1px solid var(--line); border-radius: 17px 17px 17px 5px; box-shadow: 0 5px 18px rgba(42, 35, 25, .04); }
    .message-row.out .message-bubble { background: var(--seller); border-color: #c5e4d8; border-radius: 17px 17px 5px 17px; }
    .message-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; color: var(--muted); font-size: 11px; }
    .message-kind { padding: 2px 6px; color: var(--accent-dark); background: rgba(204, 90, 61, .1); border-radius: 5px; }
    .message-content { line-height: 1.72; white-space: pre-wrap; overflow-wrap: anywhere; }
    .message-content a { color: var(--accent-dark); }
    .media { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; margin-top: 8px; }
    .media img { display: block; width: 100%; max-height: 260px; object-fit: cover; background: #eee; border-radius: 10px; }
    .card-content { padding: 10px 12px; background: rgba(204, 90, 61, .06); border-left: 3px solid var(--accent); border-radius: 8px; }
    .empty-state { display: grid; place-items: center; height: 100%; min-height: 300px; color: var(--muted); text-align: center; }
    .empty-state strong { display: block; margin-bottom: 8px; color: var(--ink); font-family: Georgia, "Songti SC", serif; font-size: 24px; }
    mark { padding: 0 2px; background: #ffe3a8; border-radius: 3px; }
    @media (max-width: 860px) {
      .app { grid-template-columns: 1fr; height: auto; min-height: 100vh; overflow: visible; }
      .sidebar { max-height: 48vh; border-right: 0; border-bottom: 1px solid var(--line); }
      .main { min-height: 52vh; }
      .topbar { align-items: flex-start; flex-direction: column; padding: 18px; }
      .toolbar { width: 100%; flex-basis: auto; }
      .message-pane { padding: 18px 12px 32px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">Goofish archive</p>
        <h1>聊天记录阅读器</h1>
        <p class="subtitle">本地离线阅读。原始字段已压缩，只保留浏览聊天真正需要的信息。</p>
      </div>
      <div class="stats">
        <div class="stat"><strong id="conversationCount">0</strong><span>个会话</span></div>
        <div class="stat"><strong id="messageCount">0</strong><span>条消息</span></div>
      </div>
      <div class="controls">
        <input id="conversationSearch" class="control" placeholder="搜索买家、商品、CID 或消息内容">
        <select id="typeFilter" class="control">
          <option value="all">全部消息类型</option>
          <option value="text">文本</option>
          <option value="image">图片</option>
          <option value="card">卡片</option>
          <option value="custom">自定义消息</option>
        </select>
      </div>
      <div class="list-meta"><span id="listCount">0 个会话</span><span>点击查看</span></div>
      <div id="conversationList" class="conversation-list"></div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="conversation-heading">
          <h2 id="conversationTitle">选择一个会话</h2>
          <p id="conversationDetails" class="conversation-details">左侧搜索并打开聊天记录</p>
        </div>
        <div class="toolbar">
          <input id="messageSearch" class="toolbar-input" placeholder="筛选当前会话消息">
          <button id="copyButton" class="action" type="button">复制会话</button>
          <button id="downloadButton" class="action" type="button">下载</button>
        </div>
      </header>
      <section id="messagePane" class="message-pane">
        <div class="empty-state"><div><strong>先选一个会话</strong><span>聊天内容会在这里展开</span></div></div>
      </section>
    </main>
  </div>

  <script id="chat-data" type="application/json">__CHAT_DATA__</script>
  <script>
    (() => {
      const data = JSON.parse(document.getElementById('chat-data').textContent);
      const conversations = (data.conversations || []).map((conversation, index) => ({
        ...conversation,
        index,
        searchText: [
          conversation.title,
          conversation.item_id,
          conversation.peer_user_id,
          conversation.cid,
          ...(conversation.messages || []).map(message => message.text || '')
        ].filter(Boolean).join(' ').toLowerCase()
      }));
      const state = { selected: -1, query: '', type: 'all', messageQuery: '' };
      const $ = id => document.getElementById(id);
      const list = $('conversationList');
      const pane = $('messagePane');

      $('conversationCount').textContent = conversations.length.toLocaleString();
      $('messageCount').textContent = Number(data.message_count || 0).toLocaleString();

      function formatCount(value) { return Number(value || 0).toLocaleString(); }
      function messageTypeLabel(type) {
        if (type === 'text') return '文本';
        if (type === 'image') return '图片';
        if (type === 'card') return '卡片';
        return type || '消息';
      }
      function escapeRegExp(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
      function appendTextWithLinks(parent, value) {
        const text = String(value || '');
        const pattern = /https?:\/\/[^\s<>]+/g;
        let cursor = 0;
        let match;
        while ((match = pattern.exec(text))) {
          if (match.index > cursor) parent.appendChild(document.createTextNode(text.slice(cursor, match.index)));
          const link = document.createElement('a');
          link.href = match[0];
          link.target = '_blank';
          link.rel = 'noreferrer';
          link.textContent = match[0];
          parent.appendChild(link);
          cursor = match.index + match[0].length;
        }
        if (cursor < text.length) parent.appendChild(document.createTextNode(text.slice(cursor)));
      }
      function conversationMatches(conversation) {
        return !state.query || conversation.searchText.includes(state.query);
      }
      function filteredConversations() { return conversations.filter(conversationMatches); }

      function renderConversationList() {
        const visible = filteredConversations();
        $('listCount').textContent = `${formatCount(visible.length)} 个会话`;
        list.replaceChildren();
        if (!visible.length) {
          const empty = document.createElement('div');
          empty.className = 'empty-list';
          empty.textContent = '没有匹配的会话';
          list.appendChild(empty);
          return;
        }
        visible.forEach(conversation => {
          const button = document.createElement('button');
          button.className = `conversation${state.selected === conversation.index ? ' active' : ''}`;
          button.type = 'button';
          button.addEventListener('click', () => selectConversation(conversation.index));

          const top = document.createElement('div');
          top.className = 'conversation-top';
          const title = document.createElement('span');
          title.className = 'conversation-title';
          title.textContent = conversation.title || conversation.peer_user_id || conversation.cid || '未命名会话';
          const time = document.createElement('span');
          time.className = 'conversation-time';
          time.textContent = conversation.modified_at || '';
          top.append(title, time);

          const preview = document.createElement('div');
          preview.className = 'conversation-preview';
          const last = (conversation.messages || []).at(-1);
          preview.textContent = last ? `${last.sender_name || (last.direction === 'out' ? '我' : '对方')}：${last.text || `[${last.type || '消息'}]`}` : '没有消息';

          const bottom = document.createElement('div');
          bottom.className = 'conversation-bottom';
          const item = document.createElement('span');
          item.textContent = conversation.item_id ? `商品 ${conversation.item_id}` : '无商品 ID';
          const count = document.createElement('span');
          count.textContent = `${formatCount(conversation.messages?.length)} 条`;
          bottom.append(item, count);
          button.append(top, preview, bottom);
          list.appendChild(button);
        });
      }

      function messageMatches(message) {
        if (state.type !== 'all') {
          const matchesType = state.type === 'custom' ? String(message.type || '').startsWith('custom') : message.type === state.type;
          if (!matchesType) return false;
        }
        return !state.messageQuery || String(message.text || '').toLowerCase().includes(state.messageQuery);
      }

      function renderMessage(message) {
        const row = document.createElement('div');
        row.className = `message-row ${message.direction === 'out' ? 'out' : 'in'}`;
        const bubble = document.createElement('article');
        bubble.className = 'message-bubble';

        const meta = document.createElement('div');
        meta.className = 'message-meta';
        const sender = document.createElement('span');
        sender.textContent = message.direction === 'out' ? '我' : (message.sender_name || '对方');
        const time = document.createElement('span');
        time.textContent = message.created_at || '未知时间';
        const kind = document.createElement('span');
        kind.className = 'message-kind';
        kind.textContent = messageTypeLabel(message.type);
        meta.append(sender, time, kind);
        bubble.appendChild(meta);

        const content = document.createElement('div');
        content.className = message.type === 'card' ? 'message-content card-content' : 'message-content';
        appendTextWithLinks(content, message.text || `[${messageTypeLabel(message.type)}]`);
        bubble.appendChild(content);

        if (message.type === 'image') {
          const urls = String(message.text || '').match(/https?:\/\/[^\s<>]+/g) || [];
          if (urls.length) {
            const media = document.createElement('div');
            media.className = 'media';
            urls.forEach(url => {
              const link = document.createElement('a');
              link.href = url;
              link.target = '_blank';
              link.rel = 'noreferrer';
              const image = document.createElement('img');
              image.src = url;
              image.loading = 'lazy';
              image.alt = '聊天图片';
              image.onerror = () => { image.replaceWith(document.createTextNode('图片链接已失效')); };
              link.appendChild(image);
              media.appendChild(link);
            });
            bubble.appendChild(media);
          }
        }
        row.appendChild(bubble);
        return row;
      }

      function renderMessages(conversation) {
        pane.replaceChildren();
        const stack = document.createElement('div');
        stack.className = 'message-stack';
        const messages = (conversation.messages || []).filter(messageMatches);
        let currentDay = '';
        messages.forEach(message => {
          const day = String(message.created_at || '').slice(0, 10);
          if (day && day !== currentDay) {
            currentDay = day;
            const divider = document.createElement('div');
            divider.className = 'day-divider';
            divider.textContent = day;
            stack.appendChild(divider);
          }
          stack.appendChild(renderMessage(message));
        });
        if (!messages.length) {
          const empty = document.createElement('div');
          empty.className = 'empty-state';
          empty.textContent = '当前筛选下没有消息';
          stack.appendChild(empty);
        }
        pane.appendChild(stack);
        pane.scrollTop = pane.scrollHeight;
      }

      function selectConversation(index) {
        state.selected = index;
        const conversation = conversations[index];
        $('conversationTitle').textContent = conversation.title || conversation.peer_user_id || conversation.cid || '未命名会话';
        $('conversationDetails').textContent = `商品 ${conversation.item_id || '未知'} · 买家 ${conversation.peer_user_id || '未知'} · ${formatCount(conversation.messages?.length)} 条消息`;
        $('messageSearch').value = '';
        state.messageQuery = '';
        renderConversationList();
        renderMessages(conversation);
      }

      function currentDialogueText() {
        const conversation = conversations[state.selected];
        if (!conversation) return '';
        return (conversation.messages || []).map(message => `[${message.created_at || '未知时间'}] ${message.direction === 'out' ? '我' : (message.sender_name || '对方')}：${message.text || `[${message.type || '消息'}]`}`).join('\n');
      }
      async function copyCurrent() {
        const text = currentDialogueText();
        if (!text) return;
        await navigator.clipboard.writeText(text);
        $('copyButton').textContent = '已复制';
        setTimeout(() => { $('copyButton').textContent = '复制会话'; }, 1200);
      }
      function downloadCurrent() {
        const conversation = conversations[state.selected];
        const text = currentDialogueText();
        if (!conversation || !text) return;
        const blob = new Blob([`# ${conversation.title || conversation.cid}\n\n${text}\n`], {type: 'text/markdown;charset=utf-8'});
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `${conversation.cid || 'conversation'}.md`;
        anchor.click();
        URL.revokeObjectURL(url);
      }

      $('conversationSearch').addEventListener('input', event => {
        state.query = event.target.value.trim().toLowerCase();
        renderConversationList();
      });
      $('typeFilter').addEventListener('change', event => {
        state.type = event.target.value;
        if (state.selected >= 0) renderMessages(conversations[state.selected]);
      });
      $('messageSearch').addEventListener('input', event => {
        state.messageQuery = event.target.value.trim().toLowerCase();
        if (state.selected >= 0) renderMessages(conversations[state.selected]);
      });
      $('copyButton').addEventListener('click', copyCurrent);
      $('downloadButton').addEventListener('click', downloadCurrent);
      renderConversationList();
    })();
  </script>
</body>
</html>
'''


def build_reader(source_path: Path, output_path: Path) -> None:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    slim = build_slim_data(source)
    data_json = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(HTML_TEMPLATE.replace("__CHAT_DATA__", data_json), encoding="utf-8")
    print(f"阅读器已生成：{output_path}")
    print(f"内嵌会话：{slim['conversation_count']} 个，消息：{slim['message_count']} 条")
    print(f"文件大小：{output_path.stat().st_size / 1024 / 1024:.2f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成离线闲鱼聊天记录 HTML 阅读器")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"输入 JSON，默认 {DEFAULT_INPUT}")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"输出 HTML，默认 {DEFAULT_OUTPUT}")
    args = parser.parse_args()
    build_reader(Path(args.input).expanduser(), Path(args.output).expanduser())


if __name__ == "__main__":
    main()
