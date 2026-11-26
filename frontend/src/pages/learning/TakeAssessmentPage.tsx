import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Badge, Button, Card, EmptyState, Spinner } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { api, apiUpload, errorMessage } from '../../lib/api'
import { clearQueuedAnswer, enqueueAnswer, kvGet, kvSet, queuedAnswers, type QueuedAnswer } from '../../lib/offline'
import type { AnswerRow, AttemptRow, QuestionOption, QuestionRow, SubmitResult } from '../../types'

type AnswerValue = string | string[] | { text?: string; file_path?: string | null; selected?: string; matches?: Record<string, string> }
interface AnswerMeta {
  clientId: string
  updatedAt: string
  timeSpentSec: number
  changedCount: number
}
interface SyncResponse {
  saved: number
  conflicts: Array<{ question_id: string; reason: string }>
  anomaly_flags: string[]
  note: string
}
interface UploadResult { file_path: string; file_name: string }

const MANUAL_TYPES = new Set(['essay', 'stepped_essay', 'project'])

function newClientId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `answer-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

function hash(text: string): number {
  let value = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i)
    value = Math.imul(value, 16777619)
  }
  return value >>> 0
}

function orderedOptions(question: QuestionRow, shuffle: boolean): QuestionOption[] {
  if (!shuffle) return question.options
  return [...question.options].sort((a, b) => hash(`${question.id}:${a.id}`) - hash(`${question.id}:${b.id}`))
}

function formatRemaining(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

export function TakeAssessmentPage() {
  const { assessmentId = '' } = useParams()
  const { notify } = useToast()
  const [attempt, setAttempt] = useState<AttemptRow | null>(null)
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({})
  const [meta, setMeta] = useState<Record<string, AnswerMeta>>({})
  const [activeIndex, setActiveIndex] = useState(0)
  const [remaining, setRemaining] = useState<number | null>(null)
  const [pending, setPending] = useState({ focus: 0, hidden: 0 })
  const [syncMessage, setSyncMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [error, setError] = useState('')
  const deadlineRef = useRef(0)
  const submitRef = useRef<() => void>(() => {})

  const loadAttempt = useCallback(async (id: string) => {
    const loaded = await api<AttemptRow>(`/learning/attempts/${id}`)
    setAttempt(loaded)
    const initialAnswers: Record<string, AnswerValue> = {}
    const initialMeta: Record<string, AnswerMeta> = {}
    for (const answer of loaded.answers as AnswerRow[]) {
      initialAnswers[answer.question_id] = answer.answer_json as AnswerValue
      initialMeta[answer.question_id] = {
        clientId: answer.client_id ?? newClientId(),
        updatedAt: answer.updated_at ?? answer.synced_at ?? loaded.started_at,
        timeSpentSec: answer.time_spent_sec,
        changedCount: answer.changed_count,
      }
    }
    const snapshot = await kvGet<{ answers: Record<string, AnswerValue>; meta: Record<string, AnswerMeta> }>(`attempt:${id}`)
    if (snapshot) {
      for (const [questionId, value] of Object.entries(snapshot.answers ?? {})) {
        initialAnswers[questionId] = value
      }
      for (const [questionId, value] of Object.entries(snapshot.meta ?? {})) {
        initialMeta[questionId] = value
      }
    }
    setAnswers(initialAnswers)
    setMeta(initialMeta)
    const started = new Date(loaded.assessment?.started_at ?? loaded.started_at).getTime()
    deadlineRef.current = started + (loaded.assessment?.duration_min ?? 45) * 60_000
    if (loaded.status === 'submitted') {
      setResult({
        attempt_id: loaded.id,
        status: loaded.status,
        total_points: loaded.total_points ?? 0,
        max_points: loaded.max_points ?? 0,
        score_percent: loaded.max_points ? Math.round((loaded.total_points ?? 0) / loaded.max_points * 10000) / 100 : 0,
        graded_automatically: 0,
        pending_manual: loaded.questions.filter((question) => MANUAL_TYPES.has(question.question_type)).length,
        anomaly_flags: loaded.anomaly_flags,
      })
    }
    return loaded
  }, [])

  useEffect(() => {
    let active = true
    void api<AttemptRow>(`/learning/assessments/${assessmentId}/start`, { method: 'POST' })
      .then(async (started) => {
        if (active) await loadAttempt(started.id)
      })
      .catch((err) => {
        if (active) setError(errorMessage(err))
      })
    return () => { active = false }
  }, [assessmentId, loadAttempt])

  useEffect(() => {
    const tick = () => {
      if (!deadlineRef.current || result) return
      const left = Math.max(0, Math.ceil((deadlineRef.current - Date.now()) / 1000))
      setRemaining(left)
      if (left === 0) submitRef.current()
    }
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [result])

  useEffect(() => {
    const onFocusLoss = () => setPending((current) => ({ ...current, focus: current.focus + 1 }))
    const onVisibility = () => {
      if (document.hidden) setPending((current) => ({ ...current, hidden: current.hidden + 1 }))
    }
    window.addEventListener('blur', onFocusLoss)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('blur', onFocusLoss)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  const sync = useCallback(async (
    items: Array<{ question_id: string; answer: AnswerValue; meta: AnswerMeta }>,
    clearQueue = false,
  ) => {
    if (!attempt || items.length === 0) return false
    try {
      const response = await api<SyncResponse>(`/learning/attempts/${attempt.id}/sync`, {
        method: 'PUT',
        body: {
          answers: items.map((item) => ({
            question_id: item.question_id,
            client_id: item.meta.clientId,
            answer: item.answer,
            time_spent_sec: item.meta.timeSpentSec,
            changed_count: item.meta.changedCount,
            client_updated_at: item.meta.updatedAt,
          })),
          focus_loss_count: pending.focus,
          page_hidden_count: pending.hidden,
        },
      })
      setPending({ focus: 0, hidden: 0 })
      setSyncMessage(`${response.saved} jawaban tersimpan`)
      if (response.conflicts.length > 0) {
        notify(`${response.conflicts.length} jawaban ditolak karena versi server lebih baru.`, 'error')
        const refreshed = await loadAttempt(attempt.id)
        for (const conflict of response.conflicts) {
          const serverAnswer = refreshed.answers.find((item) => item.question_id === conflict.question_id)
          if (serverAnswer) {
            setAnswers((current) => ({ ...current, [conflict.question_id]: serverAnswer.answer_json as AnswerValue }))
          }
        }
      }
      if (clearQueue) {
        await Promise.all(items.map((item) => clearQueuedAnswer(`${attempt.id}:${item.question_id}`)))
      }
      return true
    } catch (err) {
      setSyncMessage(errorMessage(err))
      notify(errorMessage(err), 'error')
      return false
    }
  }, [attempt, loadAttempt, notify, pending])

  const flushQueue = useCallback(async () => {
    if (!attempt) return true
    const queued = (await queuedAnswers()).filter((item) => item.attemptId === attempt.id)
    if (queued.length === 0) return true
    const items = queued.map((item) => ({
      question_id: item.questionId,
      answer: item.answer as AnswerValue,
      meta: {
        clientId: item.clientId ?? newClientId(),
        updatedAt: item.clientUpdatedAt ?? item.createdAt,
        timeSpentSec: item.timeSpentSec ?? 0,
        changedCount: item.changedCount ?? 1,
      },
    }))
    return sync(items, true)
  }, [attempt, sync])

  const setAnswerValue = async (question: QuestionRow, value: AnswerValue) => {
    if (!attempt) return
    const previous = meta[question.id]
    const nextMeta: AnswerMeta = previous
      ? { ...previous, updatedAt: new Date().toISOString(), changedCount: previous.changedCount + 1 }
      : { clientId: newClientId(), updatedAt: new Date().toISOString(), timeSpentSec: 0, changedCount: 1 }
    setAnswers((current) => ({ ...current, [question.id]: value }))
    setMeta((current) => ({ ...current, [question.id]: nextMeta }))
    await kvSet(`attempt:${attempt.id}`, {
      answers: { ...answers, [question.id]: value },
      meta: { ...meta, [question.id]: nextMeta },
    })
    if (!navigator.onLine) {
      const queued: QueuedAnswer = {
        id: `${attempt.id}:${question.id}`,
        attemptId: attempt.id,
        questionId: question.id,
        answer: value,
        createdAt: nextMeta.updatedAt,
        clientId: nextMeta.clientId,
        clientUpdatedAt: nextMeta.updatedAt,
        timeSpentSec: nextMeta.timeSpentSec,
        changedCount: nextMeta.changedCount,
      }
      await enqueueAnswer(queued)
      setSyncMessage('Jawaban masuk antrean offline')
    } else {
      await sync([{ question_id: question.id, answer: value, meta: nextMeta }])
    }
  }

  const submit = async () => {
    if (!attempt || busy || result) return
    setBusy(true)
    try {
      const flushed = await flushQueue()
      if (!flushed) {
        notify('Sinkronisasi gagal. Periksa koneksi sebelum mengumpulkan.', 'error')
        return
      }
      const outcome = await api<SubmitResult>(`/learning/attempts/${attempt.id}/submit`, { method: 'POST' })
      setResult(outcome)
      await kvSet(`attempt:${attempt.id}-result`, outcome)
      notify(outcome.pending_manual > 0 ? 'Jawaban terkumpul; menunggu koreksi guru.' : 'Jawaban terkumpul dan dinilai.')
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  submitRef.current = () => { void submit() }

  const questions = useMemo(() => attempt?.questions ?? [], [attempt])
  const active = questions[activeIndex]
  const shuffleOptions = Boolean(attempt?.assessment?.shuffle_options)

  if (error) {
    return (
      <Card>
        <EmptyState message={error} />
        <div className="mt-4 text-center"><Link to="/assessments" className="text-sm font-semibold text-brand-700">Kembali ke daftar asesmen</Link></div>
      </Card>
    )
  }
  if (!attempt) return <Spinner label="Menyiapkan asesmen…" />

  if (result) {
    return (
      <div className="space-y-5">
        <Card>
          <p className="text-sm text-slate-500">Asesmen selesai</p>
          <h1 className="mt-1 text-2xl font-bold">{attempt.assessment?.title ?? 'Asesmen'}</h1>
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Nilai</p><p className="text-2xl font-bold">{result.score_percent}%</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Poin</p><p className="text-2xl font-bold">{result.total_points}/{result.max_points}</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Otomatis</p><p className="text-2xl font-bold">{result.graded_automatically}</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Menunggu guru</p><p className="text-2xl font-bold">{result.pending_manual}</p></div>
          </div>
          {result.anomaly_flags.length > 0 && (
            <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
             Catatan untuk guru: {result.anomaly_flags.join(', ')}. Indikator ini tidak menurunkan nilai otomatis.
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            <Link to="/results" className="inline-flex min-h-[44px] items-center rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white">Lihat hasil</Link>
            <Link to="/assessments" className="inline-flex min-h-[44px] items-center rounded-xl border border-slate-300 px-4 text-sm font-semibold">Kembali</Link>
          </div>
        </Card>
      </div>
    )
  }

  const renderAnswerInput = (question: QuestionRow) => {
    const value = answers[question.id]
    const options = orderedOptions(question, shuffleOptions)
    const update = (next: AnswerValue) => { void setAnswerValue(question, next) }

    if (question.question_type === 'matching') {
      const keys = Array.from(new Set(options.map((option) => option.match_key).filter((key): key is string => Boolean(key))))
      const current = typeof value === 'object' && !Array.isArray(value) ? (value as { matches?: Record<string, string> }).matches ?? {} : {}
      return (
        <div className="space-y-2">
          {options.filter((option) => option.match_key).map((option) => (
            <div key={option.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 p-3">
              <span className="text-sm font-medium">{option.label}. {option.content}</span>
              <select
                className="min-h-[44px] rounded-xl border border-slate-300 px-3 text-sm"
                value={current[option.id] ?? ''}
                onChange={(event) => update({ matches: { ...current, [option.id]: event.target.value } })}
              >
                <option value="">Pilih pasangan</option>
                {keys.map((key) => <option key={key} value={key}>{key}</option>)}
              </select>
            </div>
          ))}
        </div>
      )
    }

    if (question.question_type === 'short_answer' || question.question_type === 'fill_blank' || MANUAL_TYPES.has(question.question_type)) {
      const text = typeof value === 'object' && !Array.isArray(value) ? (value as { text?: string }).text ?? '' : typeof value === 'string' ? value : ''
      return (
        <div className="space-y-2">
          <textarea
            rows={question.question_type === 'project' ? 4 : 6}
            className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
            value={text}
            onChange={(event) => update({ text: event.target.value, ...(typeof value === 'object' && !Array.isArray(value) ? { file_path: (value as { file_path?: string | null }).file_path } : {}) })}
            placeholder="Tulis jawaban Anda di sini"
          />
          {question.question_type === 'project' && (
            <div>
              <input
                type="file"
                className="block text-xs"
                onChange={async (event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  try {
                    const uploaded = await apiUpload<UploadResult>('/learning/uploads', file)
                    update({ text, file_path: uploaded.file_path })
                    notify(`Berkas ${uploaded.file_name} terunggah`)
                  } catch (err) {
                    notify(errorMessage(err), 'error')
                  }
                }}
              />
              {typeof value === 'object' && !Array.isArray(value) && (value as { file_path?: string | null }).file_path && (
                <a className="mt-1 inline-block text-sm font-semibold text-brand-700 underline" href={(value as { file_path: string }).file_path} target="_blank" rel="noreferrer">
                  Lampiran terunggah ↗
                </a>
              )}
            </div>
          )}
        </div>
      )
    }

    const multiple = question.question_type === 'multiple_response'
    const selected = multiple
      ? (Array.isArray(value) ? value as string[] : [])
      : (typeof value === 'object' && !Array.isArray(value) ? (value as { selected?: string }).selected ?? '' : typeof value === 'string' ? value : '')

    return (
      <div className="space-y-2">
        {question.image_path && <img src={question.image_path} alt="Gambar soal" className="max-h-64 rounded-xl border border-slate-200" />}
        {options.map((option) => {
          const checked = multiple ? (selected as string[]).includes(option.id) : selected === option.id
          return (
            <label key={option.id} className={`flex min-h-[48px] cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm ${checked ? 'border-brand-500 bg-brand-50' : 'border-slate-200'}`}>
              <input
                type={multiple ? 'checkbox' : 'radio'}
                name={`question-${question.id}`}
                className="mt-1 h-4 w-4"
                checked={checked}
                onChange={() => {
                  if (!multiple) {
                    update({ selected: option.id })
                    return
                  }
                  const current = Array.isArray(value) ? value as string[] : []
                  update(checked ? current.filter((id) => id !== option.id) : [...current, option.id])
                }}
              />
              <span><strong className="mr-2">{option.label}.</strong>{option.content}</span>
            </label>
          )
        })}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <Card className="flex flex-wrap items-center justify-between gap-3 bg-slate-900 text-white">
        <div>
          <p className="text-xs text-slate-300">{attempt.assessment?.title}</p>
          <h1 className="text-lg font-bold">Soal {activeIndex + 1} dari {questions.length}</h1>
        </div>
        <div className="flex items-center gap-3">
          {remaining !== null && <Badge tone={remaining < 60 ? 'rose' : 'indigo'}>Sisa {formatRemaining(remaining)}</Badge>}
          <Badge tone={syncMessage.includes('antrean') ? 'amber' : 'green'}>{syncMessage || 'Sinkron siap'}</Badge>
        </div>
      </Card>

      <div className="flex flex-wrap gap-1.5">
        {questions.map((question, index) => {
          const answered = answers[question.id] !== undefined
          return (
            <button
              key={question.id}
              type="button"
              onClick={() => setActiveIndex(index)}
              aria-label={`Ke soal ${index + 1}`}
              className={`h-10 w-10 rounded-lg text-sm font-semibold ${index === activeIndex ? 'bg-brand-600 text-white' : answered ? 'bg-emerald-100 text-emerald-700' : 'bg-white text-slate-500 ring-1 ring-slate-200'}`}
            >
              {index + 1}
            </button>
          )
        })}
      </div>

      {active ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Badge tone={MANUAL_TYPES.has(active.question_type) ? 'amber' : 'indigo'}>{active.question_type.replace('_', ' ')}</Badge>
            <span className="text-xs text-slate-500">{active.points} poin</span>
          </div>
          <p className="mt-3 whitespace-pre-wrap text-base font-medium text-slate-900">{active.content}</p>
          <div className="mt-5">{renderAnswerInput(active)}</div>
          <div className="mt-5 flex flex-wrap justify-between gap-2 border-t border-slate-100 pt-4">
            <Button variant="secondary" disabled={activeIndex === 0} onClick={() => setActiveIndex((current) => current - 1)}>Sebelumnya</Button>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => void flushQueue()}>Simpan sekarang</Button>
              {activeIndex === questions.length - 1 ? (
                <Button onClick={() => void submit()} disabled={busy}>{busy ? 'Mengumpulkan…' : 'Kumpulkan jawaban'}</Button>
              ) : (
                <Button onClick={() => setActiveIndex((current) => current + 1)}>Berikutnya</Button>
              )}
            </div>
          </div>
        </Card>
      ) : <Card><EmptyState message="Asesmen ini belum memiliki soal." /></Card>}

      {attempt.anomaly_flags.length > 0 && (
        <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
          Catatan sistem untuk guru: {attempt.anomaly_flags.join(', ')}. Tidak ada penalti otomatis.
        </p>
      )}
    </div>
  )
}
