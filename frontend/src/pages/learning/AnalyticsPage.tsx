import { useEffect, useState } from 'react'
import { Badge, Card, CardTitle, EmptyState, Field, Select, Spinner, StatCard } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import type { Analytics } from '../../types'

interface PortalClass { id: string; name: string }

export function AnalyticsPage() {
  const { context } = useAuth()
  const [classes, setClasses] = useState<PortalClass[]>([])
  const [classId, setClassId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [data, setData] = useState<Analytics | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void api<PortalClass[]>('/portal/teacher/classes').then(setClasses).catch(() => setClasses([]))
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    const params = new URLSearchParams()
    if (classId) params.set('class_id', classId)
    if (subjectId) params.set('subject_id', subjectId)
    const query = params.toString() ? `?${params.toString()}` : ''
    void api<Analytics>(`/learning/analytics${query}`, { signal: controller.signal })
      .then((value) => { setData(value); setError('') })
      .catch((err) => { if ((err as Error).name !== 'AbortError') setError(errorMessage(err)) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [classId, subjectId])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Analitik pembelajaran</h1>
        <p className="mt-1 text-sm text-slate-500">Angka berasal dari hasil asesmen dan jawaban yang benar-benar tersimpan.</p>
      </div>

      <Card className="grid gap-3 sm:grid-cols-2">
        <Field label="Kelas">
          <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
            <option value="">Semua kelas yang diampu</option>
            {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
          </Select>
        </Field>
        <Field label="Mata pelajaran">
          <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">Semua mata pelajaran</option>
            {context?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
          </Select>
        </Field>
      </Card>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {loading || !data ? (
        <Spinner label="Menghitung analitik…" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Siswa" value={data.student_count} />
            <StatCard label="Upaya" value={data.attempt_count} />
            <StatCard label="Rata-rata nilai" value={`${data.average_score}%`} />
            <StatCard label="Lulus (≥70)" value={data.passing_count} note="Ambang batas dapat ditinjau" />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardTitle title="Kompetensi paling sulit" subtitle="Diurutkan dari akurasi jawaban objektif terendah." />
              {data.hardest_competencies.length === 0 ? <EmptyState message="Belum ada jawaban objektif yang dinilai." /> : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {data.hardest_competencies.map((item) => (
                    <li key={item.competency_id} className="flex items-center justify-between gap-3 py-2">
                      <div><p className="font-medium">{item.name}</p><p className="text-xs text-slate-400">{item.code}</p></div>
                      <div className="text-right">
                        <Badge tone={item.accuracy_percent < 50 ? 'rose' : 'amber'}>{item.accuracy_percent}%</Badge>
                        <p className="mt-1 text-xs text-slate-400">{item.correct}/{item.total} benar</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardTitle title="Perlu perhatian" subtitle="Rata-rata di bawah ambang batas; untuk ditinjau guru." />
              {data.students_needing_help.length === 0 ? <EmptyState message="Tidak ada siswa di bawah ambang batas." /> : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {data.students_needing_help.map((item) => (
                    <li key={item.student_id} className="flex items-center justify-between gap-3 py-2">
                      <div><p className="font-medium">{item.name}</p><p className="text-xs text-slate-400">{item.attempts} upaya</p></div>
                      <Badge tone="amber">{item.average_score}%</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card className="bg-slate-50">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bukti perhitungan</p>
            <pre className="mt-2 overflow-x-auto text-xs text-slate-600">{JSON.stringify(data.evidence, null, 2)}</pre>
          </Card>
        </>
      )}
    </div>
  )
}
