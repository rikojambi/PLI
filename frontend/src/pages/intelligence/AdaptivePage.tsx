import { useState } from 'react'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Select, Spinner, StatCard } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import type { AdaptiveQuestion, AdaptiveResult } from '../../types'

function newClientId(): string {
  const random = globalThis.crypto?.randomUUID?.()
  return random ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

type AnswerValue = { selected: string } | { selected: string[] } | { text: string }

export function AdaptivePage() {
  const { context } = useAuth()
  const { notify } = useToast()
  const [subjectId, setSubjectId] = useState('')
  const [question, setQuestion] = useState<AdaptiveQuestion['question']>(null)
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState<Record<string, unknown>>({})
  const [single, setSingle] = useState('')
  const [multiple, setMultiple] = useState<string[]>([])
  const [text, setText] = useState('')
  const [clientId, setClientId] = useState(newClientId())
  const [result, setResult] = useState<AdaptiveResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const next = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setQuestion(null)
    setSingle('')
    setMultiple([])
    setText('')
    setClientId(newClientId())
    try {
      const params = subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ''
      const payload = await api<AdaptiveQuestion>(`/intelligence/adaptive/next-question${params}`, { method: 'POST' })
      setQuestion(payload.question)
      setReason(payload.reason)
      setEvidence(payload.evidence)
      if (!payload.question) notify(payload.reason, 'info')
    } catch (err) {
      setError(errorMessage(err))
      notify(errorMessage(err), 'error')
    } finally {
      setLoading(false)
    }
  }

  const answer = async () => {
    if (!question) return
    let body: AnswerValue
    if (question.question_type === 'multiple_response') {
      if (multiple.length === 0) { notify('Pilih minimal satu jawaban.', 'error'); return }
      body = { selected: multiple }
    } else if (question.question_type === 'short_answer' || question.question_type === 'fill_blank') {
      if (!text.trim()) { notify('Isi jawaban terlebih dahulu.', 'error'); return }
      body = { text }
    } else {
      if (!single) { notify('Pilih jawaban terlebih dahulu.', 'error'); return }
      body = { selected: single }
    }
    setSubmitting(true)
    try {
      const payload = await api<AdaptiveResult>('/intelligence/adaptive/answer', {
        method: 'POST',
        body: { question_id: question.id, answer: body, client_id: clientId },
      })
      setResult(payload)
      setReason('')
      notify(payload.idempotent ? 'Jawaban sudah tercatat sebelumnya.' : 'Jawaban tersimpan dan profil penguasaan diperbarui.')
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const toggle = (id: string) => {
    setMultiple((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Latihan adaptif</h1>
        <p className="mt-1 text-sm text-slate-500">
          Soal dipilih berdasarkan kompetensi dengan penguasaan terendah. Kunci jawaban tidak dikirim ke browser.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <Card className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1">
          <Field label="Mata pelajaran" hint="Kosongkan untuk memakai semua kompetensi aktif.">
            <Select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              <option value="">Semua mata pelajaran</option>
              {context?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
            </Select>
          </Field>
        </div>
        <Button onClick={() => void next()} disabled={loading}>
          {loading ? 'Mencari soal…' : question ? 'Soal berikutnya' : 'Ambil soal'}
        </Button>
      </Card>

      {!question && !loading && (
        <EmptyState message={reason || 'Tekan “Ambil soal” untuk memulai latihan adaptif.'} />
      )}

      {question && (
        <Card>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone="indigo">{question.difficulty}</Badge>
            <Badge tone="slate">{question.gap_category}</Badge>
            <span className="text-xs text-slate-400">{question.points} poin</span>
          </div>
          <CardTitle title={question.content} subtitle="Pilih jawaban yang paling tepat." />

          {question.question_type === 'multiple_response' ? (
            <div className="mt-4 space-y-2">
              {question.options.map((option) => (
                <label key={option.id} className="flex min-h-[44px] cursor-pointer items-center gap-3 rounded-xl border border-slate-200 px-3 text-sm">
                  <input type="checkbox" checked={multiple.includes(option.id)} onChange={() => toggle(option.id)} />
                  <span><strong className="mr-2">{option.label}</strong>{option.content}</span>
                </label>
              ))}
            </div>
          ) : question.question_type === 'short_answer' || question.question_type === 'fill_blank' ? (
            <div className="mt-4 max-w-md">
              <Field label="Jawaban Anda">
                <Input value={text} onChange={(event) => setText(event.target.value)} />
              </Field>
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              {question.options.map((option) => (
                <label key={option.id} className="flex min-h-[44px] cursor-pointer items-center gap-3 rounded-xl border border-slate-200 px-3 text-sm">
                  <input type="radio" name="adaptive-option" checked={single === option.id} onChange={() => setSingle(option.id)} />
                  <span><strong className="mr-2">{option.label}</strong>{option.content}</span>
                </label>
              ))}
            </div>
          )}

          <div className="mt-5 flex justify-end">
            <Button onClick={() => void answer()} disabled={submitting}>
              {submitting ? 'Menyimpan…' : 'Kirim jawaban'}
            </Button>
          </div>
        </Card>
      )}

      {result && (
        <Card>
          <CardTitle
            title={result.is_correct ? 'Jawaban benar' : 'Jawaban belum tepat'}
            subtitle={result.idempotent ? 'Pengiriman ini adalah pengulangan jawaban yang sudah tercatat.' : 'Profil penguasaan diperbarui dari jawaban ini.'}
          />
          <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Poin" value={result.points_earned} />
            <StatCard label="Sebelum" value={`${Math.round(result.mastery_before * 100)}%`} />
            <StatCard label="Sesudah" value={`${Math.round(result.mastery_after * 100)}%`} />
            <StatCard label="Status" value={result.status} />
          </div>
          <details className="mt-4 text-xs text-slate-500">
            <summary className="cursor-pointer font-semibold">Lihat bukti</summary>
            <pre className="mt-2 overflow-auto rounded-lg bg-slate-50 p-3">{JSON.stringify(result.evidence, null, 2)}</pre>
          </details>
        </Card>
      )}

      {evidence && Object.keys(evidence).length > 0 && !question && (
        <Card className="bg-slate-50">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Alasan pemilihan soal</p>
          <pre className="mt-2 overflow-auto text-xs text-slate-600">{JSON.stringify(evidence, null, 2)}</pre>
        </Card>
      )}

      {loading && <Spinner label="Menyiapkan soal…" />}
    </div>
  )
}
