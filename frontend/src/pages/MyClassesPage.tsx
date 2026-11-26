import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { api, errorMessage } from '../lib/api'
import { Badge, Card, CardTitle, EmptyState, Spinner } from '../components/ui'

interface PortalClass {
  id: string
  name: string
  grade_level: string | null
  is_active: boolean
  student_count?: number
}

interface PortalStudent {
  id: string
  full_name: string
  username: string
  student_number: string | null
  is_active: boolean
}

export function MyClassesPage() {
  const { user } = useAuth()
  const [classes, setClasses] = useState<PortalClass[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [students, setStudents] = useState<PortalStudent[] | null>(null)
  const [error, setError] = useState('')

  const isTeacher = user?.role.name === 'teacher' || user?.role.name === 'admin'

  useEffect(() => {
    void api<PortalClass[]>(isTeacher ? '/portal/teacher/classes' : '/portal/student/classes')
      .then((rows) => {
        setClasses(rows)
        if (isTeacher && rows.length > 0) setSelected(rows[0].id)
      })
      .catch((err) => setError(errorMessage(err)))
  }, [isTeacher])

  useEffect(() => {
    if (!isTeacher || !selected) return
    setStudents(null)
    void api<PortalStudent[]>(`/portal/teacher/classes/${selected}/students`)
      .then(setStudents)
      .catch((err) => setError(errorMessage(err)))
  }, [isTeacher, selected])

  if (!user) return null
  if (!classes) return error ? <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</div> : <Spinner />

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Kelas Saya</h1>
        <p className="mt-1 text-sm text-slate-500">
          {isTeacher ? 'Hanya kelas yang menjadi tanggung jawab Anda yang ditampilkan.' : 'Kelas tempat Anda terdaftar sebagai siswa.'}
        </p>
      </div>
      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {classes.map((klass) => (
          <Card
            key={klass.id}
            className={isTeacher && selected === klass.id ? 'ring-2 ring-brand-500' : ''}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold">{klass.name}</h2>
                <p className="text-xs text-slate-500">Tingkat {klass.grade_level ?? '-'}</p>
              </div>
              <Badge tone={klass.is_active ? 'green' : 'slate'}>{klass.is_active ? 'Aktif' : 'Nonaktif'}</Badge>
            </div>
            <p className="mt-3 text-sm text-slate-600">
              {isTeacher ? `${klass.student_count ?? 0} siswa terdaftar` : 'Kelas aktif'}
            </p>
            {isTeacher && (
              <button
                type="button"
                onClick={() => setSelected(klass.id)}
                className="mt-3 min-h-[44px] w-full rounded-xl bg-brand-50 text-sm font-semibold text-brand-700 hover:bg-brand-100"
              >
                Lihat daftar siswa
              </button>
            )}
          </Card>
        ))}
      </div>

      {classes.length === 0 && <Card><EmptyState message="Belum ada kelas yang dapat ditampilkan." /></Card>}

      {isTeacher && selected && (
        <Card>
          <CardTitle title={`Daftar siswa — ${classes.find((c) => c.id === selected)?.name ?? ''}`} subtitle="Data dibatasi hanya untuk kelas yang Anda ampu." />
          {!students ? <Spinner label="Memuat siswa…" /> : students.length === 0 ? (
            <EmptyState message="Belum ada siswa di kelas ini." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-sm">
                <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                  <tr><th className="py-2">Nama</th><th>Username</th><th>No. induk</th><th>Status</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {students.map((student) => (
                    <tr key={student.id}>
                      <td className="py-3 font-medium">{student.full_name}</td>
                      <td>{student.username}</td>
                      <td>{student.student_number ?? '-'}</td>
                      <td><Badge tone={student.is_active ? 'green' : 'rose'}>{student.is_active ? 'Aktif' : 'Nonaktif'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
