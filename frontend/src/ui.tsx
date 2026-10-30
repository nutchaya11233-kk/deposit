/* ชิ้นส่วนหน้าจอที่ใช้ซ้ำหลายหน้า */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

/* ── ข้อความลอย ─────────────────────────────────────────── */

type ToastKind = 'ok' | 'danger'
interface Toast {
  id: number
  kind: ToastKind
  text: string
}

interface ToastApi {
  ok: (text: string) => void
  fail: (text: string) => void
}

const ToastContext = createContext<ToastApi>({ ok: () => {}, fail: () => {} })
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const seq = useRef(0)

  const push = useCallback((kind: ToastKind, text: string) => {
    const id = ++seq.current
    setItems((prev) => [...prev, { id, kind, text }])
    // ข้อความผิดพลาดค้างนานกว่า เพราะมักต้องอ่านแล้วแก้ตาม
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id))
    }, kind === 'danger' ? 7000 : 3500)
  }, [])

  const value = useMemo<ToastApi>(
    () => ({
      ok: (text) => push('ok', text),
      fail: (text) => push('danger', text),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} role="status">
            <span>{t.text}</span>
            <button
              className="btn ghost sm"
              onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))}
              aria-label="ปิด"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/* ── หน้าต่างซ้อน ───────────────────────────────────────── */

export function Modal({
  title,
  children,
  footer,
  onClose,
  wide,
}: {
  title: string
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
  wide?: boolean
}) {
  // ปิดด้วย Esc — คนที่พิมพ์เร็วคาดหวังแบบนี้ และเป็นทางออกเสมอเวลาปุ่มปิดหลุดจอ
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal" style={wide ? { maxWidth: 720 } : undefined} role="dialog" aria-modal="true">
        <header>
          <h2>{title}</h2>
        </header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  )
}

/* ── ยืนยันก่อนทำ ───────────────────────────────────────── */

export function Confirm({
  title,
  message,
  confirmLabel = 'ยืนยัน',
  danger,
  onConfirm,
  onClose,
}: {
  title: string
  message: ReactNode
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            ยกเลิก
          </button>
          <button
            className={`btn ${danger ? 'danger' : 'primary'}`}
            onClick={() => {
              onConfirm()
              onClose()
            }}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      {message}
    </Modal>
  )
}

/* ── สถานะว่าง ──────────────────────────────────────────── */

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {hint && <p>{hint}</p>}
    </div>
  )
}

/* ── ช่องกรอก ───────────────────────────────────────────── */

export function Field({
  label,
  note,
  children,
}: {
  label: string
  note?: string
  children: ReactNode
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {note && <span className="note">{note}</span>}
    </div>
  )
}
