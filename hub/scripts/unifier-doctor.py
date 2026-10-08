#!/usr/bin/env python3
"""联合器环境自检（Mac / Linux / Windows Git Bash）。"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def warn(msg: str, fix: str = "") -> None:
    print(f"  ⚠️  {msg}")
    if fix:
        print(f"     → {fix}")


def fail(msg: str, fix: str = "") -> None:
    print(f"  ❌ {msg}")
    if fix:
        print(f"     → {fix}")


def check_python() -> bool:
    v = sys.version_info
    if v >= (3, 11):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    fail(f"Python {v.major}.{v.minor}（需要 ≥3.11）", "brew install python@3.11 或 pyenv install 3.11")
    return False


def check_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        in_use = s.connect_ex(("127.0.0.1", port)) == 0
    if in_use:
        warn(
            f"端口 {port} 已被占用（Hub 默认端口）",
            f"lsof -i :{port} 查看进程；或 UNIFIER_PORT=8788 换端口",
        )
    else:
        ok(f"端口 {port} 可用")


def check_hub_venv(hub_dir: Path) -> bool:
    venv = hub_dir / ".venv"
    if not venv.is_dir():
        fail("Hub venv 不存在", f"cd {hub_dir} && python3 -m venv .venv && pip install -r requirements.txt")
        return False
    ok("Hub venv 存在")
    return True


def check_env_files(repo: Path) -> None:
    hub_env = repo / "hub" / ".env"
    local_env = repo / "config" / "local.env"
    if hub_env.is_file():
        text = hub_env.read_text(encoding="utf-8")
        if "FEISHU_APP_ID=" in text and "your_" not in text.split("FEISHU_APP_ID=")[-1][:20]:
            ok("hub/.env 已配置飞书")
        else:
            warn("hub/.env 飞书凭证可能未填", "编辑 hub/.env 填入 FEISHU_APP_ID / SECRET")
    else:
        fail("缺少 hub/.env", "cp hub/.env.example hub/.env")

    if local_env.is_file():
        if "UNIFIER_DEVICE_ID=" in local_env.read_text(encoding="utf-8"):
            ok("config/local.env 含 DEVICE_ID")
        else:
            warn("config/local.env 未设 UNIFIER_DEVICE_ID", "运行 ./scripts/setup.sh")
    else:
        warn("缺少 config/local.env", "cp config/local.env.example config/local.env")


def check_hub_running(hub_url: str) -> None:
    try:
        with urllib.request.urlopen(f"{hub_url.rstrip('/')}/health", timeout=3) as resp:
            data = json.loads(resp.read().decode())
        if data.get("ok"):
            ok(f"Hub 在线 {hub_url}")
        else:
            warn(f"Hub 响应异常: {data}")
    except urllib.error.URLError:
        warn(f"Hub 未启动 ({hub_url})", "cd hub && ./scripts/start-services.sh")


def check_commands() -> None:
    for cmd in ("git", "curl"):
        if shutil.which(cmd):
            ok(f"{cmd} 可用")
        else:
            warn(f"未找到 {cmd}", f"安装 {cmd}")


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    hub_dir = repo / "hub"
    hub_url = os.environ.get("HUB_URL", "http://127.0.0.1:8787")
    port = int(os.environ.get("UNIFIER_PORT", "8787"))

    print("== 联合器 Health Check ==")
    print(f"平台: {platform.system()} {platform.release()}")
    print(f"仓库: {repo}")
    print()

    issues = 0
    if not check_python():
        issues += 1
    check_commands()
    check_port(port)
    if not check_hub_venv(hub_dir):
        issues += 1
    check_env_files(repo)
    check_hub_running(hub_url)

    print()
    if issues:
        print(f"发现 {issues} 项阻塞问题，请先修复后再启动 Hub。")
        return 1
    print("自检完成。若 Hub 未运行：cd hub && ./scripts/start-services.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
