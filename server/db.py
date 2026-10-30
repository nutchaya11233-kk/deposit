"""
MongoDB — เปิดต่อครั้งเดียวแล้วใช้ร่วมกันทั้งโปรเซส

Collections:
  users           ผู้ใช้หน้าเว็บ (admin | staff)
  tunnels         tunnel ของแต่ละยูส (ผูกด้วยฟิลด์ owner)
  tunnel_tokens   token ของ frpc แยกรายยูส
  app_settings    ค่าที่ระบบสร้างเอง (ตอนนี้มีแค่ secret ของ frps plugin)
"""
from __future__ import annotations

from pymongo import ASCENDING, MongoClient

from server.config import MONGODB_URI
from server.logger import log

_db = None


def get_db():
    global _db
    if _db is None:
        if not MONGODB_URI:
            raise RuntimeError("ยังไม่ได้ตั้ง MONGODB_URI ใน .env")
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
        _db = client.get_default_database()
        log("OK", f"ต่อ MongoDB แล้ว: {_db.name}")
    return _db


def ensure_indexes() -> None:
    db = get_db()
    db["users"].create_index([("username", ASCENDING)], unique=True)
    # ชื่อ tunnel ซ้ำข้ามยูสได้ — frp เติม "<user>." นำหน้าชื่อ proxy ให้เอง
    db["tunnels"].create_index([("owner", ASCENDING), ("name", ASCENDING)], unique=True)
    # sparse เพราะมีเฉพาะโหมด public ที่จองพอร์ตบน VPS
    db["tunnels"].create_index([("remote_port", ASCENDING)], unique=True, sparse=True)
