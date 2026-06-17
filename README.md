# 联合器 · Unifier

> **像胶水一样，把工具与工具粘在一起** —— 飞书、GitHub、Cursor、Trae 不再各干各的，而是一条可指挥、可审查、可留痕的协作流水线。

[![License: Unifier Community](https://img.shields.io/badge/License-Unifier%20Community-2563eb.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](hub/requirements.txt)
[![FastAPI](https://img.shields.io/badge/FastAPI-Hub-009688.svg)](hub/README.md)

**Unifier** glues your stack together: command from **Feishu (Lark)** on your phone, orchestrate via a local **Hub**, execute on **Cursor / Trae** across Mac & Windows, and keep code truth on **GitHub**.

**维护者联系 · Maintainer**

| | |
|--|--|
| QQ | `2781227205` |
| 微信 WeChat | `DT-13lw` |

合作、Collaborator 申请、商业授权或安全问题，可通过以上方式联系；代码问题请优先 [GitHub Issues](https://github.com/L-bit1/unifier/issues)。

---

## 为什么需要联合器？

你已经有飞书、GitHub、Cursor、Trae —— 但它们之间缺一层**编排**：

| 没有联合器 | 有联合器 |
|-----------|---------|
| 飞书里讨论一堆，代码仓里没有结论 | 飞书下指令 → Hub 派活 → 各端 AI 执行 |
| 多台电脑、多个 IDE 各自改代码 | 设备注册在线，按角色分配执行 / 审查 |
| 多个 AI 改完就 merge，风险大 | **审查闸门**：全票通过才允许合并 |
| 事后说不清谁改了什么 | 每次提交附带 **ChangeManifest**，可审计 |

联合器**不是**第二个 GitHub。代码与历史仍在 Git；联合器只做**协作控制面**和**人机入口**。

---

## 连接了什么？

```text
        ┌─────────────┐
        │  飞书 / 手机  │  下指令、选项目、看状态、收 AI 回复
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │  Unifier Hub │  任务状态机 · 多 Agent 审查 · 设备在线
        └──────┬──────┘
               │
     ┌─────────┼─────────┐
     │         │         │
┌────▼───┐ ┌───▼───┐ ┌───▼────┐
│ Mac    │ │ Win   │ │ GitHub │  分支 · PR · 代码真相
│ Cursor │ │ Trae  │ │  repos │
│ Trae   │ │ Cursor│ └────────┘
└────────┘ └───────┘
```

**胶水粘住的环节：**

- **飞书** ↔ Hub：派活、项目卡片、联通检查、AI 回复推送
- **Hub** ↔ 各机 Agent：收件箱 HANDOFF、心跳、manifest、审查投票
- **Hub** ↔ GitHub：项目绑定 `owner/repo`（本地工作区自动扫描 + 可选 API）
- **Cursor / Trae** ↔ Hub：MCP 工具、Hooks 自动回传对话摘要到飞书

---

## 快速开始

### 1. 克隆 & 安装

```bash
git clone https://github.com/L-bit1/unifier.git
cd unifier
./scripts/setup.sh
```

### 2. 配置（各填各的，勿提交 Git）

| 文件 | 内容 |
|------|------|
| `hub/.env` | 飞书 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` |
| `config/local.env` | 本地项目目录、设备 ID（从 `config/local.env.example` 复制） |

详细步骤 → **[INSTALL.md](INSTALL.md)**

### 3. 启动（Hub 所在机器，通常是一台常开的 Mac）

```bash
cd hub
./scripts/start-services.sh
```

### 4. 各开发机接入

```bash
export HUB_URL=http://<Hub-IP>:8787
export DEVICE_ID=my-mac          # 每台机器唯一
export AGENT_ID=cursor           # 或 trae
./scripts/start-workstation.sh
```

### 5. 飞书群里

```text
项目              → 扫描 GitHub / 本地仓库，卡片选项目
选 my-app         → 文字选择项目
修复登录超时       → 派活到已选仓库
状态 3            → 查任务进度
联通              → 看哪些设备在线
```

---

## 核心能力

1. **飞书指挥台** — 手机发任务、选项目、收状态与 AI 回复  
2. **多设备协作** — Mac / Win 注册在线，Cursor + Trae 各司其职  
3. **审查闸门** — 多 Agent 全票 `approved` 后才 `merge_ready`  
4. **变更留痕** — ChangeManifest 记录每次 Agent 提交摘要  
5. **项目发现** — 扫描本地 Git 目录 + 可选 GitHub API，飞书卡片一键选择  

---

## 仓库结构

```text
unifier/
├── README.md              ← 你在这里
├── INSTALL.md             ← 部署手册
├── hub/                   ← FastAPI Hub（可运行主体）
│   ├── app/               ← API、飞书、任务状态机
│   ├── scripts/           ← 桥接、Agent、一键启动
│   └── mcp_server/        ← Cursor/Trae MCP 工具
├── config/                ← MCP 示例 + local.env 模板
├── scripts/setup.sh       ← 首次安装
└── docs/decisions/        ← 产品决策记录
```

---

## 技术栈

- **Hub**：Python · FastAPI · SQLite · SQLAlchemy  
- **飞书**：长连接事件 + 卡片回调（`lark-cli` / `lark-oapi`）  
- **Agent**：轻量 Python 轮询 + 本地 `~/.unifier/inbox/` HANDOFF  
- **IDE**：Cursor Hooks · Trae 规则 · MCP  

API 文档：启动 Hub 后访问 `http://127.0.0.1:8787/docs`

---

## 边界说明

| ✅ 做 | ❌ 不做 |
|------|--------|
| 编排飞书 ↔ 多 IDE ↔ GitHub | 替代 Git 托管 |
| 审查状态与 merge 闸门 | 再造完整 Code Review 平台 |
| 设备在线与任务投递 | 完全遥控 IDE 内部 UI |

---

## 路线图

| 版本 | 内容 |
|------|------|
| **v0.2** | Hub + 飞书 Bot + Device Agent + 审查状态机 + 项目卡片 |
| **v0.3**（进行中） | n8n 自动化套件 · Hub 事件出站 · Head 套件总览 API |
| v0.3+ | GitHub Webhook → n8n/飞书 · 审查摘要自动生成 |
| v1 | 可选「先审 patch 再 push」· 审计周报 |

---

## 安全

- 密钥只放本机 `hub/.env`，**永远不要**提交到 Git  
- GitHub PAT 最小权限（repo 只读即可）  
- 飞书应用 scope 与群—仓库按需绑定  

---

## 参与 & 文档

- **共同维护**：请向官方仓库提 PR，勿另立独立 Fork 项目（见 [LICENSE](LICENSE) · [CONTRIBUTING.md](CONTRIBUTING.md) · [GOVERNANCE.md](GOVERNANCE.md)）
- 安装问题 → [INSTALL.md](INSTALL.md)  
- Hub API → [hub/README.md](hub/README.md)  
- 产品决策 → [docs/decisions/](docs/decisions/)  

---

## License

[Unifier Community License 1.0](LICENSE) — 源码公开、共同维护；**官方唯一上游**为 [github.com/L-bit1/unifier](https://github.com/L-bit1/unifier)。  
改进请提 Pull Request，请勿将 Fork 作为独立产品长期分叉发布。
