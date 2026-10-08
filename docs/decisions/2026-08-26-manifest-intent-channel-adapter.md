# 2026-08-26 · 意图记忆 + ChannelAdapter

## 背景

护城河 P0：ChangeManifest 需记录「为什么改」并关联 IM 消息；IM 入口需可插拔（飞书 / 钉钉 / 自有 Web），避免绑死飞书。

## 决定

### 1. Manifest 意图字段

`manifests` 表新增列：

| 列 | 说明 |
|----|------|
| `intent` | 变更意图（业务背景） |
| `cot_summary` | 思维链摘要 |
| `channel` | 来源通道，默认 `feishu` |
| `channel_message_id` | 通用消息 ID（飞书时同 `feishu_message_id`） |

- API：`POST /api/v1/tasks/{id}/manifest` 顶层可选字段 + payload 兼容
- 未传 `channel_message_id` 时继承任务 `feishu_message_id`
- MCP：`unifier_submit_manifest(intent=, cot_summary=)` · `unifier_search_manifest_intent`
- 审计：`GET /api/v1/audit/manifests?q=&channel=&task_id=`

### 2. ChannelAdapter

```
app/channels/
  base.py      # ChannelAdapter ABC
  types.py     # IncomingMessage / ChannelReply
  feishu.py    # 飞书实现（委托 feishu_handler）
  registry.py  # get_channel_adapter("feishu")
```

- `POST /api/v1/feishu/events` 改经 `FeishuChannelAdapter`
- 后续钉钉/企微/Web：新增 adapter + registry 注册，不改 Hub 核心

## 待办

- [ ] Web 控制台 UI 展示审计时间线
- [ ] 向量检索（当前为 SQLite LIKE/内存过滤）
- [ ] 钉钉 ChannelAdapter

## 关联

- `app/services/manifests.py`
- `app/routers/audit.py`
- `app/channels/feishu.py`
