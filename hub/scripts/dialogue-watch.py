#!/usr/bin/env python3
"""圆桌自动 poll：为 cursor + trae 常驻代回（IDE 睡着时补位）。

用法：
  HUB_URL=http://127.0.0.1:8787 \\
  python3 dialogue-watch.py --project-key maotai --agents cursor,trae

行为：
  1. 列出 open rooms
  2. 按顺序对每个 agent 调用 GET .../poll
  3. my_turn 且超过 grace 秒仍无人 reply → POST .../reply
  4. 写 ~/.unifier/dialogue/wake-{agent}.md + macOS 通知（可选）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def api(method: str, url: str, body: dict | None = None, timeout: float = 30) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def notify(title: str, body: str) -> None:
    if os.environ.get("DIALOGUE_WATCH_NOTIFY", "1") != "1":
        return
    if sys.platform != "darwin":
        return
    script = (
        f'display notification {json.dumps(body[:120])} '
        f'with title {json.dumps(title)}'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except Exception:
        pass


def write_wake(home: Path, agent: str, room_id: int, payload: dict) -> Path:
    d = home / "dialogue"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"wake-{agent}.md"
    tail = payload.get("transcript_tail") or []
    lines = [
        f"# wake · {agent} · room #{room_id}",
        "",
        f"- time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- my_turn: {payload.get('my_turn')}",
        f"- hint: {payload.get('hint')}",
        f"- round: {(payload.get('room') or {}).get('current_round')}",
        "",
        "## transcript_tail",
        "",
    ]
    for m in tail[-12:]:
        lines.append(
            f"- R{m.get('round')} **{m.get('participant')}**: {(m.get('body') or '')[:300]}"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def fallback_body(who: str, user_topic: str, peer: str) -> str:
    topic = (user_topic or "")[:200]
    if who == "cursor":
        return (
            f"【Cursor·Watch代言】收到：{topic}\n"
            f"立场：给可执行结论与证据路径。\n"
            f"对方上下文：{peer or '（尚无）'}\n"
            f"（dialogue-watch 自动 poll；IDE 醒着时可继续深挖。）"
        )
    if who == "trae":
        return (
            f"【Trae·Watch代言】收到：{topic}\n"
            f"补充：交叉验证 Cursor，标风险与遗漏。\n"
            f"对方上下文：{peer or '（尚无）'}\n"
            f"（dialogue-watch 自动 poll。）"
        )
    return f"【{who}·Watch代言】收到：{topic}"


def try_soul_body(hub: str, who: str, user_topic: str, transcript_txt: str) -> str | None:
    if os.environ.get("DIALOGUE_WATCH_USE_SOUL", "0") != "1":
        return None
    prompt = (
        f"你是联合器圆桌里的参与者「{who}」。用中文简短回复（≤180字）。\n"
        f"用户本轮问题：{user_topic}\n"
        f"近期 transcript：\n{transcript_txt[-2500:]}\n"
        f"要求：有实质观点；若是 trae 请与 cursor 互补而非重复。"
    )
    try:
        res = api(
            "POST",
            f"{hub.rstrip('/')}/soul/chat",
            {"message": prompt, "domain": "general"},
            timeout=60,
        )
        reply = (res.get("reply") or "").strip()
        if res.get("ok") and reply:
            return f"【{who}·Watch灵魂】{reply[:800]}"
    except Exception as e:
        print(f"[warn] soul failed for {who}: {e}", file=sys.stderr)
    return None


def extract_user_topic(tail: list[dict]) -> str:
    for m in reversed(tail or []):
        if m.get("role") == "user" or m.get("participant") == "user":
            return (m.get("body") or "").strip()
    return ""


def extract_peer(tail: list[dict], who: str, round_no: int | None) -> str:
    bits = []
    for m in tail or []:
        if m.get("role") != "agent":
            continue
        if m.get("participant") == who:
            continue
        if round_no is not None and m.get("round") != round_no:
            continue
        bits.append(f"{m.get('participant')}:{(m.get('body') or '')[:80]}")
    return "；".join(bits[:2])


def process_agent(
    hub: str,
    home: Path,
    room_id: int,
    agent: str,
    since: dict[str, int],
    pending_since: dict[str, float],
    grace: float,
    dry_run: bool,
) -> None:
    key = f"{room_id}:{agent}"
    sid = since.get(key, 0)
    poll = api(
        "GET",
        f"{hub.rstrip('/')}/api/v1/dialogue/rooms/{room_id}/poll"
        f"?participant={agent}&since_id={sid}",
    )
    room = poll.get("room") or {}
    if room.get("status") != "open":
        pending_since.pop(key, None)
        return

    tail = poll.get("transcript_tail") or []
    if tail:
        since[key] = max(since.get(key, 0), max(m.get("id", 0) for m in tail))

    if not poll.get("my_turn"):
        pending_since.pop(key, None)
        return

    write_wake(home, agent, room_id, poll)
    now = time.time()
    if key not in pending_since:
        pending_since[key] = now
        print(f"[turn] room=#{room_id} {agent} my_turn（grace {grace}s）")
        notify("联合器圆桌", f"#{room_id} 轮到 {agent}")
        return

    waited = now - pending_since[key]
    if waited < grace:
        return

    round_no = room.get("current_round")
    user_topic = extract_user_topic(tail)
    peer = extract_peer(tail, agent, round_no)
    transcript_txt = "\n".join(
        f"R{m.get('round')} {m.get('participant')}: {m.get('body')}" for m in tail[-20:]
    )
    body = try_soul_body(hub, agent, user_topic, transcript_txt)
    if not body:
        body = fallback_body(agent, user_topic, peer)

    if dry_run:
        print(f"[dry] would reply room=#{room_id} {agent}: {body[:80]}...")
        pending_since.pop(key, None)
        return

    try:
        res = api(
            "POST",
            f"{hub.rstrip('/')}/api/v1/dialogue/rooms/{room_id}/reply",
            {"participant": agent, "body": body},
        )
        print(
            f"[reply] room=#{room_id} {agent} ok "
            f"complete={ (res.get('room') or {}).get('round_complete') }"
        )
        notify("联合器圆桌", f"#{room_id} {agent} 已自动回复")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        # 可能已被 IDE / 网页代言抢先
        print(f"[skip] room=#{room_id} {agent} reply HTTP {e.code}: {err[:200]}", file=sys.stderr)
    pending_since.pop(key, None)


def tick(
    hub: str,
    home: Path,
    project_key: str,
    agents: list[str],
    since: dict[str, int],
    pending_since: dict[str, float],
    grace: float,
    dry_run: bool,
    room_id: int | None,
) -> None:
    if room_id:
        rooms = [{"id": room_id, "status": "open"}]
    else:
        data = api(
            "GET",
            f"{hub.rstrip('/')}/api/v1/dialogue/rooms"
            f"?project_key={project_key}&open_only=true",
        )
        rooms = data.get("rooms") or []

    for room in rooms:
        if room.get("status") and room.get("status") != "open":
            continue
        rid = int(room["id"])
        for agent in agents:
            try:
                process_agent(
                    hub, home, rid, agent, since, pending_since, grace, dry_run
                )
            except urllib.error.HTTPError as e:
                err = e.read().decode("utf-8", errors="replace")
                print(f"[warn] poll {rid}/{agent}: HTTP {e.code} {err[:160]}", file=sys.stderr)
            except Exception as e:
                print(f"[warn] poll {rid}/{agent}: {e}", file=sys.stderr)
            # 让 trae 有机会读到 cursor 刚写入的同轮发言
            time.sleep(0.35)


def main() -> int:
    p = argparse.ArgumentParser(description="联合器圆桌 dialogue-watch（cursor+trae）")
    p.add_argument("--hub", default=os.environ.get("HUB_URL", "http://127.0.0.1:8787"))
    p.add_argument("--project-key", default=os.environ.get("DIALOGUE_PROJECT_KEY", "maotai"))
    p.add_argument(
        "--agents",
        default=os.environ.get("DIALOGUE_WATCH_AGENTS", "cursor,trae"),
        help="逗号分隔，默认 cursor,trae",
    )
    p.add_argument("--interval", type=float, default=float(os.environ.get("DIALOGUE_WATCH_INTERVAL", "2")))
    p.add_argument(
        "--grace",
        type=float,
        default=float(os.environ.get("DIALOGUE_WATCH_GRACE", "2")),
        help="发现 my_turn 后等待秒数，给真 IDE 抢答窗口",
    )
    p.add_argument("--home", default=os.environ.get("UNIFIER_HOME", str(Path.home() / ".unifier")))
    p.add_argument("--room-id", type=int, default=0, help="只盯一个房间；0=所有 open")
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    agents = [a.strip().lower() for a in args.agents.split(",") if a.strip()]
    if not agents:
        print("agents 为空", file=sys.stderr)
        return 2

    home = Path(args.home)
    home.mkdir(parents=True, exist_ok=True)
    since: dict[str, int] = {}
    pending_since: dict[str, float] = {}
    room_id = args.room_id or None

    print(
        f"dialogue-watch 启动 hub={args.hub} project={args.project_key} "
        f"agents={agents} interval={args.interval}s grace={args.grace}s"
    )
    while True:
        try:
            tick(
                args.hub,
                home,
                args.project_key,
                agents,
                since,
                pending_since,
                args.grace,
                args.dry_run,
                room_id,
            )
        except urllib.error.URLError as e:
            print(f"[warn] Hub 不可达: {e}", file=sys.stderr)
        if args.once:
            # 再跑一轮以消化 grace
            if pending_since:
                time.sleep(max(args.grace, 0.5) + 0.2)
                try:
                    tick(
                        args.hub,
                        home,
                        args.project_key,
                        agents,
                        since,
                        pending_since,
                        0,  # grace 已等过
                        args.dry_run,
                        room_id,
                    )
                except urllib.error.URLError as e:
                    print(f"[warn] Hub 不可达: {e}", file=sys.stderr)
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
