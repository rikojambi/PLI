import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../lib/api'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input } from '../../components/ui'
import type { AcademicYearRow, AuditRow, SchoolRow, SemesterRow } from '../../types'

export function SettingsPage() {
  const { notify } = useToast()
  const [school, setSchool] = useState<SchoolRow | null>(null)
  const [years, setYears] = useState<AcademicYearRow[]>([])
  const [semesters, setSemesters] = useState<SemesterRow[]>([])
  const [audits, setAudits] = useState<AuditRow[]>([])
  const [yearForm, setYearForm] = useState({ name: '', start_date: '', end_date: '' })
  const [semesterForm, setSemesterForm] = useState({ academic_year_id: '', name: 'Ganjil', start_date: '', end_date: '' })
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    try {
      const [schoolData, yearData, semesterData, auditData] = await Promise.all([
        api<SchoolRow>('/admin/school'),
        api<AcademicYearRow[]>('/admin/academic-years'),
        api<SemesterRow[]>('/admin/semesters'),
        api<{ items: AuditRow[] }>('/admin/audit-logs?limit=10'),
      ])
      setSchool(schoolData)
      setYears(yearData)
      setSemesters(semesterData)
      setAudits(auditData.items)
      setSemesterForm((current) => ({ ...current, academic_year_id: current.academic_year_id || yearData.find((y) => y.is_active)?.id || yearData[0]?.id || '' }))
    } catch (error) {
      notify(errorMessage(error), 'error')
    }
  }, [notify])

  useEffect(() => { void load() }, [load])

  const saveSchool = async (event: FormEvent) => {
    event.preventDefault()
    if (!school) return
    setBusy('school')
    try {
      const result = await api<SchoolRow>('/admin/school', {
        method: 'PUT',
        body: {
          name: school.name,
          npsn: school.npsn || undefined,
          address: school.address || undefined,
          phone: school.phone || undefined,
          email: school.email || undefined,
        },
      })
      setSchool(result)
      notify('Identitas sekolah disimpan')
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy('')
    }
  }

  const createYear = async (event: FormEvent) => {
    event.preventDefault()
    if (!yearForm.name || !yearForm.start_date || !yearForm.end_date) {
      notify('Lengkapi tahun ajaran dan tanggal.', 'error')
      return
    }
    setBusy('year')
    try {
      await api('/admin/academic-years', {
        method: 'POST',
        body: {
          name: yearForm.name,
          start_date: new Date(yearForm.start_date).toISOString(),
          end_date: new Date(yearForm.end_date).toISOString(),
          is_active: years.length === 0,
        },
      })
      notify('Tahun ajaran dibuat')
      setYearForm({ name: '', start_date: '', end_date: '' })
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy('')
    }
  }

  const createSemester = async (event: FormEvent) => {
    event.preventDefault()
    if (!semesterForm.academic_year_id || !semesterForm.start_date || !semesterForm.end_date) {
      notify('Pilih tahun ajaran dan lengkapi tanggal.', 'error')
      return
    }
    setBusy('semester')
    try {
      await api('/admin/semesters', {
        method: 'POST',
        body: {
          ...semesterForm,
          start_date: new Date(semesterForm.start_date).toISOString(),
          end_date: new Date(semesterForm.end_date).toISOString(),
          is_active: semesters.length === 0,
        },
      })
      notify('Semester dibuat')
      setSemesterForm((current) => ({ ...current, start_date: '', end_date: '' }))
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Pengaturan Sekolah</h1>
        <p className="mt-1 text-sm text-slate-500">Identitas sekolah, tahun ajaran, semester, dan log aktivitas.</p>
      </div>

      <Card>
        <CardTitle title="Identitas sekolah" subtitle="Digunakan pada laporan dan tampilan aplikasi." />
        {school ? (
          <form onSubmit={(event) => void saveSchool(event)} className="grid gap-4 sm:grid-cols-2">
            <Field label="Nama sekolah"><Input value={school.name} onChange={(event) => setSchool({ ...school, name: event.target.value })} required /></Field>
            <Field label="NPSN"><Input value={school.npsn ?? ''} onChange={(event) => setSchool({ ...school, npsn: event.target.value })} /></Field>
            <Field label="Telepon"><Input value={school.phone ?? ''} onChange={(event) => setSchool({ ...school, phone: event.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={school.email ?? ''} onChange={(event) => setSchool({ ...school, email: event.target.value })} /></Field>
            <Field label="Alamat" hint="Opsional"><Input value={school.address ?? ''} onChange={(event) => setSchool({ ...school, address: event.target.value })} /></Field>
            <div className="flex items-end sm:justify-end"><Button type="submit" disabled={busy === 'school'}>Simpan</Button></div>
          </form>
        ) : <EmptyState message="Data sekolah belum tersedia." />}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardTitle title="Tahun ajaran" subtitle={`${years.length} tahun ajaran terdaftar.`} />
          <div className="mb-4 space-y-2">
            {years.map((year) => (
              <div key={year.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
                <span className="font-medium">{year.name}</span>
                {year.is_active && <Badge tone="green">Aktif</Badge>}
              </div>
            ))}
            {years.length === 0 && <p className="text-xs text-slate-400">Belum ada tahun ajaran.</p>}
          </div>
          <form onSubmit={(event) => void createYear(event)} className="space-y-3">
            <Field label="Nama tahun ajaran"><Input value={yearForm.name} onChange={(event) => setYearForm({ ...yearForm, name: event.target.value })} placeholder="2026/2027" required /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Mulai"><Input type="date" value={yearForm.start_date} onChange={(event) => setYearForm({ ...yearForm, start_date: event.target.value })} required /></Field>
              <Field label="Selesai"><Input type="date" value={yearForm.end_date} onChange={(event) => setYearForm({ ...yearForm, end_date: event.target.value })} required /></Field>
            </div>
            <Button type="submit" disabled={busy === 'year'}>Tambah tahun ajaran</Button>
          </form>
        </Card>

        <Card>
          <CardTitle title="Semester" subtitle={`${semesters.length} semester terdaftar.`} />
          <div className="mb-4 space-y-2">
            {semesters.map((semester) => (
              <div key={semester.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
                <span className="font-medium">{semester.name}</span>
                {semester.is_active && <Badge tone="green">Aktif</Badge>}
              </div>
            ))}
            {semesters.length === 0 && <p className="text-xs text-slate-400">Belum ada semester.</p>}
          </div>
          <form onSubmit={(event) => void createSemester(event)} className="space-y-3">
            <Field label="Tahun ajaran">
              <select className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm" value={semesterForm.academic_year_id} onChange={(event) => setSemesterForm({ ...semesterForm, academic_year_id: event.target.value })}>
                <option value="">Pilih tahun ajaran</option>
                {years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}
              </select>
            </Field>
            <Field label="Nama semester"><Input value={semesterForm.name} onChange={(event) => setSemesterForm({ ...semesterForm, name: event.target.value })} placeholder="Ganjil" required /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Mulai"><Input type="date" value={semesterForm.start_date} onChange={(event) => setSemesterForm({ ...semesterForm, start_date: event.target.value })} required /></Field>
              <Field label="Selesai"><Input type="date" value={semesterForm.end_date} onChange={(event) => setSemesterForm({ ...semesterForm, end_date: event.target.value })} required /></Field>
            </div>
            <Button type="submit" disabled={busy === 'semester'}>Tambah semester</Button>
          </form>
        </Card>
      </div>

      <Card>
        <CardTitle title="Log aktivitas" subtitle="10 kejadian terakhir (audit trail)." />
        {audits.length === 0 ? <EmptyState message="Belum ada aktivitas." /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr><th className="py-2">Aksi</th><th>Jenis</th><th>Waktu</th><th>IP</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {audits.map((audit) => (
                  <tr key={audit.id}>
                    <td className="py-2 font-medium">{audit.action}</td>
                    <td>{audit.entity_type ?? '-'}</td>
                    <td className="text-xs text-slate-500">{new Date(audit.created_at).toLocaleString('id-ID')}</td>
                    <td className="text-xs text-slate-400">{audit.ip_address ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle title="Privasi &amp; keamanan" />
        <ul className="list-disc space-y-2 pl-5 text-sm text-slate-600">
          <li>Data siswa hanya dapat diakses oleh administrator sekolah dan guru yang mengampu kelasnya.</li>
          <li>Kata sandi disimpan sebagai hash Argon2id, bukan teks biasa.</li>
          <li>Setiap perubahan data penting dicatat dalam log audit.</li>
          <li>Penyedia AI dikonfigurasi administrator lewat Menu AI → Penyedia; frontend hanya menerima nama env variable dan petunjuk terselubung, bukan kunci API.</li>
          <li>AI Tutor hanya memakai profil penguasaan siswa yang bersangkutan; RAG hanya mencari dokumen yang diizinkan untuk akun tersebut.</li>
          <li>Bila belum ada penyedia aktif dan model terverifikasi, fitur AI menyatakan tidak tersedia daripada memberi jawaban buatan.</li>
        </ul>
      </Card>
    </div>
  )
}
