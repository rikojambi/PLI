import { useEffect, useState } from 'react'
import { BarChart, LineChart } from '../components/Charts'
import {
  DashboardFilterBar,
  DEFAULT_FILTERS,
  filterQuery,
  useDashboardFilterOptions,
  type DashboardFilterState,
} from '../components/DashboardFilterBar'
import { Badge, Button, Card, CardTitle, EmptyState, StatCard } from '../components/ui'
import { useToast } from '../components/Toast'
import { api, apiDownload, errorMessage } from '../lib/api'

// Profile rows mirror backend services/dashboard.py exactly; no client-side guessing.

interface Profile {
  student: {
    id: string
    full_name: string
    username: string
    student_number: string | null
    classes: string[]
  }
  mastery: Array<{
    code: string
    name: string
    mastery_percent: number
    status: string
    practice_count: number
    observation_count: number
    accuracy_percent: number
  }>
  results: Array<{
    id: string
    date: string
    score: number
    mastery_percent: number
    assessment_title: string
    subject_name: string
    class_name: string
  }>
  recommendations: Array<{ id: string; title: string; reason: string; priority: number; rec_type: string }>
  notes: Array<{ id: string; title: string; note_type: string; is_read: boolean; created_at: string }>
  trend: {
    scores: Array<{ label: string; score: number; attempts: number }>
    mastery: Array<{ label: string; mastery_percent: number; observations: number }>
    observation_count: number
    result_count: number
  }
  evidence: { source: string; note: string }
}

export function ProgressPage() {
  const { options, error: optionsError } = useDashboardFilterOptions()
  const { notify } = useToast()
  const [filters, setFilters] = useState<DashboardFilterState>(DEFAULT_FILTERS)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState<'xlsx' | 'pdf' | null>(null)

  useEffect(() => {
    if (!options || filters.student_id) return
    const first = options.students[0]?.id
    if (first) setFilters((current) => ({ ...current, student_id: first }))
  }, [options, filters.student_id])

  const queryKey = filterQuery(filters)
  useEffect(() => {
    if (!filters.student_id) return
    const controller = new AbortController()
    setLoading(true)
    api<Profile>(`/dashboard/students/${filters.student_id}/profile?${queryKey}`, { signal: controller.signal })
      .then((data) => {
        setProfile(data)
        setError('')
      })
      .catch((err) => {
        if ((err as Error).name === 'AbortError') return
        setProfile(null)
        setError(errorMessage(err))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [filters.student_id, queryKey])

  const exportFile = async (format: 'xlsx' | 'pdf') => {
    setExporting(format)
    try {
      await apiDownload(`/dashboard/export?${filterQuery(filters, { format })}`, `pli-profil-siswa.${format}`)
      notify(`Profil siswa dalam format ${format.toUpperCase()} berhasil diunduh.`)
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setExporting(null)
    }
  }

  const masteryTone = (status: string): 'green' | 'amber' | 'rose' | 'slate' => {
    if (status.includes('mahir') || status.includes('tinggi')) return 'green'
    if (status.includes('sedang') || status.includes('berkembang')) return 'amber'
    if (status.includes('rendah') || status.includes('perlu')) return 'rose'
    return 'slate'
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Profil perkembangan siswa</h1>
        <p className="mt-2 text-sm text-slate-600">
          Ringkasan dari hasil asesmen, BKT, rekomendasi, dan catatan yang tersimpan di server.
          Bukan prediksi dropout dan bukan vonis otomatis.
        </p>
      </div>

      {(error || optionsError) && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error || optionsError}</div>
      )}

      <Card>
        <CardTitle title="Filter profil" subtitle="Guru melihat siswa dalam kelas binaannya; siswa hanya melihat profilnya sendiri." />
        <DashboardFilterBar
          options={options}
          value={filters}
          onChange={setFilters}
          includeStudent
          disabled={options?.scope === 'self'}
        />
      </Card>

      {!filters.student_id && <EmptyState message="Pilih siswa untuk melihat profilnya." />}
      {loading && !profile && <EmptyState message="Memuat profil dari server…" />}

      {profile && (
        <>
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <CardTitle
                  title={profile.student.full_name}
                  subtitle={`${profile.student.username}${profile.student.student_number ? ` · ${profile.student.student_number}` : ''} · ${profile.student.classes.join(', ') || 'Tanpa kelas'}`}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" disabled={exporting !== null} onClick={() => void exportFile('xlsx')}>
                  {exporting === 'xlsx' ? 'Menyusun…' : 'Excel'}
                </Button>
                <Button variant="secondary" disabled={exporting !== null} onClick={() => void exportFile('pdf')}>
                  {exporting === 'pdf' ? 'Menyusun…' : 'PDF'}
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Hasil asesmen" value={profile.trend.result_count} />
              <StatCard label="Observasi BKT" value={profile.trend.observation_count} />
              <StatCard label="Kompetensi" value={profile.mastery.length} />
              <StatCard label="Rekomendasi aktif" value={profile.recommendations.length} />
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardTitle title="Nilai asesmen" subtitle="Rata-rata harian dari hasil yang dinilai." />
              <LineChart
                points={profile.trend.scores.map((item) => ({ label: item.label.slice(5), value: item.score }))}
                unit="%"
              />
            </Card>
            <Card>
              <CardTitle title="Penguasaan kompetensi" subtitle="Probabilitas BKT dari jawaban nyata." />
              <BarChart
                points={profile.mastery.map((item) => ({ label: `${item.code} · ${item.name}`, value: item.mastery_percent }))}
              />
            </Card>
          </div>

          <Card>
            <CardTitle title="Detail kompetensi" subtitle="Status adalah indikator untuk ditinjau guru, bukan keputusan otomatis." />
            {profile.mastery.length === 0 ? (
              <EmptyState message="Belum ada kompetensi yang dipantau untuk siswa ini." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                    <tr><th className="py-2">Kompetensi</th><th>Penguasaan</th><th>Akurasi</th><th>Observasi</th><th>Status</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {profile.mastery.map((item) => (
                      <tr key={item.code}>
                        <td className="py-2 font-medium text-slate-700">{item.code} · {item.name}</td>
                        <td>{item.mastery_percent}%</td>
                        <td>{item.accuracy_percent}%</td>
                        <td>{item.observation_count}</td>
                        <td><Badge tone={masteryTone(item.status)}>{item.status}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card>
            <CardTitle title="Riwayat hasil" subtitle="Diambil dari assessment_results yang sudah dinilai." />
            {profile.results.length === 0 ? (
              <EmptyState message="Belum ada hasil asesmen pada rentang ini." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                    <tr><th className="py-2">Tanggal</th><th>Asesmen</th><th>Mapel</th><th>Nilai</th><th>Penguasaan</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {profile.results.map((item) => (
                      <tr key={item.id}>
                        <td className="py-2 text-slate-500">{new Date(item.date).toLocaleDateString('id-ID')}</td>
                        <td className="font-medium text-slate-700">{item.assessment_title}</td>
                        <td>{item.subject_name}</td>
                        <td>{item.score}</td>
                        <td>{item.mastery_percent}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardTitle title="Rekomendasi aktif" subtitle="Draf peninjauan guru, bukan penugasan otomatis." />
              {profile.recommendations.length === 0 ? (
                <EmptyState message="Tidak ada rekomendasi aktif." />
              ) : (
                <ul className="space-y-2 text-sm">
                  {profile.recommendations.map((item) => (
                    <li key={item.id} className="rounded-xl border border-slate-100 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-700">{item.title}</span>
                        <Badge tone="indigo">Prioritas {item.priority}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{item.reason}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardTitle title="Catatan perkembangan" subtitle="Catatan guru yang tersimpan bersama profil siswa." />
              {profile.notes.length === 0 ? (
                <EmptyState message="Belum ada catatan." />
              ) : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {profile.notes.map((item) => (
                    <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span className="font-medium text-slate-700">{item.title}</span>
                      <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString('id-ID')}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <p className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
            Sumber: {profile.evidence.source}. {profile.evidence.note}
          </p>
        </>
      )}
    </div>
  )
}
