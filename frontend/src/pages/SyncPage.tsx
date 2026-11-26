import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Modal, Select, Textarea } from '../components/ui'
import { api, errorMessage } from '../lib/api'

interface Conflict {
  id: string
  student_id: string
  attempt_id: string | null
  question_id: string
  client_id: string | null
  reason: string
  server_snapshot: Record<string, unknown> | null
  client_snapshot: Record<string, unknown> | null
  resolution: string | null
  resolved_at: string | null
  created_at: string
}

interface ConflictResponse {
  items: Conflict[]
  total: number
  strategy: string
}

type Resolution = 'server' | 'client'

export function SyncPage() {
  const { user } = useAuth()
  const { notify } = useToast()
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [strategy, setStrategy] = useState('')
  const [filter, setFilter] = useState('open')
  const [selected, setSelected] = useState<Conflict | null>(null)
  const [resolution, setResolution] = useState<Resolution>('server')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const canResolve = user?.role.name === 'teacher' || user?.role.name === 'admin'

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (filter === 'open') params.set('resolved', 'false')
      if (filter === 'resolved') params.set('resolved', 'true')
      const data = await api<ConflictResponse>(`/sync/conflicts${params.size ? `?${params}` : ''}`)
      setConflicts(data.items)
      setStrategy(data.strategy)
    } catch (error) {
      notify(errorMessage(error), 'error')
    }
  }, [filter, notify])

  useEffect(() => { void load() }, [load])

  const resolve = async () => {
    if (!selected) return
    setBusy(true)
    try {
      const result = await api<{ id: string; resolution: string; client_applied: boolean; note: string }>(
        `/sync/conflicts/${selected.id}/resolve`,
        { method: 'POST', body: { resolution, note: note || undefined } },
      )
      notify(`${result.note} Keputusan: ${result.resolution === 'client' ? 'versi perangkat' : 'versi server'}.`)
      setSelected(null)
      setNote('')
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  const timestamp = (value: unknown) => {
    if (typeof value !== 'string' || !value) return '-'
    const parsed = new Date(value.endsWith('Z') ? value : `${value}Z`)
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('id-ID')
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Sinkronisasi &amp; konflik</h1>
        <p className="mt-2 text-sm text-slate-600">Konflik jawaban offline disimpan di server dan tidak menimpa data diam-diam.</p>
      </div>

      <Card>
        <CardTitle title="Strategi penanganan" subtitle="Berlaku untuk semua perangkat yang tersambung ke sekolah ini." />
        <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">{strategy || 'Memuat strategi dari server…'}</p>
        {user?.role.name === 'student' && (
          <p className="mt-3 text-xs text-slate-500">Anda hanya melihat konflik pada jawaban Anda sendiri. Guru yang mengampu kelas dapat memilih versi yang dipakai.</p>
        )}
      </Card>

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <CardTitle title="Catatan konflik" subtitle={`${conflicts.length} kejadian ditampilkan (maksimal 200 terakhir).`} />
          <div className="w-full sm:w-56">
            <Field label="Tampilkan">
              <Select value={filter} onChange={(event) => setFilter(event.target.value)}>
                <option value="open">Belum diselesaikan</option>
                <option value="resolved">Sudah diselesaikan</option>
                <option value="all">Semua</option>
              </Select>
            </Field>
          </div>
        </div>
        {conflicts.length === 0 ? (
          <EmptyState message="Tidak ada konflik pada rentang ini." />
        ) : (
          <div className="space-y-3">
            {conflicts.map((item) => {
              const serverAt = item.server_snapshot?.updated_at
              const clientAt = item.client_snapshot?.client_updated_at
              return (
                <div key={item.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-slate-800">{item.reason}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {timestamp(item.created_at)} · soal {item.question_id.slice(0, 8)} · perangkat {item.client_id?.slice(0, 8) ?? '-'}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={item.resolution ? 'green' : 'amber'}>{item.resolution ? `selesai: ${item.resolution}` : 'menunggu guru'}</Badge>
                      {canResolve && !item.resolution && (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setSelected(item)
                            setResolution('server')
                            setNote('')
                          }}
                        >
                          Tinjau &amp; selesaikan
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                    <div className="rounded-lg bg-slate-50 p-2">
                      <strong className="block text-slate-700">Versi server</strong>
                      Diperbarui {timestamp(serverAt)}
                    </div>
                    <div className="rounded-lg bg-slate-50 p-2">
                      <strong className="block text-slate-700">Versi perangkat</strong>
                      Diperbarui {timestamp(clientAt)}
                    </div>
                  </div>
                  {item.resolved_at && <p className="mt-2 text-xs text-slate-400">Diselesaikan {timestamp(item.resolved_at)}</p>}
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {selected && (
        <Modal title="Selesaikan konflik jawaban" onClose={() => setSelected(null)}>
          <div className="space-y-4">
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">{selected.reason}</p>
            <Field label="Keputusan guru">
              <Select value={resolution} onChange={(event) => setResolution(event.target.value as Resolution)}>
                <option value="server">Pertahankan versi server (jawaban terakhir yang diterima server)</option>
                <option value="client">Gunakan jawaban dari perangkat yang dilaporkan</option>
              </Select>
            </Field>
            {resolution === 'client' && (
              <p className="text-xs text-slate-500">Versi perangkat hanya diterapkan bila upaya masih berstatus berlangsung. Jika tidak, server menolak dengan pesan yang jelas.</p>
            )}
            <Field label="Catatan keputusan" hint="Opsional, tercatat di log audit.">
              <Textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={500} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setSelected(null)}>Batal</Button>
              <Button onClick={() => void resolve()} disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan keputusan'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
