import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Select, Spinner, Textarea } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { GeneratedDraft } from '../../types'

interface CompetencyOption { id: string; code: string; name: string; subject_id: string }

function newClientId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `gen-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function GeneratorPage() {
  const { context } = useAuth()
  const { notify } = useToast()
  const [drafts, setDrafts] = useState<GeneratedDraft[]>([])
  const [kind, setKind] = useState<'question' | 'material'>('question')
  const [subjectId, setSubjectId] = useState('')
  const [competencyId, setCompetencyId] = useState('')
  const [competencies, setCompetencies] = useState<CompetencyOption[]>([])
  const [topic, setTopic] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    void api<GeneratedDraft[]>('/ai/generated')
      .then((value) => { setDrafts(value); setError('') })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  useEffect(() => {
    if (!subjectId) { setCompetencies([]); setCompetencyId(''); return }
    void api<CompetencyOption[]>(`/ai/competencies?subject_id=${encodeURIComponent(subjectId)}`)
      .then(setCompetencies)
      .catch((err) => setError(errorMessage(err)))
  }, [subjectId])

  const generate = async () => {
    if (topic.trim().length < 3 || !subjectId) {
      notify('Pilih mata pelajaran dan isi topik minimal 3 karakter.', 'error')
      return
    }
    setBusy(true)
    try {
      const draft = await api<GeneratedDraft>('/ai/generate', {
        method: 'POST',
        body: {
          kind, subject_id: subjectId, competency_id: competencyId || undefined,
          topic: topic.trim(), notes: notes.trim() || undefined, client_id: newClientId(),
        },
      })
      notify(`Draf ${draft.kind} dibuat: ${draft.title}. Draf belum dipublikasikan.`)
      load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const decide = async (id: string, publish: boolean) => {
    if (publish && !window.confirm('Publikasikan draf ini ke bank soal/materi?')) return
    setBusy(true)
    try {
      const result = await api<{ message: string }>(`/ai/generated/${id}/approve`, {
        method: 'POST', body: { publish, review_note: publish ? 'Disetujui guru' : 'Disetujui, belum dipublikasikan' },
      })
      notify(result.message)
      load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const reject = async (id: string) => {
    if (!window.confirm('Tolak dan arsipkan draf ini?')) return
    setBusy(true)
    try {
      await api(`/ai/generated/${id}/reject`, { method: 'POST', body: { review_note: 'Ditolak guru' } })
      notify('Draf ditolak')
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
        <h1 className="text-2xl font-bold">Generator soal &amp; materi</h1>
        <p className="mt-1 text-sm text-slate-500">
          Hasil AI selalu berupa draf guru. Tidak ada yang dipublikasikan otomatis: guru meninjau isi, sumber, dan
          bukti model sebelum menyetujui.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <Card>
        <CardTitle title="Buat draf baru" subtitle="Topik dan kompetensi dibatasi pada data sekolah Anda." />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Jenis">
            <Select value={kind} onChange={(event) => setKind(event.target.value as 'question' | 'material')}>
              <option value="question">Soal</option>
              <option value="material">Materi</option>
            </Select>
          </Field>
          <Field label="Mata pelajaran">
            <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              <option value="">Pilih mata pelajaran</option>
              {(context?.subjects ?? []).map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
            </Select>
          </Field>
          <Field label="Kompetensi">
            <Select value={competencyId} onChange={(event) => setCompetencyId(event.target.value)}>
              <option value="">Tanpa kompetensi tertentu</option>
              {competencies.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}
            </Select>
          </Field>
          <Field label="Topik"><Input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Misalnya perkalian dua angka" /></Field>
        </div>
        <div className="mt-4">
          <Field label="Catatan untuk generator" hint="Opsional: arahkan tingkat kesulitan, panjang materi, atau fokus tertentu.">
            <Textarea rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Field>
        </div>
        <div className="mt-4 flex justify-end"><Button onClick={() => void generate()} disabled={busy}>{busy ? 'Membuat draf…' : 'Buat draf'}</Button></div>
      </Card>

      <Card>
        <CardTitle title="Draf saya" subtitle="Status draf tidak sama dengan materi/soal yang sudah dipublikasikan." />
        {loading ? <Spinner label="Memuat draf…" /> : drafts.length === 0 ? <EmptyState message="Belum ada draf yang dibuat." /> : (
          <div className="space-y-4">
            {drafts.map((draft) => (
              <div key={draft.id} className="rounded-xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{draft.title}</p>
                    <p className="mt-1 text-xs text-slate-500">{draft.kind} · {new Date(draft.created_at).toLocaleString('id-ID')}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={draft.status === 'published' ? 'green' : draft.status === 'rejected' ? 'rose' : draft.status === 'approved' ? 'indigo' : 'amber'}>{draft.status}</Badge>
                    {draft.status === 'draft' && (
                      <>
                        <Button variant="secondary" disabled={busy} onClick={() => void decide(draft.id, false)}>Setujui</Button>
                        <Button disabled={busy} onClick={() => void decide(draft.id, true)}>Publikasikan</Button>
                        <Button variant="danger" disabled={busy} onClick={() => void reject(draft.id)}>Tolak</Button>
                      </>
                    )}
                  </div>
                </div>
                <pre className="mt-3 max-h-72 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{JSON.stringify(draft.content_json, null, 2)}</pre>
                {draft.sources_json.length > 0 && (
                  <p className="mt-2 text-xs text-slate-500">Sumber: {draft.sources_json.map((item) => item.title).join(', ')}</p>
                )}
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-500">Bukti model</summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{JSON.stringify(draft.model_info_json, null, 2)}</pre>
                </details>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
