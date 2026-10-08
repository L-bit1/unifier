#!/usr/bin/env bash
# 一键启动联合器桌面托盘：Hub + 收件箱 + 心跳常驻（关窗不退出）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="$ROOT/desktop"
LOG_DIR="${HOME}/.unifier/logs"
mkdir -p "$LOG_DIR"

cd "$DESKTOP"
if [[ ! -d node_modules/electron ]]; then
  echo "→ npm install（首次）…"
  npm install
fi

# 避免重复开多个 Electron
if pgrep -fl "electron.*unifier-desktop|Unifier.app|desktop/electron/main" >/dev/null 2>&1; then
  # 粗检：同目录 electron 已在跑则只提示
  if pgrep -f "${DESKTOP}/node_modules/electron" >/dev/null 2>&1 \
    || pgrep -f "unifier-desktop" >/dev/null 2>&1; then
    echo "联合器桌面已在运行（看菜单栏托盘）。"
    echo "若要重启：托盘 → 退出，再执行本脚本。"
    exit 0
  fi
fi

echo "→ 启动联合器托盘（日志: $LOG_DIR/desktop-app.log）"
# 个人版：自动起 daemon；已有 :8787 则复用
nohup npm start >>"$LOG_DIR/desktop-app.log" 2>&1 &
echo "pid=$!"
sleep 2
if curl -sf -m 2 http://127.0.0.1:8787/health >/dev/null 2>&1; then
  echo "✅ Hub 已在线 http://127.0.0.1:8787"
else
  echo "⏳ Hub 启动中… 几秒后再看托盘状态或："
  echo "   curl -sf http://127.0.0.1:8787/health"
fi
echo "菜单栏托盘：启动/停止/开机自启 · 关窗不退出"
