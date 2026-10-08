# 2026-08-28 · 手机遥控体验：挑最痛的打

## 原则

完善，但不是全都要做。三项缺口对应从玩具→工具的三道坎；按痛感排优先级。

## 优先级

| 优先级 | 做什么 | 做到什么程度算赢 | 不做 | 状态 |
|--------|--------|------------------|------|------|
| **P0** | 飞书状态推送（任务通知流） | 收件确认 / 完成摘要 / 审查等待 / 失败熔断，各推一条 | 不做实时聊天流 | ✅ |
| **P1** | 手机确认执行（半自动） | 卡片点「确认」→ 唤醒本机执行；点「稍后」进队列 | 不做无人值守全自动 | ✅ |
| **P2** | 里程碑进度（简化版） | 读代码 / 改文件 / 测试 / commit 阶段点 | 不做 CoT 流式 | ✅ API |
| **P3** | 全自动无人值守 | **现阶段不下表** | 视为毒药，等企业定制 | ❌ 不做 |

## P0 通知文案（任务通知流）

通道：**飞书 + 联合器 App 同源**（落库 `agent_replies`，App 轮询 `/mobile/updates`）。

- ✅ 已收到，正在唤醒 Cursor/Trae…
- ✅ 已完成。摘要：改了什么
- ⏳ 等待审查（可含已等待时长；`UNIFIER_REVIEW_NUDGE_MINUTES` 默认 3）
- ❌ 任务异常已熔断/回滚，附原因

## 实现落点（2026-08-28）

- P0：`event_bus` → `notify_lifecycle`；审查催促在 `inbox-auto-runner.poll_review_nudge`
- P1：`exec_confirm` + App「确认执行/稍后」按钮 + 飞书卡片 `confirm_exec`/`defer_exec`；默认 `UNIFIER_CONFIRM_EXEC=1`
- P2：`POST /api/v1/tasks/{id}/milestones`（context|edit|test|commit|review|done）
- 验收：`hub/scripts/e2e-decision-smoke.sh`

## 一句话

> 飞书推送是吃饭家伙（P0）；手机确认执行是体验飞跃（P1）；实时流式缓做；完全无人值守别碰。
