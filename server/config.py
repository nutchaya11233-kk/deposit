"""
ค่าตั้งของระบบ — อ่านจาก .env อย่างเดียว

⚠️ token ของแต่ละยูสไม่อยู่ที่นี่ แต่อยู่ใน MongoDB collection `tunnel_tokens`
   แก้ผ่านหน้าเว็บ เพราะแต่ละคนมีของตัวเองและ rotate ได้เอง
"""
import os
import secrets

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _bool(name: str) -> bool:
    return os.getenv(name, "false").lower() in ("1", "true", "yes")


# ── ที่ต้องมี ────────────────────────────────────────────────
MONGODB_URI = os.getenv("MONGODB_URI", "")

# กุญแจเซ็น session cookie — ต้องคงที่ ไม่งั้นทุกคนหลุด login ตอนรีสตาร์ต
SECRET_KEY = os.getenv("SECRET_KEY", "")
SECRET_IS_EPHEMERAL = not SECRET_KEY
if SECRET_IS_EPHEMERAL:
    SECRET_KEY = secrets.token_hex(32)

# แอดมินคนแรก — สร้างให้ตอนบูตถ้ายังไม่มีผู้ใช้สักคน (ว่าง = ใช้ manage.py adduser แทน)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ── เว็บ ─────────────────────────────────────────────────────
WEB_PORT = _int("WEB_PORT", 5000)
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")

# cookie ต้องเป็น secure เมื่อขึ้น https จริง
COOKIE_SECURE = _bool("COOKIE_SECURE")

# ── Tunnel (frp) ─────────────────────────────────────────────
#   TUNNEL_TRANSPORT:
#     wss = frpc ต่อผ่าน Cloudflare (เมฆส้ม/Cloudflare Tunnel) — ซ่อน IP ของ VPS ได้
#     tcp = frpc ต่อตรงมาที่ VPS — TUNNEL_SERVER_HOST ต้องเป็น DNS-only (เมฆเทา)
TUNNEL_TRANSPORT    = "tcp" if os.getenv("TUNNEL_TRANSPORT", "wss").lower() == "tcp" else "wss"
TUNNEL_SERVER_HOST  = os.getenv("TUNNEL_SERVER_HOST", "")          # เช่น frp.example.com
# พอร์ตที่ frpc ต่อเข้ามา — ผ่าน Cloudflare คือ 443 เสมอ
TUNNEL_SERVER_PORT  = _int("TUNNEL_SERVER_PORT", 443 if TUNNEL_TRANSPORT == "wss" else 7000)
TUNNEL_BIND_PORT    = _int("TUNNEL_BIND_PORT", 7000)               # frps bindPort บน VPS
TUNNEL_MAX_PER_USER = _int("TUNNEL_MAX_PER_USER", 10)
TUNNEL_FRP_VERSION  = os.getenv("TUNNEL_FRP_VERSION", "0.61.1")

# โหมด public (เปิดพอร์ต ADB ออกเน็ตตรง ๆ) — ปิดไว้เป็นค่าเริ่มต้น เพราะพอร์ตนี้
# ไม่ผ่าน Cloudflare และเปิดเผย IP ของ VPS
TUNNEL_PUBLIC_ENABLED = _bool("TUNNEL_PUBLIC_ENABLED")
TUNNEL_PUBLIC_HOST    = os.getenv("TUNNEL_PUBLIC_HOST", "")        # ต้องเป็น DNS-only (เมฆเทา)
TUNNEL_PORT_MIN       = _int("TUNNEL_PORT_MIN", 20000)
TUNNEL_PORT_MAX       = _int("TUNNEL_PORT_MAX", 20099)

# path ของ frps.toml ที่เว็บเขียนให้ · ว่าง = ไม่เขียนไฟล์ (เช่นตอน dev)
TUNNEL_FRPS_CONFIG    = os.getenv("TUNNEL_FRPS_CONFIG", "")
# ไฟล์ trigger ที่ systemd path unit เฝ้าดู เพื่อ restart frps ตอนต้องตัดการเชื่อมต่อ
TUNNEL_RELOAD_TRIGGER = os.getenv("TUNNEL_RELOAD_TRIGGER", "")

# frps dashboard (อ่านสถานะ online/offline) — ผูกไว้ที่ 127.0.0.1 เท่านั้น
TUNNEL_DASHBOARD_URL      = os.getenv("TUNNEL_DASHBOARD_URL", "")  # เช่น http://127.0.0.1:7500
TUNNEL_DASHBOARD_USER     = os.getenv("TUNNEL_DASHBOARD_USER", "admin")
TUNNEL_DASHBOARD_PASSWORD = os.getenv("TUNNEL_DASHBOARD_PASSWORD", "")
