"""
frps server plugin — จุดเดียวที่ตัดสินว่า frpc ของใครเข้าได้และเปิดอะไรได้

frps ยิง POST มาที่นี่ตอน Login และ NewProxy แล้วทำตามคำตอบ
  อนุญาต: {"reject": false, "unchange": true}
  ปฏิเสธ: {"reject": true, "reject_reason": "..."}

⚠️ ทุกทางที่ไม่แน่ใจต้องตอบปฏิเสธ (fail closed) — frps ไม่มี token กลางแล้ว
   ด่านนี้ด่านเดียวกันไม่ให้คนนอกใช้ VPS เป็น tunnel ฟรี

⚠️ เส้นทางอยู่นอก /api และมี secret อยู่ใน path เพราะ frps ใส่ header เองไม่ได้
   และ cloudflared ก็ตั้งให้ตอบ 404 ที่ /internal/ อีกชั้น (ดู deploy/cloudflared.yml)
"""
from __future__ import annotations

import hmac

from flask import Blueprint, jsonify, request

from server import tunnels
from server.db import get_db
from server.logger import log

bp = Blueprint("frp_plugin", __name__)

ALLOW = {"reject": False, "unchange": True}


def _reject(reason: str) -> dict:
    return {"reject": True, "reject_reason": reason}


def _user_ok(db, user: str, metas: dict | None) -> bool:
    if not user or not db["users"].find_one({"username": user}, {"_id": 1}):
        return False
    doc = db["tunnel_tokens"].find_one({"_id": user})
    given = str((metas or {}).get("token") or "")
    return bool(doc and given) and hmac.compare_digest(doc["token"], given)


def _check_proxy(db, content: dict) -> dict:
    info = content.get("user") or {}
    user = str(info.get("user") or "")
    if not _user_ok(db, user, info.get("metas")):
        return _reject("invalid token")

    # frp เติม "<user>." นำหน้าชื่อมาให้ — ใช้ user จาก login ไม่แยกจากจุดในชื่อ
    # เพราะทั้งชื่อยูสและชื่อ tunnel มีจุดได้
    full = str(content.get("proxy_name") or "")
    prefix = f"{user}."
    if not full.startswith(prefix):
        return _reject("proxy name does not belong to user")

    doc = db["tunnels"].find_one({"owner": user, "name": full[len(prefix):]})
    if not doc:
        return _reject("unknown tunnel")

    if content.get("proxy_type") != "tcp" or content.get("remote_port") != doc.get("remote_port"):
        return _reject("tunnel config mismatch")
    return ALLOW


def handle(db, op: str, content: dict) -> dict:
    if op == "Login":
        ok = _user_ok(db, str(content.get("user") or ""), content.get("metas"))
        return ALLOW if ok else _reject("invalid token")
    if op == "NewProxy":
        return _check_proxy(db, content)
    return _reject("unsupported op")


@bp.post("/internal/frp/<secret>")
def frp_plugin(secret: str):
    try:
        db = get_db()
        if not hmac.compare_digest(tunnels.plugin_secret(db), secret):
            return jsonify({"error": "not found"}), 404
        data = request.get_json(silent=True) or {}
        result = handle(db, request.args.get("op", ""), data.get("content") or {})
    except Exception as e:
        log("ERROR", f"frp plugin พัง: {e}")
        result = _reject("internal error")
    if result.get("reject"):
        log("WARN", f"frp ปฏิเสธ {request.args.get('op', '')}: {result['reject_reason']}")
    return jsonify(result)
