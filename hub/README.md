# 联合器 Hub（v0.2）

本地协作控制面：**项目绑定、任务状态机、多 Agent 审查、设备注册/心跳、命令编排、Device Agent 收件箱**。  
GitHub 仍负责代码；Hub 负责「能不能 merge」前的流程与留痕。

- API 文档：启动后打开 `http://<主机>:8787/docs`
- 健康检查：`GET /health`

---

## 一键跑通四端流程（本机验证）

在 **一台 Mac** 上可模拟「手机下命令 → 四 Agent 干活 → 审查 → 反馈」：

```bash
cd hub
chmod +x run.sh scripts/*.sh scripts/device-agent.py
./scripts/run-e2e-local.sh
```

成功时会输出 `✅ 四端流程跑通`，并在 `~/.unifier/inbox/` 生成各 Agent 的 HANDOFF 文件。

---

## 你的四步工作流（两台真机）

对应：**手机下命令 → 四端干活 → 联合器指挥 → 结果反馈**。

```text
① 手机（飞书群 或 curl 模拟）
      POST /api/v1/orchestrate/dispatch
           ↓
② Hub 派活给 mac-a/cursor，审查者 win-pc:cursor / win-pc:trae / mac-a:trae
           ↓
③ 各机 Device Agent 轮询 inbox → 写入 ~/.unifier/inbox/*.md → Cursor/Trae 执行
           ↓
④ 手机轮询 GET /api/v1/orchestrate/tasks/{id}/status 看 merge_ready
   （飞书 Bot 接入前用 curl；后续 Bot 读同一接口推卡片）
```

### 步骤 0：Mac 上常开 Hub

```bash
cd hub && ./run.sh
# 查局域网 IP（Win 要用）
ipconfig getifaddr en0   # 例: 192.168.1.10
```

### 步骤 1：模拟手机下命令（或日后飞书 Bot 调同一接口）

在任意终端（可理解为「手机发令」）：

```bash
cd hub
export HUB_URL=http://127.0.0.1:8787   # 外网手机经 Tailscale 等则改成可达地址
./scripts/dispatch-command.sh "智盈｜修 nginx 超时" feature/nginx-timeout
# 记下输出的 task_id
```

### 步骤 2：Mac 上跑 Cursor + Trae Agent

**终端 A**（Mac · cursor，执行者）：

```bash
export HUB_URL=http://127.0.0.1:8787
export DEVICE_ID=mac-a
export AGENT_ID=cursor
./scripts/start-workstation.sh
```

**终端 B**（Mac · trae，审查者）— 另开终端，改 `AGENT_ID`：

```bash
export HUB_URL=http://127.0.0.1:8787
export DEVICE_ID=mac-a
export AGENT_ID=trae
python3 scripts/device-agent.py --device-id mac-a --agent-id trae
```

Agent 会把任务写到 `~/.unifier/inbox/`，在 Cursor/Trae 里按 HANDOFF 改代码。

### 步骤 3：Windows 上跑 Cursor + Trae Agent

在 Win 上克隆仓库，PowerShell / Git Bash：

```bash
export HUB_URL=http://192.168.1.10:8787   # Mac Hub 的局域网 IP
export DEVICE_ID=win-pc
export AGENT_ID=cursor   # 或 trae，各开一个终端
python3 scripts/device-agent.py
```

首次需注册：

```bash
export HUB_URL=http://192.168.1.10:8787
export DEVICE_ID=win-pc
export AGENTS=cursor,trae
./scripts/register-device.sh "Windows 副机"
```

### 步骤 4：执行者提交 manifest，审查者投票

执行者（Mac cursor）改完代码后：

```bash
export HUB_URL=http://127.0.0.1:8787
export TASK_ID=1 DEVICE_ID=mac-a AGENT_ID=cursor
./scripts/submit-manifest.sh "调整 nginx upstream 超时"
curl -X POST $HUB_URL/api/v1/tasks/$TASK_ID/submit-review
```

审查者（每台 trae/cursor 审查端）：

```bash
export TASK_ID=1 REVIEWER_ID=win-pc:cursor   # 或 win-pc:trae / mac-a:trae
./scripts/submit-review-vote.sh approved
```

### 步骤 5：手机上看结果

```bash
curl -s http://127.0.0.1:8787/api/v1/orchestrate/tasks/1/status | python3 -m json.tool
```

`merge_ready: true` 且 `status: Approved` → 去 GitHub merge。  
`message` 字段即拟推送给飞书的摘要文本。

---

## 设备在线联通性检查

派活前确认 **Hub 可达** 且 **期望设备在线**（默认 `mac-a,win-pc`，可在 `.env` 设 `UNIFIER_EXPECTED_DEVICES`）。

### 命令行（任意终端 / 模拟手机）

```bash
cd hub
./scripts/check-connectivity.sh

# 本机顺便发心跳再检查
DEVICE_ID=mac-a ./scripts/check-connectivity.sh

# 自定义期望列表；STRICT=0 仅展示不报错
EXPECTED=mac-a,win-pc STRICT=0 ./scripts/check-connectivity.sh
```

### API

```bash
# 全部设备联通性报告
curl -s "http://127.0.0.1:8787/api/v1/devices/connectivity?expected=mac-a,win-pc" | python3 -m json.tool

# 单台设备
curl -s "http://127.0.0.1:8787/api/v1/devices/mac-a/connectivity" | python3 -m json.tool

# 手机端入口（与上相同）
curl -s "http://127.0.0.1:8787/api/v1/orchestrate/connectivity" | python3 -m json.tool
```

返回字段要点：

| 字段 | 含义 |
|------|------|
| `ready_for_dispatch` | 期望设备是否全部在线，可派活 |
| `missing_expected` | 期望但未注册的设备 |
| `expected_offline` | 已注册但心跳超时的设备 |
| `link_status` | 单台：`online` / `offline` / `never_seen` |

派活时可强制校验（设备离线则拒绝）：

```bash
# dispatch-command 默认 REQUIRE_CONNECTIVITY=1
REQUIRE_CONNECTIVITY=1 ./scripts/dispatch-command.sh "任务标题"
```

或在 API 里设 `"require_connectivity": true`。

---

## 快速启动（建议在一台常开的 Mac 上跑）

```bash
cd hub
chmod +x run.sh scripts/*.sh
./run.sh
```

首次会自动创建 `.venv` 并安装依赖，默认监听 **`0.0.0.0:8787`**（局域网内其他设备可访问）。

可选：复制 `.env.example` 为 `.env` 修改端口或数据库路径。

---

## 两台设备怎么连 Hub

思路：**Hub 只装在一台机器上**（例如家里 Mac），两台设备都通过 **局域网 IP** 访问同一个 Hub。

```text
        ┌─────────────────────────────────┐
        │  Mac A（运行 Hub :8787）         │
        │  局域网 IP 例: 192.168.1.10      │
        └───────────────┬─────────────────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   Mac A 本机                      Mac B / Win
   DEVICE_ID=mac-a                 DEVICE_ID=win-b
   注册 + 心跳                      注册 + 心跳
```

### 步骤 1：在跑 Hub 的机器上查 IP

```bash
# macOS
ipconfig getifaddr en0
# 或系统设置 → 网络 → Wi‑Fi → IP 地址
```

记下例如 `192.168.1.10`。

### 步骤 2：Mac A（Hub 本机）注册

```bash
cd hub
export HUB_URL=http://127.0.0.1:8787
export DEVICE_ID=mac-a
./scripts/register-device.sh "Mac A 主力机"
# 可选：另开终端保持在线
export DEVICE_ID=mac-a
./scripts/heartbeat-loop.sh
```

### 步骤 3：Mac B（Windows 副机）注册

在 **Windows** 上克隆本仓库（或只拷贝 `hub/scripts`），执行：

```bash
export HUB_URL=http://192.168.1.10:8787   # 改成 Hub 机器的局域网 IP
export DEVICE_ID=win-pc                      # 每台必须唯一
export AGENTS=cursor,trae
./scripts/register-device.sh "Windows 副机"
./scripts/heartbeat-loop.sh
```

### 步骤 4：在 Hub 上确认两台在线

浏览器或 curl：

```bash
curl "http://192.168.1.10:8787/api/v1/devices?online_only=true"
```

`online: true` 表示在 `UNIFIER_DEVICE_ONLINE_SECONDS`（默认 90 秒）内心跳过。

### 防火墙注意

- macOS：系统设置 → 网络 → 防火墙，允许 Python/终端入站，或暂时关闭防火墙做联调。
- 两台机器需在同一 Wi‑Fi/局域网；跨网需自行做端口转发或 Tailscale（后续文档可补）。

---

## 走通一条任务（手工 / curl）

以下 `HUB` 替换为你的地址。

```bash
HUB=http://127.0.0.1:8787

# 1. 绑定 GitHub 项目（元数据，不 clone）
curl -X POST $HUB/api/v1/projects -H "Content-Type: application/json" \
  -d '{"github_owner":"your-org","github_repo":"your-repo"}'

# 2. 创建任务（required_reviewers = 必须全票 approve 的 agent id）
curl -X POST $HUB/api/v1/tasks -H "Content-Type: application/json" \
  -d '{"project_id":1,"title":"示例任务","branch":"feature/demo","required_reviewers":["agent-2","agent-3"]}'

# 3. 派给 device-a 上的 cursor
curl -X POST $HUB/api/v1/tasks/1/assign -H "Content-Type: application/json" \
  -d '{"device_id":"mac-a","agent_id":"cursor"}'

# 4. 提交变更清单（ChangeManifest 内容放在 payload）
curl -X POST $HUB/api/v1/tasks/1/manifest -H "Content-Type: application/json" \
  -d '{"agent_id":"cursor","device_id":"mac-a","payload":{"summary":"改了 README","files":[]}}'

# 5. 进入审查
curl -X POST $HUB/api/v1/tasks/1/submit-review

# 6. 其他设备/agent 投票（可在 Mac B 上执行）
curl -X POST $HUB/api/v1/tasks/1/reviews -H "Content-Type: application/json" \
  -d '{"reviewer_agent_id":"agent-2","status":"approved"}'

# 7. 是否允许合并
curl $HUB/api/v1/tasks/1/merge-ready
```

`merge_ready: true` 且 `status: Approved` 时，表示审查闸门通过，可去 GitHub 开 PR / merge（Hub 暂不自动推 GitHub）。

---

## 自动化自测

```bash
./scripts/smoke-test.sh          # 基础 API
./scripts/e2e-four-agents.sh     # 四端全流程（需 Hub 已启动）
./scripts/run-e2e-local.sh       # 自动启 Hub + e2e
```

---

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/orchestrate/dispatch` | **手机下命令**：建任务 + 派活 + 设审查者 |
| GET | `/api/v1/orchestrate/tasks/{id}/status` | **结果反馈**：人类可读 status / merge_ready |
| GET | `/api/v1/orchestrate/connectivity` | **联通性检查**（手机端） |
| GET | `/api/v1/devices/connectivity` | 全部设备在线联通性报告 |
| GET | `/api/v1/devices/{id}/connectivity` | 单台设备联通状态 |
| POST | `/api/v1/devices/register` | 注册或更新设备 |
| POST | `/api/v1/devices/{device_id}/heartbeat` | 心跳 |
| GET | `/api/v1/devices` | 设备列表（`?online_only=true`） |
| POST | `/api/v1/projects` | 绑定 GitHub 仓库 |
| POST | `/api/v1/tasks` | 创建任务 |
| POST | `/api/v1/tasks/{id}/assign` | 派发到设备+agent |
| POST | `/api/v1/tasks/{id}/manifest` | 提交变更清单 |
| POST | `/api/v1/tasks/{id}/submit-review` | 进入审查 |
| POST | `/api/v1/tasks/{id}/reviews` | 审查投票 |
| GET | `/api/v1/tasks/{id}/merge-ready` | 是否可合并 |

审查者 ID 建议用 **`设备:agent`** 格式，例如 `win-pc:cursor`，避免两台机器上的 `cursor` 重名。

任务状态：`Planned` → `Assigned` → `Working` → `ReviewPending` → `Reviewing` → `Approved` → `Merged`（驳回走 `ChangesRequested`）。

---

## 飞书接入（派活 + Cursor/Trae 回复回群）

本机 `.env` 配置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`；开放平台启用 **长连接** + `im.message.receive_v1`。

```bash
# 终端 1
cd hub && ./run.sh
# 终端 2
cd hub && python3 scripts/feishu-bridge.py
```

**群里指令**：`项目` · `选 智盈` · `当前项目` · `派活 任务名 | feature/分支` · `状态 3` · `联通` · `选配 off win-pc trae` · `@联合器 任务名`

**项目选择（卡片）**：

1. `.env` 配置飞书凭证；`config/local.env` 配置 `UNIFIER_WORKSPACE_ROOTS`（见仓库根 `INSTALL.md`）
2. 可选 `GITHUB_TOKEN` 拉取 GitHub 账号下仓库，与本地扫描结果合并
3. 群里发 **`项目`** → Bot 回复**项目选择卡片**（智盈、联合器等）
4. **点击卡片按钮**选择项目（需额外启动卡片回调桥，见下）
5. 选中后直接 `@机器人 任务标题` 即派到对应 GitHub 仓库

文字备选（无需卡片回调）：`选 项目名` · `选 3` · `选 owner/repo`

```bash
# 一键启动 Hub + 飞书桥（Hub 所在机器）
cd hub && ./scripts/start-services.sh
```

**选配（哪台设备的 cursor/trae 参与）**：

```bash
./scripts/set-agent-slot.sh list
./scripts/set-agent-slot.sh win-pc trae off          # 完全不参与
./scripts/set-agent-slot.sh mac-a trae review off    # 只做执行，不审查
./scripts/set-agent-slot.sh win-pc cursor implement on
```

飞书群里也可发：`选配` · `选配 off win-pc trae` · `选配 执行 off mac-a trae`

**AI 回复回飞书**（自动）：

- **Cursor**：已配置 `.cursor/hooks.json`，每轮 Agent 结束自动推送（读 `transcript_path`）
- **Trae**：运行 `./scripts/start-auto-reply-push.sh` 监听 transcript
- 前提：`~/.unifier/active-task.json` 存在（Device Agent 收到 inbox 任务时自动写入）

手动兜底：

```bash
./scripts/submit-agent-reply.sh 3 mac-a cursor "Cursor 的回复内容..."
```

环境变量：`UNIFIER_AUTO_PUSH=1`（默认开）· `UNIFIER_PUSH_MIN_CHARS=80` · `UNIFIER_DEVICE_ID` / `UNIFIER_AGENT_ID`

manifest / 审查 / 全票通过也会自动推送到群。

### MCP（Cursor / Trae 自动调用）

在 Cursor（或支持 MCP 的 Trae）中配置后，AI 可直接调 Hub，无需手工脚本。

1. 复制 [`config/mcp.cursor.example.json`](../config/mcp.cursor.example.json) 到 Cursor 的 MCP 配置（设置 → MCP，或项目 `.cursor/mcp.json`）
2. 把 `command` 改成你本机 `hub/scripts/run-mcp.sh` 的**绝对路径**
3. 按机器修改 `env`：
   - Mac Cursor：`UNIFIER_DEVICE_ID=mac-a`，`UNIFIER_AGENT_ID=cursor`
   - Win Trae：`UNIFIER_DEVICE_ID=win-pc`，`UNIFIER_AGENT_ID=trae`，`HUB_URL=http://<Mac-IP>:8787`

```bash
# 本地试跑（stdio，配置正确时 Cursor 会自动拉起）
cd hub && UNIFIER_DEVICE_ID=mac-a UNIFIER_AGENT_ID=cursor ./scripts/run-mcp.sh
```

**常用 MCP 工具**：`unifier_get_my_inbox` · `unifier_submit_manifest` · `unifier_submit_agent_reply`（回复发飞书）· `unifier_submit_review_vote` · `unifier_get_task_status` · `unifier_list_agent_slots`

---

## 目录结构

```text
hub/
├── app/              # FastAPI 应用
├── data/             # SQLite（gitignore）
├── scripts/
│   ├── device-agent.py       # Device Agent 轮询 + HANDOFF
│   ├── dispatch-command.sh   # 模拟手机下命令
│   ├── feishu-bridge.py      # 飞书长连接 → Hub
│   ├── run-mcp.sh            # MCP Server（Cursor/Trae）
│   ├── submit-agent-reply.sh # Cursor/Trae 回复 → 飞书
│   ├── start-workstation.sh  # 注册 + 心跳 + Agent
│   ├── e2e-four-agents.sh    # 四端联调
│   └── run-e2e-local.sh      # 一键本机验证
├── run.sh
└── requirements.txt
```

**仍待接入**：GitHub Webhook → 飞书通知。
