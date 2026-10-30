"""
Login ด้วย session cookie — ผู้ใช้เก็บใน MongoDB

⚠️ ไม่มีรหัสผ่านเริ่มต้นในโค้ดอีกแล้ว (ของเดิม hardcode ไว้ ทั้ง admin และ staff
   ใช้รหัสเดียวกัน ใครอ่านโค้ดเจอก็เข้าระบบได้) — สร้างผู้ใช้คนแรกด้วย
   `py -3 manage.py adduser` แทน
"""
from __future__ import annotations

import base64
import hmac
import io
import re
import threading
import time
from datetime import datetime, timezone
from functools import wraps

import pyotp
import qrcode
from flask import jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from server.db import get_db

ROLES = ("admin", "staff")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{2,32}$")

# ชื่อที่โชว์ในแอป Authenticator — ASCII ล้วน เพราะบางแอปแสดงชื่อไทยในป้ายไม่ได้
TOTP_ISSUER = "Tunnel Console"
TOTP_STEP = 30


class AuthError(Exception):
    """ข้อผิดพลาดจากข้อมูลที่ผู้ใช้กรอก — ตอบกลับเป็น 400"""


def _validate_username(username: str) -> str:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise ValueError("ชื่อผู้ใช้ต้องเป็น a-z, 0-9, _ . - ยาว 2-32 ตัว")
    return username


def create_user(username: str, password: str, role: str = "staff") -> None:
    username = _validate_username(username)
    if role not in ROLES:
        raise ValueError(f"role ต้องเป็น {' หรือ '.join(ROLES)}")
    if len(password) < 10:
        raise ValueError("รหัสผ่านต้องยาวอย่างน้อย 10 ตัว")
    if get_db()["users"].find_one({"username": username}):
        raise ValueError(f"มีผู้ใช้ '{username}' อยู่แล้ว")
    get_db()["users"].insert_one({
        "username":   username,
        "password":   generate_password_hash(password),
        "role":       role,
        "created_at": datetime.now(timezone.utc),
    })


def list_users() -> list[dict]:
    rows = get_db()["users"].find({}, {"password": 0, "totp_secret": 0, "totp_pending": 0})
    return [serialize_user(r) for r in rows.sort("created_at", 1)]


def serialize_user(doc: dict) -> dict:
    created = doc.get("created_at")
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "username":    doc.get("username", ""),
        "role":        doc.get("role", "staff"),
        "totpEnabled": bool(doc.get("totp_enabled")),
        "createdAt":   created.isoformat() if created else "",
    }


def set_role(username: str, role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"role ต้องเป็น {' หรือ '.join(ROLES)}")
    if role != "admin" and _is_last_admin(username):
        raise ValueError("ลดสิทธิ์ไม่ได้ — นี่คือผู้ดูแลระบบคนสุดท้าย")
    res = get_db()["users"].update_one({"username": username}, {"$set": {"role": role}})
    if res.matched_count == 0:
        raise ValueError(f"ไม่พบผู้ใช้ '{username}'")


def delete_user(username: str) -> None:
    """
    ⚠️ ห้ามลบผู้ดูแลระบบคนสุดท้าย — ไม่งั้นจะไม่มีใครเข้าหน้าตั้งค่า/จัดการผู้ใช้ได้อีก
       ต้องกลับไปใช้ manage.py บนเครื่อง ซึ่งคนใช้งานทั่วไปเข้าไม่ถึง
    """
    if _is_last_admin(username):
        raise ValueError("ลบไม่ได้ — นี่คือผู้ดูแลระบบคนสุดท้าย")
    res = get_db()["users"].delete_one({"username": username})
    if res.deleted_count == 0:
        raise ValueError(f"ไม่พบผู้ใช้ '{username}'")


def bootstrap_admin(username: str, password: str) -> bool:
    """
    สร้างแอดมินคนแรกจาก .env ตอนบูต — ทำเฉพาะตอนยังไม่มีผู้ใช้สักคน

    ⚠️ ไม่เขียนทับของเดิม เปลี่ยนรหัสใน .env ทีหลังจึงไม่มีผล ให้ใช้ manage.py passwd
    """
    if not (username and password) or get_db()["users"].count_documents({}) > 0:
        return False
    create_user(username, password, "admin")
    return True


def _is_last_admin(username: str) -> bool:
    db = get_db()
    user = db["users"].find_one({"username": username}, {"role": 1})
    if not user or user.get("role") != "admin":
        return False
    return db["users"].count_documents({"role": "admin"}) <= 1


def set_password(username: str, password: str) -> bool:
    if len(password) < 10:
        raise ValueError("รหัสผ่านต้องยาวอย่างน้อย 10 ตัว")
    res = get_db()["users"].update_one(
        {"username": username},
        # เปลี่ยนรหัส = ตัด session เก่าทุกเครื่อง เผื่อเปลี่ยนเพราะรหัสหลุด
        {"$set": {"password": generate_password_hash(password)}, "$inc": {"session_gen": 1}},
    )
    return res.matched_count > 0


def verify(username: str, password: str) -> str | None:
    """คืน role ถ้าถูกต้อง, None ถ้าไม่ถูก"""
    user = get_db()["users"].find_one({"username": username})
    if not user:
        return None
    if not check_password_hash(user.get("password", ""), password):
        return None
    return user.get("role", "staff")


# กันเดารหัสผ่าน — นับแยกทั้งต่อชื่อผู้ใช้และต่อ IP (เก็บในหน่วยความจำ เพราะมีโปรเซสเดียว)
#   ⚠️ ล็อกต่อชื่อผู้ใช้ทำให้คนอื่นแกล้งล็อกชื่อนี้ชั่วคราวได้ แต่กันการไล่เดาจากหลาย IP ได้
_LOGIN_MAX_FAILS = 10
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_TRACKED = 10000
_login_fails: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def login_keys(username: str, ip: str) -> list[str]:
    return [f"user:{username.lower()}", f"ip:{ip}"]


def _recent_fails(key: str, now: float) -> list[float]:
    return [t for t in _login_fails.get(key, []) if now - t < _LOGIN_WINDOW_SECONDS]


def login_locked(keys: list[str]) -> bool:
    now = time.time()
    with _login_lock:
        return any(len(_recent_fails(k, now)) >= _LOGIN_MAX_FAILS for k in keys)


def login_failed(keys: list[str]) -> None:
    now = time.time()
    with _login_lock:
        # กันคนสุ่มชื่อผู้ใช้ไม่ซ้ำจนหน่วยความจำบวม
        if len(_login_fails) >= _LOGIN_MAX_TRACKED:
            for key in list(_login_fails):
                if not _recent_fails(key, now):
                    del _login_fails[key]
        for key in keys:
            _login_fails[key] = _recent_fails(key, now) + [now]


def login_succeeded(keys: list[str]) -> None:
    """ล้างเฉพาะตัวนับของชื่อผู้ใช้ — ไม่ล้างของ IP ไม่งั้นล็อกอินยูสตัวเองสลับได้ไม่จำกัด"""
    with _login_lock:
        _login_fails.pop(keys[0], None)


def session_gen(username: str) -> int:
    user = get_db()["users"].find_one({"username": username}, {"session_gen": 1})
    return int((user or {}).get("session_gen") or 0)


# ── ยืนยันตัวตน 2 ชั้น (TOTP — Google Authenticator / Authy / 1Password) ──
#
# ⚠️ ระบบนี้ถือกุญแจ tunnel รหัสผ่านหลุดอย่างเดียวจึงไม่ควรพอให้เข้าได้
#    ใช้ TOTP มาตรฐาน (RFC 6238) ไม่ผูกกับ Google — แอป Authenticator ตัวไหนก็ใช้ได้

def totp_enabled(username: str) -> bool:
    user = get_db()["users"].find_one({"username": username}, {"totp_enabled": 1})
    return bool(user and user.get("totp_enabled"))


def totp_begin(username: str) -> dict:
    """
    เริ่มตั้งค่า — สร้าง secret ใหม่เก็บเป็น "รอยืนยัน" ยังไม่เปิดใช้จนกว่าจะพิสูจน์
    ได้ว่าแอปในมือถือสร้างรหัสถูกต้อง (ไม่งั้นสแกนพลาดแล้วล็อกตัวเองออกถาวร)
    """
    secret = pyotp.random_base32()
    get_db()["users"].update_one({"username": username}, {"$set": {"totp_pending": secret}})
    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)
    img = qrcode.make(uri, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "secret": secret,
        "uri":    uri,
        "qr":     "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
    }


def totp_confirm(username: str, code: str) -> None:
    """ยืนยันด้วยรหัสจากแอป แล้วเปิดใช้จริง"""
    user = get_db()["users"].find_one({"username": username}, {"totp_pending": 1})
    secret = (user or {}).get("totp_pending")
    if not secret:
        raise AuthError("ยังไม่ได้เริ่มตั้งค่า — กดสร้าง QR ใหม่")
    step = _match_step(secret, code)
    if step is None:
        raise AuthError("รหัส 6 หลักไม่ถูกต้อง — เช็คว่าเวลาบนมือถือตรงและสแกน QR ล่าสุด")
    get_db()["users"].update_one(
        {"username": username},
        {"$set": {"totp_secret": secret, "totp_enabled": True, "totp_last_step": step},
         "$unset": {"totp_pending": ""}},
    )


def totp_disable(username: str) -> None:
    get_db()["users"].update_one(
        {"username": username},
        {"$set": {"totp_enabled": False},
         "$unset": {"totp_secret": "", "totp_pending": "", "totp_last_step": ""}},
    )


def _match_step(secret: str, code: str) -> int | None:
    """
    คืนช่วงเวลา (time step) ที่รหัสนี้ตรง หรือ None ถ้าไม่ตรง — ยอมคลาดได้ ±1 ช่วง
    (30 วินาที) เผื่อนาฬิกามือถือกับเซิร์ฟเวอร์ต่างกันเล็กน้อย
    """
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now = int(time.time())
    for offset in (0, -1, 1):
        at = now + offset * TOTP_STEP
        if hmac.compare_digest(totp.at(at), code):
            return at // TOTP_STEP
    return None


# กันเดารหัส 6 หลัก — ผิดเกิน 5 ครั้งใน 5 นาที ต้องรอ (เก็บในหน่วยความจำ
# เพราะมีโปรเซสเดียว ดู serve.py)
_TOTP_MAX_FAILS = 5
_TOTP_LOCK_SECONDS = 300
_totp_fails: dict[str, list[float]] = {}
_totp_lock = threading.Lock()


def totp_locked(username: str) -> bool:
    now = time.time()
    with _totp_lock:
        recent = [t for t in _totp_fails.get(username, []) if now - t < _TOTP_LOCK_SECONDS]
        _totp_fails[username] = recent
        return len(recent) >= _TOTP_MAX_FAILS


def verify_totp(username: str, code: str) -> bool:
    """
    ตรวจรหัสตอน login — รหัสแต่ละช่วงใช้ได้ครั้งเดียว (กันคนแอบดูรหัสแล้วใช้ซ้ำ
    ภายใน 30 วินาทีเดียวกัน)
    """
    user = get_db()["users"].find_one(
        {"username": username}, {"totp_secret": 1, "totp_last_step": 1},
    )
    secret = (user or {}).get("totp_secret")
    step = _match_step(secret, code) if secret else None
    if step is None or step <= int(user.get("totp_last_step") or 0):
        with _totp_lock:
            _totp_fails.setdefault(username, []).append(time.time())
        return False
    get_db()["users"].update_one({"username": username}, {"$set": {"totp_last_step": step}})
    with _totp_lock:
        _totp_fails.pop(username, None)
    return True


def current_user() -> dict:
    return {
        "username": session.get("username", ""),
        "role":     session.get("role", ""),
    }


def is_admin() -> bool:
    return session.get("role") == "admin"


def session_valid() -> bool:
    """
    เช็ค session กับฐานข้อมูลทุกคำขอ

    ⚠️ cookie อยู่ได้ 7 วัน ถ้าเชื่อค่าใน cookie อย่างเดียว ยูสที่ถูกลบ ถูกลดสิทธิ์
       หรือถูกเปลี่ยนรหัส จะยังใช้สิทธิ์เดิมต่อได้จนกว่า cookie หมดอายุ
    """
    username = session.get("username")
    if not username:
        return False
    user = get_db()["users"].find_one({"username": username}, {"role": 1, "session_gen": 1})
    if not user or int(user.get("session_gen") or 0) != int(session.get("gen") or 0):
        session.clear()
        return False
    role = user.get("role", "staff")
    if session.get("role") != role:
        session["role"] = role
    return True


def login_required(fn):
    """
    ⚠️ ตอบ 401 เป็น JSON ไม่ใช่ redirect ไปหน้า login —
       ฝั่งหน้าเว็บเป็น SPA ที่เรียกด้วย fetch ถ้า redirect มันจะได้ HTML
       ของหน้า login กลับไปแทน JSON แล้วพังตอน parse โดยไม่บอกสาเหตุ
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session_valid():
            return jsonify({"error": "ต้องเข้าสู่ระบบก่อน"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session_valid():
            return jsonify({"error": "ต้องเข้าสู่ระบบก่อน"}), 401
        if not is_admin():
            return jsonify({"error": "ต้องเป็นผู้ดูแลระบบ"}), 403
        return fn(*args, **kwargs)
    return wrapper
