# 决策与对话记录（`docs/decisions/`）

本目录存放**带日期的讨论结论**，作为联合器产品演进的「任务/决策文档」。与飞书聊天记录互补：这里写**已拍板、可执行**的要点，便于跨设备、跨 IDE 对齐。

## 命名约定

```text
YYYY-MM-DD-简短主题.md
```

示例：`2026-05-19-initial-product-vision.md`

同一天多轮可追加后缀：`2026-05-19-initial-product-vision-2.md`，或在同一文件末尾增加「## 追加（HH:MM）」小节。

## 每条记录建议包含

1. **日期与时间**（对话发生时间）
2. **参与者 / 场景**（可选：飞书群、Cursor、Trae）
3. **背景** — 要解决什么
4. **本次决定** — 条目列表，写清「做什么 / 不做什么」
5. **待办 / 未决** — 下一轮再定的事项
6. **关联** — 改动了哪些文件、分支或 GitHub 仓库（若有）

## 索引

| 日期 | 文件 | 摘要 |
|------|------|------|
| 2026-06-18 | [2026-06-18-n8n-automation-integration.md](2026-06-18-n8n-automation-integration.md) | n8n Sidecar 套件、Hub 事件出站、NAS 式套件总览 API |
| 2026-06-09 | [2026-06-09-community-license-single-upstream.md](2026-06-09-community-license-single-upstream.md) | 共同维护许可证、禁止独立 Fork 产品、CONTRIBUTING/GOVERNANCE |
| 2026-06-09 | [2026-06-09-standalone-github-release.md](2026-06-09-standalone-github-release.md) | 独立仓库发布、配置分层 |
| 2026-05-19 | [2026-05-19-initial-product-vision.md](2026-05-19-initial-product-vision.md) | 产品愿景、四能力、非 GitHub 边界、文档与规则约定 |

## 与 AI 的协作

在**联合器**仓库内对话结束时，AI 应：

1. 用几句话归纳本次**已决定**与**仍开放**的内容；
2. 询问：「是否需要同步到 `docs/decisions/` 任务文档？」；
3. 若你确认，则新建或更新对应日期的 markdown 文件，并更新上表索引。

人工也可直接在飞书拍板后，让 AI「把刚才的结论写入 decisions」。
