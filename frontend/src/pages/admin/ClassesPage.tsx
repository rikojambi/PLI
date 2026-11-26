import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../lib/api'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, Checkbox, EmptyState, Field, Input, Modal, Select } from '../../components/ui'
import type { AcademicYearRow, ClassRow, SemesterRow, User } from '../../types'

interface ClassForm {
  name: string
  grade_level: string
  academic_year_id: string
  semester_id: string
  student_ids: string[]
  teacher_ids: string[]
  is_active: boolean
}

export function ClassesPage() {
  const { notify } = useToast()
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [years, setYears] = useState<AcademicYearRow[]>([])
  const [semesters, setSemesters] = useState<SemesterRow[]>([])
  const [students, setStudents] = useState<User[]>([])
  const [teachers, setTeachers] = useState<User[]>([])
  const [form, setForm] = useState<ClassForm | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [classRows, yearRows, semesterRows, studentRows, teacherRows] = await Promise.all([
        api<ClassRow[]>('/admin/classes'),
        api<AcademicYearRow[]>('/admin/academic-years'),
        api<SemesterRow[]>('/admin/semesters'),
        api<{ items: User[] }>('/admin/users?role=student&limit=200'),
        api<{ items: User[] }>('/admin/users?role=teacher&limit=200'),
      ])
      setClasses(classRows)
      setYears(yearRows)
      setSemesters(semesterRows)
      setStudents(studentRows.items)
      setTeachers(teacherRows.items)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const startCreate = () => {
    if (!form) {
      setEditingId(null)
      setForm({
        name: '',
        grade_level: '',
        academic_year_id: years.find((y) => y.is_active)?.id ?? years[0]?.id ?? '',
        semester_id: '',
        student_ids: [],
        teacher_ids: [],
        is_active: true,
      })
    }
  }

  const startEdit = async (klass: ClassRow) => {
    try {
      const members = await api<Array<{ id: string }>>(`/admin/classes/${klass.id}/students`)
      setEditingId(klass.id)
      setForm({
        name: klass.name,
        grade_level: klass.grade_level ?? '',
        academic_year_id: klass.academic_year_id,
        semester_id: klass.semester_id,
        student_ids: members.map((member) => member.id),
        teacher_ids: klass.teachers.map((teacher) => teacher.teacher_id),
        is_active: klass.is_active,
      })
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  const toggle = (list: string[], id: string): string[] =>
    list.includes(id) ? list.filter((item) => item !== id) : [...list, id]

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!form) return
    if (form.name.trim().length < 1 || !form.academic_year_id || !form.semester_id) {
      notify('Nama kelas, tahun ajaran, dan semester wajib diisi.', 'error')
      return
    }
    setBusy(true)
    try {
      const body = {
        ...form,
        grade_level: form.grade_level || undefined,
        student_ids: form.student_ids,
        teacher_ids: form.teacher_ids,
      }
      if (editingId) {
        await api(`/admin/classes/${editingId}`, { method: 'PATCH', body })
        notify('Kelas diperbarui')
      } else {
        await api('/admin/classes', { method: 'POST', body })
        notify('Kelas berhasil dibuat')
      }
      setForm(null)
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const semesterOptions = semesters.filter((s) => s.academic_year_id === form?.academic_year_id)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Kelola Kelas</h1>
          <p className="mt-1 text-sm text-slate-500">{classes.length} kelas pada tahun ajaran berjalan.</p>
        </div>
        <Button onClick={startCreate}>+ Tambah kelas</Button>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {classes.length === 0 ? (
        <Card><EmptyState message="Belum ada kelas. Buat tahun ajaran dan semester di Pengaturan terlebih dahulu." /></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {classes.map((klass) => (
            <Card key={klass.id}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold">{klass.name}</h2>
                  <p className="text-xs text-slate-500">Tingkat {klass.grade_level ?? '-'}</p>
                </div>
                <Badge tone={klass.is_active ? 'green' : 'slate'}>{klass.is_active ? 'Aktif' : 'Nonaktif'}</Badge>
              </div>
              <p className="mt-4 text-sm text-slate-600">{klass.student_count} siswa · {klass.teachers.length} guru pengampu</p>
              <div className="mt-4 flex gap-2">
                <Button variant="secondary" className="flex-1" onClick={() => void startEdit(klass)}>Ubah anggota</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {form && (
        <Modal title={editingId ? `Ubah kelas` : 'Tambah kelas'} onClose={() => { setForm(null); setEditingId(null) }}>
          <form onSubmit={(event) => void save(event)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Nama kelas"><Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="XII RPL 1" required /></Field>
              <Field label="Tingkat / kelas"><Input value={form.grade_level} onChange={(event) => setForm({ ...form, grade_level: event.target.value })} placeholder="12" /></Field>
              <Field label="Tahun ajaran">
                <Select value={form.academic_year_id} onChange={(event) => setForm({ ...form, academic_year_id: event.target.value, semester_id: '' })}>
                  <option value="">Pilih tahun ajaran</option>
                  {years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}
                </Select>
              </Field>
              <Field label="Semester">
                <Select value={form.semester_id} onChange={(event) => setForm({ ...form, semester_id: event.target.value })}>
                  <option value="">Pilih semester</option>
                  {semesterOptions.map((semester) => <option key={semester.id} value={semester.id}>{semester.name}</option>)}
                </Select>
              </Field>
            </div>

            <Checkbox label="Kelas aktif" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-sm font-medium text-slate-700">Siswa anggota kelas ({form.student_ids.length})</p>
                <div className="max-h-44 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
                  {students.length === 0 && <p className="text-xs text-slate-400">Belum ada siswa.</p>}
                  {students.map((student) => (
                    <label key={student.id} className="flex min-h-[36px] cursor-pointer items-center gap-2 rounded-lg px-2 text-sm hover:bg-slate-50">
                      <input type="checkbox" className="h-4 w-4" checked={form.student_ids.includes(student.id)} onChange={() => setForm({ ...form, student_ids: toggle(form.student_ids, student.id) })} />
                      {student.full_name}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-1 text-sm font-medium text-slate-700">Guru pengampu ({form.teacher_ids.length})</p>
                <div className="max-h-44 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
                  {teachers.length === 0 && <p className="text-xs text-slate-400">Belum ada guru.</p>}
                  {teachers.map((teacher) => (
                    <label key={teacher.id} className="flex min-h-[36px] cursor-pointer items-center gap-2 rounded-lg px-2 text-sm hover:bg-slate-50">
                      <input type="checkbox" className="h-4 w-4" checked={form.teacher_ids.includes(teacher.id)} onChange={() => setForm({ ...form, teacher_ids: toggle(form.teacher_ids, teacher.id) })} />
                      {teacher.full_name}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => { setForm(null); setEditingId(null) }}>Batal</Button>
              <Button type="submit" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan'}</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
