#!/usr/bin/env python3
"""跨平台守护：个人版起 Hub 栈；企业版仅工作站收件箱。

- Hub 已在 :8787 时复用，不重复拉起
- inbox-auto 必带 --hub/--device-id/--agents
- 子进程日志进 ~/.unifier/logs
- 飞书桥可选；退出不拖垮整栈
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROCS: Dict[str, subprocess.Popen] = {}
LOG_HANDLES: List[object] = []
STARTED_HUB = False


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def unifier_home() -> Path:
    return Path(os.environ.get("UNIFIER_HOME", Path.home() / ".unifier"))


def log_dir() -> Path:
    d = unifier_home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def merge_env(base: dict, user_data: Path, edition: str) -> dict:
    env = os.environ.copy()
    env.update(base)
    hub_env = user_data / "hub.env"
    if hub_env.is_file():
        for line in hub_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    cfg = load_json(user_data / "config.json")
    if cfg.get("hubUrl"):
        env["HUB_URL"] = str(cfg["hubUrl"]).rstrip("/")
    if cfg.get("deviceId"):
        env["DEVICE_ID"] = str(cfg["deviceId"])
    env.setdefault("HUB_URL", "http://127.0.0.1:8787")
    if not env.get("DEVICE_ID"):
        try:
            env["DEVICE_ID"] = socket.gethostname().split(".")[0] or "mac-a"
        except Exception:
            env["DEVICE_ID"] = "mac-a"
    env.setdefault("INBOX_AUTO_AGENTS", "cursor,trae,dsh")
    env.setdefault("UNIFIER_HOME", str(unifier_home()))
    env["UNIFIER_EDITION"] = edition
    return env


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def hub_healthy(hub_url: str) -> bool:
    try:
        with urllib.request.urlopen(hub_url.rstrip("/") + "/health", timeout=2) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def open_log(name: str):
    path = log_dir() / f"daemon-{name}.log"
    fh = open(path, "a", encoding="utf-8")
    LOG_HANDLES.append(fh)
    return fh


def spawn(cmd: List[str], cwd: Path, env: dict, name: str) -> None:
    if name in PROCS and PROCS[name].poll() is None:
        print(f"[daemon] {name} already running pid={PROCS[name].pid}", flush=True)
        return
    print(f"[daemon] start {name}: {' '.join(cmd)}", flush=True)
    logf = open_log(name)
    p = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PROCS[name] = p


def ensure_venv(hub_dir: Path) -> Path:
    venv = hub_dir / ".venv"
    py = venv / "Scripts" / "python.exe" if sys.platform == "win32" else venv / "bin" / "python"
    if not py.is_file():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)], cwd=str(hub_dir))
        subprocess.check_call(
            [str(py), "-m", "pip", "install", "-q", "-r", "requirements.txt"],
            cwd=str(hub_dir),
        )
    return py


def register_device(hub_dir: Path, env: dict, py: Path) -> None:
    script = hub_dir / "scripts" / "register-device.sh"
    device = env.get("DEVICE_ID", "mac-a")
    if script.is_file() and sys.platform != "win32":
        try:
            subprocess.run(
                ["bash", str(script), device],
                cwd=str(hub_dir / "scripts"),
                env=env,
                check=False,
                timeout=30,
            )
        except Exception as e:
            print(f"[daemon] register-device warn: {e}", flush=True)
        return
    # Windows / fallback：直接打 API
    try:
        body = json.dumps(
            {
                "device_id": device,
                "name": device,
                "hostname": socket.gethostname(),
                "os_name": sys.platform,
                "agents": ["cursor", "trae"],
            }
        ).encode()
        req = urllib.request.Request(
            env["HUB_URL"].rstrip("/") + "/api/v1/devices/register",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"[daemon] register API warn: {e}", flush=True)


def start_inbox(hub_dir: Path, env: dict, py: Path) -> None:
    hub_url = env["HUB_URL"]
    device = env["DEVICE_ID"]
    agents = env.get("INBOX_AUTO_AGENTS", "cursor,trae,dsh")
    home = env.get("UNIFIER_HOME", str(unifier_home()))
    Path(home).mkdir(parents=True, exist_ok=True)
    # 避免与手动起的 runner 双开
    if sys.platform != "win32":
        try:
            subprocess.run(
                ["pkill", "-f", f"inbox-auto-runner.py.*--device-id {device}"],
                check=False,
            )
            time.sleep(0.4)
        except Exception:
            pass
    cmd = [
        str(py),
        "scripts/inbox-auto-runner.py",
        "--hub",
        hub_url,
        "--device-id",
        device,
        "--agents",
        agents,
        "--home",
        home,
        "--interval",
        env.get("INBOX_AUTO_INTERVAL", "8"),
    ]
    spawn(cmd, hub_dir, env, "inbox-auto")


def start_heartbeat(hub_dir: Path, env: dict, py: Path) -> None:
    """设备在线心跳：手机「联通」依赖 last_heartbeat。"""
    hub_url = env["HUB_URL"]
    device = env["DEVICE_ID"]
    script = hub_dir / "scripts" / "heartbeat-loop.sh"
    if script.is_file() and sys.platform != "win32":
        try:
            subprocess.run(["pkill", "-f", "heartbeat-loop.sh"], check=False)
        except Exception:
            pass
        spawn(["bash", str(script)], hub_dir / "scripts", env, "heartbeat")
        return
    # Windows / 无 shell 脚本：内联轮询
    code = (
        "import os,time,urllib.request\n"
        "u=os.environ['HUB_URL'].rstrip('/')+'/api/v1/devices/'+os.environ['DEVICE_ID']+'/heartbeat'\n"
        "while True:\n"
        "  try:\n"
        "    urllib.request.urlopen(urllib.request.Request(u,method='POST',data=b'{}',"
        "headers={'Content-Type':'application/json'}),timeout=5)\n"
        "  except Exception as e:\n"
        "    print('heartbeat fail',e,flush=True)\n"
        "  time.sleep(int(os.environ.get('INTERVAL','30')))\n"
    )
    spawn([str(py), "-c", code], hub_dir, {**env, "HUB_URL": hub_url, "DEVICE_ID": device}, "heartbeat")


def start_personal(hub_dir: Path, env: dict) -> None:
    global STARTED_HUB
    py = ensure_venv(hub_dir)
    env = {**env, "PYTHONPATH": "."}
    host = env.get("UNIFIER_HOST", "0.0.0.0")
    port = int(env.get("UNIFIER_PORT", "8787"))
    hub_url = env.get("HUB_URL", f"http://127.0.0.1:{port}")

    if hub_healthy(hub_url) or port_open("127.0.0.1", port):
        print(f"[daemon] Hub already up at {hub_url} — reuse", flush=True)
        STARTED_HUB = False
    else:
        spawn(
            [
                str(py),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ],
            hub_dir,
            env,
            "hub",
        )
        STARTED_HUB = True
        for _ in range(40):
            if hub_healthy(hub_url):
                break
            time.sleep(0.25)
        else:
            print("[daemon] WARN: Hub health not ready yet", flush=True)

    scripts = hub_dir / "scripts"
    if (scripts / "feishu-bridge.py").is_file():
        spawn([str(py), "scripts/feishu-bridge.py"], hub_dir, env, "feishu-bridge")
    if (
        env.get("FEISHU_APP_ID")
        and env.get("FEISHU_APP_SECRET")
        and (scripts / "feishu-card-bridge.py").is_file()
    ):
        spawn([str(py), "scripts/feishu-card-bridge.py"], hub_dir, env, "feishu-card")

    register_device(hub_dir, env, py)
    start_heartbeat(hub_dir, env, py)
    start_inbox(hub_dir, env, py)
    write_status(env, running=True)


def start_enterprise(hub_dir: Path, env: dict) -> None:
    py = ensure_venv(hub_dir)
    hub_url = env.get("HUB_URL", "")
    if not hub_url or "127.0.0.1" in hub_url or "localhost" in hub_url:
        print("[daemon] enterprise requires remote HUB_URL in config.json", flush=True)
        sys.exit(2)
    register_device(hub_dir, env, py)
    start_heartbeat(hub_dir, env, py)
    start_inbox(hub_dir, env, py)
    write_status(env, running=True)


def write_status(env: dict, *, running: bool) -> None:
    path = unifier_home() / "daemon-status.json"
    alive = {name: (p.poll() is None) for name, p in PROCS.items()}
    payload = {
        "running": running,
        "edition": env.get("UNIFIER_EDITION"),
        "hub_url": env.get("HUB_URL"),
        "device_id": env.get("DEVICE_ID"),
        "hub_healthy": hub_healthy(env.get("HUB_URL", "http://127.0.0.1:8787")),
        "started_hub": STARTED_HUB,
        "procs": alive,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def shutdown(_sig=None, _frame=None) -> None:
    print("[daemon] shutting down…", flush=True)
    for name, p in list(PROCS.items()):
        if name == "hub" and not STARTED_HUB:
            continue
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    time.sleep(0.6)
    for name, p in list(PROCS.items()):
        if name == "hub" and not STARTED_HUB:
            continue
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
    for fh in LOG_HANDLES:
        try:
            fh.close()
        except Exception:
            pass
    try:
        st = unifier_home() / "daemon-status.json"
        if st.is_file():
            data = json.loads(st.read_text(encoding="utf-8"))
            data["running"] = False
            data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            st.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    sys.exit(0)


def _restart_hub(hub_dir: Path, env: dict, py: Path) -> None:
    global STARTED_HUB
    host = env.get("UNIFIER_HOST", "0.0.0.0")
    port = env.get("UNIFIER_PORT", "8787")
    spawn(
        [str(py), "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
        hub_dir,
        {**env, "PYTHONPATH": "."},
        "hub",
    )
    STARTED_HUB = True


def supervise(env: dict, hub_dir: Path, py: Path) -> None:
    """关键进程退出则重启；飞书桥退出只记日志。"""
    critical = {"hub", "inbox-auto", "heartbeat"}
    while True:
        hub_url = env.get("HUB_URL", "http://127.0.0.1:8787")
        if not hub_healthy(hub_url) and (
            "hub" not in PROCS or PROCS["hub"].poll() is not None
        ):
            print("[daemon] Hub down — starting local Hub", flush=True)
            _restart_hub(hub_dir, env, py)

        for name, p in list(PROCS.items()):
            code = p.poll()
            if code is None:
                continue
            print(f"[daemon] {name} exited code={code}", flush=True)
            if name not in critical:
                PROCS.pop(name, None)
                continue
            if name == "hub" and not STARTED_HUB:
                print("[daemon] external Hub gone — starting local Hub", flush=True)
                _restart_hub(hub_dir, env, py)
            elif name == "inbox-auto":
                time.sleep(1)
                start_inbox(hub_dir, env, py)
            elif name == "heartbeat":
                time.sleep(1)
                start_heartbeat(hub_dir, env, py)
            elif name == "hub":
                time.sleep(1)
                _restart_hub(hub_dir, env, py)
        write_status(env, running=True)
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", choices=["personal", "enterprise"], required=True)
    parser.add_argument("--hub-dir", required=True)
    parser.add_argument("--user-data", required=True)
    args = parser.parse_args()

    hub_dir = Path(args.hub_dir).resolve()
    user_data = Path(args.user_data).resolve()
    user_data.mkdir(parents=True, exist_ok=True)
    unifier_home().mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    env = merge_env({}, user_data, args.edition)
    print(
        f"[daemon] edition={args.edition} hub={env.get('HUB_URL')} device={env.get('DEVICE_ID')}",
        flush=True,
    )

    if args.edition == "personal":
        start_personal(hub_dir, env)
    else:
        start_enterprise(hub_dir, env)

    py = ensure_venv(hub_dir)
    supervise(env, hub_dir, py)


if __name__ == "__main__":
    main()
