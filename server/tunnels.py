"""
Tunnel (frp) แยกรายยูส — มือถือรัน `frpc` ดันพอร์ต ADB ออกมาที่ `frps` บน VPS

การแยกยูส:
  • แต่ละยูสมี token ของตัวเอง frps ไม่รู้จัก token เหล่านี้ แต่ถาม plugin
    ของเรา (server/frp_plugin.py) ทุกครั้งที่ frpc login และเปิด proxy
  • frpc ตั้ง `user = "<ยูส>"` ทำให้ frp เติม "<ยูส>." หน้าชื่อ proxy ชื่อจึงซ้ำ
    ข้ามยูสได้ และ stcp จะยอมให้ visitor ของยูสเดียวกันเท่านั้นเข้าถึง

2 โหมดของ tunnel:
  • private (stcp) — ไม่เปิดพอร์ตบน VPS เลย คอมของเจ้าของรัน visitor แล้วได้พอร์ต
    ที่ 127.0.0.1 ทั้งสองฝั่งวิ่งผ่าน Cloudflare ได้ จึงซ่อน IP ของ VPS ได้จริง
  • public (tcp) — เปิด HOST:remotePort ออกเน็ต ใครก็ยิงมาที่พอร์ตนี้ได้ และเปิดเผย
    IP ของ VPS ใช้ได้ต่อเมื่อเปิด TUNNEL_PUBLIC_ENABLED

⚠️ Cloudflare ส่งได้แค่ HTTP/WebSocket — frpc จึงต้องใช้ transport wss ส่วนพอร์ต
   ของโหมด public เป็น raw TCP ที่ Cloudflare ส่งให้ไม่ได้ ต้องเป็น DNS-only เท่านั้น
"""
from __future__ import annotations

import os
import re
import secrets
import stat
from datetime import datetime, timezone
from urllib.parse import urlparse

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from server.config import (
    TUNNEL_BIND_PORT,
    TUNNEL_DASHBOARD_PASSWORD,
    TUNNEL_DASHBOARD_URL,
    TUNNEL_DASHBOARD_USER,
    TUNNEL_FRP_VERSION,
    TUNNEL_FRPS_CONFIG,
    TUNNEL_MAX_PER_USER,
    TUNNEL_PORT_MAX,
    TUNNEL_PORT_MIN,
    TUNNEL_PUBLIC_ENABLED,
    TUNNEL_PUBLIC_HOST,
    TUNNEL_RELOAD_TRIGGER,
    TUNNEL_SERVER_HOST,
    TUNNEL_SERVER_PORT,
    TUNNEL_TRANSPORT,
    WEB_PORT,
)
from server.logger import log

# ชื่อ tunnel = ชื่อ proxy ของ frp — จำกัดอักขระให้ปลอดภัยกับ TOML และสคริปต์
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
# ⚠️ ค่านี้ไปอยู่ใน `bash -c '...'` ของสคริปต์มือถือ ห้ามมี quote หรือช่องว่าง
LOCAL_IP_RE = re.compile(r"^[A-Za-z0-9.:-]{1,64}$")
MODES = ("private", "public")
# พอร์ตเริ่มต้นบนคอมของเจ้าของ tunnel (ฝั่ง visitor)
VISITOR_PORT_BASE = 15555


class TunnelError(Exception):
    """ข้อมูลที่ผู้ใช้กรอกไม่ถูกต้อง — ตอบกลับเป็น 400"""


# ── token รายยูส ────────────────────────────────────────────

def get_token(db, username: str) -> str:
    """token ของ frpc ของยูสนี้ — สร้างให้อัตโนมัติครั้งแรก"""
    doc = db["tunnel_tokens"].find_one({"_id": username})
    if doc:
        return doc["token"]
    token = secrets.token_hex(24)
    db["tunnel_tokens"].insert_one({
        "_id": username, "token": token, "updated_at": datetime.now(timezone.utc),
    })
    return token


def rotate_token(db, username: str) -> dict:
    """ออก token ใหม่ แล้ว restart frps เพื่อตัดการเชื่อมต่อที่ใช้ token เก่าอยู่"""
    token = secrets.token_hex(24)
    db["tunnel_tokens"].update_one(
        {"_id": username},
        {"$set": {"token": token, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    log("WARN", f"{username} rotate token — frpc ทุกเครื่องของยูสนี้ต้องตั้งใหม่")
    return {"token": token, "reloaded": trigger_reload()}


def plugin_secret(db) -> str:
    """ส่วนหนึ่งของ path ที่ frps ใช้เรียก plugin — กันคนนอกยิงมาตรง ๆ"""
    doc = db["app_settings"].find_one({"_id": "frp_plugin"})
    if doc:
        return doc["secret"]
    secret = secrets.token_hex(24)
    db["app_settings"].insert_one({"_id": "frp_plugin", "secret": secret})
    return secret


# ── frps.toml ───────────────────────────────────────────────

def _dashboard_bind() -> tuple[str, int]:
    if not TUNNEL_DASHBOARD_URL:
        return "127.0.0.1", 7500
    u = urlparse(TUNNEL_DASHBOARD_URL)
    return (u.hostname or "127.0.0.1"), (u.port or 7500)


def render_frps_toml(db) -> str:
    # wss มี cloudflared/reverse proxy อยู่ข้างหน้า frps ไม่ต้องรับจากภายนอกเลย
    bind_addr = "127.0.0.1" if TUNNEL_TRANSPORT == "wss" else "0.0.0.0"
    lines = [
        "# สร้างอัตโนมัติจากเว็บตอนบูต — อย่าแก้มือ จะถูกเขียนทับ",
        f'bindAddr = "{bind_addr}"',
        f"bindPort = {TUNNEL_BIND_PORT}",
        f"allowPorts = [{{ start = {TUNNEL_PORT_MIN}, end = {TUNNEL_PORT_MAX} }}]",
    ]
    # ⚠️ proxyBindAddr ค่าเริ่มต้นเท่ากับ bindAddr — ไม่ตั้ง พอร์ต public จะรับแค่ในเครื่อง
    if TUNNEL_PUBLIC_ENABLED:
        lines.append('proxyBindAddr = "0.0.0.0"')
    if TUNNEL_DASHBOARD_PASSWORD:
        dash_host, dash_port = _dashboard_bind()
        lines += [
            "",
            "[webServer]",
            f'addr = "{dash_host}"',
            f"port = {dash_port}",
            f'user = "{TUNNEL_DASHBOARD_USER}"',
            f'password = "{TUNNEL_DASHBOARD_PASSWORD}"',
        ]
    lines += [
        "",
        "# ทุก login และทุก proxy ต้องผ่าน plugin นี้ — token รายยูสตรวจที่นี่",
        "[[httpPlugins]]",
        'name = "per-user-auth"',
        f'addr = "127.0.0.1:{WEB_PORT}"',
        f'path = "/internal/frp/{plugin_secret(db)}"',
        'ops = ["Login", "NewProxy"]',
    ]
    return "\n".join(lines) + "\n"


def sync_frps_config(db) -> bool:
    """เขียน frps.toml ลงดิสก์ — คืน True ถ้าเขียนจริง"""
    if not TUNNEL_FRPS_CONFIG:
        return False
    try:
        os.makedirs(os.path.dirname(TUNNEL_FRPS_CONFIG) or ".", exist_ok=True)
        with open(TUNNEL_FRPS_CONFIG, "w", encoding="utf-8") as f:
            f.write(render_frps_toml(db))
        # ไฟล์นี้มี secret ของ plugin + รหัส dashboard
        try:
            os.chmod(TUNNEL_FRPS_CONFIG, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return True
    except OSError as e:
        log("ERROR", f"เขียน frps.toml ไม่ได้ ({TUNNEL_FRPS_CONFIG}): {e}")
        return False


def trigger_reload() -> bool:
    """
    สะกิดไฟล์ trigger ให้ systemd restart frps

    ⚠️ plugin ตรวจแค่ตอน login/เปิด proxy การลบ tunnel หรือ rotate token จึงไม่ตัด
       ของที่ต่ออยู่เอง ต้อง restart frps ทุกคนหลุดแป๊บเดียวแล้ว frpc ต่อกลับเอง
       ส่วนที่ถูกเพิกถอนจะต่อกลับไม่ได้
    """
    if not TUNNEL_RELOAD_TRIGGER:
        return False
    try:
        with open(TUNNEL_RELOAD_TRIGGER, "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        return True
    except OSError as e:
        log("ERROR", f"สะกิด reload frps ไม่ได้ ({TUNNEL_RELOAD_TRIGGER}): {e}")
        return False


# ── tunnel CRUD (ทุกฟังก์ชันผูกกับ owner) ───────────────────

def _alloc_remote_port(db) -> int:
    used = {
        d["remote_port"]
        for d in db["tunnels"].find({"remote_port": {"$exists": True}}, {"remote_port": 1})
    }
    for port in range(TUNNEL_PORT_MIN, TUNNEL_PORT_MAX + 1):
        if port not in used:
            return port
    raise TunnelError(f"พอร์ตเต็มช่วง {TUNNEL_PORT_MIN}-{TUNNEL_PORT_MAX} แล้ว")


def _alloc_visitor_port(db, owner: str) -> int:
    used = {
        d.get("visitor_port")
        for d in db["tunnels"].find({"owner": owner}, {"visitor_port": 1})
    }
    port = VISITOR_PORT_BASE
    while port in used:
        port += 1
    return port


def create(db, owner: str, payload: dict) -> str:
    name = str(payload.get("name") or "").strip()
    mode = str(payload.get("mode") or "private")
    local_ip = str(payload.get("localIp") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        local_port = int(payload.get("localPort") or 5555)
    except (TypeError, ValueError):
        raise TunnelError("พอร์ตในเครื่อง (Local Port) ต้องเป็นตัวเลข")

    if not NAME_RE.match(name):
        raise TunnelError(
            "ชื่อใช้ได้แค่ A-Z a-z 0-9 . _ - (ไม่เกิน 32 ตัว ไม่มีช่องว่าง) เช่น device-01"
        )
    if not LOCAL_IP_RE.match(local_ip):
        raise TunnelError("Local IP ไม่ถูกต้อง")
    if not (1 <= local_port <= 65535):
        raise TunnelError("พอร์ตในเครื่องต้องอยู่ระหว่าง 1-65535")
    if mode not in MODES:
        raise TunnelError("โหมดต้องเป็น private หรือ public")
    if mode == "public" and not TUNNEL_PUBLIC_ENABLED:
        raise TunnelError("ระบบนี้ปิดโหมด public ไว้ — ใช้โหมด private")
    if db["tunnels"].count_documents({"owner": owner}) >= TUNNEL_MAX_PER_USER:
        raise TunnelError(f"สร้างได้ไม่เกิน {TUNNEL_MAX_PER_USER} tunnel ต่อยูส")
    if db["tunnels"].find_one({"owner": owner, "name": name}):
        raise TunnelError(f"คุณมี tunnel ชื่อ '{name}' อยู่แล้ว")

    doc = {
        "owner": owner,
        "name": name,
        "mode": mode,
        "local_ip": local_ip,
        "local_port": local_port,
        "created_at": datetime.now(timezone.utc),
    }
    if mode == "public":
        doc["remote_port"] = _alloc_remote_port(db)
    else:
        doc["secret_key"] = secrets.token_hex(24)
        doc["visitor_port"] = _alloc_visitor_port(db, owner)
    try:
        result = db["tunnels"].insert_one(doc)
    except DuplicateKeyError:
        raise TunnelError("ชื่อหรือพอร์ตนี้เพิ่งถูกใช้ไป — ลองอีกครั้ง")
    log("OK", f"{owner} สร้าง tunnel '{name}' ({mode})")
    return str(result.inserted_id)


def get(db, owner: str, tunnel_id: str) -> dict:
    """⚠️ tunnel ของยูสอื่นตอบว่า "ไม่พบ" เหมือนกัน ไม่บอกว่ามีอยู่"""
    if not ObjectId.is_valid(tunnel_id):
        raise TunnelError("ไม่พบ tunnel นี้")
    doc = db["tunnels"].find_one({"_id": ObjectId(tunnel_id), "owner": owner})
    if not doc:
        raise TunnelError("ไม่พบ tunnel นี้")
    return doc


def delete(db, owner: str, tunnel_id: str) -> bool:
    """คืนว่าสั่งตัดการเชื่อมต่อของ tunnel นี้ได้ไหม"""
    doc = get(db, owner, tunnel_id)
    db["tunnels"].delete_one({"_id": doc["_id"]})
    return trigger_reload()


def delete_owner(db, owner: str) -> None:
    """ลบทุกอย่างของยูสนี้ — เรียกตอนลบผู้ใช้"""
    db["tunnels"].delete_many({"owner": owner})
    db["tunnel_tokens"].delete_one({"_id": owner})
    trigger_reload()


def proxy_name(doc: dict) -> str:
    """ชื่อจริงบน frps — frp เติม "<user>." ให้เอง"""
    return f"{doc['owner']}.{doc['name']}"


def endpoint_of(doc: dict) -> str:
    if doc.get("mode") == "public":
        host = TUNNEL_PUBLIC_HOST or TUNNEL_SERVER_HOST or "YOUR_SERVER"
        return f"{host}:{doc['remote_port']}"
    return f"127.0.0.1:{doc['visitor_port']}"


# ── สถานะ online/offline (จาก frps dashboard) ───────────────

def _status_map() -> dict[str, str]:
    """ชื่อ proxy → 'online'/'offline' จาก frps dashboard; ว่าง = อ่านไม่ได้"""
    if not status_available():
        return {}
    import requests
    result: dict[str, str] = {}
    try:
        for kind in ("tcp", "stcp"):
            res = requests.get(
                f"{TUNNEL_DASHBOARD_URL.rstrip('/')}/api/proxy/{kind}",
                auth=(TUNNEL_DASHBOARD_USER, TUNNEL_DASHBOARD_PASSWORD),
                timeout=3,
            )
            res.raise_for_status()
            for p in res.json().get("proxies") or []:
                result[p.get("name")] = p.get("status") or "offline"
    except Exception:
        # dashboard ล่ม/อ่านไม่ได้ ไม่ใช่เรื่องคอขาดบาดตาย — ให้ UI โชว์ "ไม่ทราบ"
        return {}
    return result


def status_available() -> bool:
    return bool(TUNNEL_DASHBOARD_URL and TUNNEL_DASHBOARD_PASSWORD)


def serialize(doc: dict, status_map: dict[str, str] | None = None) -> dict:
    if not status_map:
        status = "unknown"
    else:
        status = "online" if status_map.get(proxy_name(doc)) == "online" else "offline"
    return {
        "id":        str(doc["_id"]),
        "name":      doc.get("name", ""),
        "mode":      doc.get("mode", "private"),
        "localIp":   doc.get("local_ip", "127.0.0.1"),
        "localPort": int(doc.get("local_port", 5555)),
        "endpoint":  endpoint_of(doc),
        "status":    status,
        "createdAt": doc.get("created_at").isoformat() if doc.get("created_at") else "",
    }


def listing(db, owner: str) -> list[dict]:
    status_map = _status_map()
    rows = db["tunnels"].find({"owner": owner}).sort("created_at", 1)
    return [serialize(d, status_map) for d in rows]


# ── frpc.toml ───────────────────────────────────────────────

def _frpc_header(db, owner: str) -> str:
    lines = [
        f'serverAddr = "{TUNNEL_SERVER_HOST or "YOUR_SERVER"}"',
        f"serverPort = {TUNNEL_SERVER_PORT}",
        f'user = "{owner}"',
        # token รายยูสส่งผ่าน metadata ให้ plugin ตรวจ (ไม่ใช่ auth.token ของ frp)
        f'metadatas.token = "{get_token(db, owner)}"',
        # เน็ตมือถือหลุดบ่อย — ต่อไม่ติดแล้วให้ลองใหม่ ไม่ใช่ปิดตัว
        "loginFailExit = false",
    ]
    if TUNNEL_TRANSPORT == "wss":
        lines.append('transport.protocol = "wss"')
    return "\n".join(lines)


def _proxy_block(doc: dict) -> str:
    lines = [
        "[[proxies]]",
        f'name = "{doc["name"]}"',
        f'type = "{"tcp" if doc.get("mode") == "public" else "stcp"}"',
        f'localIP = "{doc.get("local_ip", "127.0.0.1")}"',
        f"localPort = {int(doc.get('local_port', 5555))}",
    ]
    if doc.get("mode") == "public":
        lines.append(f"remotePort = {int(doc['remote_port'])}")
    else:
        lines.append(f'secretKey = "{doc["secret_key"]}"')
    return "\n".join(lines)


def _visitor_block(doc: dict) -> str:
    return "\n".join([
        "[[visitors]]",
        f'name = "visit-{doc["name"]}"',
        'type = "stcp"',
        f'serverName = "{doc["name"]}"',
        f'secretKey = "{doc["secret_key"]}"',
        'bindAddr = "127.0.0.1"',
        f"bindPort = {int(doc['visitor_port'])}",
    ])


def frpc_toml(db, doc: dict) -> str:
    return _frpc_header(db, doc["owner"]) + "\n\n" + _proxy_block(doc) + "\n"


def frpc_toml_all(db, owner: str) -> str:
    """ทุก tunnel ของยูสนี้ในไฟล์เดียว — มือถือเครื่องเดียวดันหลายพอร์ต"""
    rows = db["tunnels"].find({"owner": owner}).sort("created_at", 1)
    blocks = [_proxy_block(d) for d in rows]
    body = ("\n\n".join(blocks) + "\n") if blocks else "# ยังไม่มี tunnel\n"
    return _frpc_header(db, owner) + "\n\n" + body


def visitor_toml(db, doc: dict) -> str:
    return _frpc_header(db, doc["owner"]) + "\n\n" + _visitor_block(doc) + "\n"


def visitor_toml_all(db, owner: str) -> str:
    """ทุก tunnel แบบ private ของยูสนี้ — คอมเครื่องเดียวเข้าได้ทุกมือถือ"""
    rows = db["tunnels"].find({"owner": owner, "mode": "private"}).sort("created_at", 1)
    blocks = [_visitor_block(d) for d in rows]
    body = ("\n\n".join(blocks) + "\n") if blocks else "# ยังไม่มี tunnel แบบ private\n"
    return _frpc_header(db, owner) + "\n\n" + body


# ── วิธีตั้งค่า ─────────────────────────────────────────────

def _termux_inner(db, doc: dict) -> str:
    """
    คำสั่งที่รันข้างใน Debian ผ่าน `bash -c '...'` — โหลด frpc + เขียน config + รัน

    ⚠️ binary ของ frp เป็น Linux ET_EXEC (ไม่ใช่ PIE) — Android 10+ รันตรงไม่ได้
       และ `proot ./frpc` เปล่า ๆ ก็ไม่ได้ ("unexpected e_type: 2") เพราะตัวโหลด
       เริ่มต้นของ proot รับ ET_EXEC ไม่ได้ ต้องให้ frpc เป็นลูกของ bash ที่อยู่ใน
       rootfs เต็มของ proot-distro — ทางนั้น proot handle ET_EXEC ได้ (ทดสอบจริงแล้ว)
    """
    toml = frpc_toml(db, doc)
    return "\n".join([
        "set -e",
        "apt-get update -y && apt-get install -y wget tar",
        "mkdir -p ~/frp && cd ~/frp",
        'case "$(uname -m)" in aarch64|arm64) A=arm64;; armv7l|armv8l|arm) A=arm;; *) A=amd64;; esac',
        f"V={TUNNEL_FRP_VERSION}",
        '[ -x ./frpc ] || { wget -O frp.tgz "https://github.com/fatedier/frp/releases/download/'
        'v${V}/frp_${V}_linux_${A}.tar.gz"; tar -xzf frp.tgz --strip-components=1; rm -f frp.tgz; }',
        # <<\EOF = ไม่ขยายตัวแปร (เท่ากับใส่ single quote) โดยไม่ต้องใช้ ' ที่ชนกับ bash -c
        "cat > frpc.toml <<\\FRPC_EOF",
        toml.rstrip("\n"),
        "FRPC_EOF",
        "./frpc -c ./frpc.toml",
    ])


def termux_steps(db, doc: dict) -> list[dict]:
    """
    แยกตรงคำสั่งที่รันนาน — ถ้า paste รวมกันทีเดียว คำสั่งช้า (pkg install /
    proot-distro install) จะ "กิน" บรรทัดที่ paste ตามหลังเข้า stdin ของมัน
    """
    return [
        {"label": "สเต็ป 1 — ลง proot-distro (รอจบก่อนทำสเต็ปถัดไป)",
         "cmd": "pkg install -y proot-distro"},
        {"label": "สเต็ป 2 — ลง Debian (รอจนโหลด rootfs เสร็จ กลับมา ~ $)",
         "cmd": "proot-distro install debian"},
        {"label": "สเต็ป 3 — โหลด frpc + เขียน config + รัน (วางก้อนเดียว)",
         "cmd": "termux-wake-lock\nproot-distro login debian --shared-tmp -- bash -c '"
                + _termux_inner(db, doc) + "'"},
    ]


def pc_steps(doc: dict) -> dict | None:
    """ฝั่งคอมของเจ้าของ tunnel — โหมด public ไม่ต้องใช้ visitor"""
    if doc.get("mode") == "public":
        return None
    v = TUNNEL_FRP_VERSION
    return {
        "download": f"https://github.com/fatedier/frp/releases/download/v{v}/frp_{v}_windows_amd64.zip",
        "run": "frpc.exe -c frpc-visitor.toml",
        "connect": f"adb connect {endpoint_of(doc)}",
    }


def reboot_steps() -> dict:
    """
    ⚠️ ถ้ามือถือไม่ได้ root: ADB over TCP (พอร์ต 5555) จะหายทุกครั้งที่รีบูต
       ต้องต่อ USB เข้าคอมแล้วสั่ง `adb tcpip 5555` เปิดใหม่ก่อน frpc ถึงจะดันได้
    """
    return {
        "pc": "adb tcpip 5555",
        "phone": 'termux-wake-lock\n'
                 'proot-distro login debian -- bash -c "cd ~/frp && ./frpc -c frpc.toml"',
    }


def setup(db, owner: str, tunnel_id: str) -> dict:
    doc = get(db, owner, tunnel_id)
    return {
        "summary":     serialize(doc, _status_map()),
        "termuxSteps": termux_steps(db, doc),
        "pc":          pc_steps(doc),
        "reboot":      reboot_steps(),
    }
