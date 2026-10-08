# 联合器桌面应用 · 个人版 / 企业版

**日期：** 2026-08-26  
**状态：** 已实现 v0.1 骨架

## 产品划分

| 版本 | 代号 | 能力 | 收费 |
|------|------|------|------|
| **个人版** | A · Personal | 本机 Hub + 飞书桥 + Inbox Auto-Runner；托盘控制 | 免费 |
| **企业版** | B · Enterprise | 仅工作站：连企业 Hub；多机派活/审查 | 付费（License） |

企业版**不**在本机起 Hub（避免与中心 IT 冲突）；个人版**不**需要 License。

## 技术栈

- **Electron** 控制面板 + 系统托盘（Mac / Windows）
- **Python 守护进程** `desktop/runtime/daemon.py` 跨平台拉起 Hub / 收件箱
- 产物目录：`desktop/dist/`（构建输出，不入库）
- 源码：`desktop/`

## 配置位置

| 路径 | 内容 |
|------|------|
| `~/Library/Application Support/Unifier/` (Mac) | `config.json`, `license.json`, `hub.env` |
| `%APPDATA%/Unifier/` (Win) | 同上 |

打包后 `hub/` 在 `resources/unifier-hub`；开发态读仓库 `hub/`。

## License（企业版 v0.1）

- 格式：`UNIFIER-ENT-` + 16 位十六进制（与设备指纹 + 盐校验）
- 激活 UI 写入 `license.json`
- 正式收费可换 Stripe / 自建激活 API（接口预留 `activateLicense`）

## 构建

```bash
cd desktop && npm install && npm run build:mac   # 或 build:win
```

需本机：Node 20+、Python 3.11+（运行时依赖，与 INSTALL.md 一致）。
