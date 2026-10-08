# Unifier 桌面应用

个人版（A）与企业版（B）同一安装包，企业版需 License 激活。

## 要求

- Node.js 20+
- Python 3.11+（运行时拉起 Hub / Inbox Auto-Runner）

## 开发运行

```bash
# 推荐：仓库根一键（后台托盘常驻）
./scripts/start-desktop.sh

# 或开发前台
cd desktop
npm install
npm start                 # 个人版：托盘常驻 + 自动起 Hub/收件箱/心跳
npm run start:enterprise  # 强制企业模式 UI
```

菜单栏托盘：

- **关窗不退出**（点托盘「退出」才停）
- **单实例**：重复打开会聚焦已有窗口
- 启动 / 停止 / 重启 Hub + 收件箱 + 心跳
- 开机自启（可选）
- Hub 在线状态（5s 探活）

个人版守护逻辑见 `runtime/daemon.py`：若 `:8787` 已有 Hub 则复用，只补 inbox-auto + heartbeat。

### 让手机在外面也能用

控制面板 / 托盘 → **打开「让手机在外面也能用」** → **复制给手机**。  
手机 App 设置里粘贴全部内容即可（无需同一 Wi‑Fi，也无需再装别的 App）。  
关闭后异网失效；同一 Wi‑Fi / USB 调试仍可用。

## 构建

```bash
npm run build:mac   # dmg + zip
npm run build:win   # nsis 安装包
```

产物在 `desktop/dist/`。

## 版本说明

| 版本 | 行为 |
|------|------|
| **个人版 A** | 本机 Hub (:8787) + 飞书桥 + Inbox Auto-Runner |
| **企业版 B** | 仅工作站：连远程 `HUB_URL`，需 `UNIFIER-ENT-*` License |

配置与 License：`~/Library/Application Support/Unifier/`（见 `docs/superpowers/specs/2026-08-26-unifier-desktop-apps.md`）。

默认 `config.json`：

```json
{ "hubUrl": "http://127.0.0.1:8787", "deviceId": "mac-a", "openAtLogin": false }
```

## 开发用 License 生成

```bash
node -e "const c=require('crypto');const b='ABCD1234';const h=c.createHash('sha256').update('unifier-enterprise-v1'+b).digest('hex').slice(0,8).toUpperCase();console.log('UNIFIER-ENT-'+b+h)"
```

将输出的 Key 填入企业版激活框。
