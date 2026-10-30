"""
เครื่องมือจัดการจากบรรทัดคำสั่ง — สร้างผู้ใช้ / เปลี่ยนรหัส / ดูรายชื่อ

    py -3 manage.py adduser somchai --role admin
    py -3 manage.py passwd somchai
    py -3 manage.py users
    py -3 manage.py 2fa-reset somchai        # ผู้ใช้ทำมือถือหาย เข้าไม่ได้

⚠️ รับรหัสผ่านทาง prompt เท่านั้น ไม่รับเป็น argument — argument จะติดอยู่ใน
   ประวัติของ shell และเห็นได้จาก `ps` ของผู้ใช้อื่นบนเครื่องเดียวกัน
"""
from __future__ import annotations

import argparse
import getpass
import sys

from server.auth import ROLES, create_user, set_password, totp_disable
from server.db import ensure_indexes, get_db
from server.logger import log


def _read_password() -> str:
    first = getpass.getpass("รหัสผ่านใหม่: ")
    second = getpass.getpass("พิมพ์ซ้ำอีกครั้ง: ")
    if first != second:
        raise SystemExit("รหัสผ่านสองครั้งไม่ตรงกัน")
    return first


def cmd_adduser(args) -> int:
    ensure_indexes()
    if get_db()["users"].find_one({"username": args.username}):
        log("ERROR", f"มีผู้ใช้ '{args.username}' อยู่แล้ว")
        return 1
    create_user(args.username, _read_password(), args.role)
    log("OK", f"สร้างผู้ใช้ '{args.username}' ({args.role}) แล้ว")
    return 0


def cmd_passwd(args) -> int:
    if not set_password(args.username, _read_password()):
        log("ERROR", f"ไม่พบผู้ใช้ '{args.username}'")
        return 1
    log("OK", f"เปลี่ยนรหัสผ่านของ '{args.username}' แล้ว")
    return 0


def cmd_users(_args) -> int:
    rows = list(get_db()["users"].find({}, {"username": 1, "role": 1}))
    if not rows:
        log("WARN", "ยังไม่มีผู้ใช้สักคน")
        return 0
    for row in rows:
        print(f"  {row.get('role', ''):<6} {row.get('username', '')}")
    return 0


def cmd_2fa_reset(args) -> int:
    """ทางออกเมื่อผู้ดูแลระบบคนเดียวทำมือถือหาย — ไม่มีใครในเว็บรีเซ็ตให้ได้แล้ว"""
    if not get_db()["users"].find_one({"username": args.username}):
        log("ERROR", f"ไม่พบผู้ใช้ '{args.username}'")
        return 1
    totp_disable(args.username)
    log("OK", f"ปิด 2FA ของ '{args.username}' แล้ว — เข้าด้วยรหัสผ่านอย่างเดียวได้ แล้วตั้งใหม่ในเว็บ")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="เครื่องมือจัดการ Tunnel Console")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("adduser", help="สร้างผู้ใช้ใหม่")
    p.add_argument("username")
    p.add_argument("--role", choices=ROLES, default="staff")
    p.set_defaults(func=cmd_adduser)

    p = sub.add_parser("passwd", help="เปลี่ยนรหัสผ่าน")
    p.add_argument("username")
    p.set_defaults(func=cmd_passwd)

    p = sub.add_parser("users", help="ดูรายชื่อผู้ใช้")
    p.set_defaults(func=cmd_users)

    p = sub.add_parser("2fa-reset", help="ปิด 2FA ของผู้ใช้ (กรณีมือถือหาย)")
    p.add_argument("username")
    p.set_defaults(func=cmd_2fa_reset)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (ValueError, RuntimeError) as e:
        # ⚠️ ตั้งค่าไม่ครบเป็นความผิดพลาดที่พบบ่อยที่สุดตอนติดตั้งครั้งแรก
        #    ต้องบอกวิธีแก้ ไม่ใช่พ่น traceback ให้คนอ่านเอาเอง
        log("ERROR", str(e))
        return 1
    except Exception as e:
        if "ServerSelection" in type(e).__name__ or "connect" in str(e).lower():
            log("ERROR", "ต่อ MongoDB ไม่ได้ — เช็ค MONGODB_URI ใน .env")
            log("ERROR", f"รายละเอียด: {str(e)[:200]}")
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
