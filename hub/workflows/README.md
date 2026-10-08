# 联合器工作流（路线 B：内置引擎，单进程）

Hub 启动后自动加载 `presets/` 预置模板，并在任务生命周期事件时执行已激活工作流。

## 可视化编辑器

```text
http://127.0.0.1:8787/workflows/editor
```

拖拽节点、连线、保存、激活。无需 Docker / n8n。

## 内置节点（13 个）

| 类型 | 说明 |
|------|------|
| `trigger.hub_event` | 派活、审查、merge_ready 等 |
| `trigger.webhook` | 外部 POST（GitHub 等） |
| `trigger.schedule` | Cron 定时 |
| `logic.if` | 条件分支 |
| `logic.delay` | 延迟 |
| `action.feishu` | 飞书消息 |
| `action.email` | SMTP 邮件 |
| `action.http` | HTTP 请求（可调 GitHub API） |
| `action.hub_dispatch` | Hub 派活 |
| `action.hub_task_status` | 查任务状态 |
| `action.hub_connectivity` | 设备联通检查 |
| `action.set_var` | 设置变量 |
| `action.log` | 写日志 |

模板语法：`{{event.data.task_id}}`、`{{vars.foo}}`

## 预置模板

目录：`hub/workflows/presets/`

- `merge-ready-feishu.json` — merge 通过通知（默认激活）
- `device-offline-alert.json` — 工作日 9:00 巡检
- `webhook-dispatch.json` — Webhook 派活

首次启动 Hub 自动导入；也可：

```bash
curl -X POST http://127.0.0.1:8787/api/v1/workflows/import-presets
```

## 邮件（可选）

`hub/.env`：

```env
WORKFLOW_SMTP_HOST=smtp.example.com
WORKFLOW_SMTP_PORT=587
WORKFLOW_SMTP_USER=
WORKFLOW_SMTP_PASSWORD=
WORKFLOW_SMTP_FROM=unifier@example.com
```

## API

| 方法 | 路径 |
|------|------|
| GET | `/workflows/editor` |
| GET | `/api/v1/workflows/nodes` |
| GET/POST | `/api/v1/workflows` |
| POST | `/api/v1/workflows/{id}/activate` |
| POST | `/api/v1/workflows/hooks/{hook_id}` |
| GET | `/api/v1/automation/workflows/health` |

## 与 n8n 的关系

- **路线 B（当前默认）**：内置引擎，只启动 Hub
- **路线 A（遗留可选）**：`N8N_ENABLED=true` 可同时启用 n8n Sidecar
