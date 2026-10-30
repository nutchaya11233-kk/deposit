/*
  โครงหน้าเว็บ — เมนูและสลับหน้า

  ⚠️ ไม่ได้ใช้ router library — มีไม่กี่หน้า สถานะเดียว
     URL ยังเปลี่ยนตามหน้าอยู่ (ผ่าน history API) เพื่อให้ปุ่ม back ใช้ได้
*/
import { useEffect, useState } from 'react'

import { api, setUnauthorizedHandler, type User } from './api'
import GuidePage from './pages/GuidePage'
import LoginPage from './pages/LoginPage'
import SecurityModal from './pages/SecurityModal'
import TunnelsPage from './pages/TunnelsPage'
import UsersPage from './pages/UsersPage'

type Tab = 'tunnels' | 'guide' | 'users'

const TABS: { id: Tab; label: string; icon: string; adminOnly?: boolean }[] = [
  { id: 'tunnels', label: 'Tunnel ของฉัน', icon: '⇄' },
  { id: 'guide',   label: 'วิธีใช้งาน',    icon: '?' },
  { id: 'users',   label: 'ผู้ใช้งาน',     icon: '♟', adminOnly: true },
]

function tabFromPath(): Tab {
  const slug = window.location.pathname.replace(/^\//, '') as Tab
  return TABS.some((t) => t.id === slug) ? slug : 'tunnels'
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [booting, setBooting] = useState(true)
  const [tab, setTab] = useState<Tab>(tabFromPath)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') ?? '')
  const [security, setSecurity] = useState(false)

  // session หมดอายุกลางทาง → เด้งกลับหน้า login แทนที่จะค้างหน้าว่าง
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  useEffect(() => {
    if (theme) {
      document.documentElement.setAttribute('data-theme', theme)
      localStorage.setItem('theme', theme)
    } else {
      document.documentElement.removeAttribute('data-theme')
      localStorage.removeItem('theme')
    }
  }, [theme])

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setBooting(false))
  }, [])

  const go = (next: Tab) => {
    setTab(next)
    window.history.pushState(null, '', `/${next}`)
  }

  useEffect(() => {
    const onPop = () => setTab(tabFromPath())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const logout = async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }

  if (booting) {
    return (
      <div className="login-page">
        <span className="spinner" />
      </div>
    )
  }

  if (!user) return <LoginPage onSuccess={setUser} />

  const isAdmin = user.role === 'admin'
  const visibleTabs = TABS.filter((t) => !t.adminOnly || isAdmin)

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>Tunnel Console</strong>
          <span>ต่อ ADB เข้ามือถือผ่าน tunnel ของคุณเอง</span>
        </div>

        <nav className="nav">
          {visibleTabs.map((t) => (
            <button key={t.id} aria-current={tab === t.id} onClick={() => go(t.id)}>
              <span aria-hidden style={{ width: 16, textAlign: 'center' }}>
                {t.icon}
              </span>
              {t.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="whoami">
            <strong>{user.username}</strong>
            <div>{isAdmin ? 'ผู้ดูแลระบบ' : 'ผู้ใช้'}</div>
          </div>
          <div className="actions">
            <button
              className="btn ghost sm"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              title="สลับโหมดสว่าง/มืด"
            >
              {theme === 'dark' ? '☀' : '☾'}
            </button>
            <button
              className={`btn ghost sm${user.totpEnabled ? '' : ' warn'}`}
              onClick={() => setSecurity(true)}
              title={user.totpEnabled ? 'ยืนยันตัวตน 2 ชั้น: เปิดอยู่' : 'ยังไม่ได้เปิดยืนยันตัวตน 2 ชั้น'}
            >
              {user.totpEnabled ? '🔒' : '🔓'} 2FA
            </button>
            <button className="btn sm" onClick={logout}>
              ออกจากระบบ
            </button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1>{TABS.find((t) => t.id === tab)?.label}</h1>
          </div>
        </header>

        <main className="content">
          {tab === 'users' && isAdmin ? (
            <UsersPage me={user} />
          ) : tab === 'guide' ? (
            <GuidePage />
          ) : (
            <TunnelsPage onGuide={() => go('guide')} />
          )}
        </main>
      </div>

      {security && (
        <SecurityModal user={user} onChanged={setUser} onClose={() => setSecurity(false)} />
      )}
    </div>
  )
}
