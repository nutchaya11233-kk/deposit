/*
  ทางเดียวที่หน้าเว็บคุยกับหลังบ้าน

  ⚠️ ห้ามเรียก fetch ตรง ๆ จากที่อื่น — การจัดการ 401 (session หมดอายุ)
     กับการแกะข้อความ error ต้องอยู่ที่เดียว ไม่งั้นบางหน้าจะเด้งกลับไป
     หน้า login บางหน้าค้างเงียบ ๆ แล้วผู้ใช้ไม่รู้ว่าเกิดอะไรขึ้น
*/

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** ผู้ฟังเหตุการณ์ "session หมดอายุ" — App ใช้เด้งกลับหน้า login */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      headers: init.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    // แยกให้ชัดว่าเป็นเน็ต/เซิร์ฟเวอร์ล่ม ไม่ใช่ข้อมูลผิด —
    // สองอย่างนี้ผู้ใช้ต้องทำต่างกัน (รอ vs แก้ที่กรอก)
    throw new ApiError('ติดต่อเซิร์ฟเวอร์ไม่ได้ — เช็คว่าระบบยังทำงานอยู่ไหม', 0)
  }

  if (res.status === 401 && path !== '/auth/login') {
    onUnauthorized?.()
    throw new ApiError('หมดเวลาใช้งาน กรุณาเข้าสู่ระบบใหม่', 401)
  }

  const text = await res.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!res.ok) {
    const message =
      (body as { error?: string } | null)?.error ?? `เซิร์ฟเวอร์ตอบ ${res.status}`
    throw new ApiError(message, res.status)
  }
  return body as T
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data ?? {}) })
const put = <T>(path: string, data: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(data) })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

/* ── ชนิดข้อมูล ─────────────────────────────────────────── */

export type Role = 'admin' | 'staff'
export interface User {
  username: string
  role: Role
  /** เปิดยืนยันตัวตน 2 ชั้น (Google Authenticator) แล้วหรือยัง */
  totpEnabled: boolean
}

/** login ตอบแบบนี้เมื่อรหัสผ่านถูกแต่ผู้ใช้เปิด 2FA — ต้องส่งรหัส 6 หลักมาอีกรอบ */
export interface NeedsCode {
  needsCode: true
}

/** ข้อมูลที่ได้ตอนเริ่มตั้งค่า 2FA — qr เป็น data URL ใส่ <img> ได้เลย */
export interface TotpSetup {
  secret: string
  uri: string
  qr: string
}

/** ผู้ใช้ในหน้าจัดการ (เฉพาะผู้ดูแลระบบ) */
export interface ManagedUser {
  username: string
  role: Role
  totpEnabled: boolean
  createdAt: string
}

/* ── Tunnel ─────────────────────────────────────────────── */

export type TunnelStatus = 'online' | 'offline' | 'unknown'
/** private = เข้าผ่าน visitor บนคอม ไม่เปิดพอร์ต · public = เปิดพอร์ตบน VPS */
export type TunnelMode = 'private' | 'public'

export interface Tunnel {
  id: string
  name: string
  mode: TunnelMode
  localIp: string
  localPort: number
  /** ที่อยู่สำหรับ adb connect */
  endpoint: string
  status: TunnelStatus
  createdAt: string
}

export interface TunnelList {
  serverHost: string
  serverPort: number
  /** wss = ผ่าน Cloudflare · tcp = ต่อตรงเข้า VPS */
  transport: 'wss' | 'tcp'
  frpVersion: string
  publicEnabled: boolean
  maxPerUser: number
  /** โชว์ online/offline ได้ไหม — ได้ก็ต่อเมื่อตั้ง frps dashboard ไว้ */
  statusAvailable: boolean
  tunnels: Tunnel[]
}

export interface TunnelStep {
  label: string
  cmd: string
}

export interface TunnelSetup {
  summary: Tunnel
  /** แบบทีละสเต็ป — แต่ละสเต็ปรอจบก่อนทำตัวถัดไป (กัน paste โดนตัด) */
  termuxSteps: TunnelStep[]
  /** ฝั่งคอม — null เมื่อเป็นโหมด public */
  pc: { download: string; run: string; connect: string } | null
  /** ทำยังไงหลังมือถือรีบูต — pc = เปิด ADB TCP ใหม่, phone = ปลุก frpc */
  reboot: { pc: string; phone: string }
}

export interface RotateResult {
  token: string
  /** สะกิดให้ frps ตัดการเชื่อมต่อเดิมได้ไหม — false = แอดมินต้อง restart frps เอง */
  reloaded: boolean
}

/** ที่อยู่ไฟล์ frpc.toml สำหรับโหลด — ไม่มี id = รวมทุก tunnel ของตัวเอง */
export const frpcUrl = (id?: string) =>
  id ? `/api/tunnels/${id}/frpc.toml` : '/api/tunnels/frpc.toml'

/** ที่อยู่ไฟล์ visitor สำหรับคอม — ไม่มี id = รวมทุก tunnel แบบ private */
export const visitorUrl = (id?: string) =>
  id ? `/api/tunnels/${id}/frpc-visitor.toml` : '/api/tunnels/frpc-visitor.toml'

/* ── เส้นทางที่เรียกได้ ─────────────────────────────────── */

export const api = {
  login: (username: string, password: string, code?: string) =>
    post<User | NeedsCode>('/auth/login', { username, password, code }),
  logout: () => post<{ ok: true }>('/auth/logout'),
  me: () => get<User>('/auth/me'),

  /* ยืนยันตัวตน 2 ชั้น ของตัวเอง */
  totpSetup: () => post<TotpSetup>('/auth/2fa/setup'),
  totpEnable: (code: string) => post<{ ok: true }>('/auth/2fa/enable', { code }),
  totpDisable: (code: string) => post<{ ok: true }>('/auth/2fa/disable', { code }),

  /* จัดการผู้ใช้ (เฉพาะผู้ดูแลระบบ) */
  users: () => get<ManagedUser[]>('/users'),
  addUser: (data: { username: string; password: string; role: Role }) =>
    post<{ ok: true }>('/users', data),
  editUser: (username: string, data: { role?: Role; password?: string }) =>
    put<{ ok: true }>(`/users/${encodeURIComponent(username)}`, data),
  deleteUser: (username: string) => del<{ ok: true }>(`/users/${encodeURIComponent(username)}`),
  resetUserTotp: (username: string) =>
    post<{ ok: true }>(`/users/${encodeURIComponent(username)}/2fa/reset`),

  /* Tunnel ของตัวเอง */
  tunnels: () => get<TunnelList>('/tunnels'),
  createTunnel: (data: { name: string; mode: TunnelMode; localIp: string; localPort: number }) =>
    post<{ id: string }>('/tunnels', data),
  deleteTunnel: (id: string) => del<{ ok: true; reloaded: boolean }>(`/tunnels/${id}`),
  tunnelToken: () => get<{ token: string }>('/tunnels/token'),
  rotateTunnelToken: () => post<RotateResult>('/tunnels/token/rotate'),
  tunnelSetup: (id: string) => get<TunnelSetup>(`/tunnels/${id}/setup`),
}
