import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { Badge, Button, Card, CardTitle, Field, Select, Textarea } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { RagAnswer } from '../../types'

const EXAMPLES = [
  'Apa yang dijelaskan dalam dokumen yang saya unggah?',
  'Ringkas bagian tentang proses utama.',
]

export function RagPage() {
  const { context } = useAuth()
  const [question, setQuestion] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [answer, setAnswer] = useState<RagAnswer | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const ask = async () => {
    if (question.trim().length < 3) {
      setError('Pertanyaan minimal 3 karakter.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await api<RagAnswer>('/ai/rag/ask', {
        method: 'POST', body: { question: question.trim(), subject_id: subjectId || undefined },
      })
      setAnswer(result)
    } catch (err) {
      setAnswer(null)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Tanya dokumen (RAG)</h1>
        <p className="mt-1 text-sm text-slate-500">
          Jawaban hanya diambil dari dokumen yang diizinkan untuk akun Anda. Jika tidak ada potongan relevan,
          sistem menjawab “Data tidak tersedia” dan tidak meminta model mengarang jawaban.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <Card>
        <CardTitle title="Pertanyaan" subtitle="Sertakan kata kunci yang ada pada dokumen agar pencarian lebih tepat." />
        <Field label="Pertanyaan">
          <Textarea rows={4} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={EXAMPLES[0]} />
        </Field>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Batasi mata pelajaran" hint="Kosongkan untuk mencari semua dokumen yang diizinkan.">
            <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              <option value="">Semua mata pelajaran</option>
              {(context?.subjects ?? []).map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
            </Select>
          </Field>
          <div className="flex items-end"><Button onClick={() => void ask()} disabled={busy}>{busy ? 'Mencari…' : 'Tanyakan'}</Button></div>
        </div>
      </Card>

      {answer && (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle title="Jawaban" subtitle="Sumber ditampilkan bersama bukti pencarian." />
            <Badge tone={answer.available ? 'green' : 'amber'}>{answer.status}</Badge>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{answer.answer}</p>
          {answer.citations.length > 0 && (
            <ol className="mt-4 space-y-2 text-xs text-slate-600">
              {answer.citations.map((item) => (
                <li key={`${item.document_id}-${item.chunk_index}`} className="rounded-lg bg-slate-50 p-2">
                  <span className="font-semibold">[{item.number}]</span> {item.title} · bagian {item.chunk_index + 1} · skor {item.score}
                </li>
              ))}
            </ol>
          )}
          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-semibold text-slate-500">Bukti pencarian</summary>
            <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{JSON.stringify(answer.evidence, null, 2)}</pre>
          </details>
        </Card>
      )}
    </div>
  )
}
