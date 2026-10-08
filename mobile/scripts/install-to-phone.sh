#!/usr/bin/env bash
# 构建并 adb 安装到已连接真机（绕过中文路径 + Gradle 下载超时）
set -euo pipefail
MOBILE="$(cd "$(dirname "$0")/.." && pwd)"
LINK="$HOME/Projects/unifier-android"
SDK="/opt/homebrew/share/android-commandlinetools"
GRADLE_BIN="$HOME/.gradle/wrapper/dists/gradle-8.14.3-all/10utluxaxniiv4wxiphsi49nj/gradle-8.14.3/bin/gradle"

mkdir -p "$HOME/Projects"
ln -sfn "$MOBILE/android" "$LINK"
echo "sdk.dir=$SDK" > "$LINK/local.properties"

cd "$MOBILE"
npm run sync

if [[ ! -x "$GRADLE_BIN" ]]; then
  echo "未找到本地 Gradle 8.14，请先 Android Studio Sync 一次或安装 Gradle"
  exit 1
fi

export JAVA_HOME="${JAVA_HOME:-$(/usr/libexec/java_home -v 17)}"
echo "设备列表:"
adb devices -l

cd "$LINK"
"$GRADLE_BIN" installDebug --no-daemon

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 'YOUR_LAN_IP')"
echo ""
echo "✅ 已安装到手机。打开「联合器」App"
echo "⚙ Hub 地址: http://${LAN_IP}:8787"
echo "（电脑需先 cd hub && ./scripts/start-services.sh）"
