import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Icon } from '../components/Icons'
import { Button, Field, Input } from '../components/ui'
import { errorMessage } from '../lib/api'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (user) return <Navigate to="/" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (username.trim().length < 3 || password.length < 8) {
      setError('Username minimal 3 karakter dan password minimal 8 karakter.')
      return
    }
    setBusy(true)
    try {
      await login(username.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <div className="hidden w-1/2 flex-col justify-between bg-brand-700 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/15 text-lg font-bold">P</span>
          <div>
            <p className="font-bold">Personal Learning Intelligence</p>
            <p className="text-sm text-indigo-200">Platform pembelajaran adaptif sekolah</p>
          </div>
        </div>
        <div>
          <h1 className="max-w-lg text-4xl font-bold leading-tight">Belajar yang mengikuti kemampuan setiap siswa.</h1>
          <p className="mt-5 max-w-md text-indigo-100">
            Pemetaan kompetensi, asesmen adaptif, dan analisis perkembangan dalam satu aplikasi yang tetap berguna saat koneksi sekolah tidak stabil.
          </p>
        </div>
        <p className="text-xs text-indigo-200">Fase 1 — Fondasi sistem. Modul pembelajaran dan AI hadir pada fase berikutnya.</p>
      </div>

      <div className="flex w-full items-center justify-center px-4 py-10 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 font-bold text-white">P</span>
            <div>
              <p className="font-bold">PLI</p>
              <p className="text-xs text-slate-500">Personal Learning Intelligence</p>
            </div>
          </div>
          <h2 className="text-2xl font-bold text-slate-900">Masuk ke akun Anda</h2>
          <p className="mt-2 text-sm text-slate-500">Gunakan akun yang diberikan administrator sekolah.</p>

          <form onSubmit={(event) => void submit(event)} className="mt-7 space-y-4" noValidate>
            <Field label="Username atau email">
              <Input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                placeholder="contoh: guru1"
                disabled={busy}
              />
            </Field>
            <Field label="Password">
              <div className="relative">
                <Input
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  placeholder="Minimal 8 karakter"
                  disabled={busy}
                  className="pr-16"
                />
                <button
                  type="button"
                  onClick={() => setShow((value) => !value)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-50"
                >
                  {show ? 'Sembunyi' : 'Lihat'}
                </button>
              </div>
            </Field>

            {error && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? 'Memeriksa…' : 'Masuk'}
            </Button>
          </form>

          <div className="mt-6 flex items-start gap-2 rounded-xl bg-white p-3 text-xs text-slate-500 shadow-card">
            <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
            <p>Sesi login tersimpan dalam cookie httpOnly. Kredensial akun demo dibuat acak oleh skrip <code>init_db</code> dan hanya untuk pengujian lokal.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
