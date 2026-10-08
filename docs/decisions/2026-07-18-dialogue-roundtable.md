# 圆桌对话（Dialogue Roundtable）

**日期**：2026-07-18  
**状态**：已落地 Hub API + MCP + 共用页 + dialogue-watch  
**范围**：Cursor ↔ Trae 先通；飞书 / Claude Code 后续接入同一 `participant` 座位

## 工作流

1. 用户开题 → 网页 `/dialogue` 或 `POST .../user-message` 或 MCP
2. **dialogue-watch**（常驻）对 `cursor`、`trae` 自动 `poll`；`my_turn` 超过 grace 秒仍无人答 → 自动 `reply`
3. 真 IDE 醒着时可在 grace 窗口内抢先 MCP reply（watch 遇冲突则 skip）
4. 齐员后双方互读；用户追问开新轮或 `end` 落盘 transcript

## 自动 poll（dialogue-watch）

IDE Agent 平时睡着，MCP 规则无法叫醒。补位方案：

```bash
# 前台
bash ~/.unifier/run-dialogue-watch.sh

# 或后台
nohup bash ~/.unifier/run-dialogue-watch.sh > ~/.unifier/dialogue/watch.log 2>&1 &
```

| 变量 | 默认 | 含义 |
|------|------|------|
| `DIALOGUE_WATCH_AGENTS` | `cursor,trae` | 双身份都 poll |
| `DIALOGUE_WATCH_GRACE` | `2` | 给真 IDE 抢答的秒数 |
| `DIALOGUE_WATCH_INTERVAL` | `2` | 轮询间隔 |
| `DIALOGUE_WATCH_USE_SOUL` | `0` | `1` 时走 Hub `/soul/chat` |
| `DIALOGUE_WATCH_NOTIFY` | `1` | macOS 通知 |

Wake 文件：`~/.unifier/dialogue/wake-cursor.md` / `wake-trae.md`

网页「发送后自动代言」仍可用（发完立刻齐员）；不勾时靠 watch 在 ~2s 内代回。

## 茅台试点

| IDE | MCP 示例 | Agent |
|-----|----------|-------|
| Cursor | `茅台抢单软件/.cursor/mcp.json` | `cursor` |
| Trae | `茅台抢单软件/.trae/mcp.json` | `trae` |

1. 启动 Hub：`cd 联合器/hub && ./run.sh`（或 uvicorn :8787）
2. 启动 watch：`bash ~/.unifier/run-dialogue-watch.sh`
3. 打开 http://127.0.0.1:8787/dialogue
4. 冒烟：`./scripts/smoke-dialogue-maotai.sh`

Transcript：`茅台抢单软件/data/unifier-dialogue/room-*.md` 与 `~/.unifier/dialogue/`

## 与 Task 派活关系

圆桌 **独立于** 任务状态机 / 审查合票；旧 MCP inbox 工具保留。
