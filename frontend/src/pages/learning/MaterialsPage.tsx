import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Badge, Button, Card, Checkbox, EmptyState, Field, Input, Modal, Select, Spinner, Textarea } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../context/AuthContext'
import { api, apiUpload, errorMessage } from '../../lib/api'
import type { MaterialRow } from '../../types'

const MATERIAL_TYPES = [
  { value: 'text', label: 'Teks' },
  { value: 'pdf', label: 'PDF' },
  { value: 'video', label: 'Video' },
  { value: 'slide', label: 'Slide' },
]

interface UploadResult {
  file_path: string
  file_name: string
  size_bytes: number
}

export function MaterialsPage() {
  const { user, context } = useAuth()
  const { notify } = useToast()
  const canEdit = user?.role.name === 'admin' || user?.role.name === 'teacher'
  const [rows, setRows] = useState<MaterialRow[] | null>(null)
  const [subjectId, setSubjectId] = useState('')
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<MaterialRow | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [busy, setBusy] = useState(false)

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [materialType, setMaterialType] = useState('text')
  const [published, setPublished] = useState(false)
  const [file, setFile] = useState<File | null>(null)

  const load = useCallback(async () => {
    try {
      const query = subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ''
      setRows(await api<MaterialRow[]>(`/learning/materials${query}`))
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [subjectId])

  useEffect(() => {
    void load()
  }, [load])

  const openForm = (row: MaterialRow | null) => {
    setEditing(row)
    setTitle(row?.title ?? '')
    setContent(row?.content ?? '')
    setMaterialType(row?.material_type ?? 'text')
    setPublished(row?.is_published ?? false)
    setFile(null)
    setShowForm(true)
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!canEdit) return
    const selectedSubject = editing?.subject_id || subjectId || context?.subjects[0]?.id || ''
    if (!selectedSubject) {
      notify('Pilih mata pelajaran terlebih dahulu.', 'error')
      return
    }
    if (title.trim().length < 3) {
      notify('Judul materi minimal 3 karakter.', 'error')
      return
    }
    setBusy(true)
    try {
      let filePath = editing?.file_path ?? null
      if (file) {
        const uploaded = await apiUpload<UploadResult>('/learning/uploads', file)
        filePath = uploaded.file_path
      }
      const body = {
        subject_id: selectedSubject,
        title: title.trim(),
        content: content || null,
        material_type: materialType,
        file_path: filePath,
        is_published: published,
      }
      if (editing) {
        await api(`/learning/materials/${editing.id}`, { method: 'PATCH', body })
        notify('Materi diperbarui')
      } else {
        await api('/learning/materials', { method: 'POST', body })
        notify('Materi dibuat')
      }
      setShowForm(false)
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (row: MaterialRow) => {
    if (!window.confirm(`Hapus materi "${row.title}"?`)) return
    try {
      await api(`/learning/materials/${row.id}`, { method: 'DELETE' })
      notify('Materi dihapus')
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  const togglePublish = async (row: MaterialRow) => {
    try {
      await api(`/learning/materials/${row.id}`, {
        method: 'PATCH',
        body: { is_published: !row.is_published },
      })
      notify(row.is_published ? 'Materi disembunyikan' : 'Materi dipublikasikan')
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Materi pembelajaran</h1>
          <p className="mt-1 text-sm text-slate-500">
            {canEdit ? 'Buat dan publikasikan materi untuk kelas Anda.' : 'Materi yang sudah dipublikasikan untuk kelas Anda.'}
          </p>
        </div>
        {canEdit && <Button onClick={() => openForm(null)}>Tambah materi</Button>}
      </div>

      <Card className="flex flex-wrap items-end gap-3">
        <div className="min-w-[220px] flex-1">
          <Field label="Filter mata pelajaran">
            <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              <option value="">Semua mata pelajaran</option>
              {context?.subjects.map((subject) => (
                <option key={subject.id} value={subject.id}>{subject.name}</option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {!rows ? (
        <Spinner label="Memuat materi…" />
      ) : rows.length === 0 ? (
        <Card><EmptyState message="Belum ada materi yang dapat ditampilkan." /></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <Card key={row.id} className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold text-slate-900">{row.title}</h2>
                <Badge tone={row.is_published ? 'green' : 'amber'}>
                  {row.is_published ? 'Dipublikasikan' : 'Draft'}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {context?.subjects.find((subject) => subject.id === row.subject_id)?.name ?? 'Mata pelajaran'} · {row.material_type}
              </p>
              {row.content && <p className="mt-3 whitespace-pre-wrap text-sm text-slate-600">{row.content}</p>}
              {row.file_path && (
                <a
                  href={row.file_path}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex min-h-[44px] items-center rounded-xl bg-brand-50 px-3 text-sm font-semibold text-brand-700 hover:bg-brand-100"
                >
                  Unduh {row.file_name ?? 'lampiran'} ↗
                </a>
              )}
              {canEdit && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                  <Button variant="secondary" onClick={() => openForm(row)}>Ubah</Button>
                  <Button variant="secondary" onClick={() => void togglePublish(row)}>
                    {row.is_published ? 'Sembunyikan' : 'Publikasikan'}
                  </Button>
                  <Button variant="danger" onClick={() => void remove(row)}>Hapus</Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {showForm && (
        <Modal title={editing ? 'Ubah materi' : 'Materi baru'} onClose={() => setShowForm(false)}>
          <form className="space-y-4" onSubmit={(event) => void save(event)}>
            <Field label="Mata pelajaran">
              <Select
                value={editing?.subject_id ?? subjectId ?? context?.subjects[0]?.id ?? ''}
                onChange={(event) => setSubjectId(event.target.value)}
                disabled={Boolean(editing)}
              >
                {context?.subjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>{subject.name}</option>
                ))}
              </Select>
            </Field>
            <Field label="Judul">
              <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Contoh: Operasi hitung bilangan bulat" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Jenis materi">
                <Select value={materialType} onChange={(event) => setMaterialType(event.target.value)}>
                  {MATERIAL_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                </Select>
              </Field>
              <Field label="Lampiran (opsional)" hint="PDF, TXT, MD, DOCX, PPTX, PNG, JPG, WEBP">
                <Input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              </Field>
            </div>
            <Field label="Isi materi">
              <Textarea rows={6} value={content} onChange={(event) => setContent(event.target.value)} />
            </Field>
            <Checkbox label="Publikasikan kepada siswa" checked={published} onChange={(event) => setPublished(event.target.checked)} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Batal</Button>
              <Button type="submit" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan'}</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
