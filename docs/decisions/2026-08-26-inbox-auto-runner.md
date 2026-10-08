# 2026-08-26 · Inbox Auto-Runner（手机遥控闭环）

## 背景

用户目标：手机飞书交代任务给 Cursor / Trae / DSH，电脑自己执行，完成后回飞书。  
已有 `device-agent.py`（单 Agent 写 HANDOFF），缺「多端常驻 + 唤醒 + 飞书送达确认 + DSH 队列」。

## 本次决定

1. 新增 `hub/scripts/inbox-auto-runner.py` + `run-inbox-auto.sh`
2. 默认轮询 `cursor,trae,dsh`；新任务写 HANDOFF、`wake-{agent}.md`、macOS 通知
3. 默认飞书 ack「电脑已收到」；完成后仍靠 Hook / outbox / `submit-agent-reply`
4. `dsh` 额外写 `~/.unifier/dsh-queue/LATEST.md` 提示词（配合 DSH 插件）
5. 可选 `UNIFIER_ON_INBOX_HOOK` 自定义唤醒（如打开 HANDOFF）
6. **不做**：完全遥控 Cursor GUI；不做公网裸暴露 DSH

## 待办

- [x] 半自动确认门：`UNIFIER_CONFIRM_EXEC`（默认开）→ 手机/飞书确认后再 dispatch
- [x] 审查催促：`poll_review_nudge`（`UNIFIER_REVIEW_NUDGE_MINUTES`）
- [x] 可选：DSH 自动打开 LATEST（`UNIFIER_DSH_AUTO_OPEN=1`，macOS `open`）
- [ ] 真机完整闭环：App/飞书派活 → 确认执行 → Cursor 执行 → 摘要回气泡（人工抽测）

## 关联

- `hub/scripts/inbox-auto-runner.py`
- `hub/scripts/run-inbox-auto.sh`
- `hub/scripts/e2e-decision-smoke.sh`
- `integrations/dsh-plugin/MOBILE.md`
