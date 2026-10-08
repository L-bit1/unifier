# Unifier × DeepSeek Harness 插件

将 **联合器 Hub** 注册为 DSH 工具，使 Harness 里的 Agent 能派活、查收件箱、并把回复 **推回飞书**。

> GitHub topic：`dsh-plugin`（生态发现用，勿向 deepseek-harness 官方仓提合并 PR）

## 手机怎么用（重要）

插件**不会**在手机上跑 DSH 本体（DSH 默认只监听 `127.0.0.1:3080`）。手机有两条正路：

### 方式 A — 飞书遥控（推荐，与联合器一致）

```text
手机飞书 @联合器 → 派活 / 查状态
        ↓
Unifier Hub (:8787)
        ↓
家里 Mac/Win 上：dsh web + 本插件
        ↓
DSH 调用 unifier_dispatch_task / inbox / …
        ↓
unifier_submit_agent_reply → 飞书群（手机收到）
```

**这是「手机用 DSH 能力」的主路径**：你在手机上指挥，编码在电脑上跑，结果回飞书。

### 方式 B — 手机直接开 DSH 网页（可选）

电脑先开 DSH，再用 **Tailscale** 安全暴露（勿把 3080 裸绑公网）：

```bash
# 电脑
export DSH_TRUSTED_HOST=my-mac.tailnet-name.ts.net
./scripts/run-dsh-with-unifier.sh

# 另开终端（Tailscale）
tailscale serve --https=443 127.0.0.1:3080
```

手机：Tailscale VPN 打开后，浏览器访问 `https://my-mac.tailnet-name.ts.net`，或社区客户端 [DSH-Mobile](https://github.com/SimonMedy/DSH-Mobile)。

详见 [MOBILE.md](./MOBILE.md)。

## 快速开始

### 1. 启动 Hub

```bash
cd hub && ./scripts/run-hub.sh   # 或你现有方式，默认 :8787
```

### 2. 启动 DSH + 插件

```bash
export UNIFIER_DEVICE_ID=mac-a
export UNIFIER_AGENT_ID=dsh
./scripts/run-dsh-with-unifier.sh
```

浏览器 `http://127.0.0.1:3080`，对 Agent 说：

> 用 unifier_hub_health 检查联合器，再派一个任务「测试 DSH 插件」。

### 3. 手动 patch（已有 deepseek-harness 源码时）

```bash
cd integrations/dsh-plugin
UNIFIER_HUB_URL=http://127.0.0.1:8787 npm run print-patch
# 在 harness 仓库根目录：
pnpm dsh web --patch /abs/path/to/unifier/integrations/dsh-plugin/unifier.cordis.yml
```

## 工具列表

| 工具 | 作用 |
|------|------|
| `unifier_hub_health` | Hub 健康检查 |
| `unifier_whoami` | 当前 device/agent |
| `unifier_dispatch_task` | 派活（同飞书） |
| `unifier_get_my_inbox` | 收件箱 |
| `unifier_get_task_status` | 任务状态 |
| `unifier_check_merge_ready` | 审查是否全票 |
| `unifier_submit_agent_reply` | **回复并推飞书（手机可见）** |

## 环境变量

| 变量 | 默认 |
|------|------|
| `UNIFIER_HUB_URL` / `HUB_URL` | `http://127.0.0.1:8787` |
| `UNIFIER_DEVICE_ID` | （必填，收件箱路由） |
| `UNIFIER_AGENT_ID` | `dsh` |
| `DSH_TRUSTED_HOST` | 手机远程访问时传给 `dsh web --trusted-host` |

## 许可证

插件适配层随联合器仓库 [Unifier Community License](../../LICENSE)。DeepSeek Harness 为 MIT。
