import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  App,
  Button,
  Card,
  Collapse,
  Empty,
  Image,
  Input,
  Layout,
  List,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import data from './chat_data.json';
import './styles.css';

const { Header, Sider, Content } = Layout;
const { Text, Title } = Typography;

function messageTypeLabel(type) {
  if (type === 'text') return '文本';
  if (type === 'image') return '图片';
  if (type === 'card') return '卡片';
  return type || '消息';
}

function messageTypeColor(type) {
  if (type === 'image') return 'green';
  if (type === 'card') return 'orange';
  if (type === 'text') return 'blue';
  return 'default';
}

function extractUrls(text) {
  return String(text || '').match(/https?:\/\/[^\s<>]+/g) || [];
}

function formatMessageText(text) {
  return String(text || '').replace(/\s+$/g, '');
}

function getLastMessage(conversation) {
  return conversation.messages?.[conversation.messages.length - 1];
}

function ConversationItem({ conversation, active, onClick }) {
  const last = getLastMessage(conversation);
  return (
    <List.Item className={`conversation-item ${active ? 'conversation-item-active' : ''}`} onClick={onClick}>
      <div className="conversation-main">
        <div className="conversation-line">
          <Text strong ellipsis={{ tooltip: conversation.title || conversation.peer_user_id || '未命名会话' }}>
            {conversation.title || conversation.peer_user_id || '未命名会话'}
          </Text>
          <Text type="secondary" className="conversation-time">{conversation.modified_at || ''}</Text>
        </div>
        <Text type="secondary" ellipsis className="conversation-preview">
          {last ? `${last.direction === 'out' ? '我' : (last.sender_name || '对方')}：${last.text || `[${messageTypeLabel(last.type)}]`}` : '没有消息'}
        </Text>
        <div className="conversation-line conversation-foot">
          <Text type="secondary">商品 {conversation.item_id || '未知'}</Text>
          <Text type="secondary">{conversation.messages?.length || 0} 条</Text>
        </div>
      </div>
    </List.Item>
  );
}

function MessageBubble({ item, day }) {
  const urls = item.type === 'image' ? extractUrls(item.text) : [];
  const text = formatMessageText(item.text || `[${messageTypeLabel(item.type)}]`);
  return (
    <React.Fragment>
      {day && <div className="day-divider">{day}</div>}
      <div className={`message-row ${item.direction === 'out' ? 'message-row-out' : 'message-row-in'}`}>
        <Card size="small" className={`message-card ${item.direction === 'out' ? 'message-card-out' : ''}`}>
          <div className="message-meta">
            <Text type="secondary">{item.direction === 'out' ? '我' : (item.sender_name || '对方')}</Text>
            <Text type="secondary">{item.created_at || '未知时间'}</Text>
            <Tag color={messageTypeColor(item.type)}>{messageTypeLabel(item.type)}</Tag>
          </div>
          <Typography.Paragraph className="message-text">{text}</Typography.Paragraph>
          {urls.length > 0 && (
            <Image.PreviewGroup>
              <Space wrap size={8} className="message-images">
                {urls.map((url) => <Image key={url} src={url} fallback="" alt="聊天图片" />)}
              </Space>
            </Image.PreviewGroup>
          )}
        </Card>
      </div>
    </React.Fragment>
  );
}

function ChatReader() {
  const [conversationQuery, setConversationQuery] = useState('');
  const [messageQuery, setMessageQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedCid, setSelectedCid] = useState(data.conversations?.[0]?.cid || '');
  const conversations = useMemo(() => (data.conversations || []).map((item) => ({
    ...item,
    searchText: [item.title, item.item_id, item.peer_user_id, item.cid, ...(item.messages || []).map((messageItem) => messageItem.text || '')]
      .filter(Boolean)
      .join(' ')
      .toLowerCase(),
  })), []);

  const visibleConversations = useMemo(() => {
    const query = conversationQuery.trim().toLowerCase();
    return query ? conversations.filter((item) => item.searchText.includes(query)) : conversations;
  }, [conversationQuery, conversations]);

  const selected = conversations.find((item) => item.cid === selectedCid) || null;
  const visibleMessages = useMemo(() => {
    if (!selected) return [];
    const query = messageQuery.trim().toLowerCase();
    return (selected.messages || []).filter((item) => {
      const typeMatch = typeFilter === 'all'
        || (typeFilter === 'custom' ? String(item.type || '').startsWith('custom') : item.type === typeFilter);
      const queryMatch = !query || String(item.text || '').toLowerCase().includes(query);
      return typeMatch && queryMatch;
    });
  }, [messageQuery, selected, typeFilter]);

  const copyConversation = async () => {
    if (!selected) return;
    const text = selected.messages
      .map((item) => `[${item.created_at || '未知时间'}] ${item.direction === 'out' ? '我' : (item.sender_name || '对方')}：${item.text || `[${item.type || '消息'}]`}`)
      .join('\n');
    await navigator.clipboard.writeText(text);
    message.success('当前会话已复制');
  };

  const downloadConversation = () => {
    if (!selected) return;
    const text = selected.messages
      .map((item) => `[${item.created_at || '未知时间'}] ${item.direction === 'out' ? '我' : (item.sender_name || '对方')}：${item.text || `[${item.type || '消息'}]`}`)
      .join('\n');
    const blob = new Blob([`# ${selected.title || selected.cid}\n\n${text}\n`], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${selected.cid || 'conversation'}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Layout className="reader-layout">
      <Sider width={370} theme="light" className="reader-sider">
        <div className="reader-sider-inner">
          <Collapse
            className="reader-overview-collapse"
            defaultActiveKey={['overview']}
            expandIconPosition="end"
            items={[{
              key: 'overview',
              label: (
                <div className="reader-collapse-label">
                  <Text className="reader-eyebrow">GOOFISH ARCHIVE</Text>
                  <Text strong>聊天记录阅读器</Text>
                </div>
              ),
              children: (
                <>
                  <div className="reader-brand">
                    <Text type="secondary">离线阅读全量会话，图片、卡片和自定义消息都会保留。</Text>
                  </div>
                  <div className="reader-stats">
                    <Card size="small"><Statistic title="会话" value={data.conversation_count} /></Card>
                    <Card size="small"><Statistic title="消息" value={data.message_count} /></Card>
                  </div>
                  <div className="reader-controls">
                    <Input.Search value={conversationQuery} onChange={(event) => setConversationQuery(event.target.value)} placeholder="搜索买家、商品、CID、消息" allowClear />
                    <Select value={typeFilter} onChange={setTypeFilter} className="reader-select" options={[
                      { value: 'all', label: '全部消息类型' },
                      { value: 'text', label: '文本' },
                      { value: 'image', label: '图片' },
                      { value: 'card', label: '卡片' },
                      { value: 'custom', label: '自定义消息' },
                    ]} />
                  </div>
                </>
              ),
            }]}
          />
          <div className="reader-list-summary"><Text type="secondary">{visibleConversations.length.toLocaleString()} 个会话</Text><Text type="secondary">可滚动浏览</Text></div>
          <div className="reader-list-viewport">
            <List
              split={false}
              dataSource={visibleConversations}
              renderItem={(item) => (
                <ConversationItem
                  key={item.cid}
                  conversation={item}
                  active={item.cid === selectedCid}
                  onClick={() => setSelectedCid(item.cid)}
                />
              )}
            />
          </div>
        </div>
      </Sider>
      <Layout className="reader-main-layout">
        <Header className="reader-header">
          <div className="reader-header-title">
            <Title level={3}>{selected?.title || '选择一个会话'}</Title>
            <Text type="secondary">{selected ? `商品 ${selected.item_id || '未知'} · 买家 ${selected.peer_user_id || '未知'} · ${selected.messages?.length || 0} 条消息` : '从左侧选择会话'}</Text>
          </div>
          <Space wrap>
            <Input value={messageQuery} onChange={(event) => setMessageQuery(event.target.value)} placeholder="筛选当前会话" allowClear />
            <Button onClick={copyConversation} disabled={!selected}>复制会话</Button>
            <Button type="primary" onClick={downloadConversation} disabled={!selected}>下载 Markdown</Button>
          </Space>
        </Header>
        <Content className="reader-content">
          <div className="reader-message-viewport">
            {selected ? (
              <List
                split={false}
                dataSource={visibleMessages}
                renderItem={(item, index) => {
                  const previous = visibleMessages[index - 1];
                  const day = item.created_at?.slice(0, 10) !== previous?.created_at?.slice(0, 10) ? item.created_at?.slice(0, 10) : '';
                  return (
                    <List.Item className="message-list-item" key={item.message_id || `${item.created_at_ms}-${index}`}>
                      <MessageBubble item={item} day={day} />
                    </List.Item>
                  );
                }}
              />
            ) : (
              <Empty description="选择一个会话开始阅读" />
            )}
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

createRoot(document.getElementById('root')).render(<App><ChatReader /></App>);
