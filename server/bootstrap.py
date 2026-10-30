"""เตรียมระบบก่อนเปิดรับงาน — ใช้ร่วมกันทั้ง run.py และ serve.py"""
from __future__ import annotations

from server import auth, tunnels
from server.config import ADMIN_PASSWORD, ADMIN_USERNAME
from server.db import ensure_indexes, get_db
from server.logger import log


def prepare() -> bool:
    try:
        get_db()
        ensure_indexes()
    except Exception as e:
        log("ERROR", f"ต่อ MongoDB ไม่ได้: {e}")
        log("ERROR", "เช็ค MONGODB_URI ใน .env แล้วลองใหม่")
        return False

    try:
        if auth.bootstrap_admin(ADMIN_USERNAME, ADMIN_PASSWORD):
            log("OK", f"สร้างแอดมินคนแรก '{ADMIN_USERNAME}' แล้ว — ลบ ADMIN_PASSWORD ออกจาก .env ได้เลย")
    except ValueError as e:
        log("ERROR", f"สร้างแอดมินจาก .env ไม่ได้: {e}")
        return False

    if get_db()["users"].count_documents({}) == 0:
        log("WARN", "ยังไม่มีผู้ใช้สักคน — ตั้ง ADMIN_USERNAME/ADMIN_PASSWORD ใน .env "
                    "หรือสั่ง  py -3 manage.py adduser <ชื่อ> --role admin")

    moved = tunnels.migrate_private(get_db())
    if moved:
        log("WARN", f"แปลง tunnel แบบ private {moved} อันเป็นแบบมีพอร์ต — มือถือต้องตั้งค่า frpc ใหม่")

    if tunnels.sync_frps_config(get_db()):
        log("OK", "เขียน frps.toml แล้ว")
    return True
