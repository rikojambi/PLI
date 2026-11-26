import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../lib/api'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Modal, Select, Textarea } from '../../components/ui'
import type { CompetencyRow, SubjectRow } from '../../types'

interface SubjectForm { code: string; name: string; description: string; color: string }
interface CompetencyForm { subject_id: string; code: string; name: string; description: string; grade_level: string; order_index: number }

const emptySubject = (): SubjectForm => ({ code: '', name: '', description: '', color: '#6366f1' })
const emptyCompetency = (subjectId = ''): CompetencyForm => ({
  subject_id: subjectId, code: '', name: '', description: '', grade_level: '', order_index: 0,
})

export function SubjectsPage() {
  const { notify } = useToast()
  const [subjects, setSubjects] = useState<SubjectRow[]>([])
  const [competencies, setCompetencies] = useState<CompetencyRow[]>([])
  const [subjectForm, setSubjectForm] = useState<SubjectForm | null>(null)
  const [competencyForm, setCompetencyForm] = useState<CompetencyForm | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [subjectRows, competencyRows] = await Promise.all([
        api<SubjectRow[]>('/admin/subjects'),
        api<CompetencyRow[]>('/admin/competencies'),
      ])
      setSubjects(subjectRows)
      setCompetencies(competencyRows)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const saveSubject = async (event: FormEvent) => {
    event.preventDefault()
    if (!subjectForm) return
    setBusy(true)
    try {
      await api('/admin/subjects', {
        method: 'POST',
        body: { ...subjectForm, description: subjectForm.description || undefined },
      })
      notify('Mata pelajaran ditambahkan')
      setSubjectForm(emptySubject())
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const saveCompetency = async (event: FormEvent) => {
    event.preventDefault()
    if (!competencyForm) return
    setBusy(true)
    try {
      await api('/admin/competencies', {
        method: 'POST',
        body: {
          ...competencyForm,
          description: competencyForm.description || undefined,
          grade_level: competencyForm.grade_level || undefined,
        },
      })
      notify('Kompetensi ditambahkan')
      setCompetencyForm(emptyCompetency(competencyForm.subject_id))
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Mata Pelajaran &amp; Kompetensi</h1>
          <p className="mt-1 text-sm text-slate-500">{subjects.length} mata pelajaran · {competencies.length} kompetensi.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setCompetencyForm(emptyCompetency(subjects[0]?.id ?? ''))}>+ Kompetensi</Button>
          <Button onClick={() => setSubjectForm(emptySubject())}>+ Mata pelajaran</Button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {subjects.length === 0 ? (
        <Card><EmptyState message="Belum ada mata pelajaran." /></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {subjects.map((subject) => {
            const items = competencies.filter((item) => item.subject_id === subject.id)
            return (
              <Card key={subject.id}>
                <CardTitle title={subject.name} subtitle={`Kode: ${subject.code}`} />
                <div className="flex items-center justify-between">
                  <Badge tone={subject.is_active ? 'green' : 'slate'}>{subject.is_active ? 'Aktif' : 'Nonaktif'}</Badge>
                  <Button variant="ghost" className="px-2 py-1" onClick={() => setCompetencyForm(emptyCompetency(subject.id))}>+ Kompetensi</Button>
                </div>
                <div className="mt-3 space-y-2">
                  {items.length === 0 && <p className="text-xs text-slate-400">Belum ada kompetensi.</p>}
                  {items.map((item) => (
                    <div key={item.id} className="rounded-xl bg-slate-50 px-3 py-2 text-sm">
                      <p className="font-medium text-slate-700">{item.code} — {item.name}</p>
                      {item.description && <p className="text-xs text-slate-400">{item.description}</p>}
                    </div>
                  ))}
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {subjectForm && (
        <Modal title="Tambah mata pelajaran" onClose={() => setSubjectForm(null)}>
          <form onSubmit={(event) => void saveSubject(event)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Kode"><Input value={subjectForm.code} onChange={(event) => setSubjectForm({ ...subjectForm, code: event.target.value })} placeholder="MTK" required /></Field>
              <Field label="Nama"><Input value={subjectForm.name} onChange={(event) => setSubjectForm({ ...subjectForm, name: event.target.value })} placeholder="Matematika" required /></Field>
              <Field label="Warna (hex)"><Input value={subjectForm.color} onChange={(event) => setSubjectForm({ ...subjectForm, color: event.target.value })} /></Field>
            </div>
            <Field label="Deskripsi"><Textarea rows={3} value={subjectForm.description} onChange={(event) => setSubjectForm({ ...subjectForm, description: event.target.value })} /></Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => setSubjectForm(null)}>Batal</Button>
              <Button type="submit" disabled={busy}>Simpan</Button>
            </div>
          </form>
        </Modal>
      )}

      {competencyForm && (
        <Modal title="Tambah kompetensi" onClose={() => setCompetencyForm(null)}>
          <form onSubmit={(event) => void saveCompetency(event)} className="space-y-4">
            <Field label="Mata pelajaran">
              <Select value={competencyForm.subject_id} onChange={(event) => setCompetencyForm({ ...competencyForm, subject_id: event.target.value })} required>
                <option value="">Pilih mata pelajaran</option>
                {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Kode kompetensi"><Input value={competencyForm.code} onChange={(event) => setCompetencyForm({ ...competencyForm, code: event.target.value })} placeholder="MTK-K3" required /></Field>
              <Field label="Nama kompetensi"><Input value={competencyForm.name} onChange={(event) => setCompetencyForm({ ...competencyForm, name: event.target.value })} required /></Field>
              <Field label="Urutan"><Input type="number" min={0} value={competencyForm.order_index} onChange={(event) => setCompetencyForm({ ...competencyForm, order_index: Number(event.target.value) })} /></Field>
            </div>
            <Field label="Tingkat (opsional)"><Input value={competencyForm.grade_level} onChange={(event) => setCompetencyForm({ ...competencyForm, grade_level: event.target.value })} /></Field>
            <Field label="Deskripsi"><Textarea rows={3} value={competencyForm.description} onChange={(event) => setCompetencyForm({ ...competencyForm, description: event.target.value })} /></Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => setCompetencyForm(null)}>Batal</Button>
              <Button type="submit" disabled={busy}>Simpan</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
