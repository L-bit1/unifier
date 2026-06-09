# 决策记录：联合器独立仓库发布

- **日期**：2026-06-09
- **状态**：已执行

---

## 背景

联合器原与本地「工作/软件」目录、个人设备名、业务仓混在同一上下文。需拆成**可独立克隆部署**的开源仓库，供他人使用。

---

## 本次决定

1. **新 GitHub 仓库**：`L-bit1/unifier`
2. **产品定位**：像胶水一样连接飞书、GitHub、Cursor、Trae，提高多工具协作效率
3. **配置分层**：
   - 可提交：`hub/.env.example`、`config/local.env.example`
   - 不提交：`hub/.env`、`config/local.env`、数据库
4. **入口文档**：根 `README.md`（GitHub 介绍）+ `INSTALL.md`（部署）
5. **许可证**：MIT

---

## 关联文件

- `README.md`、`INSTALL.md`、`LICENSE`
- `config/local.env.example`、`hub/scripts/load-env.sh`
- `.gitignore`
