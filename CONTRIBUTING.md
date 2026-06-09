# 贡献指南 · Contributing

感谢参与 **联合器（Unifier）**！本项目采用 **共同维护** 模式：代码公开，但**官方唯一上游**是 [github.com/L-bit1/unifier](https://github.com/L-bit1/unifier)。

---

## 我们欢迎什么

- Bug 修复、功能改进、文档与翻译
- 飞书 / Cursor / Trae 集成相关的经验与补丁
- Issue 讨论：先搜是否已有同类问题

## 我们不鼓励什么

- 在 GitHub 上 **Fork 后长期独立维护** 另一套「联合器分支版」而不向官方回馈（见 [LICENSE](LICENSE)）
- 未沟通的大范围重构（请先开 Issue 讨论方向）

> GitHub 公开仓无法关闭 Fork 按钮；请理解：**Fork 用于提 PR 可以，另立门户不行。**

---

## 如何贡献（标准流程）

### 1. 从官方仓库开始

```bash
git clone https://github.com/L-bit1/unifier.git
cd unifier
git checkout -b feat/your-topic
```

若你已有 Fork（仅用于 PR），请 **Sync upstream** 保持与 `L-bit1/unifier` 一致，PR 目标仓库请选择 **L-bit1/unifier** 的 `master`。

### 2. 本地开发与验证

```bash
./scripts/setup.sh
cd hub && ./scripts/run-e2e-local.sh   # 可选：跑通四端流程
```

### 3. 提交 Pull Request

- 目标：**L-bit1/unifier** → `master`
- PR 标题建议：`feat:` / `fix:` / `docs:` 前缀（Conventional Commits）
- 说明：改了什么、为什么、如何验证
- **不要**在 PR 中包含密钥（`.env`、`config/local.env`）

### 4. 代码审查

维护者会 Review；通过后合并。合并后你的 Fork 可删除或仅作同步用。

---

## 配置与密钥

| 文件 | 是否提交 |
|------|----------|
| `hub/.env.example` | ✅ |
| `config/local.env.example` | ✅ |
| `hub/.env` | ❌ 切勿提交 |
| `config/local.env` | ❌ 切勿提交 |

---

## 行为准则

请友好、具体、对事不对人。恶意骚扰、泄露他人密钥的行为将被拒绝合作。

---

## 成为长期维护者

持续高质量 PR 的贡献者，可在 Issue 中申请 **Collaborator** 写权限，直接在官方仓库分支开发（仍建议 PR 合并，便于 Review）。

详见 [GOVERNANCE.md](GOVERNANCE.md)。
