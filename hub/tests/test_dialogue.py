"""圆桌对话单测：开房 → 双回 → 互见 → 结束。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["UNIFIER_DB"] = _tmp.name
os.environ["WORKFLOWS_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()


def test_dialogue_roundtrip():
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/dialogue/rooms",
            json={
                "title": "7/17 零单复盘",
                "topic": "主因是不是 19:58 online=0？",
                "project_key": "maotai",
                "participants": ["cursor", "trae"],
            },
        )
        assert r.status_code == 200, r.text
        room_id = r.json()["room"]["id"]

        pc = client.get(
            f"/api/v1/dialogue/rooms/{room_id}/poll",
            params={"participant": "cursor", "since_id": 0},
        )
        assert pc.status_code == 200
        assert pc.json()["my_turn"] is True

        pt = client.get(
            f"/api/v1/dialogue/rooms/{room_id}/poll",
            params={"participant": "trae", "since_id": 0},
        )
        assert pt.json()["my_turn"] is True

        rc = client.post(
            f"/api/v1/dialogue/rooms/{room_id}/reply",
            json={"participant": "cursor", "body": "同意：心跳与 AutoRush 解耦是 P0。"},
        )
        assert rc.status_code == 200
        assert rc.json()["round_complete"] is False

        pt2 = client.get(
            f"/api/v1/dialogue/rooms/{room_id}/poll",
            params={"participant": "trae", "since_id": 0},
        )
        peers = pt2.json()["new_peer_messages"]
        assert not any(m["participant"] == "cursor" for m in peers)

        rt = client.post(
            f"/api/v1/dialogue/rooms/{room_id}/reply",
            json={"participant": "trae", "body": "补充：装 1.9.128 后熄屏验 online。"},
        )
        assert rt.status_code == 200
        assert rt.json()["round_complete"] is True

        pc3 = client.get(
            f"/api/v1/dialogue/rooms/{room_id}/poll",
            params={"participant": "cursor", "since_id": 0},
        )
        assert pc3.json()["round_complete"] is True
        assert pc3.json()["my_turn"] is False
        bodies = " ".join(m["body"] for m in pc3.json()["transcript_tail"])
        assert "1.9.128" in bodies

        bad = client.post(
            f"/api/v1/dialogue/rooms/{room_id}/reply",
            json={"participant": "cursor", "body": "再来一句"},
        )
        assert bad.status_code == 409

        um = client.post(
            f"/api/v1/dialogue/rooms/{room_id}/user-message",
            json={"body": "那 4030 熔断要不要先做？"},
        )
        assert um.status_code == 200
        assert um.json()["room"]["current_round"] == 2

        end = client.post(f"/api/v1/dialogue/rooms/{room_id}/end")
        assert end.status_code == 200
        assert end.json()["room"]["status"] == "closed"

        tr = client.get(f"/api/v1/dialogue/rooms/{room_id}/transcript")
        assert len(tr.json()["messages"]) >= 4


if __name__ == "__main__":
    test_dialogue_roundtrip()
    print("OK", _tmp.name)
    Path(_tmp.name).unlink(missing_ok=True)
