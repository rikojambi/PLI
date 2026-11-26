import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Card, Checkbox, EmptyState, Field, Input, Modal, Select, Spinner, Textarea } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import type { AssessmentRow, QuestionRow } from '../../types'

interface PortalClass { id: string; name: string }

function toLocalInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export function AssessmentsPage() {
  const { user, context } = useAuth()
  const { notify } = useToast()
  const navigate = useNavigate()
  const canEdit = user?.role.name === 'admin' || user?.role.name === 'teacher'
  const [rows, setRows] = useState<AssessmentRow[] | null>(null)
  const [classes, setClasses] = useState<PortalClass[]>([])
  const [questions, setQuestions] = useState<QuestionRow[]>([])
  const [classFilter, setClassFilter] = useState('')
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<AssessmentRow | null>(null)
  const [busy, setBusy] = useState(false)

  const [subjectId, setSubjectId] = useState('')
  const [classId, setClassId] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [duration, setDuration] = useState(45)
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [shuffleQuestions, setShuffleQuestions] = useState(false)
  const [shuffleOptions, setShuffleOptions] = useState(false)
  const [allowResume, setAllowResume] = useState(true)
  const [allowOffline, setAllowOffline] = useState(false)
  const [published, setPublished] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const load = useCallback(async () => {
    try {
      const query = classFilter ? `?class_id=${encodeURIComponent(classFilter)}` : ''
      setRows(await api<AssessmentRow[]>(`/learning/assessments${query}`))
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [classFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!canEdit) return
    void api<PortalClass[]>('/portal/teacher/classes').then(setClasses).catch(() => setClasses([]))
  }, [canEdit])

  const loadQuestions = useCallback(async (subject: string) => {
    if (!subject) {
      setQuestions([])
      return
    }
    try {
      setQuestions(await api<QuestionRow[]>(`/learning/questions?subject_id=${encodeURIComponent(subject)}`))
    } catch {
      setQuestions([])
    }
  }, [])

  useEffect(() => {
    if (showForm) void loadQuestions(subjectId)
  }, [showForm, subjectId, loadQuestions])

  const openForm = (row: AssessmentRow | null) => {
    setEditing(row)
    setSubjectId(row?.subject_id ?? context?.subjects[0]?.id ?? '')
    setClassId(row?.class_id ?? classes[0]?.id ?? '')
    setTitle(row?.title ?? '')
    setDescription(row?.description ?? '')
    setDuration(row?.duration_min ?? 45)
    setStartAt(toLocalInput(row?.start_at ?? null))
    setEndAt(toLocalInput(row?.end_at ?? null))
    setShuffleQuestions(row?.shuffle_questions ?? false)
    setShuffleOptions(row?.shuffle_options ?? false)
    setAllowResume(row?.allow_resume ?? true)
    setAllowOffline(row?.allow_offline ?? false)
    setPublished(row?.is_published ?? false)
    setSelectedIds(row?.question_ids ?? [])
    setShowForm(true)
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (title.trim().length < 3 || !classId || !subjectId) {
      notify('Judul, kelas, dan mata pelajaran wajib diisi.', 'error')
      return
    }
    const locked = Boolean(editing?.attempt_count)
    if (!locked && selectedIds.length === 0) {
      notify('Pilih minimal satu soal.', 'error')
      return
    }
    setBusy(true)
    try {
      const body = {
        subject_id: subjectId,
        class_id: classId,
        title: title.trim(),
        description: description || null,
        duration_min: Number(duration),
        start_at: startAt ? new Date(startAt).toISOString() : null,
        end_at: endAt ? new Date(endAt).toISOString() : null,
        shuffle_questions: shuffleQuestions,
        shuffle_options: shuffleOptions,
        allow_resume: allowResume,
        allow_offline: allowOffline,
        is_published: published,
        question_ids: locked ? [] : selectedIds,
      }
      if (editing) {
        await api(`/learning/assessments/${editing.id}`, { method: 'PATCH', body })
        notify('Asesmen diperbarui')
      } else {
        await api('/learning/assessments', { method: 'POST', body })
        notify('Asesmen dibuat')
      }
      setShowForm(false)
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const togglePublish = async (row: AssessmentRow) => {
    try {
      await api(`/learning/assessments/${row.id}`, {
        method: 'PATCH',
        body: {
          subject_id: row.subject_id,
          class_id: row.class_id,
          title: row.title,
          description: row.description,
          duration_min: row.duration_min,
          start_at: row.start_at,
          end_at: row.end_at,
          shuffle_questions: row.shuffle_questions,
          shuffle_options: row.shuffle_options,
          allow_resume: row.allow_resume,
          allow_offline: row.allow_offline,
          is_published: !row.is_published,
          question_ids: row.question_ids,
        },
      })
      notify(row.is_published ? 'Asesmen ditutup' : 'Asesmen dipublikasikan')
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Asesmen</h1>
          <p className="mt-1 text-sm text-slate-500">
            {canEdit ? 'Susun asesmen dari bank soal dan tentukan jendela waktu pengerjaan.' : 'Asesmen yang dipublikasikan untuk kelas Anda.'}
          </p>
        </div>
        {canEdit && <Button onClick={() => openForm(null)}>Buat asesmen</Button>}
      </div>

      {canEdit && (
        <Card>
          <Field label="Filter kelas">
            <Select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}>
              <option value="">Semua kelas yang diampu</option>
              {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
            </Select>
          </Field>
        </Card>
      )}

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {!rows ? <Spinner label="Memuat asesmen…" /> : rows.length === 0 ? (
        <Card><EmptyState message="Belum ada asesmen yang dapat ditampilkan." /></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <Card key={row.id} className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="font-semibold">{row.title}</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    {classes.find((klass) => klass.id === row.class_id)?.name ?? 'Kelas'} · {context?.subjects.find((subject) => subject.id === row.subject_id)?.name ?? 'Mapel'}
                  </p>
                </div>
                <Badge tone={row.is_published ? 'green' : 'amber'}>{row.is_published ? 'Dibuka' : 'Draft'}</Badge>
              </div>
              {row.description && <p className="mt-2 text-sm text-slate-600">{row.description}</p>}
              <p className="mt-3 text-xs text-slate-500">
                {row.question_count} soal · {row.max_points} poin · {row.duration_min} menit · {row.attempt_count} upaya
              </p>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                {canEdit ? (
                  <>
                    <Button variant="secondary" onClick={() => openForm(row)}>Ubah</Button>
                    <Button variant="secondary" onClick={() => void togglePublish(row)}>
                      {row.is_published ? 'Tutup' : 'Publikasikan'}
                    </Button>
                  </>
                ) : (
                  <Button
                    disabled={!row.is_published}
                    onClick={() => navigate(`/assessments/${row.id}/take`)}
                  >
                    {row.already_started ? 'Lanjutkan mengerjakan' : 'Kerjakan'}
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {showForm && (
        <Modal title={editing ? 'Ubah asesmen' : 'Asesmen baru'} onClose={() => setShowForm(false)}>
          <form className="space-y-4" onSubmit={(event) => void save(event)}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Kelas">
                <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
                  {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
                </Select>
              </Field>
              <Field label="Mata pelajaran">
                <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
                  {context?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
                </Select>
              </Field>
            </div>
            <Field label="Judul">
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="Deskripsi">
              <Textarea rows={2} value={description} onChange={(event) => setDescription(event.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Durasi (menit)">
                <Input type="number" min={1} max={480} value={duration} onChange={(event) => setDuration(Number(event.target.value))} />
              </Field>
              <Field label="Mulai (opsional)">
                <Input type="datetime-local" value={startAt} onChange={(event) => setStartAt(event.target.value)} />
              </Field>
              <Field label="Selesai (opsional)">
                <Input type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} />
              </Field>
            </div>
            <div className="grid gap-1 sm:grid-cols-2">
              <Checkbox label="Acak urutan soal" checked={shuffleQuestions} onChange={(event) => setShuffleQuestions(event.target.checked)} />
              <Checkbox label="Acak pilihan jawaban" checked={shuffleOptions} onChange={(event) => setShuffleOptions(event.target.checked)} />
              <Checkbox label="Izinkan lanjut mengerjakan" checked={allowResume} onChange={(event) => setAllowResume(event.target.checked)} />
              <Checkbox label="Izinkan penyimpanan offline" checked={allowOffline} onChange={(event) => setAllowOffline(event.target.checked)} />
              <Checkbox label="Publikasikan kepada siswa" checked={published} onChange={(event) => setPublished(event.target.checked)} />
            </div>

            <div className="space-y-2 rounded-xl border border-slate-200 p-3">
              <p className="text-sm font-semibold">Pilih soal</p>
              {editing?.attempt_count ? (
                <p className="text-xs text-amber-700">Susunan soal tidak dapat diubah karena sudah ada siswa yang mengerjakan.</p>
              ) : questions.length === 0 ? (
                <p className="text-xs text-slate-500">Tidak ada soal untuk mata pelajaran ini.</p>
              ) : (
                <div className="max-h-56 space-y-1 overflow-y-auto">
                  {questions.map((question) => {
                    const checked = selectedIds.includes(question.id)
                    return (
                      <label key={question.id} className="flex min-h-[40px] cursor-pointer items-center gap-3 rounded-lg px-2 text-sm hover:bg-slate-50">
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          checked={checked}
                          onChange={() => setSelectedIds((current) => checked ? current.filter((id) => id !== question.id) : [...current, question.id])}
                        />
                        <span className="flex-1">{question.content.slice(0, 90)}</span>
                        <span className="text-xs text-slate-400">{question.points} poin</span>
                      </label>
                    )
                  })}
                </div>
              )}
              <p className="text-xs font-medium text-slate-600">Terpilih: {selectedIds.length} soal</p>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Batal</Button>
              <Button type="submit" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan asesmen'}</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
