import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Modal, Select, Textarea } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'

interface OpsStatus {
  status: 'ok' | 'degraded'
  service: string
  environment: string
  version: string
  database_url_kind: string
  tables: number
  migration_head: string | null
  expected_migration_head: string
  checks: Record<string, boolean>
  checked_by: string
}

interface RetentionPreview {
  policy: {
    student_data_retention_days: number
    ai_log_retention_days: number
    audit_retention_days: number
  }
  eligible: Record<string, number>
  note: string
}

interface DeletionRequest {
  id: string
  student_id: string
  status: string
  reason: string | null
  due_at: string | null
  processed_at: string | null
  certificate: Record<string, unknown> | null
}

interface StudentOption {
  id: string
  full_name: string
  username: string
}

type Action = 'purge' | 'request' | 'delete' | 'rotate' | null

const CONFIRM_WORD: Record<Exclude<Action, null>, string> = {
  purge: 'BERSIHKAN',
  request: 'AJUKAN',
  delete: 'HAPUS',
  rotate: 'ROTASI',
}

export function OperationsPage() {
  const { notify } = useToast()
  const [status, setStatus] = useState<OpsStatus | null>(null)
  const [preview, setPreview] = useState<RetentionPreview | null>(null)
  const [requests, setRequests] = useState<DeletionRequest[]>([])
  const [students, setStudents] = useState<StudentOption[]>([])
  const [studentId, setStudentId] = useState('')
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [typed, setTyped] = useState('')
  const [action, setAction] = useState<Action>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [ops, retention, deletion, users] = await Promise.all([
        api<OpsStatus>('/ops/status'),
        api<RetentionPreview>('/privacy/retention/preview'),
        api<{ items: DeletionRequest[] }>('/privacy/deletion-requests'),
        api<{ items: StudentOption[] }>('/admin/users?role=student&limit=200'),
      ])
      setStatus(ops)
      setPreview(retention)
      setRequests(deletion.items)
      setStudents(users.items)
      setStudentId((current) => current || users.items[0]?.id || '')
    } catch (error) {
      notify(errorMessage(error), 'error')
    }
  }, [notify])

  useEffect(() => { void load() }, [load])

  const open = (next: Exclude<Action, null>) => {
    setTyped('')
    setAction(next)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!action) return
    if (typed.trim() !== CONFIRM_WORD[action]) {
      notify(`Ketik ${CONFIRM_WORD[action]} persis untuk melanjutkan.`, 'error')
      return
    }
    if ((action === 'request' || action === 'delete') && !studentId) {
      notify('Pilih siswa terlebih dahulu.', 'error')
      return
    }
    setBusy(true)
    try {
      if (action === 'purge') {
        const result = await api<{ purged: Record<string, number>; note: string }>('/privacy/retention/purge', {
          method: 'POST',
          body: { confirm: true },
        })
        notify(`Pembersihan selesai: ${Object.values(result.purged).reduce((sum, value) => sum + value, 0)} data kedaluwarsa dibersihkan.`)
      } else if (action === 'request') {
        const result = await api<{ id: string; status: string; due_at: string }>(`/privacy/students/${studentId}/delete-request`, {
          method: 'POST',
          body: { confirm: true, reason: reason || undefined },
        })
        notify(`Permintaan penghapusan dicatat (${result.status}).`)
      } else if (action === 'delete') {
        const result = await api<{ student_ref: string; deleted_at: string; method: string }>(`/privacy/students/${studentId}/delete`, {
          method: 'POST',
          body: { confirm: true, reason: reason || undefined },
        })
        notify(`Data siswa dihapus permanen. Referensi sertifikat: ${result.student_ref}.`)
        setStudentId('')
      } else {
        const result = await api<{ key_hint: string; previous_key_hint: string | null; note?: string }>('/privacy/secret/rotate', {
          method: 'POST',
          body: { confirm: true, note: note || undefined },
        })
        notify(`Kunci sesi diputar. Petunjuk kunci aktif: ${result.key_hint}. Kunci lama masih berlaku satu siklus.`)
      }
      setAction(null)
      setTyped('')
      setReason('')
      setNote('')
      await load()
    } catch (error) {
      notify(errorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  const requestModal = (kind: Exclude<Action, null>) => {
    const title = {
      purge: 'Bersihkan data kedaluwarsa',
      request: 'Ajukan penghapusan siswa',
      delete: 'Hapus permanen data siswa',
      rotate: 'Putar kunci sesi server',
    }[kind]
    const warning = {
      purge: 'Hanya log AI, sesi kedaluwarsa, dan konflik yang sudah selesai yang dibersihkan. Log audit dipertahankan.',
      request: 'Permintaan dicatat dan menunggu eksekusi eksplisit. Data belum berubah.',
      delete: 'Seluruh data belajar siswa ini dihapus permanen dan tidak dapat dikembalikan. Sertifikat penghapusan tetap disimpan.',
      rotate: 'Sesi lama tetap diverifikasi satu siklus memakai kunci sebelumnya. Kunci mentah tidak ditampilkan maupun disimpan di database.',
    }[kind]
    return (
      <Modal title={title} onClose={() => setAction(null)}>
        <form onSubmit={(event) => void submit(event)} className="space-y-4">
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">{warning}</p>
          {kind === 'delete' && (
            <p className="text-sm text-slate-700">
              Siswa: <strong>{students.find((item) => item.id === studentId)?.full_name ?? '-'}</strong>
            </p>
          )}
          {(kind === 'request' || kind === 'delete') && (
            <Field label="Alasan" hint="Opsional, tercatat di log audit.">
              <Textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} maxLength={500} />
            </Field>
          )}
          {kind === 'rotate' && (
            <Field label="Catatan rotasi" hint="Opsional, tercatat di log audit.">
              <Textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2} maxLength={300} />
            </Field>
          )}
          <Field label={`Ketik ${CONFIRM_WORD[kind]} untuk mengonfirmasi`}>
            <Input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" required />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setAction(null)}>Batal</Button>
            <Button type="submit" variant="danger" disabled={busy}>{busy ? 'Memproses…' : 'Lanjutkan'}</Button>
          </div>
        </form>
      </Modal>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Operasional &amp; privasi</h1>
        <p className="mt-2 text-sm text-slate-600">Status layanan, retensi, penghapusan data, dan rotasi kunci. Semua tindakan membutuhkan konfirmasi eksplisit.</p>
      </div>

      <Card>
        <CardTitle
          title="Status layanan"
          subtitle={status ? `${status.version} · ${status.environment} · migrasi ${status.migration_head ?? '-'} / ${status.expected_migration_head}` : 'Memuat status dari server…'}
        />
        {status ? (
          <>
            <div className="mb-4 flex items-center gap-2">
              <Badge tone={status.status === 'ok' ? 'green' : 'amber'}>{status.status === 'ok' ? 'Sehat' : 'Perlu perhatian'}</Badge>
              <span className="text-xs text-slate-500">Diperiksa oleh {status.checked_by} · {status.tables} tabel · database {status.database_url_kind}</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(status.checks).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
                  <span className="text-slate-600">{key.replace(/_/g, ' ')}</span>
                  <Badge tone={value ? 'green' : 'rose'}>{value ? 'OK' : 'Gagal'}</Badge>
                </div>
              ))}
            </div>
            <a href="/api/metrics" target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-semibold text-brand-700 hover:underline">Lihat metrik server →</a>
          </>
        ) : <EmptyState message="Status operasional tidak tersedia." />}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle title="Retensi data" subtitle={preview?.note ?? 'Memuat kebijakan retensi…'} />
          {preview && (
            <>
              <ul className="mb-4 space-y-1 text-sm text-slate-600">
                <li>Data siswa: {preview.policy.student_data_retention_days} hari</li>
                <li>Log AI: {preview.policy.ai_log_retention_days} hari</li>
                <li>Log audit: {preview.policy.audit_retention_days} hari (dipertahankan sebagai bukti)</li>
              </ul>
              <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
                {Object.entries(preview.eligible).map(([key, value]) => (
                  <div key={key} className="rounded-xl border border-slate-100 p-2">
                    <span className="block text-xs text-slate-500">{key.replace(/_/g, ' ')}</span>
                    <strong className="text-lg text-slate-800">{value}</strong>
                  </div>
                ))}
              </div>
              <Button variant="secondary" onClick={() => open('purge')}>Bersihkan data kedaluwarsa</Button>
            </>
          )}
        </Card>

        <Card>
          <CardTitle title="Rotasi kunci sesi" subtitle="Kunci aktif diganti di server; kunci sebelumnya hanya dipakai untuk verifikasi satu siklus." />
          <p className="mb-4 text-sm text-slate-600">Petunjuk kunci (bukan kunci penuh) tercatat di log audit. Kunci API penyedia AI tidak ikut diputar lewat tombol ini.</p>
          <Button variant="secondary" onClick={() => open('rotate')}>Putar kunci sesi</Button>
        </Card>
      </div>

      <Card>
        <CardTitle title="Penghapusan data siswa" subtitle="Permintaan dan eksekusi tercatat; sertifikat memakai referensi hash, bukan identitas mentah." />
        <div className="grid gap-3 sm:grid-cols-[2fr,1fr]">
          <Field label="Siswa">
            <Select value={studentId} onChange={(event) => setStudentId(event.target.value)}>
              <option value="">Pilih siswa</option>
              {students.map((item) => (
                <option key={item.id} value={item.id}>{item.full_name} ({item.username})</option>
              ))}
            </Select>
          </Field>
          <Field label="Alasan" hint="Opsional">
            <Input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
          </Field>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => open('request')}>Ajukan permintaan</Button>
          <Button variant="danger" onClick={() => open('delete')}>Hapus permanen</Button>
        </div>
        <div className="mt-5">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Riwayat permintaan</h3>
          {requests.length === 0 ? <EmptyState message="Belum ada permintaan penghapusan." /> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="py-2">Siswa</th><th>Status</th><th>Diajukan</th><th>Selesai</th><th>Sertifikat</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {requests.map((item) => (
                    <tr key={item.id}>
                      <td className="py-2 font-medium text-slate-700">{students.find((student) => student.id === item.student_id)?.full_name ?? item.student_id.slice(0, 8)}</td>
                      <td><Badge tone={item.status === 'completed' ? 'green' : 'amber'}>{item.status}</Badge></td>
                      <td className="text-xs text-slate-500">{item.due_at ? new Date(item.due_at).toLocaleDateString('id-ID') : '-'}</td>
                      <td className="text-xs text-slate-500">{item.processed_at ? new Date(item.processed_at).toLocaleString('id-ID') : '-'}</td>
                      <td className="text-xs text-slate-500">{item.certificate?.student_ref ? String(item.certificate.student_ref) : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {action && requestModal(action)}
    </div>
  )
}
