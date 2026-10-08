# 2026-08-26 · 护城河优先级（修订版）

## 完整优先级表

| 优先级 | 做什么 | 为什么 |
|--------|--------|--------|
| **P0** | ChangeManifest 意图记忆 + `/api/v1/audit/manifests` | 数据护城河，成本低 ✅ |
| **P0** | ChannelAdapter（飞书首实现） | 多 IM 皮肤，不绑死飞书 ✅ |
| **P0.5** | **ExecutorAdapter**（Cursor/Trae/DSH 统一协议） | 避免被 IDE 厂商锁死 ✅ 骨架 |
| **P0.5** | **ExecutionSupervisor** 超时熔断 + git 回滚 + 飞书告警 | 执行卡死是信任基石 ✅ 骨架 |
| **P1** | Web 控制台 v1（GitHub PR 风格 + CoT 折叠块） | 黑匣子阅读器，非第二个 Jira |
| **P1** | 双 Agent manifest diff 报告 | 中立第三方标签 |
| **P1.5** | **unifier-doctor / health-check** 零信任自检 | 冷启动失败则 P0 全白费 ✅ |
| **P2** | 飞书 OA 审批单对接 | ToB 收钱，定制向 |
| **P3** | 内网离线通道、语义补丁边界 | 政企单再做 |

## Web 控制台 v1 原则

- **复刻 GitHub PR 界面**：Commits → Agent 思维链（CoT）折叠块
- 不做复杂 Kanban / 第二个 Jira
- 心智定位：**GitHub AI 审查插件**，不是项目管理工具

## 已实现（2026-08-26）

### ExecutorAdapter

```
hub/app/executors/
  base.py       ExecutorAdapter
  handoff.py    HandoffExecutor(cursor/trae) + DshQueueExecutor
  registry.py   get_executor() · 未知 agent 自动 Handoff 回退
```

`GET /api/v1/executors` 列出已注册执行器。

### ExecutionSupervisor

- 环境变量：`UNIFIER_EXEC_TIMEOUT_SECONDS`（默认 300）
- `UNIFIER_EXEC_ROLLBACK=1` → 超时 `git checkout -- .` + `git clean -fd`
- `POST /api/v1/tasks/{id}/execution-abort` → ChangesRequested + 飞书推送
- `inbox-auto-runner.py` 集成 supervisor

### Health Check

```bash
./scripts/health-check.sh
# 或 cd hub && python3 scripts/unifier-doctor.py
```

检查：Python≥3.11、端口占用、venv、.env、Hub /health。

## 待办

- [x] ~~Web 控制台 static/audit.html（PR 风格）~~ ✅ `/audit`
- [x] 向量检索替代关键词 audit（轻量 bag-of-words + cosine，`vector_search.py`）
- [x] Continue / OpenCode ExecutorAdapter 插件（`HandoffExecutor` 注册）
- [x] 飞书 OA 审批骨架（`/api/v1/feishu/oa/*`，`implemented=skeleton`）
- [ ] 内网离线通道（P3，政企单再做）
