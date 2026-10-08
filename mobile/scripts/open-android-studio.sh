#!/usr/bin/env bash
# 同步并在 Android Studio 打开联合器 App（真机 Run ▶）
# 注意：工程路径含中文时 Android Studio 会乱码崩溃，必须用 ASCII 符号链接打开
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LINK="$HOME/Projects/unifier-android"
mkdir -p "$HOME/Projects"
ln -sfn "$ROOT/android" "$LINK"
cd "$ROOT"
npm install
npm run sync
echo ""
echo "→ 工程符号链接（给 Android Studio 用）: $LINK"
echo "→ 请在 Android Studio 打开上述路径，不要直接开含中文的目录"
echo "→ 手机 USB 调试已连接时，点 Run ▶ 安装到真机"
echo ""
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 'YOUR_LAN_IP')"
echo "App 内 Hub 地址建议: http://${LAN_IP}:8787"
open -a "Android Studio" "$LINK"
