#!/usr/bin/env bash
# 联合器首次安装 / 新成员 onboarding
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HUB_DIR="${REPO_ROOT}/hub"
CONFIG_DIR="${REPO_ROOT}/config"

echo "== 联合器 Setup =="
echo "仓库: ${REPO_ROOT}"

# 1. Hub Python 环境
if [[ ! -d "${HUB_DIR}/.venv" ]]; then
  echo "→ 创建 Python venv..."
  python3 -m venv "${HUB_DIR}/.venv"
fi
# shellcheck disable=SC1091
source "${HUB_DIR}/.venv/bin/activate"
pip install -q -r "${HUB_DIR}/requirements.txt"

# 2. hub/.env（飞书密钥等）
if [[ ! -f "${HUB_DIR}/.env" ]]; then
  cp "${HUB_DIR}/.env.example" "${HUB_DIR}/.env"
  echo "→ 已创建 hub/.env，请填入 FEISHU_APP_ID / FEISHU_APP_SECRET"
else
  echo "→ hub/.env 已存在，跳过"
fi

# 3. config/local.env（个人路径与设备名）
if [[ ! -f "${CONFIG_DIR}/local.env" ]]; then
  cp "${CONFIG_DIR}/local.env.example" "${CONFIG_DIR}/local.env"
  echo "→ 已创建 config/local.env，请设置 UNIFIER_WORKSPACE_ROOTS 与设备 ID"
else
  echo "→ config/local.env 已存在，跳过"
fi

# 4. 脚本可执行
chmod +x "${HUB_DIR}/run.sh" "${HUB_DIR}/scripts/"*.sh "${HUB_DIR}/scripts/"*.py 2>/dev/null || true
chmod +x "${REPO_ROOT}/scripts/"*.sh 2>/dev/null || true

# 5. 本机 Agent 目录
mkdir -p "${HOME}/.unifier/inbox"

# 6. 交互式提示（可选）
DEFAULT_DEVICE="$(hostname -s | tr ' ' '-' | tr '[:upper:]' '[:lower:]')"
read -r -p "本机设备 ID [${DEFAULT_DEVICE}]: " DEVICE_ID || true
DEVICE_ID="${DEVICE_ID:-$DEFAULT_DEVICE}"

if grep -q '^# UNIFIER_DEVICE_ID=' "${CONFIG_DIR}/local.env" 2>/dev/null; then
  :
fi

if ! grep -q '^UNIFIER_DEVICE_ID=' "${CONFIG_DIR}/local.env" 2>/dev/null; then
  echo "UNIFIER_DEVICE_ID=${DEVICE_ID}" >> "${CONFIG_DIR}/local.env"
  echo "UNIFIER_AGENT_ID=cursor" >> "${CONFIG_DIR}/local.env"
fi

read -r -p "本地项目根目录（留空跳过）: " WORKSPACE_ROOT || true
if [[ -n "${WORKSPACE_ROOT}" ]]; then
  if grep -q '^UNIFIER_WORKSPACE_ROOTS=' "${CONFIG_DIR}/local.env" 2>/dev/null; then
    sed -i.bak "s|^UNIFIER_WORKSPACE_ROOTS=.*|UNIFIER_WORKSPACE_ROOTS=${WORKSPACE_ROOT}|" "${CONFIG_DIR}/local.env"
    rm -f "${CONFIG_DIR}/local.env.bak"
  else
    echo "UNIFIER_WORKSPACE_ROOTS=${WORKSPACE_ROOT}" >> "${CONFIG_DIR}/local.env"
  fi
fi

echo ""
echo "✅ Setup 完成"
echo ""
echo "建议运行自检: ./scripts/health-check.sh"
echo ""
echo "下一步："
echo "  1. 编辑 hub/.env 填入飞书应用凭证"
echo "  2. 编辑 config/local.env 设置工作区路径与设备"
echo "  3. 启动: cd hub && ./scripts/start-services.sh"
echo "  4. 工作站: DEVICE_ID=${DEVICE_ID} AGENT_ID=cursor ./scripts/start-workstation.sh"
echo ""
echo "完整文档: ${REPO_ROOT}/INSTALL.md"
