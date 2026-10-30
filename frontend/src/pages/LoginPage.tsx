import { useState, type FormEvent } from 'react'

import { api, ApiError, type User } from '../api'
import { Field } from '../ui'

export default function LoginPage({ onSuccess }: { onSuccess: (user: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  // ขั้นที่ 2 — โชว์ช่องรหัส 6 หลักเมื่อหลังบ้านบอกว่าผู้ใช้คนนี้เปิด 2FA ไว้
  const [needsCode, setNeedsCode] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = await api.login(username.trim(), password, needsCode ? code : undefined)
      if ('needsCode' in result) {
        setNeedsCode(true)
        return
      }
      onSuccess(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'เข้าสู่ระบบไม่สำเร็จ')
      if (needsCode) {
        setCode('')
      } else {
        setPassword('')
      }
    } finally {
      setBusy(false)
    }
  }

  const back = () => {
    setNeedsCode(false)
    setCode('')
    setError('')
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="mark">฿</div>
        <h1>Tunnel Console</h1>
        <p className="muted" style={{ marginTop: 4, marginBottom: 22 }}>
          {needsCode ? 'ยืนยันตัวตนขั้นที่ 2' : 'เข้าสู่ระบบเพื่อใช้งาน'}
        </p>

        {needsCode ? (
          <div className="grid" style={{ gap: 14 }}>
            <Field label="รหัส 6 หลักจากแอป Authenticator" note={`บัญชี ${username.trim()}`}>
              <input
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={6}
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                style={{ fontSize: 22, letterSpacing: 8, textAlign: 'center' }}
              />
            </Field>
          </div>
        ) : (
          <div className="grid" style={{ gap: 14 }}>
            <Field label="ชื่อผู้ใช้">
              <input
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label="รหัสผ่าน">
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </div>
        )}

        {error && (
          <div className="banner danger" style={{ marginTop: 16 }}>
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <button
          className="btn primary block tall"
          type="submit"
          style={{ marginTop: 20 }}
          disabled={busy || (needsCode ? code.length !== 6 : !username.trim() || !password)}
        >
          {busy && <span className="spinner" />}
          {needsCode ? 'ยืนยัน' : 'เข้าสู่ระบบ'}
        </button>

        {needsCode && (
          <button className="btn ghost block" type="button" style={{ marginTop: 8 }} onClick={back}>
            ← กลับไปใส่รหัสผ่าน
          </button>
        )}
      </form>
    </div>
  )
}
