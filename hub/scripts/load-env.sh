#!/usr/bin/env bash
# 加载 Hub 环境变量：hub/.env → 仓库 config/local.env（个人覆盖，不提交）
HUB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${HUB_DIR}/.." && pwd)"

if [[ -f "${HUB_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${HUB_DIR}/.env"
  set +a
fi

if [[ -f "${REPO_ROOT}/config/local.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${REPO_ROOT}/config/local.env"
  set +a
fi
