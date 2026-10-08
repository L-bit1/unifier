# 决策记录：内置工作流引擎（路线 B）

- **日期**：2026-06-18
- **场景**：Cursor 对话（联合器仓库）
- **状态**：已实施

---

## 背景

- 用户选择 **路线 B**：不依赖 n8n 独立进程，在 Hub 内实现轻量自动化 + 可视化编排。
- 目标：只启动 Hub 即可拖拽工作流，覆盖飞书 / 邮件 / HTTP / GitHub（经 HTTP）/ 定时 / Hub 派活等场景。
- n8n Sidecar（路线 A）保留为可选，默认关闭。

---

## 本次决定

### 1. 架构

```text
联合器 Hub（单进程）
├── 协作核心（飞书、审查、Device Agent）— 不变
├── 事件总线 → 内置 workflow_engine
├── APScheduler → 定时工作流
└── /workflows/editor → Drawflow 可视化编辑器
```

### 2. 内置节点（13 个）

触发：`hub_event` · `webhook` · `schedule`  
逻辑：`if` · `delay`  
动作：`feishu` · `email` · `http` · `hub_dispatch` · `hub_task_status` · `hub_connectivity` · `set_var` · `log`

### 3. 预置模板

`hub/workflows/presets/` — Hub 首次启动自动 import

### 4. 配置

- `WORKFLOWS_ENABLED=true`（默认）
- 邮件：`WORKFLOW_SMTP_*`
- n8n：`N8N_ENABLED` 仍为可选 Sidecar

### 5. 边界

| ✅ | ❌ |
|----|-----|
| 13 节点 + 可视化编辑器 | 不做 400+ 第三方集成 |
| HTTP 节点调 GitHub API | 不重写 n8n 全功能 |
| 模板 `{{event.data.x}}` | 不强制 Docker |

---

## 关联文件

- `hub/app/models.py` — Workflow / WorkflowRun
- `hub/app/services/workflow_*.py`
- `hub/app/routers/workflows.py`
- `hub/static/workflow-editor.html`
- `hub/workflows/presets/`
