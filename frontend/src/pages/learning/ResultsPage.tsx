import { useEffect, useState } from 'react'
import { Badge, Card, CardTitle, EmptyState, Spinner } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { ResultRow } from '../../types'

export function ResultsPage() {
  const [rows, setRows] = useState<ResultRow[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void api<ResultRow[]>('/learning/results')
      .then((data) => { setRows(data); setError('') })
      .catch((err) => setError(errorMessage(err)))
  }, [])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Hasil belajar</h1>
        <p className="mt-1 text-sm text-slate-500">Hanya hasil upaya Anda sendiri yang ditampilkan.</p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <Card>
        <CardTitle title="Riwayat asesmen" />
        {!rows ? <Spinner label="Memuat hasil…" /> : rows.length === 0 ? (
          <EmptyState message="Anda belum memiliki hasil asesmen." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr><th className="py-2">Asesmen</th><th>Nilai</th><th>Penguasaan</th><th>Status</th><th>Waktu</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="py-3 font-medium">{row.assessment_title ?? 'Asesmen'}</td>
                    <td><Badge tone={row.score >= 70 ? 'green' : 'amber'}>{row.score}%</Badge></td>
                    <td>{row.mastery_percent === null ? '-' : `${row.mastery_percent}%`}</td>
                    <td>{row.graded_by ? 'Sudah dikoreksi guru' : 'Penilaian otomatis'}</td>
                    <td className="text-xs text-slate-500">{new Date(row.graded_at).toLocaleString('id-ID')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
