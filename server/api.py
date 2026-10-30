"""
API ทั้งหมดของหน้าเว็บ — JSON ล้วน ไม่มี HTML

ทุกเส้นทางอยู่ใต้ /api และคุยกับหน้าเว็บด้วย JSON เท่านั้น
หน้าเว็บเป็นไฟล์ static ที่ Flask เสิร์ฟจากที่เดียวกัน จึงเป็น same-origin
ไม่ต้องตั้ง CORS และ session cookie ใช้ได้ตรง ๆ
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, session

from server import auth, tunnels
from server.auth import admin_required, current_user, login_required, verify
from server.config import (
    TUNNEL_FRP_VERSION,
    TUNNEL_MAX_PER_USER,
    TUNNEL_SERVER_HOST,
    TUNNEL_SERVER_PORT,
    TUNNEL_TRANSPORT,
)
from server.db import get_db
from server.logger import log

bp = Blueprint("api", __name__, url_prefix="/api")


def _fail(message: str, code: int = 400):
    return jsonify({"error": message}), code


@bp.errorhandler(Exception)
def _unhandled(e):
    """
    ⚠️ ตอบ JSON เสมอแม้ตอนพัง — ถ้าปล่อยให้ Flask ส่งหน้า HTML error ออกไป
       หน้าเว็บจะ parse ไม่ออกแล้วขึ้นข้อความว่างเปล่าให้ผู้ใช้งง
    """
    if isinstance(e, (auth.AuthError, tunnels.TunnelError)):
        return _fail(str(e))
    log("ERROR", f"{request.method} {request.path} พัง: {e}")
    return _fail("ระบบขัดข้อง ลองใหม่อีกครั้ง", 500)


# ── เข้าสู่ระบบ ─────────────────────────────────────────────

@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    role = verify(username, password) if username and password else None
    if not role:
        log("WARN", f"เข้าสู่ระบบไม่สำเร็จ: {username or '(ไม่ระบุ)'}")
        return _fail("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", 401)

    # ขั้นที่ 2 — ถ้าผู้ใช้เปิด 2FA ไว้ ต้องมีรหัสจากแอป Authenticator ด้วย
    # ยังไม่สร้าง session จนกว่าจะผ่านทั้งสองขั้น
    two_factor = auth.totp_enabled(username)
    if two_factor:
        code = str(data.get("code") or "").strip()
        if not code:
            return jsonify({"needsCode": True})
        if auth.totp_locked(username):
            log("WARN", f"{username} ใส่รหัส 2FA ผิดหลายครั้ง — ล็อกชั่วคราว")
            return _fail("ใส่รหัสผิดหลายครั้ง รอ 5 นาทีแล้วลองใหม่", 429)
        if not auth.verify_totp(username, code):
            log("WARN", f"{username} ใส่รหัส 2FA ไม่ถูกต้อง")
            return _fail("รหัสยืนยัน 6 หลักไม่ถูกต้อง", 401)

    session.clear()
    session["username"] = username
    session["role"] = role
    session.permanent = True
    log("OK", f"{username} ({role}) เข้าสู่ระบบ{' (2FA)' if two_factor else ''}")
    return jsonify({"username": username, "role": role, "totpEnabled": two_factor})


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/auth/me")
def me():
    user = current_user()
    if not user["username"]:
        return _fail("ยังไม่ได้เข้าสู่ระบบ", 401)
    user["totpEnabled"] = auth.totp_enabled(user["username"])
    return jsonify(user)


# ── ยืนยันตัวตน 2 ชั้น ของตัวเอง ────────────────────────────

@bp.post("/auth/2fa/setup")
@login_required
def totp_setup():
    """สร้าง QR ใหม่ — ยังไม่เปิดใช้จนกว่าจะยืนยันรหัสได้ (ดู auth.totp_begin)"""
    return jsonify(auth.totp_begin(session["username"]))


@bp.post("/auth/2fa/enable")
@login_required
def totp_enable():
    data = request.get_json(silent=True) or {}
    auth.totp_confirm(session["username"], str(data.get("code") or ""))
    log("OK", f"{session['username']} เปิดใช้ 2FA")
    return jsonify({"ok": True})


@bp.post("/auth/2fa/disable")
@login_required
def totp_disable():
    """ปิดต้องใส่รหัสปัจจุบัน — กันคนที่ได้ session ค้าง (ลืม logout) มาปิดทิ้ง"""
    data = request.get_json(silent=True) or {}
    username = session["username"]
    if not auth.totp_enabled(username):
        return _fail("ยังไม่ได้เปิด 2FA")
    if auth.totp_locked(username):
        return _fail("ใส่รหัสผิดหลายครั้ง รอ 5 นาทีแล้วลองใหม่", 429)
    if not auth.verify_totp(username, str(data.get("code") or "")):
        return _fail("รหัสยืนยัน 6 หลักไม่ถูกต้อง", 401)
    auth.totp_disable(username)
    log("WARN", f"{username} ปิด 2FA")
    return jsonify({"ok": True})


# ── จัดการผู้ใช้ (เฉพาะผู้ดูแลระบบ) ─────────────────────────

@bp.get("/users")
@admin_required
def list_users():
    return jsonify(auth.list_users())


@bp.post("/users")
@admin_required
def add_user():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    try:
        auth.create_user(username, str(data.get("password") or ""), str(data.get("role") or "staff"))
    except ValueError as e:
        return _fail(str(e))
    log("OK", f"{session['username']} สร้างผู้ใช้ '{username}'")
    return jsonify({"ok": True}), 201


@bp.put("/users/<username>")
@admin_required
def edit_user(username):
    """แก้ role และ/หรือ ตั้งรหัสผ่านใหม่ — ส่งมาเฉพาะช่องที่จะเปลี่ยน"""
    data = request.get_json(silent=True) or {}
    role = str(data.get("role") or "")
    password = str(data.get("password") or "")
    try:
        if role:
            if username == session["username"] and role != "admin":
                return _fail("ลดสิทธิ์ตัวเองไม่ได้ — ให้ผู้ดูแลระบบคนอื่นทำ")
            auth.set_role(username, role)
        if password:
            if not auth.set_password(username, password):
                return _fail(f"ไม่พบผู้ใช้ '{username}'", 404)
    except ValueError as e:
        return _fail(str(e))
    log("OK", f"{session['username']} แก้ผู้ใช้ '{username}'"
               f"{' (role)' if role else ''}{' (รหัสผ่าน)' if password else ''}")
    return jsonify({"ok": True})


@bp.delete("/users/<username>")
@admin_required
def remove_user(username):
    if username == session["username"]:
        return _fail("ลบบัญชีตัวเองไม่ได้")
    try:
        auth.delete_user(username)
    except ValueError as e:
        return _fail(str(e))
    tunnels.delete_owner(get_db(), username)
    log("WARN", f"{session['username']} ลบผู้ใช้ '{username}' พร้อม tunnel ทั้งหมด")
    return jsonify({"ok": True})


@bp.post("/users/<username>/2fa/reset")
@admin_required
def reset_user_totp(username):
    """ใช้เมื่อผู้ใช้ทำมือถือหาย — ปิด 2FA ให้ เขาจะเข้าด้วยรหัสผ่านอย่างเดียวแล้วตั้งใหม่"""
    if not get_db()["users"].find_one({"username": username}, {"_id": 1}):
        return _fail(f"ไม่พบผู้ใช้ '{username}'", 404)
    auth.totp_disable(username)
    log("WARN", f"{session['username']} รีเซ็ต 2FA ของ '{username}'")
    return jsonify({"ok": True})


# ── Tunnel ──────────────────────────────────────────────────
#
#   ⚠️ ทุกเส้นทางผูกกับ session["username"] — ยูสเห็นและแตะได้เฉพาะของตัวเอง
#      แอดมินก็เช่นกัน แอดมินมีสิทธิ์เพิ่มลบยูส ไม่ใช่เข้า tunnel ของคนอื่น

def _download(text: str, filename: str):
    """ส่งเป็นไฟล์ให้โหลด — เอาไปวางข้าง frpc ได้ตรง ๆ"""
    res = Response(text, mimetype="application/toml")
    res.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return res


@bp.get("/tunnels")
@login_required
def list_tunnels():
    return jsonify({
        "serverHost":      TUNNEL_SERVER_HOST,
        "serverPort":      TUNNEL_SERVER_PORT,
        "transport":       TUNNEL_TRANSPORT,
        "frpVersion":      TUNNEL_FRP_VERSION,
        "maxPerUser":      TUNNEL_MAX_PER_USER,
        "statusAvailable": tunnels.status_available(),
        "tunnels":         tunnels.listing(get_db(), session["username"]),
    })


@bp.post("/tunnels")
@login_required
def add_tunnel():
    payload = request.get_json(silent=True) or {}
    return jsonify({"id": tunnels.create(get_db(), session["username"], payload)}), 201


@bp.delete("/tunnels/<tunnel_id>")
@login_required
def remove_tunnel(tunnel_id):
    reloaded = tunnels.delete(get_db(), session["username"], tunnel_id)
    log("WARN", f"{session['username']} ลบ tunnel {tunnel_id}")
    return jsonify({"ok": True, "reloaded": reloaded})


@bp.get("/tunnels/token")
@login_required
def tunnel_token():
    return jsonify({"token": tunnels.get_token(get_db(), session["username"])})


@bp.post("/tunnels/token/rotate")
@login_required
def rotate_tunnel_token():
    return jsonify(tunnels.rotate_token(get_db(), session["username"]))


@bp.get("/tunnels/frpc.toml")
@login_required
def download_all_frpc():
    return _download(tunnels.frpc_toml_all(get_db(), session["username"]), "frpc.toml")


@bp.get("/tunnels/<tunnel_id>/frpc.toml")
@login_required
def download_frpc(tunnel_id):
    doc = tunnels.get(get_db(), session["username"], tunnel_id)
    return _download(tunnels.frpc_toml(get_db(), doc), f"frpc-{doc['name']}.toml")


@bp.get("/tunnels/<tunnel_id>/setup")
@login_required
def tunnel_setup(tunnel_id):
    return jsonify(tunnels.setup(get_db(), session["username"], tunnel_id))
