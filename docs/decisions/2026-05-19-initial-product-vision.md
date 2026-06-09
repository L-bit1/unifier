# 决策记录：联合器产品愿景与文档体系

- **日期**：2026-05-19
- **场景**：Cursor 对话（联合器仓库）
- **状态**：已写入 README；规则待本机生效

---

## 背景

- 厘清「联合器」目录现状：原为飞书 + 多设备 Cursor/Trae + Git 的**协作编排说明**，非业务应用。
- 用户希望演进为**可落地的软件**，但不成为第二个 GitHub；需明确四方面能力与多 Agent 互审流程。

---

## 本次决定

### 1. 产品定位

- 联合器 = **协作控制面**（飞书指挥 + 设备/Agent 编排 + 审查闸门 + 审计），**不是**代码托管平台。
- **GitHub** 继续作为代码与历史的唯一事实源；联合器在 merge/push 前增加「全票审查通过」等闸门。
- **飞书**：选项目、派活、通知、可选人工终审。
- **设备 Agent**（规划中）：各台 Mac/Win 注册在线，接收任务，上报状态；v1 可先半自动（人开 IDE + Agent 上报 manifest）。

### 2. 四项核心能力（与 README 对齐）

| # | 能力 | 要点 |
|---|------|------|
| 1 | 飞书连接 | 机器人/卡片/群与仓库绑定 |
| 2 | 多人协作 + 仓库 | 会话绑定 GitHub repo；参与者含多设备上的 Agent |
| 3 | 连接设备 | Hub ↔ Device Agent；各司其职 |
| 4 | 多 Agent 互审 | 例：4 Agent；先审后合并；每次提交附 **ChangeManifest**（时间、摘要、文件与修改说明） |

### 3. 审查流程（概念状态机）

`Planned` → `Assigned` → `Working` → `ReviewPending` → `Reviewing` → `Approved` → `Merged`；驳回则 `ChangesRequested` 后重做。

- 实现上优先：**feature 分支隔离** + 审查状态由 Hub 记录；可选后续「先审 patch 再 push」。
- 建议区分：**N 个 AI 全票** vs **是否增加真人一票否决**（未最终选定，见待办）。

### 4. 文档与仓库约定（本次新增）

- 更新根目录 **`README.md`**：写入上述愿景、边界、目录结构、路线图草案。
- 新建 **`docs/decisions/`**：按 `YYYY-MM-DD-主题.md` 记录每轮对话结论；本文件为第一条。
- 提供 **ChangeManifest 示例模板**：`docs/decisions/templates/change-manifest.example.yaml`。
- **Cursor 规则**：对话结束前询问是否同步到 `docs/decisions/`（见 `.cursor/rules/session-decisions-sync.mdc`）。

### 5. 分阶段路线（草案，未排期）

1. 现在：文档 + 手工流程  
2. MVP：飞书 Bot + 简易 Hub + GitHub 绑定  
3. v0.2：Device Agent + 审查状态机 + merge 闸门  
4. v0.3+：多角色 Agent、自动审查摘要、审计周报  

---

## 待办 / 未决

- [ ] Hub 技术选型（自建服务 / 语言 / 部署）未讨论。
- [ ] 「4 个 AI 全票」是否包含 1 个真人必审 — 待团队约定。
- [ ] Cursor/Trae 深度集成方式（CLI / 脚本 / 仅 HANDOFF 投递）待 MVP 时验证。
- [ ] 上级仓 `HANDOFF.md`、`AI协作记录.md` 与联合器 `docs/decisions/` 的同步关系待业务仓对齐。
- [ ] `scripts/`、`feishu-bot/` 尚未创建，实现未启动。

---

## 本次变更的文件

- `README.md` — 重写/扩充产品说明
- `docs/decisions/README.md` — 目录说明与索引
- `docs/decisions/2026-05-19-initial-product-vision.md` — 本文件
- `docs/decisions/templates/change-manifest.example.yaml` — 变更清单模板
- `.cursor/rules/session-decisions-sync.mdc` — 对话结束同步询问规则
- `.cursor/rules/collaboration-git.mdc` — 补充 decisions 与 README 引用
