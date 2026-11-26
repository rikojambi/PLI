import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { BarChart, LineChart } from '../components/Charts'
import {
  DashboardFilterBar,
  DEFAULT_FILTERS,
  filterQuery,
  useDashboardFilterOptions,
  type DashboardFilterState,
} from '../components/DashboardFilterBar'
import { Button, Card, CardTitle, EmptyState, StatCard } from '../components/ui'
import { useToast } from '../components/Toast'
import { api, apiDownload, errorMessage } from '../lib/api'
import type { AiStatus, AuditRow } from '../types'

interface TrendPoint {
  label: string
  score: number
  attempts: number
}

interface MasteryPoint {
  label: string
  mastery_percent: number
  observations: number
}

interface Evidence {
  source: string
  note: string
}

interface DashboardOverview {
  student_count: number
  assessment_count: number
  result_count: number
  average_score: number
  passing_count: number
  trend: TrendPoint[]
  mastery_trend: MasteryPoint[]
  evidence: Evidence
}

interface DashboardProgress {
  scores: TrendPoint[]
  mastery: MasteryPoint[]
  result_count: number
  observation_count: number
  evidence: Evidence
}

interface LegacyOverview {
  classes?: number
  students?: number
  competencies_tracked?: number
  average_mastery?: number
  subjects?: number
  assessments?: number
}

interface AdminOverview {
  users: number
  teachers: number
  students: number
  classes: number
  audits: number
  recent: AuditRow[]
}

export function DashboardPage() {
  const { user, context } = useAuth()
  const { notify } = useToast()
  const { options: filterOptions, error: filterError } = useDashboardFilterOptions()
  const [filters, setFilters] = useState<DashboardFilterState>(DEFAULT_FILTERS)
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [progress, setProgress] = useState<DashboardProgress | null>(null)
  const [legacy, setLegacy] = useState<LegacyOverview | null>(null)
  const [admin, setAdmin] = useState<AdminOverview | null>(null)
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState<'xlsx' | 'pdf' | null>(null)

  const query = filterQuery(filters)
  const queryKey = query

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    const load = async () => {
      try {
        const [fresh, series] = await Promise.all([
          api<DashboardOverview>(`/dashboard/overview?${queryKey}`, { signal: controller.signal }),
          api<DashboardProgress>(`/dashboard/progress?${queryKey}`, { signal: controller.signal }),
        ])
        setOverview(fresh)
        setProgress(series)
        setError('')
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setError(errorMessage(err))
      }
    }
    void load()
    return () => controller.abort()
  }, [user, queryKey])

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    const load = async () => {
      try {
        if (user.role.name === 'admin') {
          const [users, teachers, students, classes, audits] = await Promise.all([
            api<{ total: number }>('/admin/users?limit=1', { signal: controller.signal }),
            api<{ total: number }>('/admin/users?role=teacher&limit=1', { signal: controller.signal }),
            api<{ total: number }>('/admin/users?role=student&limit=1', { signal: controller.signal }),
            api<Array<unknown>>('/admin/classes', { signal: controller.signal }),
            api<{ total: number; items: AuditRow[] }>('/admin/audit-logs?limit=5', { signal: controller.signal }),
          ])
          setAdmin({
            users: users.total,
            teachers: teachers.total,
            students: students.total,
            classes: classes.length,
            audits: audits.total,
            recent: audits.items,
          })
        } else {
          const path = user.role.name === 'teacher' ? '/portal/teacher/overview' : '/portal/student/overview'
          setLegacy(await api<LegacyOverview>(path, { signal: controller.signal }))
        }
        setAiStatus(await api<AiStatus>('/ai/status', { signal: controller.signal }))
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setError(errorMessage(err))
      }
    }
    void load()
    return () => controller.abort()
  }, [user])

  if (!user) return null

  const exportFile = async (format: 'xlsx' | 'pdf') => {
    setExporting(format)
    try {
      await apiDownload(`/dashboard/export?${filterQuery(filters, { format })}`, `pli-laporan.${format}`)
      notify(`Laporan ${format.toUpperCase()} berhasil diunduh dari data server.`)
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-slate-500">{context?.academic_year?.name ?? '-'} · {context?.semester?.name ?? '-'}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Selamat datang, {user.full_name}</h1>
        <p className="mt-2 text-sm text-slate-600">
          {user.role.name === 'admin'
            ? 'Pantau perkembangan lintas kelas dari hasil asesmen dan jejak BKT yang tersimpan.'
            : user.role.name === 'teacher'
              ? 'Pantau perkembangan kelas yang Anda ampu berdasarkan data asesmen nyata.'
              : 'Lihat perkembangan Anda sendiri; data siswa lain tidak dapat diakses.'}
        </p>
      </div>

      {(error || filterError) && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error || filterError}</div>
      )}

      <Card>
        <CardTitle
          title="Filter analitik"
          subtitle="Periode, kelas, mapel, kompetensi, dan siswa dibatasi oleh hak akses Anda."
        />
        <DashboardFilterBar options={filterOptions} value={filters} onChange={setFilters} />
      </Card>

      {overview && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard label="Siswa" value={overview.student_count} />
            <StatCard label="Asesmen" value={overview.assessment_count} />
            <StatCard label="Hasil dinilai" value={overview.result_count} />
            <StatCard label="Rata-rata nilai" value={overview.average_score} note="Skala 0–100" />
            <StatCard label="Nilai ≥ 70" value={overview.passing_count} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardTitle title="Perkembangan nilai" subtitle="Rata-rata harian dari hasil asesmen yang sudah dinilai." />
              <LineChart
                points={overview.trend.map((item) => ({ label: item.label.slice(5), value: item.score }))}
                unit="%"
              />
            </Card>
            <Card>
              <CardTitle title="Perkembangan penguasaan" subtitle="Turunan BKT dari jawaban siswa yang tersimpan." />
              <LineChart
                points={overview.mastery_trend.map((item) => ({ label: item.label.slice(5), value: item.mastery_percent }))}
                unit="%"
              />
            </Card>
          </div>
          {progress && (
            <Card>
              <CardTitle
                title="Ringkasan bukti"
                subtitle={`${progress.result_count} hasil asesmen · ${progress.observation_count} observasi BKT dalam rentang ini.`}
              />
              <BarChart
                points={progress.mastery.map((item) => ({ label: item.label, value: item.mastery_percent }))}
              />
              <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-500">
                Sumber: {overview.evidence.source}. {overview.evidence.note} Prediksi dropout belum tersedia tanpa dataset tervalidasi.
              </p>
            </Card>
          )}
        </>
      )}
      {!overview && !error && <EmptyState message="Memuat ringkasan analitik dari server…" />}

      <Card>
        <CardTitle
          title="Ekspor laporan"
          subtitle="Berkas dibuat di server dari data yang sama dengan filter di atas, lalu dikirim sebagai unduhan terautentikasi."
        />
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={exporting !== null} onClick={() => void exportFile('xlsx')}>
            {exporting === 'xlsx' ? 'Menyusun Excel…' : 'Unduh Excel (.xlsx)'}
          </Button>
          <Button variant="secondary" disabled={exporting !== null} onClick={() => void exportFile('pdf')}>
            {exporting === 'pdf' ? 'Menyusun PDF…' : 'Unduh PDF'}
          </Button>
          <Link to="/progress" className="inline-flex min-h-[44px] items-center rounded-xl bg-brand-50 px-4 text-sm font-semibold text-brand-700 hover:bg-brand-100">
            Lihat profil siswa →
          </Link>
        </div>
      </Card>

      {user.role.name === 'admin' && admin && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Pengguna" value={admin.users} />
            <StatCard label="Guru" value={admin.teachers} />
            <StatCard label="Siswa" value={admin.students} />
            <StatCard label="Kelas" value={admin.classes} />
          </div>
          <Card>
            <CardTitle title="Aktivitas terbaru" subtitle={`${admin.audits} kejadian tercatat di log audit.`} />
            {admin.recent.length === 0 ? (
              <EmptyState message="Belum ada aktivitas yang tercatat." />
            ) : (
              <ul className="divide-y divide-slate-100 text-sm">
                {admin.recent.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span className="font-medium text-slate-700">{item.action}</span>
                    <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString('id-ID')}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      {user.role.name === 'teacher' && legacy && (
        <Card>
          <CardTitle title="Kelas yang diampu" subtitle="Angka dasar dari modul sekolah; analitik detail ada di filter atas." />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Kelas diampu" value={legacy.classes ?? 0} />
            <StatCard label="Siswa" value={legacy.students ?? 0} />
            <StatCard label="Mapel" value={legacy.subjects ?? 0} />
            <StatCard label="Asesmen" value={legacy.assessments ?? 0} />
          </div>
        </Card>
      )}

      <Card className="bg-slate-900 text-white">
        <CardTitle
          title="Status layanan & pengembangan"
          subtitle="Konfigurasi AI berasal dari server; kunci API tidak pernah dikirim ke peramban."
        />
        {aiStatus ? (
          <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm">
            <p className="font-semibold">
              Layanan AI: {aiStatus.available ? 'siap digunakan' : 'belum tersedia'}
            </p>
            <p className="mt-1 text-slate-300">{aiStatus.detail}</p>
            <p className="mt-1 text-xs text-slate-400">
              {aiStatus.active_providers} penyedia aktif · {aiStatus.verified_models} model terverifikasi ·
              sisa token hari ini {aiStatus.budget.daily_remaining_tokens}
            </p>
          </div>
        ) : <p className="text-sm text-slate-300">Status AI sedang dimuat…</p>}
        <div className="mt-4 grid gap-2 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-3">
          <p>✓ Analitik &amp; ekspor dari data nyata — Fase 5</p>
          <p>✓ Offline-first &amp; konflik tersimpan — Fase 6</p>
          <p>✓ Rotasi kunci &amp; backup terenkripsi — Fase 6</p>
          <p>✓ BKT &amp; latihan adaptif — Fase 3</p>
          <p>✓ AI Tutor, RAG, dan generator draf — Fase 4</p>
          <p>○ Prediksi dropout: menunggu dataset tervalidasi</p>
        </div>
      </Card>
    </div>
  )
}
