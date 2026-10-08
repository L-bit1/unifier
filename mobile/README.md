# 联合器 Android App（Capacitor）

手机遥控 Hub：**派活 · 查任务 · 设备联通 · 意图审计**  
与飞书并列的 **Channel 皮肤**（不替代飞书，适合不想开飞书时快速派活）。

## 能力

| Tab | 功能 |
|-----|------|
| 派活 | `POST /api/v1/orchestrate/dispatch` |
| 任务 | 任务列表与状态 |
| 联通 | 设备在线检查 |
| 审计 | 意图记忆搜索 |

## 前置条件

1. 电脑已启动 Hub：`cd hub && ./scripts/start-services.sh`
2. 电脑已启动 Inbox Auto-Runner：`./scripts/run-inbox-auto.sh`
3. **手机与电脑同一 WiFi**
4. Hub 需监听局域网（默认 `UNIFIER_HOST=0.0.0.0`）

## 开发 / 打 APK

> **重要**：仓库在 `Desktop/工作 /软件/` 等中文路径下时，**Android Studio 会乱码崩溃**。  
> 请始终通过英文符号链接打开工程：`~/Projects/unifier-android`

```bash
cd 联合器/mobile
./scripts/open-android-studio.sh   # 自动 sync + 打开 ~/Projects/unifier-android
```

或手动：

```bash
mkdir -p ~/Projects
ln -sfn "/path/to/联合器/mobile/android" ~/Projects/unifier-android
cd mobile && npm install && npm run sync
open -a "Android Studio" ~/Projects/unifier-android
```

Android Studio：**Build → Build APK(s)**  
或命令行（需本机 Android SDK）：

```bash
npm run build:apk
# APK: android/app/build/outputs/apk/debug/app-debug.apk
```

## 首次配置（App 内）

1. 点右上角 ⚙
2. Hub 地址填电脑局域网 IP，例如：`http://192.168.1.10:8787`
3. 保存并检测 → 显示 `ok: true`
4. 填默认仓库 `owner/repo`、默认 `device_id`

## 与飞书的关系

```text
飞书 Bot ──┐
           ├──→ Hub ──→ Inbox Auto-Runner ──→ Cursor/Trae
Android App ┘
```

App **不**直接连 Cursor；只连 Hub，和飞书是同一层入口。

## 技术栈

- Capacitor 6 + 原生 WebView
- `@capacitor/preferences` 存 Hub URL
- 深色 UI，品牌色 #6366F1 / #22D3EE

## 注意

- 纯局域网验收：手机不能填 `127.0.0.1`（那是手机自己）
- 公网暴露 Hub 需自行加 VPN（Tailscale）或 HTTPS，勿裸奔公网
- 企业版远程 Hub：填企业 `https://unifier.company.com:8787`
