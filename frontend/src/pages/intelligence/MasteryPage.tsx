import { useCallback, useEffect, useState } from 'react'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Select, Spinner, StatCard } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import type { MasteryResponse, MasteryRow, Recommendation } from '../../types'

interface ClassRow { id: string; name: string }
interface StudentRow { id: string; full_name: string; username: string }

const statusTone: Record<string, 'slate' | 'amber' | 'rose' | 'green' | 'indigo'> = {
  not_started: 'slate',
  emerging: 'rose',
  developing: 'amber',
  proficient: 'indigo',
  mastered: 'green',
}

function MasteryTable({ rows }: { rows: MasteryRow[] }) {
  if (rows.length === 0) return <EmptyState message="Belum ada kompetensi yang dapat ditampilkan." />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
          <tr><th className="py-2">Kompetensi</th><th className="py-2">Probabilitas</th><th className="py-2">Status</th><th className="py-2">Bukti</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.competency_id} className="align-top">
              <td className="py-2 pr-3">
                <p className="font-medium">{row.name}</p>
                <p className="text-xs text-slate-400">{row.code}</p>
              </td>
              <td className="w-48 py-2 pr-3">
                <div className="flex items-center gap-2">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, Math.max(0, row.mastery_percent))}%` }} />
                  </div>
                  <span className="w-12 text-right font-semibold">{row.mastery_percent}%</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{row.practice_count} jawaban · {row.correct_count} benar</p>
              </td>
              <td className="py-2 pr-3"><Badge tone={statusTone[row.status] ?? 'slate'}>{row.status.replace('_', ' ')}</Badge></td>
              <td className="py-2 text-xs text-slate-500">{row.observation_count} observasi BKT</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function MasteryPage() {
  const { user, context } = useAuth()
  const { notify } = useToast()
  const isStudent = user?.role.name === 'student'
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [students, setStudents] = useState<StudentRow[]>([])
  const [classId, setClassId] = useState('')
  const [studentId, setStudentId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [data, setData] = useState<MasteryResponse | null>(null)
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const query = () => {
    const params = new URLSearchParams()
    if (classId) params.set('class_id', classId)
    if (studentId) params.set('student_id', studentId)
    if (subjectId) params.set('subject_id', subjectId)
    const value = params.toString()
    return value ? `?${value}` : ''
  }

  const load = useCallback(() => {
    setLoading(true)
    void Promise.all([
      api<MasteryResponse>(`/intelligence/mastery${query()}`),
      api<Recommendation[]>(`/intelligence/recommendations${studentId ? `?student_id=${studentId}` : ''}`),
    ])
      .then(([mastery, recs]) => { setData(mastery); setRecommendations(recs); setError('') })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [classId, studentId, subjectId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (isStudent) return
    void api<ClassRow[]>('/portal/teacher/classes').then(setClasses).catch(() => setClasses([]))
  }, [isStudent])

  useEffect(() => {
    setStudentId('')
    if (isStudent || !classId) { setStudents([]); return }
    void api<StudentRow[]>(`/portal/teacher/classes/${classId}/students`).then(setStudents).catch(() => setStudents([]))
  }, [classId, isStudent])

  const refresh = async () => {
    setRefreshing(true)
    try {
      const params = new URLSearchParams()
      if (studentId) params.set('student_id', studentId)
      const value = params.toString()
      const rows = await api<Recommendation[]>(`/intelligence/recommendations/refresh${value ? `?${value}` : ''}`, { method: 'POST' })
      setRecommendations(rows)
      notify(`Rekomendasi diperbarui: ${rows.length} butir`)
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const totalCompetencies = data?.competency_count ?? 0
  const average = data?.mode === 'student' && data.rows?.length
    ? Math.round(data.rows.reduce((sum, row) => sum + row.mastery_probability, 0) / data.rows.length * 100)
    : 0

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Profil penguasaan siswa</h1>
        <p className="mt-1 text-sm text-slate-500">
          Probabilitas dihitung dari jawaban nyata dengan Bayesian Knowledge Tracing, bukan dari nilai asesmen mentah.
        </p>
      </div>

      {!isStudent && (
        <Card className="grid gap-3 sm:grid-cols-3">
          <Field label="Kelas">
            <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
              <option value="">Semua kelas</option>
              {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
            </Select>
          </Field>
          <Field label="Siswa">
            <Select value={studentId} onChange={(event) => setStudentId(event.target.value)} disabled={!classId}>
              <option value="">Semua siswa di kelas</option>
              {students.map((student) => <option key={student.id} value={student.id}>{student.full_name}</option>)}
            </Select>
          </Field>
          <Field label="Mata pelajaran">
            <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              <option value="">Semua mata pelajaran</option>
              {context?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
            </Select>
          </Field>
        </Card>
      )}

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {loading || !data ? <Spinner label="Menghitung profil penguasaan…" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <StatCard label="Kompetensi" value={totalCompetencies} />
            {data.mode === 'student' && <StatCard label="Rata-rata penguasaan" value={`${average}%`} />}
            <StatCard label="Sumber data" value="Jawaban nyata" note="Dapat ditinjau melalui bukti di bawah" />
          </div>

          {data.mode === 'student' ? (
            <Card>
              <CardTitle title="Penguasaan per kompetensi" subtitle="Indikator untuk ditinjau guru, bukan vonis otomatis." />
              <MasteryTable rows={data.rows ?? []} />
            </Card>
          ) : (
            <Card>
              <CardTitle title={`Profil ${data.students?.length ?? 0} siswa`} subtitle="Pilih satu siswa untuk menyegarkan rekomendasi." />
              {(data.students?.length ?? 0) === 0 ? <EmptyState message="Belum ada siswa pada cakupan ini." /> : (
                <div className="space-y-4">
                  {data.students?.map((student) => (
                    <div key={student.student_id} className="rounded-xl border border-slate-100 p-3">
                      <p className="mb-2 font-semibold">{student.name}</p>
                      <MasteryTable rows={student.rows} />
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <div className="mb-3 flex items-start justify-between gap-3">
                <CardTitle title="Rekomendasi adaptive" subtitle="Dibuat dari profil penguasaan, bukan prediksi ketertinggalan." />
                <Button variant="secondary" onClick={() => void refresh()} disabled={refreshing}>
                  {refreshing ? 'Menyegarkan…' : 'Segarkan'}
                </Button>
              </div>
              {recommendations.length === 0 ? <EmptyState message="Belum ada rekomendasi. Tekan Segarkan untuk menghasilkan." /> : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {recommendations.map((item) => (
                    <li key={item.id} className="py-2">
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-medium">{item.title}</p>
                        <Badge tone="indigo">{item.rec_type}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{item.reason}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card className="bg-slate-50">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bukti perhitungan</p>
              <pre className="mt-2 max-h-80 overflow-auto text-xs text-slate-600">{JSON.stringify(data.evidence, null, 2)}</pre>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
