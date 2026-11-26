import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Select, Spinner, Textarea } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import type { NoteRow } from '../../types'

interface PortalClass { id: string; name: string }
interface PortalStudent { id: string; full_name: string; username: string }

const NOTE_TYPES = [
  { value: 'info', label: 'Informasi' },
  { value: 'encouragement', label: 'Dorongan' },
  { value: 'warning', label: 'Perlu perhatian' },
] as const

export function NotesPage() {
  const { user } = useAuth()
  const { notify } = useToast()
  const canWrite = user?.role.name === 'admin' || user?.role.name === 'teacher'
  const [notes, setNotes] = useState<NoteRow[] | null>(null)
  const [classes, setClasses] = useState<PortalClass[]>([])
  const [students, setStudents] = useState<PortalStudent[]>([])
  const [classId, setClassId] = useState('')
  const [studentId, setStudentId] = useState('')
  const [noteType, setNoteType] = useState<(typeof NOTE_TYPES)[number]['value']>('info')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const query = canWrite && classId ? `?class_id=${encodeURIComponent(classId)}` : ''
      setNotes(await api<NoteRow[]>(`/learning/notes${query}`))
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [canWrite, classId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!canWrite) return
    void api<PortalClass[]>('/portal/teacher/classes').then(setClasses).catch(() => setClasses([]))
  }, [canWrite])

  useEffect(() => {
    setStudents([])
    if (!canWrite || !classId) return
    void api<PortalStudent[]>(`/portal/teacher/classes/${classId}/students`).then(setStudents).catch(() => setStudents([]))
  }, [canWrite, classId])

  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (!studentId || title.trim().length < 2 || content.trim().length < 3) {
      notify('Lengkapi siswa, judul, dan isi catatan.', 'error')
      return
    }
    setBusy(true)
    try {
      await api('/learning/notes', {
        method: 'POST',
        body: { student_id: studentId, class_id: classId || null, note_type: noteType, title: title.trim(), content: content.trim() },
      })
      notify('Catatan dikirim')
      setTitle('')
      setContent('')
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const markRead = async (note: NoteRow) => {
    try {
      await api(`/learning/notes/${note.id}/read`, { method: 'PATCH', body: {} })
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Catatan belajar</h1>
        <p className="mt-1 text-sm text-slate-500">
          {canWrite ? 'Catatan hanya dikirim kepada siswa yang bersangkutan.' : 'Catatan dari guru untuk Anda.'}
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {canWrite && (
        <Card>
          <CardTitle title="Catatan baru" subtitle="Gunakan untuk umpan balik yang bersifat mendidik." />
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void create(event)}>
            <Field label="Kelas">
              <Select value={classId} onChange={(event) => { setClassId(event.target.value); setStudentId('') }}>
                <option value="">Pilih kelas</option>
                {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
              </Select>
            </Field>
            <Field label="Siswa">
              <Select value={studentId} onChange={(event) => setStudentId(event.target.value)}>
                <option value="">Pilih siswa</option>
                {students.map((student) => <option key={student.id} value={student.id}>{student.full_name} ({student.username})</option>)}
              </Select>
            </Field>
            <Field label="Jenis catatan">
              <Select value={noteType} onChange={(event) => setNoteType(event.target.value as typeof noteType)}>
                {NOTE_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
              </Select>
            </Field>
            <Field label="Judul">
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Isi catatan">
                <Textarea rows={3} value={content} onChange={(event) => setContent(event.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={busy}>{busy ? 'Mengirim…' : 'Kirim catatan'}</Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        <CardTitle title="Daftar catatan" />
        {!notes ? <Spinner label="Memuat catatan…" /> : notes.length === 0 ? (
          <EmptyState message="Belum ada catatan." />
        ) : (
          <div className="space-y-3">
            {notes.map((note) => (
              <div key={note.id} className={`rounded-xl border p-4 ${note.is_read ? 'border-slate-200 bg-white' : 'border-brand-200 bg-brand-50'}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{note.title}</p>
                  <div className="flex items-center gap-2">
                    <Badge tone={note.note_type === 'warning' ? 'amber' : note.note_type === 'encouragement' ? 'green' : 'slate'}>
                      {NOTE_TYPES.find((type) => type.value === note.note_type)?.label ?? note.note_type}
                    </Badge>
                    {!note.is_read && <Badge tone="indigo">Baru</Badge>}
                  </div>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{note.content}</p>
                <p className="mt-2 text-xs text-slate-400">{new Date(note.created_at).toLocaleString('id-ID')}</p>
                {!canWrite && !note.is_read && (
                  <Button className="mt-3" variant="secondary" onClick={() => void markRead(note)}>Tandai dibaca</Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
