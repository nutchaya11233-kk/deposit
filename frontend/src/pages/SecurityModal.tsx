/*
  ยืนยันตัวตน 2 ชั้น ของตัวเอง — เปิดจากปุ่มในแถบด้านข้าง ทุก role ใช้ได้

  ⚠️ เปิดใช้เป็น 2 จังหวะโดยตั้งใจ: สร้าง QR → ผู้ใช้ต้องพิมพ์รหัสจากแอปให้ถูก
     ก่อนถึงจะเปิดจริง ถ้าเปิดทันทีตอนสร้าง QR แล้วผู้ใช้สแกนพลาด จะล็อกตัวเอง
     ออกจากระบบถาวรจนกว่าผู้ดูแลระบบจะรีเซ็ตให้
*/
import { useState, type FormEvent } from 'react'

import { api, ApiError, type TotpSetup, type User } from '../api'
import { Field, Modal, useToast } from '../ui'

export default function SecurityModal({
  user,
  onChanged,
  onClose,
}: {
  user: User
  onChanged: (user: User) => void
  onClose: () => void
}) {
  const toast = useToast()
  const [setup, setSetup] = useState<TotpSetup | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const begin = async () => {
    setBusy(true)
    setError('')
    try {
      setSetup(await api.totpSetup())
      setCode('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'สร้าง QR ไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  const enable = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.totpEnable(code)
      toast.ok('เปิดใช้ยืนยันตัวตน 2 ชั้นแล้ว — ครั้งหน้า login ต้องใส่รหัสจากแอปด้วย')
      onChanged({ ...user, totpEnabled: true })
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'ยืนยันไม่สำเร็จ')
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  const disable = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.totpDisable(code)
      toast.ok('ปิดยืนยันตัวตน 2 ชั้นแล้ว')
      onChanged({ ...user, totpEnabled: false })
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'ปิดไม่สำเร็จ')
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  const codeInput = (
    <input
      autoFocus
      inputMode="numeric"
      autoComplete="one-time-code"
      pattern="[0-9]*"
      maxLength={6}
      placeholder="000000"
      value={code}
      onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
      style={{ fontSize: 20, letterSpacing: 6, textAlign: 'center', maxWidth: 200 }}
    />
  )

  return (
    <Modal
      title="ยืนยันตัวตน 2 ชั้น"
      onClose={onClose}
      footer={
        <button className="btn" type="button" onClick={onClose}>
          ปิด
        </button>
      }
    >
      <p className="muted" style={{ marginTop: 0 }}>
        บัญชี <strong>{user.username}</strong> · สถานะ:{' '}
        {user.totpEnabled ? (
          <span className="tag ok">เปิดใช้อยู่</span>
        ) : (
          <span className="tag warn">ยังไม่ได้เปิด</span>
        )}
      </p>

      {user.totpEnabled ? (
        <form onSubmit={disable} className="grid" style={{ gap: 14 }}>
          <p className="muted" style={{ margin: 0 }}>
            ถ้าจะปิด ต้องใส่รหัสจากแอป Authenticator เพื่อยืนยันว่าเป็นคุณจริง
            (ถ้าเปลี่ยนมือถือใหม่ ให้ปิดจากเครื่องเก่าก่อน แล้วค่อยตั้งใหม่)
          </p>
          <Field label="รหัส 6 หลัก">{codeInput}</Field>
          {error && (
            <div className="banner danger">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}
          <div className="actions">
            <button className="btn danger" type="submit" disabled={busy || code.length !== 6}>
              {busy && <span className="spinner" />}
              ปิดยืนยันตัวตน 2 ชั้น
            </button>
          </div>
        </form>
      ) : !setup ? (
        <div className="grid" style={{ gap: 14 }}>
          <p className="muted" style={{ margin: 0 }}>
            เมื่อเปิดใช้ ทุกครั้งที่ login จะต้องใส่รหัส 6 หลักจากแอปในมือถือเพิ่มจากรหัสผ่าน
            ต่อให้รหัสผ่านหลุดก็ยังเข้าไม่ได้ ระบบนี้ถือกุญแจ tunnel ของคุณจึงแนะนำให้เปิดทุกคน
          </p>
          <ol className="muted" style={{ margin: 0, paddingLeft: 20 }}>
            <li>ลงแอป Google Authenticator (หรือ Authy, Microsoft Authenticator) ในมือถือ</li>
            <li>กดปุ่มด้านล่าง แล้วสแกน QR ด้วยแอป</li>
            <li>พิมพ์รหัส 6 หลักที่แอปแสดง เพื่อยืนยัน</li>
          </ol>
          {error && (
            <div className="banner danger">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}
          <div className="actions">
            <button className="btn primary" type="button" onClick={begin} disabled={busy}>
              {busy && <span className="spinner" />}
              เริ่มตั้งค่า — สร้าง QR
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={enable} className="grid" style={{ gap: 14 }}>
          <div style={{ textAlign: 'center' }}>
            <img
              src={setup.qr}
              alt="QR สำหรับสแกนด้วยแอป Authenticator"
              style={{ width: 220, height: 220, borderRadius: 10, background: '#fff', padding: 6 }}
            />
            <div className="sub" style={{ marginTop: 8 }}>
              สแกนไม่ได้? พิมพ์รหัสนี้ในแอปแทน
            </div>
            <code className="mono" style={{ fontSize: 13, userSelect: 'all', wordBreak: 'break-all' }}>
              {setup.secret}
            </code>
          </div>
          <Field label="รหัส 6 หลักจากแอป" note="รหัสเปลี่ยนทุก 30 วินาที ใส่ตัวที่แสดงอยู่ตอนนี้">
            {codeInput}
          </Field>
          {error && (
            <div className="banner danger">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}
          <div className="actions">
            <button className="btn primary" type="submit" disabled={busy || code.length !== 6}>
              {busy && <span className="spinner" />}
              ยืนยันและเปิดใช้
            </button>
            <button className="btn ghost" type="button" onClick={begin} disabled={busy}>
              สร้าง QR ใหม่
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}
