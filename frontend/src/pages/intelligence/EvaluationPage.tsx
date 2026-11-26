import { useEffect, useState } from 'react'
import { Badge, Card, CardTitle, EmptyState, Spinner } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { DropoutEvaluation } from '../../types'

export function EvaluationPage() {
  const [data, setData] = useState<DropoutEvaluation | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    void api<DropoutEvaluation>('/intelligence/dropout-evaluation', { signal: controller.signal })
      .then((value) => { setData(value); setError('') })
      .catch((err) => { if ((err as Error).name !== 'AbortError') setError(errorMessage(err)) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Evaluasi prediksi ketertinggalan</h1>
        <p className="mt-1 text-sm text-slate-500">
          Tidak ada model prediksi yang diaktifkan tanpa dataset berlabel tervalidasi. Halaman ini menampilkan status evaluasi dan indikator peninjauan guru.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {loading || !data ? <Spinner label="Memeriksa status evaluasi…" /> : (
        <>
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle title="Status evaluasi" subtitle="Metrik hanya ditampilkan jika dataset tervalidasi tersedia." />
              <Badge tone={data.available ? 'green' : 'amber'}>{data.status}</Badge>
            </div>
            <p className="mt-3 text-sm text-slate-600">{data.reason ?? 'Dataset tervalidasi tersedia.'}</p>
            {data.available && (
              <pre className="mt-3 overflow-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(data.metrics, null, 2)}</pre>
            )}
            {data.limitations && data.limitations.length > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-500">
                {data.limitations.map((item) => <li key={item}>{item}</li>)}
              </ul>
            )}
            {data.requirements && (
              <div className="mt-4 rounded-xl bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Persyaratan evaluasi</p>
                <ul className="mt-2 list-decimal space-y-1 pl-5 text-xs text-slate-600">
                  {data.requirements.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            )}
          </Card>

          <Card>
            <CardTitle
              title="Indikator peninjauan guru"
              subtitle="Bukan prediksi dan tidak digunakan untuk keputusan otomatis terhadap siswa."
            />
            {data.advisory_indicators.length === 0 ? <EmptyState message="Belum ada siswa pada cakupan ini." /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
                    <tr><th className="py-2">Siswa</th><th className="py-2">Penguasaan rata-rata</th><th className="py-2">Kompetensi rendah</th><th className="py-2">Sinyal</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.advisory_indicators.map((item) => (
                      <tr key={item.student_id} className="align-top">
                        <td className="py-2 pr-3 font-medium">{item.name}</td>
                        <td className="py-2 pr-3">{item.average_mastery_percent}%</td>
                        <td className="py-2 pr-3">{item.low_competency_count}</td>
                        <td className="py-2 text-xs text-slate-500">
                          {item.signals.length === 0 ? 'Tidak ada sinyal khusus' : item.signals.join('; ')}
                          <p className="mt-1 text-slate-400">Prediksi: {item.is_prediction ? 'ya' : 'tidak'}</p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
