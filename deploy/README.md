# ติดตั้งบน VPS

แนะนำให้ติดตั้งผ่าน **Cloudflare Tunnel** ซึ่ง `cloudflared` บน VPS ต่อออกไปหา
Cloudflare เอง VPS จึงไม่ต้องเปิดพอร์ตขาเข้าเลย และ IP ของ VPS ไม่อยู่ใน DNS

```
มือถือ (frpc) ──wss──┐
                     ├─► Cloudflare ─► cloudflared ─► frps (127.0.0.1:7000)
คอม (visitor) ──wss──┘
ผู้ใช้เว็บ ──https──► Cloudflare ─► cloudflared ─► เว็บ (127.0.0.1:5000)
```

## 1. ลงตัวเว็บ

```bash
sudo useradd -r -m -d /opt/tunnel-console app
# คัดลอกโปรเจคไปที่ /opt/tunnel-console แล้ว
cd /opt/tunnel-console
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env              # กรอกค่าให้ครบ
(cd frontend && npm ci && npm run build)
mkdir -p frps
```

`.env` อย่างน้อยต้องมี `MONGODB_URI`, `SECRET_KEY`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD` (รหัสอย่างน้อย 10 ตัว), `TUNNEL_SERVER_HOST=frp.example.com`
และ `TUNNEL_DASHBOARD_PASSWORD`

แอดมินคนแรกถูกสร้างตอนบูตครั้งแรก หลังจากนั้นลบ `ADMIN_PASSWORD` ออกจาก `.env`
ได้เลย แล้วเพิ่มยูสจากเมนู **ผู้ใช้งาน** หรือสร้างแอดมินเองด้วย:

```bash
.venv/bin/python manage.py adduser admin --role admin
```

## 2. ลง frps

```bash
cd /opt/tunnel-console/frps
V=0.61.1                           # ให้ตรงกับ TUNNEL_FRP_VERSION
wget -O frp.tgz "https://github.com/fatedier/frp/releases/download/v${V}/frp_${V}_linux_amd64.tar.gz"
tar -xzf frp.tgz --strip-components=1 && rm frp.tgz
sudo chown -R app:app /opt/tunnel-console
```

## 3. เปิดบริการ

```bash
sudo cp deploy/tunnel-console.service deploy/frps.service deploy/frps-reload.service deploy/frps-reload.path /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tunnel-console   # ต้องขึ้นก่อน frps เพราะเป็นตัวเขียน frps.toml
sudo systemctl enable --now frps frps-reload.path
```

## 4. ซ่อน VPS ด้วย Cloudflare Tunnel

โดเมนต้องอยู่บน Cloudflare แล้ว

```bash
# ลง cloudflared ตามคู่มือของ Cloudflare จากนั้น
cloudflared tunnel login
cloudflared tunnel create tunnel-console     # จด <TUNNEL_ID>
cloudflared tunnel route dns tunnel-console panel.example.com
cloudflared tunnel route dns tunnel-console frp.example.com
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/<TUNNEL_ID>.json /etc/cloudflared/
sudo cp deploy/cloudflared.yml /etc/cloudflared/config.yml   # แก้ TUNNEL_ID และโดเมน
sudo cloudflared service install
```

ใน Cloudflare dashboard ของโดเมนนี้:

- SSL/TLS เป็น **Full** ขึ้นไป
- Security ปิด **Bot Fight Mode** ถ้า frpc ต่อไม่ติด เพราะ frpc ไม่ใช่เบราว์เซอร์

เมื่อเปิดเว็บผ่าน `https://panel.example.com` ได้แล้วจึงปิดพอร์ต:

```bash
sudo ufw default deny incoming
sudo ufw allow from <IP ที่คุณใช้ SSH> to any port 22 proto tcp
sudo ufw enable
```

ถ้า VPS เคยมี DNS record ชี้ตรงมาก่อน IP เก่าอาจยังอยู่ในประวัติ DNS สาธารณะ
การซ่อนเต็มรูปแบบควรใช้ IP ใหม่ที่ไม่เคยเปิดเผย

## ข้อจำกัดของการผ่าน Cloudflare

- Cloudflare ส่งได้แค่ HTTP/WebSocket จึงซ่อนได้เฉพาะ tunnel แบบ **private**
  (ใช้ visitor บนคอม)
- โหมด **public** เป็น raw TCP ต้องเปิดพอร์ตที่ VPS ใช้ DNS เมฆเทา และเปิดเผย IP
  เปิดใช้ด้วย `TUNNEL_PUBLIC_ENABLED=true`, `TUNNEL_PUBLIC_HOST` และ `ufw allow 20000:20099/tcp`
  **การเปิดโหมดนี้ทำให้ซ่อน IP ไม่ได้อีก**
- ADB วิ่งอ้อมผ่าน Cloudflare ความหน่วงจะสูงขึ้น งานสตรีมจอแบบ scrcpy อาจกระตุก
- ควรอ่านเงื่อนไขการใช้งานของ Cloudflare ก่อนส่งทราฟฟิกปริมาณมากผ่านแผนฟรี

## ไม่ใช้ Cloudflare

ตั้ง `TUNNEL_TRANSPORT=tcp`, `TUNNEL_SERVER_PORT=7000` ใช้ DNS เมฆเทา แล้ว
`sudo ufw allow 7000/tcp` กรณีนี้ต้องทำ https ให้หน้าเว็บเอง

## การแยกยูสทำงานยังไง

- frps ไม่มี token กลาง ทุก login และทุก proxy ถูกส่งมาถามเว็บที่
  `/internal/frp/<secret>` ซึ่งตรวจ token รายยูสและความเป็นเจ้าของ tunnel
  (`server/frp_plugin.py`)
- **เว็บล่ม = frpc ที่ต่อใหม่จะเข้าไม่ได้** แต่ตัวที่ต่ออยู่แล้วไม่หลุด
- การลบ tunnel, ลบยูส หรือ rotate token จะ restart frps เพื่อตัดการเชื่อมต่อเดิม
  ทุกยูสจึงหลุดสั้น ๆ แล้ว frpc ต่อกลับเอง ส่วนที่ถูกเพิกถอนจะต่อกลับไม่ได้
