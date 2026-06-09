---
description: 联合器 Trae — AI 回复自动推送飞书
alwaysApply: true
---

# Trae · 联合器自动回传飞书

## 环境要求

每台 Trae 机器需：

1. 设置 `UNIFIER_DEVICE_ID`、`UNIFIER_AGENT_ID`（如 `win-pc` + `trae`）
2. 运行 Device Agent 或确保 `~/.unifier/active-task.json` 存在（收到 Hub 任务后自动写入）
3. 启动自动推送守护：

```bash
cd hub
export HUB_URL=http://<Mac-Hub-IP>:8787
export UNIFIER_DEVICE_ID=win-pc
export UNIFIER_AGENT_ID=trae
./scripts/start-auto-reply-push.sh
```

## 行为

- `reply-auto-push.py` 监听 Cursor/Trae 对话 transcript
- 每轮 AI 回复结束后，自动 POST 到 Hub → 飞书群
- 与 Cursor Hook 共用去重逻辑（相同内容不重复推送）

## 关闭自动推送

```bash
export UNIFIER_AUTO_PUSH=0
```

## 手动兜底

```bash
hub/scripts/submit-agent-reply.sh <task_id> win-pc trae "回复摘要"
```
