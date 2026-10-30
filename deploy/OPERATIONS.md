# คู่มือดูแลระบบบน VPS

รันด้วย root ทุกคำสั่ง ถ้าเข้าด้วยยูสอื่นให้สั่ง `sudo -i` ก่อน

## อัปเดตโค้ดใหม่

ฝั่งคอม: commit แล้ว push ขึ้น GitHub ถ้าแก้หน้าเว็บต้อง build ก่อน commit
เพราะ VPS ใช้ `frontend/dist` จาก repo โดยตรง

```bash
cd frontend && npm run build
```

ฝั่ง VPS:

```bash
cd /opt/tunnel-console && git pull && .venv/bin/pip install -r requirements.txt && chown -R app:app /opt/tunnel-console && systemctl restart tunnel-console
```

ถ้าฟ้อง `dubious ownership` ให้รันครั้งเดียว:

```bash
git config --global --add safe.directory /opt/tunnel-console
```

ถ้ารอบนั้นแก้ส่วนที่เขียน `frps.toml` ให้ restart frps ตามด้วย:

```bash
systemctl restart frps
```

## แก้ .env

```bash
nano /opt/tunnel-console/.env
```

```bash
systemctl restart tunnel-console
```

ถ้าแก้ค่า `TUNNEL_DASHBOARD_*` หรือ `TUNNEL_PORT_*`
ต้อง restart frps ต่อด้วย โดยเปิดเว็บก่อนเสมอ เพราะเว็บเป็นตัวเขียน `frps.toml`

```bash
sleep 5; systemctl restart frps
```

## Restart แต่ละตัว

| ตัว | หน้าที่ | คำสั่ง | ผลกระทบ |
|---|---|---|---|
| เว็บ | หน้าเว็บ + ตรวจ token | `systemctl restart tunnel-console` | เครื่องที่ต่ออยู่ไม่หลุด แต่เครื่องที่ต่อใหม่รอจนเว็บขึ้น |
| frps | ตัวรับ tunnel | `systemctl restart frps` | ทุกยูสหลุดสั้น ๆ แล้ว frpc ต่อกลับเอง |
| cloudflared | ทางเข้าจาก Cloudflare | `systemctl restart cloudflared` | เว็บและ frpc ผ่าน Cloudflare สะดุดสั้น ๆ |

ทั้งสามตัวเปิดเองหลังรีบูต VPS

## เช็กสถานะ

```bash
systemctl is-active tunnel-console frps cloudflared
```

```bash
curl http://127.0.0.1:5000/healthz
```

## ดู log

```bash
journalctl -u tunnel-console -n 50 --no-pager -l
```

```bash
journalctl -u frps -n 50 --no-pager -l
```

```bash
journalctl -u cloudflared -n 50 --no-pager -l
```

ดูสดให้เติม `-f` และกด Ctrl+C เพื่อออก

```bash
journalctl -u frps -f
```

⚠️ ก่อนส่ง log ให้คนอื่น ให้ตัดค่า token และรหัส MongoDB ออก

## จัดการผู้ใช้จากบรรทัดคำสั่ง

ปกติเพิ่มยูสจากเมนู **ผู้ใช้งาน** บนเว็บ คำสั่งนี้ใช้ตอนเข้าเว็บไม่ได้

```bash
cd /opt/tunnel-console && sudo -u app .venv/bin/python manage.py passwd admin
```

```bash
cd /opt/tunnel-console && sudo -u app .venv/bin/python manage.py 2fa-reset admin
```

```bash
cd /opt/tunnel-console && sudo -u app .venv/bin/python manage.py users
```

## มือถือรีบูต

ถ้ามือถือไม่ได้ root ต้องเปิด ADB over TCP ใหม่ทุกครั้ง

บนคอม เสียบ USB แล้วรัน:

```bash
adb tcpip 5555
```

ใน Termux:

```bash
termux-wake-lock
proot-distro login debian -- bash -c "cd ~/frp && ./frpc -c frpc.toml"
```

จากนั้นบนคอมต่อตามช่อง **เข้าที่** ของ tunnel:

```bash
adb connect tcp.monkey-dog.site:20000
```

## อาการที่พบบ่อย

| อาการ | เช็กอะไร |
|---|---|
| เว็บขึ้น 502 | `systemctl is-active tunnel-console` แล้วดู log ของเว็บ |
| เว็บล่มหลังเปลี่ยนรหัส MongoDB | รหัสใน `.env` และ IP ใน Network Access ของ Atlas |
| มือถือไม่ออนไลน์ | frpc ใน Termux ยังรันอยู่ไหม และดู log ของ frps |
| `invalid token` ใน log | เพิ่ง Rotate token หรือไม่ ถ้าใช่ ให้ตั้งค่า frpc ใหม่ |
| `adb connect` ต่อไม่ติด | สถานะออนไลน์ไหม และเปิดพอร์ต 20000–20099 ที่ firewall แล้วหรือยัง |
| สถานะขึ้น "ไม่ทราบ" | `TUNNEL_DASHBOARD_URL` และ `TUNNEL_DASHBOARD_PASSWORD` ใน `.env` |
