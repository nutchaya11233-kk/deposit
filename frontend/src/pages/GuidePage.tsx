/* วิธีใช้งาน — ตัวอย่างคำสั่งจริงอยู่ในปุ่ม "วิธีตั้งค่า" ของแต่ละ tunnel */

const STEPS: { title: string; body: string }[] = [
  {
    title: 'เปิด ADB over TCP บนมือถือ',
    body: 'เปิด Developer options แล้วเสียบ USB เข้าคอม สั่ง adb tcpip 5555 (มือถือที่ไม่ root ต้องทำใหม่ทุกครั้งหลังรีบูต)',
  },
  {
    title: 'สร้าง tunnel',
    body: 'เมนู "Tunnel ของฉัน" ตั้งชื่อเครื่อง เช่น device-01 แล้วกดสร้าง 1 tunnel ใช้กับมือถือ 1 เครื่อง',
  },
  {
    title: 'ตั้งค่าบนมือถือ',
    body: 'ลง Termux จาก F-Droid กด "วิธีตั้งค่า" แล้วคัดลอกคำสั่งไปวางทีละสเต็ป รอจนสถานะขึ้น "ออนไลน์"',
  },
  {
    title: 'ต่อ ADB',
    body: 'สั่ง adb connect ตามที่อยู่ในช่อง "เข้าที่" ของ tunnel นั้น ครั้งแรกให้กดอนุญาตบนหน้าจอมือถือ',
  },
]

const NOTES = [
  'tunnel และ token แยกรายยูส คนอื่นรวมถึงแอดมินจะไม่เห็นของคุณ',
  'อย่าแชร์ไฟล์ตั้งค่า เพราะในไฟล์มี token ของคุณ ใครได้ไปจะเข้ามือถือของคุณได้',
  'ถ้าไฟล์รั่ว ให้กด Rotate token แล้วตั้งค่าทุกเครื่องใหม่',
  'ใครต่อ ADB ติดจะคุมมือถือได้ทั้งเครื่อง ควรเปิด 2FA ของบัญชีนี้ไว้',
]

export default function GuidePage() {
  return (
    <div className="stack">
      <div className="card">
        <header>
          <h2>เริ่มใช้งาน</h2>
          <span className="hint">ใช้เวลาประมาณ 10 นาทีต่อเครื่อง</span>
        </header>
        <div className="body">
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            {STEPS.map((s) => (
              <li key={s.title} style={{ marginBottom: 12 }}>
                <strong>{s.title}</strong>
                <div className="muted" style={{ fontSize: 13 }}>{s.body}</div>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <div className="card">
        <header>
          <h2>ควรรู้</h2>
        </header>
        <div className="body">
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {NOTES.map((n) => (
              <li key={n} style={{ marginBottom: 6, fontSize: 13 }}>{n}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
