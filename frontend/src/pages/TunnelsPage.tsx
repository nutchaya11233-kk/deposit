/*
  Tunnel ของฉัน — สร้าง/ดู/ลบ tunnel ของตัวเอง และ token ของตัวเอง

  ⚠️ หลังบ้านกรองตามคนที่ login อยู่ หน้านี้จึงเห็นเฉพาะของตัวเองเสมอ
     รวมถึงแอดมินด้วย
*/
import { useCallback, useEffect, useState } from 'react'

import {
  api,
  ApiError,
  frpcUrl,
  type Tunnel,
  type TunnelList,
  type TunnelSetup,
} from '../api'
import { Confirm, Empty, Field, Modal, useToast } from '../ui'

const STATUS_LOOK: Record<Tunnel['status'], { label: string; tone: string; live?: boolean }> = {
  online:  { label: 'ออนไลน์', tone: 'ok', live: true },
  offline: { label: 'ยังไม่ต่อ', tone: 'info' },
  unknown: { label: 'ไม่ทราบ', tone: 'info' },
}

const POLL_MS = 10000
const EMPTY_DRAFT = { name: '', localIp: '127.0.0.1', localPort: '5555' }

/* ── ปุ่มคัดลอก ─────────────────────────────────────────── */

function CopyButton({ text, label = 'คัดลอก', className = 'btn ghost sm' }: {
  text: string
  label?: string
  className?: string
}) {
  const toast = useToast()
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast.ok('คัดลอกแล้ว')
    } catch {
      // clipboard API ใช้ไม่ได้ (http หรือเบราว์เซอร์เก่า) — เลือกข้อความให้ผู้ใช้กด copy เอง
      toast.fail('คัดลอกอัตโนมัติไม่ได้ — เลือกข้อความแล้วกด Ctrl+C')
    }
  }
  return (
    <button type="button" className={className} onClick={copy}>
      ⧉ {label}
    </button>
  )
}

function CodeBlock({ text }: { text: string }) {
  return (
    <div className="codeblock">
      <CopyButton text={text} className="btn sm copy" />
      <pre>{text}</pre>
    </div>
  )
}

/* ── หน้าต่างวิธีตั้งค่า ─────────────────────────────────── */

function SetupModal({ tunnelId, onClose }: { tunnelId: string; onClose: () => void }) {
  const toast = useToast()
  const [data, setData] = useState<TunnelSetup | null>(null)

  useEffect(() => {
    api
      .tunnelSetup(tunnelId)
      .then(setData)
      .catch((e) => {
        toast.fail(e instanceof ApiError ? e.message : 'โหลดวิธีตั้งค่าไม่ได้')
        onClose()
      })
  }, [tunnelId, toast, onClose])

  return (
    <Modal title="วิธีตั้งค่า" onClose={onClose} wide>
      {!data ? (
        <div className="row">
          <span className="spinner" /> กำลังโหลด…
        </div>
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="banner info">
            <span>ℹ️</span>
            <span>
              <strong>{data.summary.name}</strong>
              หลังตั้งค่าบนมือถือ เข้าได้ที่ <code>{data.summary.endpoint}</code>
            </span>
          </div>

          <div className="stack" style={{ gap: 16 }}>
            <strong style={{ fontSize: 14 }}>ฝั่งมือถือ (Termux)</strong>
            <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>
              ลง Termux จาก F-Droid (เวอร์ชัน Play Store เก่าเกิน) · ทำ<strong>ทีละสเต็ป</strong> รอแต่ละอัน
              ขึ้น <code>~ $</code> ก่อนค่อยทำตัวถัดไป
            </p>
            {data.termuxSteps.map((s, i) => (
              <div key={i}>
                <strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>{s.label}</strong>
                <CodeBlock text={s.cmd} />
              </div>
            ))}
          </div>

          <div className="stack" style={{ gap: 10 }}>
            <strong style={{ fontSize: 14 }}>ฝั่งคอม</strong>
            <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>
              รอสถานะขึ้นออนไลน์ แล้วต่อ ADB:
            </p>
            <CodeBlock text={data.connect} />
          </div>

          <div>
            <strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
              หลังเปิดเครื่องใหม่ (รีบูต)
            </strong>
            <p className="muted" style={{ fontSize: 12.5, margin: '0 0 10px' }}>
              ADB over TCP หายทุกครั้งที่รีบูต (ถ้ามือถือไม่ root) — ต่อ USB เข้าคอมเปิดใหม่ก่อน แล้วค่อยปลุก frpc
            </p>
            <p className="muted" style={{ fontSize: 12, margin: '0 0 4px' }}>1) บนคอม (เสียบ USB):</p>
            <CodeBlock text={data.reboot.pc} />
            <p className="muted" style={{ fontSize: 12, margin: '10px 0 4px' }}>2) ในมือถือ (Termux):</p>
            <CodeBlock text={data.reboot.phone} />
          </div>
        </div>
      )}
    </Modal>
  )
}

/* ── หน้าหลัก ────────────────────────────────────────────── */

export default function TunnelsPage({ onGuide }: { onGuide: () => void }) {
  const toast = useToast()
  const [info, setInfo] = useState<TunnelList | null>(null)
  const [draft, setDraft] = useState(EMPTY_DRAFT)
  const [busy, setBusy] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const [setupId, setSetupId] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState<Tunnel | null>(null)
  const [confirmRotate, setConfirmRotate] = useState(false)

  const load = useCallback(async () => {
    try {
      setInfo(await api.tunnels())
    } catch (e) {
      if (e instanceof ApiError && e.status !== 401) toast.fail(e.message)
    }
  }, [toast])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  const create = async () => {
    setBusy(true)
    try {
      const { id } = await api.createTunnel({
        name: draft.name.trim(),
        localIp: draft.localIp.trim() || '127.0.0.1',
        localPort: Number(draft.localPort) || 5555,
      })
      toast.ok('สร้าง tunnel แล้ว')
      setDraft(EMPTY_DRAFT)
      setSetupId(id)
      load()
    } catch (e) {
      toast.fail(e instanceof ApiError ? e.message : 'สร้างไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  const rotate = async () => {
    setBusy(true)
    try {
      const res = await api.rotateTunnelToken()
      setToken(res.token)
      toast.ok(
        res.reloaded
          ? 'ออก token ใหม่แล้ว — ตั้งค่า frpc ทุกเครื่องของคุณใหม่'
          : 'ออก token ใหม่แล้ว — เครื่องที่ต่ออยู่ยังไม่หลุดจนกว่าจะ restart frps',
      )
    } catch (e) {
      toast.fail(e instanceof ApiError ? e.message : 'rotate ไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  const showToken = async () => {
    try {
      setToken((await api.tunnelToken()).token)
    } catch (e) {
      toast.fail(e instanceof ApiError ? e.message : 'อ่าน token ไม่ได้')
    }
  }

  const remove = async (t: Tunnel) => {
    try {
      const res = await api.deleteTunnel(t.id)
      toast.ok(
        res.reloaded
          ? `ลบ tunnel '${t.name}' แล้ว`
          : `ลบ '${t.name}' แล้ว — เครื่องที่ต่ออยู่ยังไม่หลุดจนกว่าจะ restart frps`,
      )
      load()
    } catch (e) {
      toast.fail(e instanceof ApiError ? e.message : 'ลบไม่สำเร็จ')
    }
  }

  if (!info) {
    return (
      <div className="card">
        <div className="body">
          <Empty title="กำลังโหลด…" />
        </div>
      </div>
    )
  }

  return (
    <div className="stack">
      {!info.serverHost && (
        <div className="banner danger">
          <span>⚠️</span>
          <span>
            <strong>ผู้ดูแลระบบยังไม่ได้ตั้ง TUNNEL_SERVER_HOST</strong>
            ไฟล์ตั้งค่าจะยังใช้จริงไม่ได้จนกว่าจะตั้งโดเมนใน <code>.env</code>
          </span>
        </div>
      )}

      {/* ── สร้าง tunnel ─────────────────────────────── */}
      <div className="card">
        <header>
          <h2>สร้าง tunnel</h2>
          <span className="hint">
            {info.tunnels.length}/{info.maxPerUser} · 1 tunnel = 1 มือถือ ·{' '}
            <a href="#" onClick={(e) => { e.preventDefault(); onGuide() }}>วิธีใช้งาน</a>
          </span>
        </header>
        <div className="body">
          <div className="grid two">
            <Field label="ชื่อ" note="A-Z a-z 0-9 . _ - เช่น device-01">
              <input
                placeholder="device-01"
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
              />
            </Field>
            <Field label="Local IP" note="ที่อยู่ของ ADB ในตัวมือถือเอง">
              <input
                className="mono"
                value={draft.localIp}
                onChange={(e) => setDraft((d) => ({ ...d, localIp: e.target.value }))}
              />
            </Field>
            <Field label="Local Port" note="พอร์ต ADB บนมือถือ (ปกติ 5555)">
              <input
                className="mono"
                inputMode="numeric"
                value={draft.localPort}
                onChange={(e) => setDraft((d) => ({ ...d, localPort: e.target.value }))}
              />
            </Field>
          </div>
          <div className="actions" style={{ marginTop: 16 }}>
            <button className="btn primary" disabled={busy || !draft.name.trim()} onClick={create}>
              {busy && <span className="spinner" />}
              สร้าง
            </button>
          </div>
        </div>
      </div>

      {/* ── รายการ tunnel ────────────────────────────── */}
      <div className="card">
        <header>
          <h2>Tunnel ของฉัน</h2>
          <div style={{ flex: 1 }} />
          {info.tunnels.length > 0 && (
            <a className="btn ghost sm" href={frpcUrl()} download>
              ⤓ frpc.toml (รวมทุกอัน)
            </a>
          )}
        </header>
        <div className="body" style={{ padding: info.tunnels.length ? 0 : undefined }}>
          {info.tunnels.length === 0 ? (
            <Empty title="ยังไม่มี tunnel" hint="สร้างอันแรกจากฟอร์มด้านบน" />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ชื่อ</th>
                    <th>เข้าที่</th>
                    <th>ในมือถือ</th>
                    <th>สถานะ</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {info.tunnels.map((t) => {
                    const look = STATUS_LOOK[t.status]
                    return (
                      <tr key={t.id}>
                        <td><strong>{t.name}</strong></td>
                        <td>
                          <div className="copyline">
                            <code>{t.endpoint}</code>
                            <CopyButton text={t.endpoint} label="" />
                          </div>
                        </td>
                        <td className="mono">{t.localIp}:{t.localPort}</td>
                        <td>
                          <span className={`tag ${look.tone}`}>
                            <span className={`dot${look.live ? ' live' : ''}`} />
                            {look.label}
                          </span>
                        </td>
                        <td>
                          <div className="row" style={{ justifyContent: 'flex-end' }}>
                            <button className="btn sm" onClick={() => setSetupId(t.id)}>
                              วิธีตั้งค่า
                            </button>
                            <a className="btn ghost sm" href={frpcUrl(t.id)} download>
                              frpc.toml
                            </a>
                            <button className="btn danger sm" onClick={() => setConfirmDel(t)}>
                              ลบ
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {!info.statusAvailable && info.tunnels.length > 0 && (
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          * สถานะออนไลน์/ออฟไลน์จะโชว์ได้เมื่อผู้ดูแลระบบตั้ง frps dashboard ไว้
        </p>
      )}

      {/* ── token ของตัวเอง ──────────────────────────── */}
      <div className="card">
        <header>
          <h2>Token ของฉัน</h2>
          <span className="hint">อยู่ในไฟล์ตั้งค่าอยู่แล้ว ไม่ต้องกรอกเอง</span>
        </header>
        <div className="body">
          <p className="muted" style={{ fontSize: 12.5, margin: '0 0 12px' }}>
            token นี้เป็นของคุณคนเดียว ถ้า rotate จะกระทบเฉพาะเครื่องของคุณ ซึ่งต้องตั้งค่าใหม่ทุกเครื่อง
          </p>
          {token && (
            <div className="copyline" style={{ marginBottom: 12 }}>
              <code>{token}</code>
              <CopyButton text={token} />
            </div>
          )}
          <div className="actions">
            <button className="btn danger" disabled={busy} onClick={() => setConfirmRotate(true)}>
              {busy && <span className="spinner" />}
              Rotate token
            </button>
            {!token && (
              <button className="btn ghost" onClick={showToken}>
                แสดง token
              </button>
            )}
          </div>
        </div>
      </div>

      {confirmRotate && (
        <Confirm
          title="Rotate token — เครื่องของคุณจะหลุดทุกเครื่อง"
          danger
          confirmLabel="ยืนยัน Rotate"
          message={
            <>
              ไฟล์ตั้งค่าเดิมของ<strong>ทุกเครื่องของคุณ</strong>จะใช้ไม่ได้ จนกว่าจะตั้งค่าใหม่ —
              ทำเฉพาะตอน token รั่วจริง ๆ
            </>
          }
          onConfirm={rotate}
          onClose={() => setConfirmRotate(false)}
        />
      )}

      {setupId && <SetupModal tunnelId={setupId} onClose={() => setSetupId(null)} />}
      {confirmDel && (
        <Confirm
          title="ลบ tunnel"
          danger
          confirmLabel="ลบ"
          message={<>ลบ <strong>{confirmDel.name}</strong>? มือถือเครื่องนี้จะต่อไม่ได้อีก</>}
          onConfirm={() => remove(confirmDel)}
          onClose={() => setConfirmDel(null)}
        />
      )}
    </div>
  )
}
