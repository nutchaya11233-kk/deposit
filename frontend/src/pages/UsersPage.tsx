/*
  จัดการผู้ใช้ (เฉพาะผู้ดูแลระบบ) — เพิ่ม / เปลี่ยน role / ตั้งรหัสใหม่ / ลบ / รีเซ็ต 2FA

  ⚠️ หลังบ้านกันไว้ว่าลบหรือลดสิทธิ์ผู้ดูแลระบบคนสุดท้ายไม่ได้ — ไม่งั้นจะไม่มีใคร
     เข้าหน้านี้ได้อีก ต้องกลับไปใช้ manage.py บนเครื่อง
*/
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { api, ApiError, type ManagedUser, type Role, type User } from '../api'
import { Confirm, Empty, Field, Modal, useToast } from '../ui'

const ROLE_LABEL: Record<Role, string> = { admin: 'ผู้ดูแลระบบ', staff: 'ผู้ใช้' }

export default function UsersPage({ me }: { me: User }) {
  const toast = useToast()
  const [rows, setRows] = useState<ManagedUser[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<ManagedUser | null>(null)
  const [deleting, setDeleting] = useState<ManagedUser | null>(null)
  const [resetting, setResetting] = useState<ManagedUser | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await api.users())
    } catch (e) {
      if (e instanceof ApiError && e.status !== 401) toast.fail(e.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  const run = async (action: () => Promise<unknown>, okMessage: string) => {
    try {
      await action()
      toast.ok(okMessage)
      load()
      return true
    } catch (e) {
      toast.fail(e instanceof ApiError ? e.message : 'ทำรายการไม่สำเร็จ')
      return false
    }
  }

  return (
    <div className="stack">
      <div className="card">
        <header>
          <h2>ผู้ใช้งาน</h2>
          <span className="hint">{rows.length} คน</span>
          <div className="spacer" style={{ flex: 1 }} />
          {loading && <span className="spinner" />}
          <button className="btn primary sm" onClick={() => setAdding(true)}>
            + เพิ่มผู้ใช้
          </button>
        </header>

        <div className="table-wrap">
          {rows.length === 0 ? (
            <Empty title="ยังไม่มีผู้ใช้" />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>ชื่อผู้ใช้</th>
                  <th>สิทธิ์</th>
                  <th>ยืนยันตัวตน 2 ชั้น</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => {
                  const self = u.username === me.username
                  return (
                    <tr key={u.username}>
                      <td>
                        <strong>{u.username}</strong>
                        {self && <div className="sub">คุณ</div>}
                      </td>
                      <td>
                        <span className={`tag ${u.role === 'admin' ? 'info' : ''}`}>
                          {ROLE_LABEL[u.role]}
                        </span>
                      </td>
                      <td>
                        {u.totpEnabled ? (
                          <span className="tag ok">เปิดแล้ว</span>
                        ) : (
                          <span className="tag warn">ยังไม่เปิด</span>
                        )}
                      </td>
                      <td className="right">
                        <div className="actions end">
                          <button className="btn ghost sm" onClick={() => setEditing(u)}>
                            แก้ไข
                          </button>
                          {u.totpEnabled && !self && (
                            <button className="btn ghost sm" onClick={() => setResetting(u)}>
                              รีเซ็ต 2FA
                            </button>
                          )}
                          {!self && (
                            <button className="btn danger sm" onClick={() => setDeleting(u)}>
                              ลบ
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {adding && (
        <UserForm
          title="เพิ่มผู้ใช้"
          onClose={() => setAdding(false)}
          onSubmit={async (data) => {
            if (await run(() => api.addUser({ username: data.username, password: data.password, role: data.role }), `สร้างผู้ใช้ '${data.username}' แล้ว`)) {
              setAdding(false)
            }
          }}
        />
      )}

      {editing && (
        <UserForm
          title={`แก้ไข ${editing.username}`}
          existing={editing}
          lockRole={editing.username === me.username}
          onClose={() => setEditing(null)}
          onSubmit={async (data) => {
            const changes: { role?: Role; password?: string } = {}
            if (data.role !== editing.role) changes.role = data.role
            if (data.password) changes.password = data.password
            if (!changes.role && !changes.password) {
              setEditing(null)
              return
            }
            if (await run(() => api.editUser(editing.username, changes), 'บันทึกแล้ว')) {
              setEditing(null)
            }
          }}
        />
      )}

      {deleting && (
        <Confirm
          title="ลบผู้ใช้นี้?"
          danger
          confirmLabel="ลบผู้ใช้"
          message={
            <p style={{ margin: 0 }}>
              <strong>{deleting.username}</strong> จะเข้าระบบไม่ได้อีก
              และ tunnel ทั้งหมดของเขาจะถูกลบไปด้วย
            </p>
          }
          onConfirm={async () => {
            await run(() => api.deleteUser(deleting.username), `ลบ '${deleting.username}' แล้ว`)
            setDeleting(null)
          }}
          onClose={() => setDeleting(null)}
        />
      )}

      {resetting && (
        <Confirm
          title="รีเซ็ตยืนยันตัวตน 2 ชั้น?"
          danger
          confirmLabel="รีเซ็ต 2FA"
          message={
            <p style={{ margin: 0 }}>
              ใช้เมื่อ <strong>{resetting.username}</strong> ทำมือถือหายหรือลบแอปไป
              หลังรีเซ็ตเขาจะเข้าด้วยรหัสผ่านอย่างเดียวได้ แล้วควรไปตั้ง 2FA ใหม่ทันที
            </p>
          }
          onConfirm={async () => {
            await run(() => api.resetUserTotp(resetting.username), `รีเซ็ต 2FA ของ '${resetting.username}' แล้ว`)
            setResetting(null)
          }}
          onClose={() => setResetting(null)}
        />
      )}
    </div>
  )
}

function UserForm({
  title,
  existing,
  lockRole,
  onClose,
  onSubmit,
}: {
  title: string
  existing?: ManagedUser
  lockRole?: boolean
  onClose: () => void
  onSubmit: (data: { username: string; password: string; role: Role }) => Promise<void>
}) {
  const [username, setUsername] = useState(existing?.username ?? '')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>(existing?.role ?? 'staff')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await onSubmit({ username: username.trim(), password, role })
    } finally {
      setBusy(false)
    }
  }

  const passwordTooShort = password.length > 0 && password.length < 10
  const canSubmit = existing
    ? !passwordTooShort
    : username.trim().length >= 2 && password.length >= 10

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            ยกเลิก
          </button>
          <button className="btn primary" type="submit" form="user-form" disabled={busy || !canSubmit}>
            {busy && <span className="spinner" />}
            บันทึก
          </button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="grid" style={{ gap: 14 }}>
        <Field label="ชื่อผู้ใช้" note={existing ? undefined : 'a-z, 0-9, _ . - ยาว 2-32 ตัว'}>
          <input
            autoFocus={!existing}
            autoComplete="off"
            value={username}
            disabled={!!existing}
            onChange={(e) => setUsername(e.target.value)}
          />
        </Field>
        <Field
          label={existing ? 'ตั้งรหัสผ่านใหม่' : 'รหัสผ่าน'}
          note={existing ? 'เว้นว่างไว้ถ้าไม่เปลี่ยน · อย่างน้อย 10 ตัว' : 'อย่างน้อย 10 ตัว'}
        >
          <input
            type="password"
            autoComplete="new-password"
            autoFocus={!!existing}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Field
          label="สิทธิ์"
          note={lockRole ? 'ลดสิทธิ์ตัวเองไม่ได้ — ให้ผู้ดูแลระบบคนอื่นทำ' : undefined}
        >
          <select value={role} disabled={lockRole} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="staff">ผู้ใช้ — สร้างและจัดการ tunnel ของตัวเอง</option>
            <option value="admin">ผู้ดูแลระบบ — เพิ่ม/แก้/ลบผู้ใช้ และมี tunnel ของตัวเอง</option>
          </select>
        </Field>
      </form>
    </Modal>
  )
}
