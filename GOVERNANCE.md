# 项目治理 · Governance

## 目标

**联合器**是公开源码的协作编排工具，但采用 **Single Upstream（单一上游）** 治理：

- 所有人看同一份代码、向 **同一个官方仓库** 贡献
- **不**鼓励各自 Fork 成独立产品线长期分叉

这与「随便 Fork 改 MIT 项目」不同；详见 [LICENSE](LICENSE) 中的 **Unifier Community License 1.0**。

---

## 官方仓库

| 项 | 值 |
|----|-----|
| 唯一上游 | https://github.com/L-bit1/unifier |
| 默认分支 | `master` |
| 许可证 | Unifier Community License 1.0 |

---

## 角色

| 角色 | 权限 | 说明 |
|------|------|------|
| **访客** | 读代码、提 Issue | 任何人 |
| **贡献者** | Fork → PR | 合并后进入贡献者列表 |
| **Collaborator** | 官方仓写权限 | 由维护者邀请，仍推荐 PR |
| **维护者** | 合并 PR、发版 | 仓库 Owner / 核心维护者 |

---

## 决策方式

1. **小改动**（文档、bugfix）：PR Review 通过即可合并  
2. **架构 / 破坏性变更**：先开 Issue 讨论，达成共识再 PR  
3. **产品方向**长期记录于 `docs/decisions/YYYY-MM-DD-主题.md`

---

## 关于 Fork

GitHub **公开仓库无法关闭 Fork 功能**（平台限制）。因此：

- **许可证**禁止将 Fork 作为独立项目长期对外运营  
- **流程上**要求改进回流官方仓库 PR  
- Fork 的合理用途：**临时开发 → 提 PR → 合并后可删 Fork**

---

## 发版（草案）

- 标签：`v0.2.0` 形式  
- `master` 保持可部署；重大变更写 CHANGELOG（待建）

---

## 联系

- Bug / 功能： [GitHub Issues](https://github.com/L-bit1/unifier/issues)  
- 维护者：QQ `2781227205` · 微信 `DT-13lw`（Collaborator 申请、商业授权、安全漏洞私信，勿公开贴密钥）
