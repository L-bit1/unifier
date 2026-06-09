# 决策记录：共同维护许可证与单一上游

- **日期**：2026-06-09
- **状态**：已执行

---

## 背景

仓库已公开至 `L-bit1/unifier`。希望**开源**供所有人使用与贡献，但不希望被 Fork 成各自独立维护的新项目，而是**大家一起维护官方仓库**。

## 平台限制

GitHub **公开仓库无法关闭 Fork 按钮**（仅组织私有仓可配置 `allow_forking=false`）。无法从技术上 100% 阻止 `git clone` 后推到新仓库。

## 本次决定

1. **许可证**：由 MIT 改为 **Unifier Community License 1.0**
   - 允许使用、部署、向官方仓 PR
   - 禁止另建仓库长期维护独立「分支产品」
2. **流程文档**：新增 `CONTRIBUTING.md`、`GOVERNANCE.md`
3. **README**：明确 Single Upstream 与 PR 贡献方式

## 待办

- [ ] 按需邀请长期贡献者为 Collaborator
- [ ] 可选：迁移至 GitHub Organization 并配置分支保护（PR 必审）

## 关联文件

- `LICENSE`、`CONTRIBUTING.md`、`GOVERNANCE.md`、`README.md`
