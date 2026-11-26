import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'
import type { Role } from '../types'
import { Icon, type IconName } from './Icons'
import { InstallPrompt } from './InstallPrompt'
import { StatusBar } from './StatusBar'
import { useToast } from './Toast'
import { Button, Field, Input, Modal } from './ui'

interface NavItem {
  to: string
  label: string
  icon: IconName
}

const learningNav: NavItem[] = [
  { to: '/progress', label: 'Perkembangan', icon: 'chart' },
  { to: '/sync', label: 'Sinkronisasi', icon: 'refresh' },
  { to: '/materials', label: 'Materi', icon: 'book' },
  { to: '/questions', label: 'Soal', icon: 'plus' },
  { to: '/assessments', label: 'Asesmen', icon: 'check' },
  { to: '/grading', label: 'Koreksi', icon: 'shield' },
  { to: '/analytics', label: 'Analitik', icon: 'chart' },
  { to: '/mastery', label: 'Penguasaan', icon: 'chart' },
  { to: '/gaps', label: 'Celah Belajar', icon: 'book' },
  { to: '/evaluation', label: 'Evaluasi', icon: 'shield' },
  { to: '/notes', label: 'Catatan', icon: 'edit' },
  { to: '/import', label: 'Impor', icon: 'users' },
]

const navByRole: Record<Role, NavItem[]> = {
  admin: [
    { to: '/', label: 'Dashboard', icon: 'home' },
    { to: '/users', label: 'Pengguna', icon: 'users' },
    { to: '/classes', label: 'Kelas', icon: 'school' },
    { to: '/subjects', label: 'Mapel', icon: 'book' },
    ...learningNav,
    { to: '/settings', label: 'Pengaturan', icon: 'settings' },
    { to: '/operations', label: 'Operasional', icon: 'shield' },
    { to: '/engine', label: 'Mesin Intelijen', icon: 'settings' },
    { to: '/ai-providers', label: 'Penyedia AI', icon: 'spark' },
    { to: '/ai-usage', label: 'Pemakaian AI', icon: 'chart' },
    { to: '/ai-ask', label: 'Tanya Dokumen', icon: 'online' },
  ],
  teacher: [
    { to: '/', label: 'Dashboard', icon: 'home' },
    { to: '/my-classes', label: 'Kelas Saya', icon: 'school' },
    ...learningNav,
    { to: '/ai-documents', label: 'Dokumen AI', icon: 'book' },
    { to: '/ai-generator', label: 'Generator AI', icon: 'spark' },
    { to: '/ai-ask', label: 'Tanya Dokumen', icon: 'online' },
  ],
  student: [
    { to: '/', label: 'Dashboard', icon: 'home' },
    { to: '/my-classes', label: 'Kelas Saya', icon: 'school' },
    { to: '/progress', label: 'Perkembangan', icon: 'chart' },
    { to: '/sync', label: 'Sinkronisasi', icon: 'refresh' },
    { to: '/materials', label: 'Materi', icon: 'book' },
    { to: '/assessments', label: 'Asesmen', icon: 'check' },
    { to: '/results', label: 'Hasil', icon: 'chart' },
    { to: '/adaptive', label: 'Latihan Adaptif', icon: 'check' },
    { to: '/mastery', label: 'Penguasaan', icon: 'chart' },
    { to: '/notes', label: 'Catatan', icon: 'edit' },
    { to: '/ai-tutor', label: 'AI Tutor', icon: 'chat' },
    { to: '/ai-ask', label: 'Tanya Dokumen', icon: 'online' },
  ],
}

const roleLabel: Record<Role, string> = {
  admin: 'Administrator',
  teacher: 'Guru',
  student: 'Siswa',
}

export function AppShell() {
  const { user, context, logout, changePassword } = useAuth()
  const { notify } = useToast()
  const navigate = useNavigate()
  const [showPassword, setShowPassword] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  if (!user) return null
  const items = navByRole[user.role.name]

  const submitPassword = async () => {
    if (next.length < 10 || next !== confirm) {
      notify('Password baru minimal 10 karakter dan harus sama dengan konfirmasi.', 'error')
      return
    }
    setBusy(true)
    try {
      await changePassword(current, next)
      notify('Password berhasil diubah')
      setShowPassword(false)
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  const navList = (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-medium transition ${
                isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100'
              }`
            }
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  )

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-slate-200 bg-white px-4 py-5 lg:flex">
        <div className="mb-8 flex items-center gap-3 px-2">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 font-bold text-white">P</span>
          <div>
            <p className="text-sm font-bold tracking-tight">Personal Learning</p>
            <p className="text-xs text-slate-400">Intelligence</p>
          </div>
        </div>
        <nav aria-label="Navigasi utama">{navList}</nav>
        <div className="mt-auto rounded-xl bg-slate-50 p-3 text-xs text-slate-500">
          <p className="font-semibold text-slate-700">{context?.school?.name ?? 'Sekolah'}</p>
          <p>{context?.academic_year?.name ?? '-'} · {context?.semester?.name ?? '-'}</p>
        </div>
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-bold lg:text-base">{context?.school?.name ?? 'Personal Learning Intelligence'}</p>
              <StatusBar />
            </div>
            <div className="flex items-center gap-2">
              <div className="hidden text-right sm:block">
                <p className="text-sm font-semibold">{user.full_name}</p>
                <p className="text-xs text-slate-400">{roleLabel[user.role.name]}</p>
              </div>
              <Button variant="secondary" className="px-3" onClick={() => setShowPassword(true)} title="Ubah password">
                <Icon name="key" className="h-4 w-4" /><span className="hidden sm:inline">Password</span>
              </Button>
              <Button
                variant="ghost"
                className="px-3"
                onClick={async () => {
                  await logout()
                  navigate('/login', { replace: true })
                  notify('Anda telah keluar', 'info')
                }}
              >
                <Icon name="logout" className="h-4 w-4" /><span className="hidden sm:inline">Keluar</span>
              </Button>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 lg:pb-10">
          <Outlet />
        </main>
      </div>

      <nav aria-label="Navigasi bawah" className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        <div className="flex gap-1 overflow-x-auto px-2">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex min-h-[60px] min-w-[76px] flex-col items-center justify-center gap-1 px-1 text-[11px] font-medium ${
                  isActive ? 'text-brand-700' : 'text-slate-500'
                }`
              }
            >
              <Icon name={item.icon} className="h-5 w-5" />
              <span className="whitespace-nowrap">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      <InstallPrompt />

      {showPassword && (
        <Modal title="Ubah password" onClose={() => setShowPassword(false)}>
          <div className="space-y-4">
            <Field label="Password saat ini">
              <Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" />
            </Field>
            <Field label="Password baru" hint="Minimal 10 karakter, memuat huruf dan angka.">
              <Input type="password" value={next} onChange={(event) => setNext(event.target.value)} autoComplete="new-password" />
            </Field>
            <Field label="Ulangi password baru">
              <Input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} autoComplete="new-password" />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowPassword(false)}>Batal</Button>
              <Button onClick={() => void submitPassword()} disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
