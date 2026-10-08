#!/usr/bin/env python3
"""异网访问：内置公网映射 + 连接密码（对用户隐藏技术细节）。"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


def unifier_home() -> Path:
    return Path(os.environ.get("UNIFIER_HOME", Path.home() / ".unifier"))


def state_path() -> Path:
    return unifier_home() / "remote-access.json"


def token_path() -> Path:
    return unifier_home() / "access-token.txt"


def bin_dir() -> Path:
    d = unifier_home() / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cloudflared_bin() -> Path:
    name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
    return bin_dir() / name


def ensure_cloudflared() -> Path:
    path = cloudflared_bin()
    if path.is_file() and os.access(path, os.X_OK):
        return path
    which = shutil.which("cloudflared")
    if which:
        return Path(which)

    # 按需拉取一次，用户无感
    if sys.platform == "darwin":
        machine = os.uname().machine
        arch = "arm64" if machine == "arm64" else "amd64"
        url = (
            "https://github.com/cloudflare/cloudflared/releases/latest/download/"
            f"cloudflared-darwin-{arch}.tgz"
        )
        tgz = bin_dir() / "cloudflared.tgz"
        print(f"[remote] downloading helper…", flush=True)
        urllib.request.urlretrieve(url, tgz)
        subprocess.check_call(["tar", "-xzf", str(tgz), "-C", str(bin_dir())])
        tgz.unlink(missing_ok=True)
        # tarball 可能直接解出 cloudflared
        cand = bin_dir() / "cloudflared"
        if not cand.is_file():
            for p in bin_dir().glob("cloudflared*"):
                if p.is_file() and "tgz" not in p.name:
                    p.rename(cand)
                    break
        cand.chmod(0o755)
        return cand

    if sys.platform.startswith("linux"):
        machine = os.uname().machine
        arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
        url = (
            "https://github.com/cloudflare/cloudflared/releases/latest/download/"
            f"cloudflared-linux-{arch}"
        )
        print("[remote] downloading helper…", flush=True)
        urllib.request.urlretrieve(url, path)
        path.chmod(0o755)
        return path

    raise RuntimeError("当前系统暂不支持一键异网访问，请在同一 Wi‑Fi 下使用")


def write_state(data: dict) -> None:
    unifier_home().mkdir(parents=True, exist_ok=True)
    state_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_state() -> dict:
    if not state_path().is_file():
        return {}
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_token(*, rotate: bool = False) -> str:
    if not rotate and token_path().is_file():
        t = token_path().read_text(encoding="utf-8").strip()
        if t:
            return t
    t = secrets.token_urlsafe(18)
    unifier_home().mkdir(parents=True, exist_ok=True)
    token_path().write_text(t + "\n", encoding="utf-8")
    return t


def clear_token() -> None:
    try:
        token_path().unlink(missing_ok=True)
    except OSError:
        pass


def connection_card(hub_url: str, token: str, session_id: str = "default") -> str:
    return "\n".join(
        [
            "【联合器 · 手机连接】",
            f"电脑连接地址：{hub_url}",
            f"连接密码：{token}",
            f"会话 ID：{session_id}",
            "打开联合器 App → 设置 → 粘贴以上全部内容 → 保存。",
            "请保持电脑上的联合器开着。",
        ]
    )


def start(hub_local: str = "http://127.0.0.1:8787", session_id: str = "default") -> dict:
    # 先停旧的
    try:
        stop(clear_secret=False)
    except Exception:
        pass
    cf = ensure_cloudflared()
    token = ensure_token(rotate=True)
    log_path = unifier_home() / "logs" / "remote-access.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 截断旧日志，避免匹配到过期 URL
    log_path.write_text("", encoding="utf-8")
    logf = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [
            str(cf),
            "tunnel",
            "--url",
            hub_local,
            "--no-autoupdate",
            "--protocol",
            "http2",
        ],
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    public_url: Optional[str] = None
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        # 只看末尾，避免旧 URL
        tail = text[-4000:]
        found = URL_RE.findall(tail)
        if found:
            public_url = found[-1]
            break
        if proc.poll() is not None:
            raise RuntimeError("无法开启异网访问，请检查网络后重试")
        time.sleep(0.4)

    if not public_url:
        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError("开启超时，请稍后重试")

    card = connection_card(public_url, token, session_id)
    state = {
        "enabled": True,
        "pid": proc.pid,
        "public_url": public_url,
        "local_hub": hub_local,
        "session_id": session_id,
        "card": card,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_state(state)
    (unifier_home() / "remote-access.card.txt").write_text(card + "\n", encoding="utf-8")
    print(card, flush=True)
    return state


def stop(*, clear_secret: bool = True) -> None:
    st = read_state()
    pid = st.get("pid")
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                subprocess.run(["pkill", "-f", "cloudflared tunnel --url"], check=False)
            except Exception:
                pass
    if clear_secret:
        clear_token()
    write_state(
        {
            "enabled": False,
            "public_url": None,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    if clear_secret:
        print("已关闭：手机在外面将连不上（同一 Wi‑Fi 仍可用）", flush=True)


def status() -> dict:
    st = read_state()
    if st.get("enabled") and st.get("pid"):
        try:
            os.kill(int(st["pid"]), 0)
        except OSError:
            st["enabled"] = False
            st["alive"] = False
            write_state(st)
            return st
        st["alive"] = True
        st["token_set"] = token_path().is_file()
    return st


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["start", "stop", "status", "card"])
    p.add_argument("--hub", default="http://127.0.0.1:8787")
    p.add_argument("--session-id", default="default")
    args = p.parse_args()
    if args.action == "start":
        start(args.hub, args.session_id)
    elif args.action == "stop":
        stop()
    elif args.action == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        st = read_state()
        print(st.get("card") or "尚未开启「让手机在外面也能用」")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"出错了：{e}", file=sys.stderr)
        sys.exit(1)
