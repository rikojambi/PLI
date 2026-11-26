import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Select, Spinner } from '../../components/ui'
import { api, apiUpload, errorMessage } from '../../lib/api'
import type { AiDocument } from '../../types'

export function DocumentsPage() {
  const { context } = useAuth()
  const { notify } = useToast()
  const [documents, setDocuments] = useState<AiDocument[]>([])
  const [title, setTitle] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    void api<AiDocument[]>('/ai/documents')
      .then((value) => { setDocuments(value); setError('') })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const upload = async () => {
    if (!file || title.trim().length < 3) {
      notify('Isi judul dan pilih berkas terlebih dahulu.', 'error')
      return
    }
    setBusy(true)
    try {
      await apiUpload<AiDocument>('/ai/documents', file, 'file', {
        title: title.trim(), subject_id: subjectId,
      })
      notify('Berkas diunggah. Klik Indeks sebelum dipakai RAG.')
      setTitle('')
      setFile(null)
      load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const index = async (id: string) => {
    setBusy(true)
    try {
      const result = await api<{ chunks: number; method: string }>(`/ai/documents/${id}/index`, { method: 'POST' })
      notify(`${result.chunks} bagian diindeks (${result.method})`)
      load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: string) => {
    if (!window.confirm('Hapus dokumen ini dari indeks dan penyimpanan server?')) return
    setBusy(true)
    try {
      await api(`/ai/documents/${id}`, { method: 'DELETE' })
      notify('Dokumen dihapus')
      load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Pustaka dokumen RAG</h1>
        <p className="mt-1 text-sm text-slate-500">
          Dokumen diekstrak menjadi potongan teks. Jika tidak ada model embedding terverifikasi, pencarian memakai
          skor leksikal dan diberi label jujur “lexical”. Guru dapat menentukan kelas atau mata pelajaran agar
          siswa hanya melihat sumber yang diizinkan.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <Card>
        <CardTitle title="Unggah dokumen" subtitle="Format didukung: PDF, DOCX, PPTX, TXT, MD (maksimal 12 MB)." />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Judul"><Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Misalnya Modul Fotosintesis" /></Field>
          <Field label="Mata pelajaran">
            <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              <option value="">Semua mata pelajaran</option>
              {(context?.subjects ?? []).map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
            </Select>
          </Field>
          <Field label="Berkas"><Input type="file" accept=".pdf,.docx,.pptx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></Field>
        </div>
        <div className="mt-4 flex justify-end"><Button onClick={() => void upload()} disabled={busy || !file}>{busy ? 'Memproses…' : 'Unggah'}</Button></div>
      </Card>

      <Card>
        <CardTitle title="Dokumen tersedia" subtitle="Status “indexed_lexical” berarti pencarian tanpa embedding model." />
        {loading ? <Spinner label="Memuat dokumen…" /> : documents.length === 0 ? <EmptyState message="Belum ada dokumen pada sekolah ini." /> : (
          <div className="space-y-3">
            {documents.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 p-3">
                <div>
                  <p className="font-medium">{item.title}</p>
                  <p className="mt-1 text-xs text-slate-500">{item.mime_type} · {item.file_size} byte · {item.chunk_count} potongan</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={item.status.startsWith('indexed') ? 'green' : 'amber'}>{item.status}</Badge>
                  <Button variant="secondary" disabled={busy || item.status.startsWith('indexed')} onClick={() => void index(item.id)}>Indeks</Button>
                  <Button variant="danger" disabled={busy} onClick={() => void remove(item.id)}>Hapus</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
