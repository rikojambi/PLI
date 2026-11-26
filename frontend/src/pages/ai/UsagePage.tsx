import { useEffect, useState } from 'react'
import { Badge, Card, CardTitle, EmptyState, Select, Spinner, StatCard } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { AiUsage } from '../../types'

const PURPOSES = ['', 'tutor', 'rag', 'generate_question', 'generate_material', 'embedding', 'test']

export function UsagePage() {
  const [items, setItems] = useState<AiUsage[]>([])
  const [total, setTotal] = useState(0)
  const [purpose, setPurpose] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    const query = purpose ? `?purpose=${encodeURIComponent(purpose)}` : ''
    setLoading(true)
    void api<{ items: AiUsage[]; total: number }>(`/ai/usage${query}`, { signal: controller.signal })
      .then((value) => { setItems(value.items); setTotal(value.total); setError('') })
      .catch((err) => { if ((err as Error).name !== 'AbortError') setError(errorMessage(err)) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [purpose])

  const tokens = items.reduce((sum, item) => sum + item.tokens_in + item.tokens_out, 0)
  const cost = items.reduce((sum, item) => sum + item.cost_usd, 0)
  const failures = items.filter((item) => !item.success).length

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Catatan penggunaan AI</h1>
        <p className="mt-1 text-sm text-slate-500">
          Setiap percobaan pemanggilan penyedia tercatat, termasuk yang gagal. Biaya hanya akurat bila administrator
          mengisi harga token; jika tidak, statusnya jujur “unknown”.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard label="Total entri" value={total} note="Sesuai filter" />
        <StatCard label="Token ditampilkan" value={tokens} note="Halaman ini" />
        <StatCard label="Biaya diketahui" value={`$${cost.toFixed(4)}`} note="Halaman ini" />
        <StatCard label="Gagal" value={failures} note="Percobaan gagal" />
      </div>

      <Card>
        <CardTitle title="Riwayat panggilan" subtitle="Maksimal 50 entri terbaru pada tampilan ini." />
        <div className="mb-4 max-w-xs">
          <Select value={purpose} onChange={(event) => setPurpose(event.target.value)} aria-label="Filter tujuan">
            {PURPOSES.map((value) => <option key={value} value={value}>{value || 'Semua tujuan'}</option>)}
          </Select>
        </div>
        {loading ? <Spinner label="Memuat catatan…" /> : items.length === 0 ? <EmptyState message="Belum ada pemanggilan AI pada sekolah ini." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
                <tr><th className="py-2">Waktu</th><th className="py-2">Tujuan</th><th className="py-2">Penyedia / model</th><th className="py-2">Token</th><th className="py-2">Biaya</th><th className="py-2">Status</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr key={item.id} className="align-top">
                    <td className="py-2 pr-3 text-xs text-slate-500">{new Date(item.created_at).toLocaleString('id-ID')}</td>
                    <td className="py-2 pr-3">{item.purpose}</td>
                    <td className="py-2 pr-3 text-xs">{item.provider_name ?? '-'}<br /><span className="font-mono text-slate-400">{item.model ?? '-'}</span></td>
                    <td className="py-2 pr-3 text-xs">{item.tokens_in} / {item.tokens_out}</td>
                    <td className="py-2 pr-3 text-xs">${item.cost_usd.toFixed(6)}<br /><span className="text-slate-400">{item.cost_source}</span></td>
                    <td className="py-2 text-xs">
                      <Badge tone={item.success ? 'green' : 'rose'}>{item.success ? 'Berhasil' : 'Gagal'}</Badge>
                      {item.error && <p className="mt-1 max-w-xs break-words text-rose-600">{item.error}</p>}
                    </td>
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
