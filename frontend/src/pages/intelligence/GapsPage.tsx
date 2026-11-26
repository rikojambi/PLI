import { useEffect, useState } from 'react'
import { Badge, Card, CardTitle, EmptyState, Field, Select, Spinner, StatCard } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import type { GapReport } from '../../types'

interface ClassRow { id: string; name: string }

const categoryLabel: Record<string, string> = {
  konsep: 'Konsep',
  prosedur: 'Prosedur',
  hitungan: 'Hitungan',
  membaca_soal: 'Membaca soal',
  aplikasi: 'Aplikasi',
}

export function GapsPage() {
  const { user, context } = useAuth()
  const isStudent = user?.role.name === 'student'
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [classId, setClassId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [data, setData] = useState<GapReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isStudent) return
    void api<ClassRow[]>('/portal/teacher/classes').then(setClasses).catch(() => setClasses([]))
  }, [isStudent])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    const params = new URLSearchParams()
    if (classId) params.set('class_id', classId)
    if (subjectId) params.set('subject_id', subjectId)
    const query = params.toString() ? `?${params.toString()}` : ''
    void api<GapReport>(`/intelligence/gaps${query}`, { signal: controller.signal })
      .then((value) => { setData(value); setError('') })
      .catch((err) => { if ((err as Error).name !== 'AbortError') setError(errorMessage(err)) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [classId, subjectId])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Analisis celah belajar</h1>
        <p className="mt-1 text-sm text-slate-500">
          Kategori celah berasal dari label yang ditetapkan guru pada soal, bukan tebakan otomatis.
        </p>
      </div>

      {!isStudent && (
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
      )}

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {loading || !data ? <Spinner label="Menganalisis celah belajar…" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <StatCard label="Siswa" value={data.student_count} />
            <StatCard label="Observasi" value={data.observation_count} note="Jawaban yang benar-benar dinilai" />
            <StatCard label="Kompetensi terdampak" value={data.rows.length} />
          </div>

          <Card>
            <CardTitle title="Kompetensi dengan celah terbesar" subtitle="Diurutkan dari skor celah; untuk menjadi fokus remedial guru." />
            {data.rows.length === 0 ? <EmptyState message="Belum ada jawaban yang dinilai pada cakupan ini." /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="py-2">Kompetensi</th><th className="py-2">Skor celah</th>
                      <th className="py-2">Akurasi</th><th className="py-2">Kategori dominan</th><th className="py-2">Observasi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.rows.map((row) => (
                      <tr key={row.competency_id} className="align-top">
                        <td className="py-2 pr-3">
                          <p className="font-medium">{row.name}</p>
                          <p className="text-xs text-slate-400">{row.code}</p>
                        </td>
                        <td className="py-2 pr-3"><Badge tone={row.gap_score >= 0.5 ? 'rose' : 'amber'}>{row.gap_score}</Badge></td>
                        <td className="py-2 pr-3">{row.accuracy_percent}%</td>
                        <td className="py-2 pr-3">
                          <p className="font-medium">{categoryLabel[row.dominant_category] ?? row.dominant_category}</p>
                          <p className="text-xs text-slate-400">
                            {Object.entries(row.category_counts)
                              .filter(([, count]) => count > 0)
                              .map(([key, count]) => `${categoryLabel[key] ?? key}: ${count}`)
                              .join(', ') || 'Tidak ada jawaban salah'}
                          </p>
                        </td>
                        <td className="py-2">{row.observations}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card className="bg-slate-50">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bukti perhitungan</p>
            <pre className="mt-2 max-h-80 overflow-auto text-xs text-slate-600">{JSON.stringify(data.evidence, null, 2)}</pre>
          </Card>
        </>
      )}
    </div>
  )
}
