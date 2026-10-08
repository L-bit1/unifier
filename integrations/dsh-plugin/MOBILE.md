# DSH / 手机遥控指南（联合器）

## 你要的体验

> 手机飞书交代任务 → 电脑 Cursor / Trae / DSH 自己干 → 干完回飞书。

## 电脑常驻（一条命令）

```bash
# Hub 已启动的前提下
cd 联合器/hub
export HUB_URL=http://127.0.0.1:8787
export DEVICE_ID=mac-a
export INBOX_AUTO_AGENTS=cursor,trae,dsh
./scripts/run-inbox-auto.sh
```

收到任务后会：

1. 写 `~/.unifier/inbox/*.md`（HANDOFF）
2. 写 `~/.unifier/wake/wake-{agent}.md` + macOS 通知
3. 飞书推一条「电脑已收到」
4. 若 agent=`dsh`：写 `~/.unifier/dsh-queue/LATEST.md`（给 DSH 的提示词）
5. 监听 `~/.unifier/outbox/` → 自动推飞书结果

Cursor / Trae：打开 HANDOFF 执行；Hook / outbox 回飞书。  
DSH：起 `../scripts/run-dsh-with-unifier.sh`，对 Agent 说「按 ~/.unifier/dsh-queue/LATEST.md 执行」。

可选：`export UNIFIER_ON_INBOX_HOOK="$(pwd)/scripts/hooks/open-handoff.sh"` 自动打开 HANDOFF。

---

## 方式 A — 飞书遥控（主路径）

```text
手机飞书 派活
    → Hub
    → Inbox Auto-Runner（本机）
    → Cursor / Trae / DSH
    → submit_agent_reply / outbox
    → 飞书（手机看结果）
```

### 验收

- [ ] 飞书派活后，手机很快收到「电脑已收到」
- [ ] `~/.unifier/inbox/` 出现新 HANDOFF
- [ ] 执行完 outbox 或 submit-agent-reply 后飞书有结果摘要

---

## 方式 B — 手机直接开 DSH 网页（可选）

日常不必用。电脑先开 DSH，再用 Tailscale：

```bash
export DSH_TRUSTED_HOST=my-mac.tailnet-name.ts.net
# 在联合器仓库根
./scripts/run-dsh-with-unifier.sh
tailscale serve --https=443 127.0.0.1:3080
```

手机开 Tailscale VPN → 浏览器访问该 HTTPS。社区壳：[DSH-Mobile](https://github.com/SimonMedy/DSH-Mobile)。  
**勿**把 `dsh web` 裸绑公网。

---

## 与 MCP / 插件关系

| 入口 | 场景 |
|------|------|
| 飞书 Bot | 手机下指令 |
| Inbox Auto-Runner | 电脑收件与唤醒 |
| Cursor MCP `unifier_*` | IDE 内执行 |
| DSH 插件 `unifier_*` | Harness 内执行 |
