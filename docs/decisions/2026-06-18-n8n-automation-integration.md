# 决策记录：n8n 自动化套件接入（NAS 式扩展）

- **日期**：2026-06-18
- **场景**：Cursor 对话（联合器仓库）
- **状态**：已实施（v0.3 进行中）

---

## 背景

- 用户希望联合器支持更多集成能力，参考 **NAS 套件中心**模式：Head 常开机、可选装应用、统一看状态。
- **n8n** 作为通用工作流引擎，可补 Hub 不做的跨系统自动化（GitHub、邮件、定时、审批等）。
- 联合器核心仍是 **AI 协作控制面**（飞书派活、多 Agent 审查、Device Agent），n8n 不替代 Cursor/Trae 执行层。

---

## 本次决定

### 1. 定位与边界

| ✅ 做 | ❌ 不做 |
|------|--------|
| n8n 作为 **Sidecar 可选套件**（Docker） | 把 n8n 源码 fork 进 Hub |
| Hub **事件出站** → n8n Webhook | 用 n8n 替代 Device Agent / MCP |
| n8n **反向调用** Hub REST API 派活 | n8n 替代飞书 bridge |
| **套件总览 API**（NAS 式控制面板） | 联合器变成完整 iPaaS 平台 |

### 2. 架构

```text
飞书 / API 派活 → Hub（协作核心 + 审查闸门）
                      │
                      ├── Cursor/Trae（AI 执行，不变）
                      └──→ n8n（自动化扩展）
                             ├── 接收 Hub 生命周期事件
                             └── 可 POST /orchestrate/dispatch 反向派活
```

### 3. 已实现能力（v0.3）

**事件类型**（Hub → n8n Webhook）：

- `task.dispatched`
- `task.manifest_submitted`
- `task.review_started`
- `task.review_submitted`
- `task.merge_ready`
- `task.changes_requested`

**API**：

- `GET /api/v1/automation/stack` — Head 套件总览
- `GET /api/v1/automation/connectors` — Connector 列表
- `GET /api/v1/automation/n8n/health`
- `POST /api/v1/automation/n8n/test-event`

**部署**：

- `hub/docker-compose.yml` — n8n 容器
- `hub/workflows/` — 预置工作流模板
- `hub/.env`：`N8N_ENABLED`、`N8N_URL`、`N8N_WEBHOOK_PATH`
- `start-services.sh` — `N8N_ENABLED=true` 时随 Hub 启动 n8n

**飞书指令**：`套件` / `栈` / `自动化` / `n8n`

### 4. 配置约定

```env
# hub/.env
N8N_ENABLED=true
N8N_URL=http://127.0.0.1:5678
N8N_WEBHOOK_PATH=unifier-events
N8N_API_KEY=          # 可选，用于 import-n8n-workflows.sh
```

Webhook 完整地址：`{N8N_URL}/webhook/{N8N_WEBHOOK_PATH}`

### 5. 路线图调整

- **v0.2**：Hub + 飞书 + Device Agent + 审查（已完成）
- **v0.3**（进行中）：n8n 套件 + 事件出站 + 套件总览
- **v0.3+**：GitHub Webhook → n8n/飞书（可优先用 n8n 实现，不必重复写 Python bridge）

---

## 待办 / 未决

- [ ] 本机 Docker 环境跑通 `start-services.sh` + 导入工作流端到端验证
- [ ] 预置「GitHub PR → 派活」「merge_ready → 多通道通知」n8n 模板（可合并进主工作流）
- [ ] 可选：Connector 抽象层统一 feishu / soul / n8n 注册（v0.4）
- [ ] 可选：飞书「套件」卡片 UI（当前为文字回复）

---

## 关联文件

- `hub/app/config.py` — n8n 配置项
- `hub/app/services/n8n_bridge.py` — n8n HTTP 桥接
- `hub/app/services/event_bus.py` — 事件总线
- `hub/app/routers/automation.py` — 套件 API
- `hub/app/routers/orchestrate.py`、`tasks.py` — 事件挂钩
- `hub/app/services/feishu_handler.py` — 飞书「套件/自动化」指令
- `hub/docker-compose.yml`
- `hub/workflows/`、`hub/scripts/import-n8n-workflows.sh`
- `hub/scripts/start-services.sh`
- `hub/README.md`、`README.md`（路线图）
