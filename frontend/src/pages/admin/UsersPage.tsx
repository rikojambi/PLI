import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../lib/api'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, Checkbox, EmptyState, Field, Input, Modal, Select } from '../../components/ui'
import type { ClassRow, User } from '../../types'

const LIMIT = 20

interface UserForm {
  username: string
  full_name: string
  email: string
  password: string
  role: 'admin' | 'teacher' | 'student'
  class_id: string
}

const emptyForm = (): UserForm => ({
  username: '',
  full_name: '',
  email: '',
  password: '',
  role: 'student',
  class_id: '',
})

export function UsersPage() {
  const { notify } = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [form, setForm] = useState<UserForm | null>(null)
  const [editing, setEditing] = useState<User | null>(null)
  const [resetTarget, setResetTarget] = useState<User | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState('')

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
      if (role) params.set('role', role)
      if (search) params.set('search', search)
      const result = await api<{ items: User[]; total: number }>(`/admin/users?${params.toString()}`)
      setUsers(result.items)
      setTotal(result.total)
      setLoadError('')
    } catch (error) {
      setLoadError(errorMessage(error))
    }
  }, [offset, role, search])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    void api<ClassRow[]>('/admin/classes').then(setClasses).catch(() => undefined)
  }, [])

  const createUser = async (event: FormEvent) => {
    event.preventDefault()
    if (!form) return
    if (!/^[a-z0-9._]{3,80}$/.test(form.username)) {
      notify('Username 3-80 karakter, huruf kecil, angka, titik, atau garis bawah.', 'error')
      return
    }
    if (form.full_name.trim().length < 2 || form.password.length < 10) {
      notify('Nama minimal 2 karakter dan password minimal 10 karakter.', 'error')
      return
    }
    setBusy(true)
    try {
      await api('/admin/users', {
        method: 'POST',
        body: {
          ...form,
          email: form.email || undefined,
          class_id: form.class_id || undefined,
        },
      })
      notify('Pengguna berhasil dibuat. Password harus diganti saat login pertama.')
      setForm(null)
      setForm(emptyForm())
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  const saveEdit = async (event: FormEvent) => {
    event.preventDefault()
    if (!editing) return
    setBusy(true)
    try {
      await api(`/admin/users/${editing.id}`, {
        method: 'PATCH',
        body: {
          full_name: editing.full_name,
          email: editing.email || undefined,
          phone: editing.phone || undefined,
          student_number: editing.student_number || undefined,
          is_active: editing.is_active,
        },
      })
      notify('Data pengguna diperbarui')
      setEditing(null)
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  const reset = async (event: FormEvent) => {
    event.preventDefault()
    if (!resetTarget) return
    if (newPassword.length < 10 || newPassword !== confirmPassword) {
      notify('Password minimal 10 karakter dan konfirmasi harus sama.', 'error')
      return
    }
    setBusy(true)
    try {
      await api(`/admin/users/${resetTarget.id}/reset-password`, {
        method: 'POST',
        body: { new_password: newPassword },
      })
      notify('Password berhasil direset')
      setResetTarget(null)
      setNewPassword('')
      setConfirmPassword('')
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (user: User) => {
    try {
      await api(`/admin/users/${user.id}`, {
        method: 'PATCH',
        body: { is_active: !user.is_active },
      })
      notify(user.is_active ? 'Akun dinonaktifkan' : 'Akun diaktifkan')
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Kelola Pengguna</h1>
          <p className="mt-1 text-sm text-slate-500">{total} akun terdaftar di sekolah ini.</p>
        </div>
        <Button onClick={() => setForm(emptyForm())}>+ Tambah pengguna</Button>
      </div>

      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Cari">
            <Input value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0) }} placeholder="Nama atau username" />
          </Field>
          <Field label="Peran">
            <Select value={role} onChange={(event) => { setRole(event.target.value); setOffset(0) }}>
              <option value="">Semua peran</option>
              <option value="admin">Administrator</option>
              <option value="teacher">Guru</option>
              <option value="student">Siswa</option>
            </Select>
          </Field>
          <div className="flex items-end gap-2">
            <Button variant="secondary" onClick={() => void load()}>Terapkan</Button>
            <Button variant="ghost" onClick={() => { setSearch(''); setRole(''); setOffset(0) }}>Reset</Button>
          </div>
        </div>
      </Card>

      {loadError && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{loadError}</div>}

      <Card>
        {users.length === 0 ? (
          <EmptyState message="Tidak ada pengguna yang cocok dengan filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr><th className="py-2">Nama</th><th>Username</th><th>Peran</th><th>Status</th><th className="text-right">Aksi</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="py-3">
                      <p className="font-semibold text-slate-800">{user.full_name}</p>
                      <p className="text-xs text-slate-400">{user.email ?? '-'}</p>
                    </td>
                    <td>{user.username}</td>
                    <td><Badge tone={user.role.name === 'admin' ? 'indigo' : user.role.name === 'teacher' ? 'amber' : 'slate'}>{user.role.name}</Badge></td>
                    <td><Badge tone={user.is_active ? 'green' : 'rose'}>{user.is_active ? 'Aktif' : 'Nonaktif'}</Badge></td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" className="px-2 py-1" onClick={() => setEditing(user)}>Ubah</Button>
                        <Button variant="ghost" className="px-2 py-1" onClick={() => setResetTarget(user)}>Reset</Button>
                        <Button variant="ghost" className="px-2 py-1" onClick={() => void toggleActive(user)}>
                          {user.is_active ? 'Nonaktifkan' : 'Aktifkan'}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex items-center justify-between text-sm">
          <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Sebelumnya</Button>
          <span className="text-slate-500">{offset + 1}–{Math.min(offset + LIMIT, total)} dari {total}</span>
          <Button variant="secondary" disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}>Berikutnya</Button>
        </div>
      </Card>

      {form && (
        <Modal title="Tambah pengguna" onClose={() => setForm(null)}>
          <form onSubmit={(event) => void createUser(event)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Username">
                <Input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value.toLowerCase() })} placeholder="siswa3" required />
              </Field>
              <Field label="Nama lengkap">
                <Input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required />
              </Field>
              <Field label="Email" hint="Opsional">
                <Input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
              </Field>
              <Field label="Peran">
                <Select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as UserForm['role'] })}>
                  <option value="student">Siswa</option>
                  <option value="teacher">Guru</option>
                  <option value="admin">Administrator</option>
                </Select>
              </Field>
              <Field label="Password sementara" hint="Minimal 10 karakter; wajib diganti saat login pertama.">
                <Input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required />
              </Field>
              <Field label="Kelas" hint="Opsional; siswa dapat ditambahkan ke kelas lain kemudian.">
                <Select value={form.class_id} onChange={(event) => setForm({ ...form, class_id: event.target.value })}>
                  <option value="">Tanpa kelas</option>
                  {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
                </Select>
              </Field>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => setForm(null)}>Batal</Button>
              <Button type="submit" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan'}</Button>
            </div>
          </form>
        </Modal>
      )}

      {editing && (
        <Modal title={`Ubah ${editing.full_name}`} onClose={() => setEditing(null)}>
          <form onSubmit={(event) => void saveEdit(event)} className="space-y-4">
            <Field label="Nama lengkap">
              <Input value={editing.full_name} onChange={(event) => setEditing({ ...editing, full_name: event.target.value })} required />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email"><Input type="email" value={editing.email ?? ''} onChange={(event) => setEditing({ ...editing, email: event.target.value })} /></Field>
              <Field label="Telepon"><Input value={editing.phone ?? ''} onChange={(event) => setEditing({ ...editing, phone: event.target.value })} /></Field>
              <Field label="Nomor induk siswa"><Input value={editing.student_number ?? ''} onChange={(event) => setEditing({ ...editing, student_number: event.target.value })} /></Field>
            </div>
            <Checkbox label="Akun aktif" checked={editing.is_active} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => setEditing(null)}>Batal</Button>
              <Button type="submit" disabled={busy}>Simpan</Button>
            </div>
          </form>
        </Modal>
      )}

      {resetTarget && (
        <Modal title={`Reset password ${resetTarget.full_name}`} onClose={() => setResetTarget(null)}>
          <form onSubmit={(event) => void reset(event)} className="space-y-4">
            <Field label="Password baru" hint="Minimal 10 karakter. Sementara, akun akan diminta menggantinya.">
              <Input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
            </Field>
            <Field label="Ulangi password baru">
              <Input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => setResetTarget(null)}>Batal</Button>
              <Button type="submit" disabled={busy}>Reset password</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
