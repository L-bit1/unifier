# 联合器 · 安装与部署

联合器是**独立开源协作编排工具**，他人克隆本仓库即可使用，无需你的个人目录或业务仓。

---

## 你需要准备

| 项 | 说明 |
|----|------|
| Python 3.11+ | Hub 与 Agent |
| 飞书自建应用 | 机器人、长连接事件 + 卡片回调 |
| GitHub 账号（可选） | `GITHUB_TOKEN` 拉取仓库列表 |
| 1～N 台开发机 | Mac / Windows，跑 Cursor 或 Trae |

---

## 快速开始（新成员）

```bash
git clone <本仓库 URL> unifier
cd unifier
./scripts/setup.sh
```

然后编辑：

1. **`hub/.env`** — 飞书 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（勿提交）
2. **`config/local.env`** — 本机路径与设备名（勿提交，从 `config/local.env.example` 复制）

### 配置说明

```env
# config/local.env 示例
UNIFIER_WORKSPACE_ROOTS=/path/to/your/git-projects
UNIFIER_EXPECTED_DEVICES=alice-mac,bob-win
UNIFIER_DEVICE_ID=alice-mac
UNIFIER_AGENT_ID=cursor
FEISHU_DEFAULT_IMPLEMENTER_DEVICE=alice-mac
FEISHU_DEFAULT_REVIEWERS=bob-win:cursor,bob-win:trae,alice-mac:trae
```

- **`UNIFIER_WORKSPACE_ROOTS`**：飞书发「项目」时扫描的本地目录（其下每个含 `.git` 的子文件夹 → 一个可选项目）
- **`UNIFIER_DEVICE_ID`**：每台机器唯一，用于注册与派活
- **密钥只在 `hub/.env`**，个人路径只在 `config/local.env`

---

## 启动服务（Hub 所在机器，通常是 Mac）

```bash
cd hub
./scripts/start-services.sh
```

会启动：

- Hub API（8787）
- 飞书消息桥
- 飞书卡片回调桥

### 飞书开放平台（一次性）

1. **事件配置** → 长连接 → `im.message.receive_v1`
2. **回调配置** → 长连接 → `card.action.trigger`
3. 保存前需先运行 `start-services.sh`（建立长连接）

---

## 各开发机接入

```bash
cd hub
export HUB_URL=http://<Hub机器IP>:8787
export DEVICE_ID=your-device-name    # 每台唯一
export AGENT_ID=cursor               # 或 trae
./scripts/start-workstation.sh
```

Windows 用 Git Bash 或 WSL，同样命令。

首次会自动 `register-device` 并启动心跳 + Device Agent。

---

## 飞书群里怎么用

```text
项目              → 项目选择卡片
选 my-app         → 文字选择项目
当前项目          → 查看已选仓库
修复登录页        → 派活到已选项目
派活 xxx | feature/yyy
状态 1
联通
```

---

## 目录与「个人配置」分离

```text
unifier/                    ← 可公开分享的代码
├── INSTALL.md              ← 本文件
├── config/
│   ├── local.env.example   ← 模板（提交）
│   └── local.env           ← 你的路径/设备（不提交）
├── hub/
│   ├── .env.example
│   └── .env                ← 飞书密钥（不提交）
└── docs/decisions/         ← 产品决策（可选）
```

**原则**：仓库内不含任何人自己的 `工作/软件` 路径；每人用 `config/local.env` 覆盖。

---

## MCP（Cursor / Trae）

复制并修改：

- `config/mcp.cursor.example.json` → Cursor MCP 配置
- `config/mcp.trae.example.json` → Trae MCP 配置

设置 `HUB_URL`、`UNIFIER_DEVICE_ID`、`UNIFIER_AGENT_ID` 为本机值。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| `Address already in use` | Hub 已在跑；`lsof -i :8787` 查看 |
| 飞书无回复 | 检查 `feishu-bridge.py` 是否在跑、应用是否在群内 |
| 卡片按钮无效 | 检查 `feishu-card-bridge.py` + 开放平台卡片回调 |
| 派活进错仓库 | 先发「项目」或「选 xxx」 |
| 项目列表为空 | 配置 `UNIFIER_WORKSPACE_ROOTS` 或 `GITHUB_TOKEN` |

---

## 与业务仓库的关系

联合器**不存放业务代码**。它只编排：

飞书指令 → Hub 任务 → 各机 Cursor/Trae → GitHub 分支/PR

你的业务仓（如 `my-app`、`my-saas`）只需正常 Git 托管；在联合器里通过「项目」绑定 `owner/repo` 即可。
