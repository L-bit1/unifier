# 联合器 n8n 预置工作流

Hub 在任务生命周期节点会向 n8n Webhook 推送事件（需 `hub/.env` 启用 `N8N_ENABLED=true`）。

## 事件类型

| event | 触发时机 |
|-------|----------|
| `task.dispatched` | 派活（飞书 / API） |
| `task.manifest_submitted` | 执行者提交变更清单 |
| `task.review_started` | 进入审查 |
| `task.review_submitted` | 审查者投票 |
| `task.merge_ready` | 全票通过，可合并 |
| `task.changes_requested` | 审查驳回 |

Payload 示例：

```json
{
  "event": "task.merge_ready",
  "timestamp": "2026-06-18T12:00:00+00:00",
  "source": "unifier-hub",
  "data": {
    "task_id": 3,
    "title": "修 nginx 超时",
    "status": "Approved",
    "merge_ready": true
  }
}
```

## 导入

1. 启动 n8n：`cd hub && docker compose up -d n8n`
2. 打开 http://127.0.0.1:5678 ，创建 API Key
3. 写入 `hub/.env`：`N8N_API_KEY=...`
4. 运行：`./scripts/import-n8n-workflows.sh`
5. 在 n8n 面板**激活**「联合器 · 事件接收」

`merge-ready-notify.json` 为示例分支流，请合并进主工作流或按需修改（同一 Webhook 路径只能有一个激活工作流）。

## n8n → Hub 派活

在 n8n 中使用 **HTTP Request** 节点：

```text
POST http://127.0.0.1:8787/api/v1/orchestrate/dispatch
Content-Type: application/json

{
  "github_owner": "your-org",
  "github_repo": "your-repo",
  "title": "来自 n8n 的任务",
  "branch": "feature/n8n-task"
}
```
