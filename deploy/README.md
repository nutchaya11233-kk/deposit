# ติดตั้งบน VPS

หน้าเว็บและการต่อของ frpc วิ่งผ่าน **Cloudflare Tunnel** ส่วนพอร์ต ADB เปิดตรงที่ VPS

```
มือถือ (frpc) ──wss──► Cloudflare ─► cloudflared ─► frps (127.0.0.1:7000)
ผู้ใช้เว็บ ──https──► Cloudflare ─► cloudflared ─► เว็บ (127.0.0.1:5000)
adb บนคอม ──tcp──► tcp.example.com:20000 ─► frps ─► มือถือ
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
`ADMIN_PASSWORD` (รหัสอย่างน้อย 10 ตัว), `TUNNEL_SERVER_HOST=frp.example.com`,
`TUNNEL_PUBLIC_HOST=tcp.example.com` และ `TUNNEL_DASHBOARD_PASSWORD`

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

## 4. ต่อ Cloudflare Tunnel

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

## 5. เปิดพอร์ต ADB

เพิ่ม DNS record `A` ชื่อ `tcp` ชี้ไป IP ของ VPS แบบ **DNS only (เมฆเทา)**
เพราะ Cloudflare proxy ส่ง raw TCP ไม่ได้ แล้วเปิดพอร์ตที่ firewall:

```bash
sudo ufw allow 20000:20099/tcp
```

ถ้าใช้ Cloud Firewall ของผู้ให้บริการ VPS ต้องเปิดช่วงเดียวกันที่นั่นด้วย

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
